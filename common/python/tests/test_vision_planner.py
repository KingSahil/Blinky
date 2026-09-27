"""Tests for vision-guided planning module."""

from __future__ import annotations

from unittest.mock import ANY, patch

from computer_use.vision_planner import plan_action


def _tool_schema() -> dict:
    return {"open_app": {}, "screenshot": {}, "type_text": {}, "press_key": {}, "click_element": {}, "list_windows": {}, "get_app_state": {}, "mouse": {}}


@patch("ai.client.ask_model")
def test_plan_action_returns_structured_action(mock_ask) -> None:
    mock_ask.return_value = {"action": "screenshot", "args": {}, "reasoning": "Need to see the screen first"}
    result = plan_action(
        screenshot_path="/tmp/test.png",
        query="open calculator",
        history=[],
        tool_schema=_tool_schema(),
    )
    assert "error" not in result
    assert result["action"] == "screenshot"
    assert result["args"] == {}
    assert "reasoning" in result


@patch("ai.client.ask_model")
def test_plan_action_none_screenshot(mock_ask) -> None:
    result = plan_action(
        screenshot_path=None,
        query="open calculator",
        history=[],
        tool_schema=_tool_schema(),
    )
    assert "error" in result
    assert result["error"] == "Screenshot unavailable"
    mock_ask.assert_not_called()


@patch("ai.client.ask_model")
def test_plan_action_model_error(mock_ask) -> None:
    mock_ask.side_effect = RuntimeError("API timeout")
    result = plan_action(
        screenshot_path="/tmp/test.png",
        query="open calculator",
        history=[],
        tool_schema=_tool_schema(),
    )
    assert "error" in result
    assert "API timeout" in result["error"]


@patch("ai.client.ask_model")
def test_plan_action_no_action_field(mock_ask) -> None:
    mock_ask.return_value = {"args": {}, "reasoning": "something"}
    result = plan_action(
        screenshot_path="/tmp/test.png",
        query="open calculator",
        history=[],
        tool_schema=_tool_schema(),
    )
    assert "error" in result
    assert "No action" in result["error"]


@patch("ai.client.ask_model")
def test_plan_action_misparse_retries_then_raw_text(mock_ask) -> None:
    mock_ask.side_effect = [
        {"action": "invalid_tool", "args": {}, "reasoning": "bad"},
        {"action": "also_invalid", "args": {}, "reasoning": "still bad"},
        {"action": "still_wrong", "args": {}, "reasoning": "nope"},
        {"action": "still_wrong_again", "args": {}, "reasoning": "nope"},
    ]
    result = plan_action(
        screenshot_path="/tmp/test.png",
        query="open calculator",
        history=[],
        tool_schema=_tool_schema(),
    )
    assert "error" not in result
    assert result["action"] == "raw_text"
    assert "unparseable" in result["reasoning"]


@patch("ai.client.ask_model")
def test_plan_action_misparse_recovers(mock_ask) -> None:
    mock_ask.side_effect = [
        {"action": "invalid_tool", "args": {}, "reasoning": "bad"},
        {"action": "screenshot", "args": {}, "reasoning": "fixed"},
    ]
    result = plan_action(
        screenshot_path="/tmp/test.png",
        query="open calculator",
        history=[],
        tool_schema=_tool_schema(),
    )
    assert "error" not in result
    assert result["action"] == "screenshot"


@patch("ai.client.ask_model")
def test_plan_action_metrics_logged_on_success(mock_ask) -> None:
    mock_ask.return_value = {"action": "open_app", "args": {"app_name": "calc"}, "reasoning": "launch"}
    with patch("computer_use.vision_planner.metrics.log_vision_call") as mock_log:
        result = plan_action(
            screenshot_path="/tmp/test.png",
            query="open calc",
            history=[],
            tool_schema=_tool_schema(),
        )
        assert "error" not in result
        mock_log.assert_called_once_with(
            module="vision_planner",
            latency_ms=ANY,
            success=True,
            app_type="unknown",
            action_taken="open_app",
        )


@patch("ai.client.ask_model")
def test_plan_action_metrics_logged_on_error(mock_ask) -> None:
    mock_ask.side_effect = RuntimeError("fail")
    with patch("computer_use.vision_planner.metrics.log_vision_call") as mock_log:
        result = plan_action(
            screenshot_path="/tmp/test.png",
            query="open calc",
            history=[],
            tool_schema=_tool_schema(),
        )
        assert "error" in result
        mock_log.assert_called_once_with(
            module="vision_planner",
            latency_ms=ANY,
            success=False,
            app_type="unknown",
            model_error=ANY,
        )
