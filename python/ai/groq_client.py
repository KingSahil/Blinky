from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from utils.logging import get_logger

LOGGER = get_logger("blinky.groq")

DEFAULT_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
DECOMMISSIONED_GROQ_MODELS = {"llama-3.2-90b-vision-preview"}


def ask_groq_vision(prompt: str, screenshot_path: Path) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required when BLINKY_AI_PROVIDER=groq.")

    model = _active_groq_model()
    groq_url = os.getenv("BLINKY_GROQ_URL", DEFAULT_GROQ_URL).strip() or DEFAULT_GROQ_URL
    
    # Allow configuring timeout via environment variable, defaulting to 90s for slower networks/heavy API load
    try:
        timeout_val = int(os.getenv("BLINKY_GROQ_TIMEOUT", "90").strip())
    except ValueError:
        timeout_val = 90

    image_payload = _image_to_data_url(screenshot_path)
    
    try:
        response = requests.post(
            groq_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.1,
                "max_tokens": 350,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_payload}},
                        ],
                    }
                ],
            },
            timeout=timeout_val,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Groq API request timed out after {timeout_val} seconds. Please check your network connection "
            f"or switch BLINKY_AI_PROVIDER to local 'ollama' under your Settings for offline offline guidance."
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Groq API connection error: {exc}")

    if not response.ok:
        raise RuntimeError(_format_groq_error(response))
    body = response.json()
    content = _extract_content(body)
    return _validate_response(_parse_json(content))


def ask_groq_text(prompt: str, max_tokens: int = 300) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required when BLINKY_AI_PROVIDER=groq.")

    model = _active_groq_model()
    groq_url = os.getenv("BLINKY_GROQ_URL", DEFAULT_GROQ_URL).strip() or DEFAULT_GROQ_URL

    try:
        timeout_val = int(os.getenv("BLINKY_GROQ_TIMEOUT", "90").strip())
    except ValueError:
        timeout_val = 90

    try:
        response = requests.post(
            groq_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.1,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout_val,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Groq API request timed out after {timeout_val} seconds.")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Groq API connection error: {exc}")

    if not response.ok:
        raise RuntimeError(_format_groq_error(response))
    body = response.json()
    return _parse_json(_extract_content(body))



def _active_groq_model() -> str:
    model = os.getenv("BLINKY_GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
    if model in DECOMMISSIONED_GROQ_MODELS:
        LOGGER.warning("Ignoring decommissioned Groq model %s; using %s", model, DEFAULT_GROQ_MODEL)
        return DEFAULT_GROQ_MODEL
    return model


def _format_groq_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"Groq request failed with HTTP {response.status_code}: {response.text[:300]}"

    error = payload.get("error", {})
    if isinstance(error, dict):
        message = str(error.get("message", "")).strip()
        code = str(error.get("code", "")).strip()
        if message and code:
            return f"Groq request failed ({code}): {message}"
        if message:
            return f"Groq request failed: {message}"

    return f"Groq request failed with HTTP {response.status_code}: {payload}"


def _image_to_data_url(screenshot_path: Path) -> str:
    raw = screenshot_path.read_bytes()
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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _validate_response(payload: dict[str, Any]) -> dict[str, Any]:
    summary = str(payload.get("summary", "")).strip() or "Here is the shortest visible path."
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    normalized_steps = []
    for index, step in enumerate(steps[:6], start=1):
        if not isinstance(step, dict):
            continue
        instruction = str(step.get("instruction", "")).strip()
        target_text = str(step.get("target_text", "")).strip()
        if instruction:
            normalized_steps.append(
                {
                    "step": int(step.get("step") or index),
                    "instruction": instruction,
                    "target_text": target_text,
                }
            )

    return {"summary": summary, "steps": normalized_steps, "warnings": []}
