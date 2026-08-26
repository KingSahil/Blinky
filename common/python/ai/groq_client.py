from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import requests
from PIL import Image

from utils.logging import get_logger

LOGGER = get_logger("blinky.groq")

DEFAULT_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_GROQ_VISION_MODEL = "qwen/qwen3.6-27b"
DEFAULT_IMAGE_MAX_DIM = 768
DEFAULT_IMAGE_QUALITY = 80
MAX_RATE_LIMIT_WAIT_SECONDS = 35

DECOMMISSIONED_GROQ_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview",
    "meta-llama/llama-4-scout-17b-16e-instruct",
}


def ask_groq_vision(prompt: str, screenshot_path: Path) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required when BLINKY_AI_PROVIDER=groq.")

    model = _active_groq_vision_model()
    groq_url = os.getenv("BLINKY_GROQ_URL", DEFAULT_GROQ_URL).strip() or DEFAULT_GROQ_URL
    prompt_str = prompt if isinstance(prompt, str) else json.dumps(prompt)

    try:
        timeout_val = int(os.getenv("BLINKY_GROQ_TIMEOUT", "90").strip())
    except ValueError:
        timeout_val = 90

    base_max_dim = _get_configured_image_max_dim()

    def build_payload(attempt: int = 1) -> dict[str, Any]:
        # On retry attempts, scale down further (e.g. 768 -> 512 -> 384) to aggressively drop TPM token usage
        if attempt == 1:
            max_dim = base_max_dim
            max_items = 25
        elif attempt == 2:
            max_dim = min(base_max_dim, 512)
            max_items = 15
        else:
            max_dim = min(base_max_dim, 384)
            max_items = 10

        image_payload = _image_to_data_url(screenshot_path, max_dimension=max_dim)
        compacted_prompt = _compact_vision_prompt(prompt_str, max_items=max_items)
        return {
            "model": model,
            "temperature": 0.1,
            "max_tokens": 750,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": compacted_prompt},
                        {"type": "image_url", "image_url": {"url": image_payload}},
                    ],
                }
            ],
        }

    response = _post_groq_with_retry(groq_url, api_key, build_payload, timeout_val)
    if _is_model_not_found_error(response) and model != DEFAULT_GROQ_VISION_MODEL:
        LOGGER.warning("Groq model '%s' not found; retrying with default '%s'.", model, DEFAULT_GROQ_VISION_MODEL)
        model = DEFAULT_GROQ_VISION_MODEL
        response = _post_groq_with_retry(groq_url, api_key, build_payload, timeout_val)

    if _is_content_string_error(response):
        LOGGER.warning("Groq model '%s' rejected multimodal image array; falling back to OCR text prompt.", model)
        text_payload = {
            "model": model,
            "temperature": 0.1,
            "max_tokens": 750,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt_str}],
        }
        response = _post_groq_with_retry(groq_url, api_key, text_payload, timeout_val)

    if _is_json_validate_error(response):
        LOGGER.warning("Groq JSON-mode generation failed; retrying vision request without response_format.")
        base_payload = text_payload if "_is_content_string_error" in locals() and _is_content_string_error(response) else build_payload(1)
        retry_payload = _without_response_format(base_payload)
        if isinstance(retry_payload.get("messages", [{}])[0].get("content"), list):
            retry_payload["messages"][0]["content"][0]["text"] = _json_recovery_prompt(prompt_str)
        else:
            retry_payload["messages"][0]["content"] = _json_recovery_prompt(prompt_str)
        response = _post_groq_with_retry(groq_url, api_key, retry_payload, timeout_val)

    if not response.ok:
        raise RuntimeError(_format_groq_error(response, model=model))
    body = response.json()
    content = _extract_content(body)
    return _validate_response(_parse_json(content))


