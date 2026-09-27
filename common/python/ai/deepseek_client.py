"""DeepSeek API client — OpenAI-compatible chat completions."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from utils.logging import get_logger

LOGGER = get_logger("blinky.deepseek")

DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash-free"


def ask_deepseek_text(prompt: str, max_tokens: int = 0) -> dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required when BLINKY_AI_PROVIDER=deepseek.")

    url = os.getenv("BLINKY_DEEPSEEK_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.getenv("BLINKY_DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip() or DEFAULT_DEEPSEEK_MODEL

    try:
        response = requests.post(
            url + "/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("DeepSeek API request timed out after 60 seconds.")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"DeepSeek API connection error: {exc}")

    if not response.ok:
        try:
            err = response.json()
            msg = err.get("error", {}).get("message", response.text[:200])
        except Exception:
            msg = response.text[:200]
        raise RuntimeError(f"DeepSeek request failed (HTTP {response.status_code}): {msg}")

    body = response.json()
    content = _extract_content(body)
    return _parse_json(content)


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices or not isinstance(choices, list):
        raise RuntimeError("DeepSeek returned no choices.")
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
