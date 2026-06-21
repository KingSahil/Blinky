from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ai.groq_client import ask_groq_text, ask_groq_vision
from ai.ollama_client import ask_ollama, ask_ollama_text


def ask_model(prompt: str, screenshot_path: Path) -> dict[str, Any]:
    provider = (os.getenv("BLINKY_AI_PROVIDER", "ollama").strip() or "ollama").lower()
    if provider == "groq":
        return ask_groq_vision(prompt=prompt, screenshot_path=screenshot_path)
    if provider == "ollama":
        return ask_ollama(prompt)

    raise RuntimeError("Unsupported BLINKY_AI_PROVIDER. Use 'ollama' or 'groq'.")


def ask_text_model(prompt: str, max_tokens: int = 300) -> dict[str, Any]:
    provider = (os.getenv("BLINKY_AI_PROVIDER", "ollama").strip() or "ollama").lower()
    if provider == "groq":
        return ask_groq_text(prompt, max_tokens)
    if provider == "ollama":
        return ask_ollama_text(prompt, max_tokens)

    raise RuntimeError("Unsupported BLINKY_AI_PROVIDER. Use 'ollama' or 'groq'.")



def get_provider_label() -> str:
    provider = (os.getenv("BLINKY_AI_PROVIDER", "ollama").strip() or "ollama").lower()
    return provider.capitalize()

