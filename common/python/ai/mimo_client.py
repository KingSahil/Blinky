"""MiMo V2.5 client — OpenAI-compatible chat completions with vision support."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from utils.logging import get_logger

LOGGER = get_logger("blinky.mimo")

DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_MIMO_MODEL = "mimo-v2.5-free"


def ask_mimo_vision(prompt: str, screenshot_path: Path) -> dict[str, Any]:
    api_key = os.getenv("MIMO_API_KEY", "").strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MIMO_API_KEY or DEEPSEEK_API_KEY is required when BLINKY_AI_PROVIDER=mimo.")

    url = os.getenv("BLINKY_MIMO_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.getenv("BLINKY_MIMO_MODEL", DEFAULT_MIMO_MODEL).strip() or DEFAULT_MIMO_MODEL

    image_payload = _image_to_data_url(screenshot_path)

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
            timeout=90,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("MiMo API request timed out after 90 seconds.")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"MiMo API connection error: {exc}")

    if not response.ok:
        try:
            err = response.json()
            msg = err.get("error", {}).get("message", response.text[:200])
        except Exception:
            msg = response.text[:200]
        raise RuntimeError(f"MiMo request failed (HTTP {response.status_code}): {msg}")

    body = response.json()
    content = _extract_content(body)
    return _parse_json(content)


def ask_mimo_text(prompt: str, max_tokens: int = 300) -> dict[str, Any]:
    api_key = os.getenv("MIMO_API_KEY", "").strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MIMO_API_KEY or DEEPSEEK_API_KEY is required when BLINKY_AI_PROVIDER=mimo.")

    url = os.getenv("BLINKY_MIMO_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.getenv("BLINKY_MIMO_MODEL", DEFAULT_MIMO_MODEL).strip() or DEFAULT_MIMO_MODEL

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
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("MiMo API request timed out after 60 seconds.")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"MiMo API connection error: {exc}")

    if not response.ok:
        try:
            err = response.json()
            msg = err.get("error", {}).get("message", response.text[:200])
        except Exception:
            msg = response.text[:200]
        raise RuntimeError(f"MiMo request failed (HTTP {response.status_code}): {msg}")

    body = response.json()
    content = _extract_content(body)
    return _parse_json(content)


def _image_to_data_url(screenshot_path: Path) -> str:
    raw = screenshot_path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices or not isinstance(choices, list):
        raise RuntimeError("MiMo returned no choices.")
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
