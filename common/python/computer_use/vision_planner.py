"""
Vision-guided planning module.
Called before the first action and after recovery to decide the next atomic step.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from utils.logging import get_logger

from . import config
from . import metrics

LOGGER = get_logger("blinky.computer_use.vision_planner")


def plan_action(
    screenshot_path: str | None,
    query: str,
    history: list[str],
    tool_schema: dict[str, Any],
    app_type: str = "unknown",
) -> dict[str, Any]:
    """
    Given a screenshot and user query, return the next action as a structured plan.

    Args:
        screenshot_path: Path to PNG screenshot file, or None if unavailable
        query: The user's task string
        history: Previous vision observations (most recent first, max MAX_HISTORY_OBSERVATIONS)
        tool_schema: Dict mapping tool names to their parameter specs
        app_type: Always "unknown" in this phase

    Returns:
        On success: {"action": "tool_name", "args": {...}, "reasoning": "..."}
        On failure: {"error": "..."}
    """
    from prompts import get_prompts
    from ai.client import ask_model

    if screenshot_path is None:
        LOGGER.warning("plan_action: screenshot_path is None")
        return {"error": "Screenshot unavailable"}

    # Build prompt
    prompts = get_prompts()
    prompt = prompts.get("vision_planner_prompt", "").format(query=query)

    start = time.perf_counter()
    try:
        result = ask_model(prompt, Path(screenshot_path))
        latency_ms = (time.perf_counter() - start) * 1000
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        LOGGER.exception("plan_action: vision model error")
        metrics.log_vision_call(
            module="vision_planner",
            latency_ms=latency_ms,
            success=False,
            app_type=app_type,
            model_error=str(exc),
        )
        return {"error": f"Vision model error: {exc}"}

    action = result.get("action", "")
    args = result.get("args", {})
    reasoning = result.get("reasoning", "")

    if not action:
        metrics.log_vision_call(
            module="vision_planner",
            latency_ms=latency_ms,
            success=False,
            app_type=app_type,
            model_error="No action field in response",
        )
        return {"error": "No action returned by vision model"}

    misparses = 0
    while action not in tool_schema and misparses < config.MAX_PLANNER_MISPARSE_RETRIES:
        misparses += 1
        LOGGER.warning("plan_action: misparse #%d: action='%s' not in schema", misparses, action)
        schema_clarification = (
            f"Your previous output had action='{action}' which is not a valid tool. "
            f"Valid tools: {list(tool_schema.keys())}. "
            f"Return a JSON object with 'action' (one of the valid tool names), 'args' (dict), and 'reasoning' (string)."
        )
        try:
            result = ask_model(schema_clarification, Path(screenshot_path))
            action = result.get("action", "")
            args = result.get("args", {})
            reasoning = result.get("reasoning", "")
        except Exception:
            break

    if action not in tool_schema:
        metrics.log_vision_call(
            module="vision_planner",
            latency_ms=latency_ms,
            success=True,
            app_type=app_type,
            action_taken=f"raw_text after {misparses} misparses",
        )
        return {
            "action": "raw_text",
            "args": {"suggestion": f"{action}: {json.dumps(args)}"},
            "reasoning": f"Model returned unparseable tool call after {misparses} retries",
        }

    metrics.log_vision_call(
        module="vision_planner",
        latency_ms=latency_ms,
        success=True,
        app_type=app_type,
        action_taken=action,
    )

    return {
        "action": action,
        "args": args,
        "reasoning": reasoning,
    }
