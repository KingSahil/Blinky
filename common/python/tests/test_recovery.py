"""Tests for failure recovery module."""

from __future__ import annotations

from unittest.mock import ANY, patch

from computer_use.recovery import diagnose_failure


@patch("ai.client.ask_model")
def test_diagnose_failure_success(mock_ask) -> None:
    mock_ask.return_value = {
        "diagnosis": "Window not focused",
        "suggestion": "Click on the window first",
        "actions": [{"tool": "click_element", "args": {"name": "calc"}}],
        "requires_replan": False,
        "root_cause_category": "wrong_window_focus",
    }
    result = diagnose_failure(
        screenshot_path="/tmp/test.png",
        failed_action="type_text",
        error="Keystrokes not delivered",
    )
    assert result["diagnosis"] == "Window not focused"
    assert result["suggestion"] == "Click on the window first"
    assert len(result["actions"]) == 1
    assert result["actions"][0]["tool"] == "click_element"
    assert result["requires_replan"] is False
    assert result["root_cause_category"] == "wrong_window_focus"


@patch("ai.client.ask_model")
def test_diagnose_failure_none_screenshot(mock_ask) -> None:
    result = diagnose_failure(
        screenshot_path=None,
        failed_action="type_text",
        error="error",
    )
    assert result["diagnosis"] == "Recovery unavailable"
    assert result["suggestion"] == "Proceed with fallback"
    assert result["actions"] == []
    assert result["root_cause_category"] == "unknown"
    mock_ask.assert_not_called()


@patch("ai.client.ask_model")
def test_diagnose_failure_model_error(mock_ask) -> None:
    mock_ask.side_effect = RuntimeError("API error")
    result = diagnose_failure(
        screenshot_path="/tmp/test.png",
        failed_action="type_text",
        error="error",
    )
    assert "Recovery model unavailable" in result["diagnosis"]
    assert result["root_cause_category"] == "unknown"


@patch("ai.client.ask_model")
def test_diagnose_failure_invalid_root_cause(mock_ask) -> None:
    mock_ask.return_value = {
        "diagnosis": "Something",
        "suggestion": "Fix it",
        "actions": [],
        "requires_replan": False,
        "root_cause_category": "made_up_category",
    }
    result = diagnose_failure(
        screenshot_path="/tmp/test.png",
        failed_action="type_text",
        error="error",
    )
    assert result["root_cause_category"] == "unknown"


@patch("ai.client.ask_model")
def test_diagnose_failure_actions_not_list(mock_ask) -> None:
    mock_ask.return_value = {
        "diagnosis": "Issue",
        "suggestion": "Fix",
        "actions": "not_a_list",
        "requires_replan": False,
        "root_cause_category": "unknown",
    }
    result = diagnose_failure(
        screenshot_path="/tmp/test.png",
        failed_action="type_text",
        error="error",
    )
    assert result["actions"] == []


@patch("ai.client.ask_model")
def test_diagnose_failure_no_error_string(mock_ask) -> None:
    mock_ask.return_value = {
        "diagnosis": "Verification failure",
        "suggestion": "Retry",
        "actions": [],
        "requires_replan": True,
        "root_cause_category": "element_missing",
    }
    result = diagnose_failure(
        screenshot_path="/tmp/test.png",
        failed_action="click_element",
        error=None,
    )
    assert result["diagnosis"] == "Verification failure"
    assert result["requires_replan"] is True


@patch("ai.client.ask_model")
def test_diagnose_failure_metrics_logged(mock_ask) -> None:
    mock_ask.return_value = {
        "diagnosis": "Window not focused",
        "suggestion": "Click first",
        "actions": [],
        "requires_replan": False,
        "root_cause_category": "wrong_window_focus",
    }
    with patch("computer_use.recovery.metrics.log_vision_call") as mock_log:
        result = diagnose_failure(
            screenshot_path="/tmp/test.png",
            failed_action="type_text",
            error="error",
        )
        assert result["root_cause_category"] == "wrong_window_focus"
        mock_log.assert_called_once_with(
            module="recovery",
            latency_ms=ANY,
            success=True,
            app_type="unknown",
            root_cause_category="wrong_window_focus",
            action_taken="type_text",
        )


@patch("ai.client.ask_model")
def test_diagnose_failure_requires_replan(mock_ask) -> None:
    mock_ask.return_value = {
        "diagnosis": "App crashed",
        "suggestion": "Restart and replan",
        "actions": [{"tool": "open_app", "args": {"app_name": "calc"}}],
        "requires_replan": True,
        "root_cause_category": "environment_changed",
    }
    result = diagnose_failure(
        screenshot_path="/tmp/test.png",
        failed_action="type_text",
        error="Connection lost",
    )
    assert result["requires_replan"] is True
    assert result["root_cause_category"] == "environment_changed"
