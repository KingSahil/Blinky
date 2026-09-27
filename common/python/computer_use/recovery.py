"""
Failure recovery module.
Diagnoses failures from screen evidence and proposes corrective actions.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from utils.logging import get_logger

from . import config
from . import metrics

LOGGER = get_logger("blinky.computer_use.recovery")

VALID_ROOT_CAUSES = {
    "wrong_window_focus", "app_not_ready", "element_missing", "syntax_error",
    "permission_denied", "environment_changed", "hallucination", "transient_state", "unknown",
}


def diagnose_failure(
    screenshot_path: str | None,
    failed_action: str,
    error: str | None,
    history: list[str] | None = None,
    app_type: str = "unknown",
) -> dict[str, Any]:
    """
    Diagnose a failure by examining the current screen and return corrective actions.

    Args:
        screenshot_path: Path to PNG screenshot file, or None if unavailable
        failed_action: String describing what failed
        error: Error message string, or None for verification failures
        history: Last few vision observations for context
        app_type: Always "unknown" in this phase

    Returns:
        {"diagnosis": str, "suggestion": str, "actions": list, "requires_replan": bool, "root_cause_category": str}
    """
    from prompts import get_prompts
    from ai.client import ask_model

    if screenshot_path is None:
        LOGGER.warning("diagnose_failure: screenshot_path is None")
        return {
            "diagnosis": "Recovery unavailable",
            "suggestion": "Proceed with fallback",
            "actions": [],
            "requires_replan": False,
            "root_cause_category": "unknown",
        }

    error_detail = error or "No error message"
    prompts = get_prompts()
    prompt = prompts.get("recovery_prompt", "").format(action=failed_action, error=error_detail)

    start = time.perf_counter()
    try:
        result = ask_model(prompt, Path(screenshot_path))
        latency_ms = (time.perf_counter() - start) * 1000
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        LOGGER.exception("diagnose_failure: vision model error")
        metrics.log_vision_call(
            module="recovery",
            latency_ms=latency_ms,
            success=False,
            app_type=app_type,
            model_error=str(exc),
        )
        return {
            "diagnosis": "Recovery model unavailable",
            "suggestion": "Proceed using fallback logic",
            "actions": [],
            "requires_replan": False,
            "root_cause_category": "unknown",
        }

    diagnosis = str(result.get("diagnosis", ""))
    suggestion = str(result.get("suggestion", ""))
    actions = result.get("actions", [])
    if not isinstance(actions, list):
        actions = []
    requires_replan = bool(result.get("requires_replan", False))
    root_cause_category = str(result.get("root_cause_category", "unknown"))

    if root_cause_category not in VALID_ROOT_CAUSES:
        LOGGER.warning("diagnose_failure: unknown root_cause_category '%s', defaulting to 'unknown'", root_cause_category)
        root_cause_category = "unknown"

    metrics.log_vision_call(
        module="recovery",
        latency_ms=latency_ms,
        success=True,
        app_type=app_type,
        root_cause_category=root_cause_category,
        action_taken=failed_action,
    )

    return {
        "diagnosis": diagnosis,
        "suggestion": suggestion,
        "actions": actions,
        "requires_replan": requires_replan,
        "root_cause_category": root_cause_category,
    }
