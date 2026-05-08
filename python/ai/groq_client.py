from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from utils.logging import get_logger

LOGGER = get_logger("clicky.groq")

DEFAULT_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.2-90b-vision-preview"


def ask_groq_vision(prompt: str, screenshot_path: Path) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required when CLICKY_AI_PROVIDER=groq.")

    model = os.getenv("CLICKY_GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
    groq_url = os.getenv("CLICKY_GROQ_URL", DEFAULT_GROQ_URL).strip() or DEFAULT_GROQ_URL

    image_payload = _image_to_data_url(screenshot_path)
    response = requests.post(
        groq_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.1,
            "max_tokens": 700,
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
        timeout=45,
    )
    response.raise_for_status()
    body = response.json()
    content = _extract_content(body)
    return _validate_response(_parse_json(content))


def _image_to_data_url(screenshot_path: Path) -> str:
    raw = screenshot_path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"


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

    if not normalized_steps:
        normalized_steps.append(
            {
                "step": 1,
                "instruction": "I cannot see the needed control yet. Open the relevant panel or menu and ask again.",
                "target_text": "",
            }
        )

    return {"summary": summary, "steps": normalized_steps, "warnings": []}

