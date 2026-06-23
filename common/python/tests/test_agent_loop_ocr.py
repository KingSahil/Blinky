from __future__ import annotations

import os
from unittest.mock import patch

from computer_use.loop import build_system_prompt


def test_system_prompt_includes_app_inventory() -> None:
    prompt = build_system_prompt(app_inventory=["firefox", "kate"])
    assert "Available Applications on this system:" in prompt
    assert "- firefox" in prompt
    assert "- kate" in prompt


def test_system_prompt_omits_app_inventory_when_empty() -> None:
    prompt = build_system_prompt(app_inventory=[])
    assert "Available Applications on this system:" not in prompt


def test_system_prompt_omits_app_inventory_when_none() -> None:
    prompt = build_system_prompt(app_inventory=None)
    assert "Available Applications on this system:" not in prompt


def test_system_prompt_includes_vision_note_when_true() -> None:
    prompt = build_system_prompt(has_vision=True)
    assert "vision capability" in prompt
    assert "screenshot image will be available" in prompt


def test_system_prompt_excludes_vision_note_when_false() -> None:
    prompt = build_system_prompt(has_vision=False)
    assert "vision capability" not in prompt


def test_system_prompt_includes_coordinate_guidance() -> None:
    prompt = build_system_prompt()
    assert "ABSOLUTE pixel coordinates from OCR items directly" in prompt
    assert "Do NOT convert to fractions" in prompt


def test_system_prompt_includes_enriched_screenshot_description() -> None:
    prompt = build_system_prompt()
    assert "OCR text items" in prompt


def test_system_prompt_with_recipe_context() -> None:
    prompt = build_system_prompt(recipe_context="\n\nRecipe knowledge: Calculator has buttons 0-9")
    assert "Recipe knowledge" in prompt
