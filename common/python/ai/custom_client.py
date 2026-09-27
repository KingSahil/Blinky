"""Custom OpenAI-compatible provider client for Blinky.

Works with any endpoint speaking the OpenAI chat/completions API
(OpenCode Zen/Go, OpenRouter, vLLM, LM Studio, Ollama's OpenAI shim, etc).

Text mode:      POST {base}/chat/completions  {messages: [{role, content: str}]}
Vision mode:    content is an array with text + image_url (base64 data URL),
                matching the standard OpenAI multimodal schema.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from utils.logging import get_logger

LOGGER = get_logger("blinky.custom")

DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_CUSTOM_MODEL = "minimax-m3"


def _config() -> tuple[str, str, str]:
    """(base_url, api_key, model) from env, with sensible defaults.

    Tolerates both forms of custom URL:
      - base:     https://opencode.ai/zen/v1            (client appends /chat/completions)
      - full:     https://opencode.ai/zen/v1/chat/completions  (normalized to base)
    """
    base_url = os.getenv("BLINKY_CUSTOM_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")].rstrip("/")
    api_key = os.getenv("CUSTOM_API_KEY", "").strip()
    model = os.getenv("BLINKY_CUSTOM_MODEL", "").strip() or DEFAULT_CUSTOM_MODEL
    return base_url, api_key, model


def _build_messages(prompt: str, screenshot_path: Path | str | None) -> list[dict[str, Any]]:
    """Build OpenAI-format messages. With a screenshot, use the multimodal
    content array (base64 data URL) so vision-capable models see the screen."""
    if screenshot_path is None:
        return [{"role": "user", "content": prompt}]

    path = Path(screenshot_path)
    if not path.exists():
        LOGGER.warning("Screenshot path missing for custom vision call: %s", path)
        return [{"role": "user", "content": prompt}]

    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        LOGGER.warning("Could not read screenshot for custom vision call: %s", exc)
        return [{"role": "user", "content": prompt}]

    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]


def _post(
    payload: dict[str, Any],
    base_url: str,
    api_key: str,
    timeout: int = 90,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = f"{base_url}/chat/completions"
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Custom provider request timed out after {timeout}s")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Custom provider connection error: {exc}")

    if not response.ok:
        try:
            err = response.json()
            msg = err.get("error", {}).get("message", response.text[:200])
        except Exception:
            msg = response.text[:200]
        raise RuntimeError(f"Custom provider failed (HTTP {response.status_code}): {msg}")

    return response.json()


def _post_with_fallback(
    base_payload: dict[str, Any],
    base_url: str,
    api_key: str,
    model: str,
    timeout: int = 90,
) -> dict[str, Any]:
    """Execute chat completion with automatic fallback for optional parameters
    (such as thinking disable or response_format) that certain endpoints reject."""
    candidates: list[dict[str, Any]] = []

    # 1. For minimax specifically on Zen/Go, try with thinking disabled + response_format
    if "minimax" in model.lower():
        candidates.append({
            **base_payload,
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        })
        candidates.append({
            **base_payload,
            "thinking": {"type": "disabled"},
        })

    # 2. Standard structured JSON mode (OpenAI standard)
    candidates.append({
        **base_payload,
        "response_format": {"type": "json_object"},
    })

    # 3. Plain base payload (most compatible fallback)
    candidates.append(base_payload)

    last_err: Exception | None = None
    for payload in candidates:
        try:
            return _post(payload, base_url, api_key, timeout=timeout)
        except RuntimeError as exc:
            last_err = exc
            LOGGER.debug("Custom provider fallback from %s due to: %s", list(payload.keys()), exc)

    if last_err:
        raise last_err
    raise RuntimeError("Custom provider failed with no response.")


def _extract_content(payload: dict[str, Any]) -> str:
    """Extract visible or reasoning text from a chat-completion response."""
    choices = payload.get("choices", [])
    if not choices or not isinstance(choices, list):
        raise RuntimeError("Custom provider returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(
            str(item.get("text", "")) for item in content if isinstance(item, dict)
        )
    content_str = str(content) if content is not None else ""
    if not content_str.strip():
        # Check reasoning_content in case model output was placed entirely in reasoning
        reasoning = message.get("reasoning_content") or message.get("reasoning") or message.get("thought") or ""
        if reasoning:
            return str(reasoning)
    return content_str


def _parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from provider output, tolerating common wrappers."""
    # Strip thinking-model chain-of-thought blocks (minimax-m3, deepseek, glm, etc.)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned.strip(), flags=re.IGNORECASE)
    if not cleaned.strip():
        raise RuntimeError(
            "Custom provider returned empty content. The model may have exhausted "
            "its token budget on chain-of-thought (thinking model) or the context "
            "is too long. Try a larger max_tokens or a shorter conversation."
        )
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Extract the first balanced JSON object (handles trailing prose
        # after the object, which a greedy `{.*}` regex would swallow).
        match = _find_json_object(cleaned)
        if match is None:
            raise
        return json.loads(match)


def _find_json_object(text: str) -> str | None:
    """Return the first balanced {...} substring, or None."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break  # not valid JSON; try next {
        start = text.find("{", start + 1)
    return None


def ask_custom_text(prompt: str, max_tokens: int = 1024) -> dict[str, Any]:
    """Send a text prompt to the configured provider and return its JSON result."""
    base_url, api_key, model = _config()
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "messages": _build_messages(prompt, None),
    }
    body = _post_with_fallback(payload, base_url, api_key, model)
    return _parse_json(_extract_content(body))


def ask_custom_vision(prompt: str, screenshot_path: Path, max_tokens: int = 2048) -> dict[str, Any]:
    """Send a screenshot prompt to the configured provider and return JSON."""
    base_url, api_key, model = _config()
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "messages": _build_messages(prompt, screenshot_path),
    }
    body = _post_with_fallback(payload, base_url, api_key, model)
    return _parse_json(_extract_content(body))


def has_vision_capability() -> bool:
    """Vision depends on the configured model; report True so the caller
    attempts multimodal and degrades gracefully if the endpoint rejects it."""
    _, _, model = _config()
    model_lower = model.lower()
    # Known text-only families on Zen/Go
    text_only_hints = ("deepseek", "mimo", "hy3", "text")
    return not any(hint in model_lower for hint in text_only_hints)