def ask_groq_text(prompt: str, max_tokens: int = 300) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required when BLINKY_AI_PROVIDER=groq.")

    model = _active_groq_model()
    groq_url = os.getenv("BLINKY_GROQ_URL", DEFAULT_GROQ_URL).strip() or DEFAULT_GROQ_URL
    prompt_str = prompt if isinstance(prompt, str) else json.dumps(prompt)

    try:
        timeout_val = int(os.getenv("BLINKY_GROQ_TIMEOUT", "90").strip())
    except ValueError:
        timeout_val = 90

    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt_str}],
    }

    response = _post_groq_with_retry(groq_url, api_key, payload, timeout_val)
    if _is_model_not_found_error(response) and model != DEFAULT_GROQ_MODEL:
        LOGGER.warning("Groq text model '%s' not found; retrying with default '%s'.", model, DEFAULT_GROQ_MODEL)
        model = DEFAULT_GROQ_MODEL
        payload["model"] = model
        response = _post_groq_with_retry(groq_url, api_key, payload, timeout_val)

    if _is_json_validate_error(response):
        LOGGER.warning("Groq JSON-mode generation failed; retrying text request without response_format.")
        retry_payload = _without_response_format(payload)
        retry_payload["messages"][0]["content"] = _json_recovery_prompt(prompt_str)
        response = _post_groq_with_retry(groq_url, api_key, retry_payload, timeout_val)

    if not response.ok:
        raise RuntimeError(_format_groq_error(response, model=model))
    body = response.json()
    return _parse_json(_extract_content(body))




def _compact_vision_prompt(prompt: str, max_items: int = 25) -> str:
    """
    For multimodal vision models (which already visually analyze the screenshot),
    compact large text OCR item listings and redundant rules to keep total tokens well under 8,000 TPM.
    """
    if "Visible UI/OCR items:" not in prompt:
        return prompt

    parts = prompt.split("Visible UI/OCR items:")
    prefix = parts[0]
    remainder = parts[1]

    split_marker = None
    for marker in ["Completed workflow context:", "Rules:", "Return valid JSON only."]:
        if marker in remainder:
            split_marker = marker
            break

    if split_marker:
        items_part, suffix_part = remainder.split(split_marker, 1)
        suffix = split_marker + suffix_part
    else:
        items_part = remainder
        suffix = ""

    lines = [line.strip() for line in items_part.splitlines() if line.strip()]
    if len(lines) > max_items:
        lines = lines[:max_items]

    compacted_items = "\n".join(lines)
    return f"{prefix}Visible UI/OCR items:\n{compacted_items}\n\n{suffix}".strip()


def _post_groq_with_retry(
    groq_url: str,
    api_key: str,
    payload_or_builder: dict[str, Any] | Callable[[int], dict[str, Any]],
    timeout_val: int,
    max_retries: int = 3,
) -> requests.Response:
    try:
        max_allowed_wait = float(os.getenv("BLINKY_GROQ_MAX_RETRY_WAIT", str(MAX_RATE_LIMIT_WAIT_SECONDS)))
    except ValueError:
        max_allowed_wait = MAX_RATE_LIMIT_WAIT_SECONDS

    last_response: requests.Response | None = None
    for attempt in range(1, max_retries + 1):
        if callable(payload_or_builder):
            payload = payload_or_builder(attempt)
        else:
            payload = payload_or_builder

        last_response = _post_groq(groq_url, api_key, payload, timeout_val)
        if last_response.ok:
            return last_response

        if _is_rate_limit_error(last_response) and attempt < max_retries:
            # Check if this was a "Request too large" error (meaning the single request was > 8000 tokens)
            is_request_too_large = _is_request_too_large_error(last_response)
            
            wait_seconds = _parse_retry_wait_seconds(last_response)
            if wait_seconds is None:
                wait_seconds = 0.5 if is_request_too_large else min(attempt * 4.0, 15.0)

            # If request was too large, we don't need a huge sleep if the next attempt downscales the payload
            if is_request_too_large:
                LOGGER.warning(
                    "Groq request payload too large for model TPM; retrying with more aggressive downscaling (attempt %d/%d)...",
                    attempt + 1,
                    max_retries,
                )
                time.sleep(1.0)
                continue

            if wait_seconds <= max_allowed_wait:
                sleep_time = wait_seconds + 0.5
                LOGGER.warning(
                    "Groq rate limit hit (TPM/RPM limit); waiting %.1fs before retrying (attempt %d/%d)...",
                    sleep_time,
                    attempt,
                    max_retries,
                )
                time.sleep(sleep_time)
                continue

        break

    return last_response if last_response is not None else _post_groq(groq_url, api_key, payload_or_builder if isinstance(payload_or_builder, dict) else payload_or_builder(1), timeout_val)


