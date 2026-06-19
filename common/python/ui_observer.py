from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import psutil

from capture.screen import capture_screen
from main import get_or_build_visible_ui_map
from utils.logging import get_logger
from utils.window import get_active_window, get_target_window_element


LOGGER = get_logger("blinky.ui_observer")


def observe_once() -> int:
    target_pid: int | None = None
    try:
        target = get_target_window_element()
        target_pid = target.process_id() if target else None
    except Exception:
        target_pid = None

    screenshot = capture_screen()
    active_app = get_active_window(target_pid=target_pid)
    items = get_or_build_visible_ui_map(active_app, screenshot, target_pid)
    LOGGER.info(
        "Warmed UI map for %s (%s): %d items",
        active_app.get("title"),
        active_app.get("process"),
        len(items),
    )
    return len(items)


def run_observer(interval_seconds: float, once: bool = False, parent_pid: int | None = None) -> None:
    while True:
        if parent_pid is not None and not psutil.pid_exists(parent_pid):
            LOGGER.info("Stopping UI observer because parent process %s is gone", parent_pid)
            return

        try:
            observe_once()
        except Exception as exc:
            LOGGER.warning("UI observer refresh failed: %s", exc)

        if once:
            return

        time.sleep(max(0.25, interval_seconds))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continuously warm Blinky's UI map cache.")
    parser.add_argument("--interval", type=float, default=float(os.environ.get("BLINKY_UI_OBSERVER_INTERVAL", "1.5")))
    parser.add_argument("--parent-pid", type=int, default=int(os.environ.get("BLINKY_UI_OBSERVER_PARENT_PID", "0") or "0"))
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_observer(args.interval, once=args.once, parent_pid=args.parent_pid or None)


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    main()
