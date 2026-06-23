from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.computer_use.metrics")

LOG_DIR = Path(".brain") / "logs" / "vision"


def get_log_path(day: date | None = None) -> Path:
    d = day or date.today()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"{d.isoformat()}.jsonl"


def log_vision_call(
    module: str,
    latency_ms: float | None = None,
    token_count: int | None = None,
    success: bool = True,
    verified: bool | None = None,
    confidence: float | None = None,
    root_cause_category: str | None = None,
    app_type: str = "unknown",
    action_taken: str | None = None,
    model_error: str | None = None,
) -> None:
    from datetime import datetime, timezone

    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "module": module,
        "latency_ms": latency_ms,
        "token_count": token_count,
        "success": success,
        "verified": verified,
        "confidence": confidence,
        "root_cause_category": root_cause_category,
        "app_type": app_type,
        "action_taken": action_taken,
        "model_error": model_error,
    }
    log_path = get_log_path()
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:
        LOGGER.warning("Failed to write vision metrics: %s", exc)
