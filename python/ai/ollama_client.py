from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from utils.logging import get_logger

LOGGER = get_logger("blinky.ollama")

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "gemma4:e4b"


def ask_ollama(prompt: str) -> dict[str, Any]:
    ollama_url = os.getenv("BLINKY_OLLAMA_URL", DEFAULT_OLLAMA_URL).strip() or DEFAULT_OLLAMA_URL
    model = os.getenv("BLINKY_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.post(
                ollama_url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 350,
                    },
                },
                timeout=120,
            )
            response.raise_for_status()
            body = response.json()
            return _validate_response(_parse_json(body.get("response", "")))
        except Exception as exc:
            last_error = exc
            LOGGER.warning("Ollama attempt %s failed: %s", attempt + 1, exc)
            time.sleep(0.4)

    raise RuntimeError(
        f"Ollama did not return valid guidance. Is Ollama running with {model}? {last_error}"
    )


def ask_ollama_text(prompt: str) -> dict[str, Any]:
    ollama_url = os.getenv("BLINKY_OLLAMA_URL", DEFAULT_OLLAMA_URL).strip() or DEFAULT_OLLAMA_URL
    model = os.getenv("BLINKY_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL

    response = requests.post(
        ollama_url,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 300,
            },
        },
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    return _parse_json(body.get("response", ""))


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
