"""Prompt loader — reads agent prompts from YAML config file."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from utils.logging import get_logger

LOGGER = get_logger("blinky.prompts")

_PROMPTS_DIR = Path(__file__).parent
_DEFAULT_CONFIG = _PROMPTS_DIR / "agent.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        LOGGER.warning("Failed to load prompts from %s: %s", path, e)
        return {}


def get_prompts() -> dict[str, str]:
    """Load all prompts from the config file.

    Returns a dict with keys: system, app_inventory, vision_note,
    premature_answer, inspection_loop, repeated_tool.
    """
    config_path = Path(os.getenv("BLINKY_PROMPTS_CONFIG", str(_DEFAULT_CONFIG)))
    prompts = _load_yaml(config_path)

    if not prompts:
        LOGGER.warning("Prompts config empty or missing, using fallback defaults")
        prompts = _fallback_prompts()

    return prompts


def _fallback_prompts() -> dict[str, str]:
    """Minimal fallback prompts if config file is missing."""
    return {
        "system": (
            "You are Blinky's desktop automation engine on Linux (KDE).\n"
            "Tools:\n{tools}\n"
            "Output exactly one JSON: {{\"tool\": \"name\", \"args\": {{}}}} or {{\"answer\": \"...\"}}\n"
            "Output only valid JSON."
        ),
        "app_inventory": "Available Applications on this system:\n{inventory}",
        "vision_note": "You have vision capability — the screenshot image will be available for visual understanding.",
        "premature_answer": "SYSTEM: Take a screenshot to verify before answering.",
        "inspection_loop": "SYSTEM: You have inspected the screen {count} times without taking action. Do something now.",
        "repeated_tool": "SYSTEM: You have called {tool_name} {count} times in a row. Try a different tool.",
    }
