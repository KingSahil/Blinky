"""Tests for vision-guided verification module."""

from __future__ import annotations

from unittest.mock import ANY, patch

from computer_use.vision_verifier import verify_action


@patch("ai.client.ask_model")
def test_verify_action_verified(mock_ask) -> None:
    mock_ask.return_value = {"verified": True, "observation": "Calculator app is open", "suggestion": "", "confidence": 0.95}
    result = verify_action(
        screenshot_path="/tmp/test.png",
        action_taken="open_app(calc)",
        expected_outcome="Calculator should be open",
    )
    assert result["verified"] is True
    assert result["confidence"] == 0.95
    assert "Calculator" in result["observation"]


@patch("ai.client.ask_model")
def test_verify_action_not_verified(mock_ask) -> None:
    mock_ask.return_value = {"verified": False, "observation": "Calculator is not visible", "suggestion": "Try launching again", "confidence": 0.3}
    result = verify_action(
        screenshot_path="/tmp/test.png",
        action_taken="open_app(calc)",
        expected_outcome="Calculator should be open",
    )
    assert result["verified"] is False
    assert result["confidence"] == 0.3
    assert "Try launching" in result["suggestion"]


@patch("ai.client.ask_model")
def test_verify_action_none_screenshot(mock_ask) -> None:
    result = verify_action(
        screenshot_path=None,
        action_taken="open_app(calc)",
        expected_outcome="Calculator should be open",
    )
    assert result["verified"] is False
    assert result["confidence"] == 0.0
    assert "Screenshot unavailable" in result["observation"]
    mock_ask.assert_not_called()


@patch("ai.client.ask_model")
def test_verify_action_model_error(mock_ask) -> None:
    mock_ask.side_effect = RuntimeError("API error")
    result = verify_action(
        screenshot_path="/tmp/test.png",
        action_taken="open_app(calc)",
        expected_outcome="Calculator should be open",
    )
    assert result["verified"] is False
    assert result["confidence"] == 0.0
    assert "Verification model error" in result["observation"]


@patch("ai.client.ask_model")
def test_verify_action_hallucination_guard(mock_ask) -> None:
    mock_ask.return_value = {"verified": True, "observation": "I can see open calculator on the screen", "suggestion": "", "confidence": 0.95}
    result = verify_action(
        screenshot_path="/tmp/test.png",
        action_taken="open_app(calc)",
        expected_outcome="Calculator should be open",
        query="open calculator",
    )
    assert result["verified"] is False
    assert result["confidence"] == 0.0
    assert "hallucinated" in result["suggestion"]


@patch("ai.client.ask_model")
def test_verify_action_confidence_below_low(mock_ask) -> None:
    mock_ask.return_value = {"verified": True, "observation": "Something happened", "suggestion": "", "confidence": 0.1}
    result = verify_action(
        screenshot_path="/tmp/test.png",
        action_taken="open_app(calc)",
        expected_outcome="Calculator should be open",
    )
    assert result["verified"] is False


@patch("ai.client.ask_model")
def test_verify_action_borderline_confidence_passes_through(mock_ask) -> None:
    mock_ask.return_value = {"verified": True, "observation": "Calculator is visible", "suggestion": "", "confidence": 0.65}
    with patch("computer_use.vision_verifier.config.VISION_CONFIDENCE_LOW", 0.5), \
         patch("computer_use.vision_verifier.config.VISION_CONFIDENCE_HIGH", 0.8):
        result = verify_action(
            screenshot_path="/tmp/test.png",
            action_taken="open_app(calc)",
            expected_outcome="Calculator should be open",
        )
        assert result["verified"] is True
        assert result["confidence"] == 0.65


@patch("ai.client.ask_model")
def test_verify_action_metrics_logged(mock_ask) -> None:
    mock_ask.return_value = {"verified": True, "observation": "ok", "suggestion": "", "confidence": 0.9}
    with patch("computer_use.vision_verifier.metrics.log_vision_call") as mock_log:
        result = verify_action(
            screenshot_path="/tmp/test.png",
            action_taken="open_app(calc)",
            expected_outcome="Calculator should be open",
        )
        assert result["verified"] is True
        mock_log.assert_called_once_with(
            module="vision_verifier",
            latency_ms=ANY,
            success=True,
            verified=True,
            confidence=0.9,
            app_type="unknown",
            action_taken="open_app(calc)",
        )
