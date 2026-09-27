"""
Post-action verification module.
Checks if the last action had the expected effect on screen.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from utils.logging import get_logger

from . import config
from . import metrics

LOGGER = get_logger("blinky.computer_use.vision_verifier")


def verify_action(
    screenshot_path: str | None,
    action_taken: str,
    expected_outcome: str,
    query: str = "",
    app_type: str = "unknown",
) -> dict[str, Any]:
    """
    Verify whether an action had the expected effect by examining a screenshot.

    Args:
        screenshot_path: Path to PNG screenshot file, or None if unavailable
        action_taken: String describing what the LLM just did
        expected_outcome: String describing what should appear on screen
        query: The original user query (for hallucination guard)
        app_type: Always "unknown" in this phase

    Returns:
        {"verified": bool, "observation": str, "suggestion": str, "confidence": float}
    """
    from prompts import get_prompts
    from ai.client import ask_model

    if screenshot_path is None:
        LOGGER.warning("verify_action: screenshot_path is None")
        return {
            "verified": False,
            "confidence": 0.0,
            "observation": "Screenshot unavailable",
            "suggestion": "Proceed without vision verification",
        }

    prompts = get_prompts()
    prompt = prompts.get("vision_verifier_prompt", "").format(action=action_taken, expected=expected_outcome)

    start = time.perf_counter()
    try:
        result = ask_model(prompt, Path(screenshot_path))
        latency_ms = (time.perf_counter() - start) * 1000
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        LOGGER.exception("verify_action: vision model error")
        metrics.log_vision_call(
            module="vision_verifier",
            latency_ms=latency_ms,
            success=False,
            app_type=app_type,
            model_error=str(exc),
        )
        return {
            "verified": False,
            "confidence": 0.0,
            "observation": "Verification model error",
            "suggestion": "Retry verification with fresh screenshot",
        }

    verified = bool(result.get("verified", False))
    observation = str(result.get("observation", ""))
    suggestion = str(result.get("suggestion", ""))
    confidence = float(result.get("confidence", 0.0))

    if query and observation and query.strip().lower() in observation.strip().lower():
        LOGGER.warning("verify_action: hallucination suspected — observation contains query text")
        verified = False
        suggestion = "Cross-reference: observation may be hallucinated. Take a fresh screenshot and re-verify."
        confidence = 0.0
        metrics.log_vision_call(
            module="vision_verifier",
            latency_ms=latency_ms,
            success=True,
            verified=False,
            confidence=0.0,
            app_type=app_type,
            action_taken=action_taken,
            model_error="hallucination_suspected",
        )
        return {
            "verified": False,
            "observation": observation,
            "suggestion": suggestion,
            "confidence": 0.0,
        }

    if confidence < config.VISION_CONFIDENCE_LOW:
        verified = False
    elif confidence <= config.VISION_CONFIDENCE_HIGH:
        pass

    metrics.log_vision_call(
        module="vision_verifier",
        latency_ms=latency_ms,
        success=True,
        verified=verified,
        confidence=confidence,
        app_type=app_type,
        action_taken=action_taken,
    )

    return {
        "verified": verified,
        "observation": observation,
        "suggestion": suggestion,
        "confidence": confidence,
    }
