"""Tests for vision-guided agent configuration constants."""

from __future__ import annotations

from computer_use import config


def test_max_history_observations_is_positive_int() -> None:
    assert isinstance(config.MAX_HISTORY_OBSERVATIONS, int)
    assert config.MAX_HISTORY_OBSERVATIONS > 0


def test_max_failures_is_positive_int() -> None:
    assert isinstance(config.MAX_FAILURES, int)
    assert config.MAX_FAILURES > 0


def test_loop_detection_threshold_is_positive_int() -> None:
    assert isinstance(config.LOOP_DETECTION_THRESHOLD, int)
    assert config.LOOP_DETECTION_THRESHOLD > 0


def test_screenshot_poll_interval_ms_is_positive_int() -> None:
    assert isinstance(config.SCREENSHOT_POLL_INTERVAL_MS, int)
    assert config.SCREENSHOT_POLL_INTERVAL_MS > 0


def test_screenshot_poll_timeout_ms_is_positive_int() -> None:
    assert isinstance(config.SCREENSHOT_POLL_TIMEOUT_MS, int)
    assert config.SCREENSHOT_POLL_TIMEOUT_MS > 0


def test_screenshot_stable_frames_is_positive_int() -> None:
    assert isinstance(config.SCREENSHOT_STABLE_FRAMES, int)
    assert config.SCREENSHOT_STABLE_FRAMES > 0


def test_vision_confidence_low_is_float() -> None:
    assert isinstance(config.VISION_CONFIDENCE_LOW, (int, float))
    assert 0 <= config.VISION_CONFIDENCE_LOW <= 1.0


def test_vision_confidence_high_is_float() -> None:
    assert isinstance(config.VISION_CONFIDENCE_HIGH, (int, float))
    assert 0 <= config.VISION_CONFIDENCE_HIGH <= 1.0


def test_confidence_low_less_than_high() -> None:
    assert config.VISION_CONFIDENCE_LOW < config.VISION_CONFIDENCE_HIGH


def test_max_planner_misparse_retries_is_positive_int() -> None:
    assert isinstance(config.MAX_PLANNER_MISPARSE_RETRIES, int)
    assert config.MAX_PLANNER_MISPARSE_RETRIES > 0


def test_transient_backoff_ms_is_positive_int() -> None:
    assert isinstance(config.TRANSIENT_BACKOFF_MS, int)
    assert config.TRANSIENT_BACKOFF_MS > 0


def test_max_consecutive_vision_failures_is_positive_int() -> None:
    assert isinstance(config.MAX_CONSECUTIVE_VISION_FAILURES, int)
    assert config.MAX_CONSECUTIVE_VISION_FAILURES > 0
