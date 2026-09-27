from __future__ import annotations

import os
from unittest.mock import patch

from ai.client import has_vision_capability


def test_vision_groq_returns_true() -> None:
    with patch.dict(os.environ, {"BLINKY_AI_PROVIDER": "groq"}):
        assert has_vision_capability() is True


def test_vision_groq_capitalized_returns_true() -> None:
    with patch.dict(os.environ, {"BLINKY_AI_PROVIDER": "Groq"}):
        assert has_vision_capability() is True


def test_vision_deepseek_returns_false() -> None:
    with patch.dict(os.environ, {"BLINKY_AI_PROVIDER": "deepseek"}):
        assert has_vision_capability() is False


def test_vision_unset_returns_false() -> None:
    with patch.dict(os.environ, clear=True):
        assert has_vision_capability() is False


def test_vision_empty_returns_false() -> None:
    with patch.dict(os.environ, {"BLINKY_AI_PROVIDER": ""}):
        assert has_vision_capability() is False


def test_vision_ollama_returns_false() -> None:
    with patch.dict(os.environ, {"BLINKY_AI_PROVIDER": "ollama"}):
        assert has_vision_capability() is False
