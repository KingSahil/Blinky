from __future__ import annotations

import logging
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    logs_dir = Path("tmp") / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    # File Handler
    file_handler = logging.FileHandler(logs_dir / "blinky.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console Handler (sys.stderr)
    import sys
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