def _post_groq(groq_url: str, api_key: str, payload: dict[str, Any], timeout_val: int) -> requests.Response:
    try:
        return requests.post(
            groq_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout_val,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Groq API request timed out after {timeout_val} seconds. Please check your network connection "
            f"or switch BLINKY_AI_PROVIDER to local 'ollama' under your Settings for offline guidance."
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Groq API connection error: {exc}")


def _is_rate_limit_error(response: requests.Response) -> bool:
    if response.status_code == 429:
        return True
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error", {})
    if not isinstance(error, dict):
        return False
    code = str(error.get("code", "")).strip().lower()
    message = str(error.get("message", "")).strip().lower()
    return (
        code == "rate_limit_exceeded"
        or "rate limit" in message
        or "tokens per minute" in message
        or "requests per minute" in message
        or "request too large" in message
    )


def _is_request_too_large_error(response: requests.Response) -> bool:
    try:
        payload = response.json()
        message = str(payload.get("error", {}).get("message", "")).lower()
        return "request too large" in message or "reduce your message size" in message
    except Exception:
        return False


def _parse_retry_wait_seconds(response: requests.Response) -> float | None:
    # 1. Try 'Retry-After' header
    retry_header = response.headers.get("retry-after", "").strip()
    if retry_header:
        try:
            return max(0.1, float(retry_header))
        except ValueError:
            pass

    # 2. Try 'x-ratelimit-reset-tokens' or 'x-ratelimit-reset-requests'
    reset_tokens = response.headers.get("x-ratelimit-reset-tokens", "").strip()
    if reset_tokens:
        match = re.search(r"([\d\.]+)\s*(s|ms|m)?", reset_tokens, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            unit = (match.group(2) or "s").lower()
            if unit == "ms":
                return val / 1000.0
            if unit == "m":
                return val * 60.0
            return max(0.1, val)

    # 3. Try parsing from error message (e.g. "Please try again in 13.485s")
    try:
        payload = response.json()
        message = str(payload.get("error", {}).get("message", ""))
        match = re.search(r"try again in\s+([\d\.]+)\s*(s|ms|m)?", message, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            unit = (match.group(2) or "s").lower()
            if unit == "ms":
                return val / 1000.0
            if unit == "m":
                return val * 60.0
            return max(0.1, val)
    except Exception:
        pass

    return None


def _get_configured_image_max_dim() -> int:
    env_dim = os.getenv("BLINKY_GROQ_IMAGE_MAX_DIM", str(DEFAULT_IMAGE_MAX_DIM)).strip()
    try:
        val = int(env_dim)
        return max(256, min(val, 2048))
    except ValueError:
        return DEFAULT_IMAGE_MAX_DIM


def _without_response_format(payload: dict[str, Any]) -> dict[str, Any]:
    retry_payload = json.loads(json.dumps(payload))
    retry_payload.pop("response_format", None)
    retry_payload["temperature"] = 0
    return retry_payload


def _json_recovery_prompt(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "The previous attempt failed Groq JSON validation. Return only one raw JSON object, "
        "with no markdown, no code fences, no commentary, no <think> tags, and no trailing text. "
        "The object must have this shape: {\"summary\":\"...\",\"steps\":[]}."
    )


def _is_model_not_found_error(response: requests.Response) -> bool:
    if response.ok:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error", {})
    if not isinstance(error, dict):
        return False
    code = str(error.get("code", "")).strip().lower()
    message = str(error.get("message", "")).strip().lower()
    return code == "model_not_found" or "does not exist" in message or "do not have access to it" in message


def _is_content_string_error(response: requests.Response) -> bool:
    if response.ok:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error", {})
    if not isinstance(error, dict):
        return False
    message = str(error.get("message", "")).strip().lower()
    return "must be a string" in message or "expected a string" in message or "invalid type for 'messages" in message



def _is_json_validate_error(response: requests.Response) -> bool:
    if response.ok:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error", {})
    if not isinstance(error, dict):
        return False
    code = str(error.get("code", "")).strip().lower()
    message = str(error.get("message", "")).strip().lower()
    return code == "json_validate_failed" or "json validation" in message or "failed to generate json" in message


def _active_groq_model() -> str:
    model = os.getenv("BLINKY_GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
    if model in DECOMMISSIONED_GROQ_MODELS:
        LOGGER.warning("Ignoring decommissioned Groq model %s; using %s", model, DEFAULT_GROQ_MODEL)
        return DEFAULT_GROQ_MODEL
    return model


def _active_groq_vision_model() -> str:
    model = os.getenv("BLINKY_GROQ_VISION_MODEL", "").strip()
    if not model or model in DECOMMISSIONED_GROQ_MODELS or model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
        return DEFAULT_GROQ_VISION_MODEL
    return model




def _format_groq_error(response: requests.Response, model: str = "") -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"Groq request failed with HTTP {response.status_code}: {response.text[:300]}"

    error = payload.get("error", {})
    if isinstance(error, dict):
        message = str(error.get("message", "")).strip()
        code = str(error.get("code", "")).strip()
        if _is_rate_limit_error(response):
            model_info = f" for model '{model}'" if model else ""
            return (
                f"Groq request failed ({code or 'rate_limit_exceeded'}): {message}\n\n"
                f"Tip: Free-tier Groq vision{model_info} has an 8,000 TPM limit. "
                f"You can wait a moment for the token window to reset, configure a smaller image size via "
                f"BLINKY_GROQ_IMAGE_MAX_DIM=768, or switch BLINKY_AI_PROVIDER to 'ollama' or 'mimo' in your .env."
            )
        if message and code:
            return f"Groq request failed ({code}): {message}"
        if message:
            return f"Groq request failed: {message}"

    return f"Groq request failed with HTTP {response.status_code}: {payload}"


def _image_to_data_url(screenshot_path: Path | str, max_dimension: int = DEFAULT_IMAGE_MAX_DIM, quality: int = DEFAULT_IMAGE_QUALITY) -> str:
    path_obj = Path(screenshot_path) if isinstance(screenshot_path, str) else screenshot_path
    
    try:
        with Image.open(path_obj) as img:
            # Convert RGBA / palette mode to RGB
            if img.mode in ("RGBA", "LA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            else:
                rgb_img = img.convert("RGB")

            # Downscale keeping aspect ratio if larger than max_dimension
            w, h = rgb_img.size
            if max(w, h) > max_dimension:
                resample_method = getattr(getattr(Image, "Resampling", Image), "LANCZOS", getattr(Image, "LANCZOS", Image.BICUBIC))
                rgb_img.thumbnail((max_dimension, max_dimension), resample_method)

            # Compress to JPEG in memory
            buffer = io.BytesIO()
            rgb_img.save(buffer, format="JPEG", quality=quality, optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
    except Exception as exc:
        LOGGER.warning("PIL optimization failed for %s (%s); falling back to raw file encoding", path_obj, exc)
        raw = path_obj.read_bytes()
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices or not isinstance(choices, list):
        raise RuntimeError("Groq returned no choices.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return str(content)


def _parse_json(text: str) -> dict[str, Any]:
    # 1. Strip <think>...</think> tags if model produced reasoning output
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.DOTALL).strip()

    # 2. Strip markdown code fences if wrapped in ```json ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    # 3. Attempt direct JSON parsing
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 4. Search for { ... } object in the text
    match = re.search(r"(\{[\s\S]*\})", cleaned)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 5. Extract summary if partially formed JSON
    summary_match = re.search(r'"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', cleaned)
    if summary_match:
        return {"summary": summary_match.group(1), "steps": []}

    # Final fallback attempt or raise
    return json.loads(cleaned)


def _validate_response(payload: dict[str, Any]) -> dict[str, Any]:
    summary = str(payload.get("summary", "")).strip() or "Here is the shortest visible path."
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    normalized_steps = []
    for index, step in enumerate(steps[:6], start=1):
        if isinstance(step, str) and step.strip():
            normalized_steps.append(
                {
                    "step": index,
                    "instruction": step.strip(),
                    "target_ref": "",
                    "target_text": step.strip(),
                }
            )
        elif isinstance(step, dict):
            instruction = str(step.get("instruction", "")).strip()
            target_ref = str(step.get("target_ref", "")).strip()
            target_text = str(step.get("target_text", "")).strip()
            if instruction:
                normalized_steps.append(
                    {
                        "step": int(step.get("step") or index),
                        "instruction": instruction,
                        "target_ref": target_ref,
                        "target_text": target_text,
                    }
                )

    return {"summary": summary, "steps": normalized_steps, "warnings": []}
