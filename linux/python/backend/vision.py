"""Vision-pipeline helpers for Blinky on Linux (Hyprland-first).

Replaces the old wayland_vision.py (kscreen-doctor/KWin based) with
hyprctl-native equivalents:
  - get_screen_scale        → hyprctl monitors (scale)
  - capture_window_crop     → grim -g with bounds (unchanged mechanism)
  - translate_to_absolute   → window_xy + relative_xy (logical px)
  - click_at_absolute       → backend input (compositor-accurate)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from utils.logging import get_logger

LOGGER = get_logger("blinky.backend.vision")


def get_screen_scale() -> float:
    """Display scale factor from `hyprctl monitors -j` (fallback 1.0)."""
    try:
        result = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import json

            data = json.loads(result.stdout)
            for output in data:
                if output.get("enabled", True):
                    return float(output.get("scale", 1.0))
    except Exception:
        pass
    return 1.0


def get_active_window_bounds() -> dict | None:
    """Active window bounds from the compositor backend (hyprctl)."""
    try:
        from .window import get_active_window

        win = get_active_window()
        if win is None:
            return None
        return {
            "x": win.x,
            "y": win.y,
            "width": win.width,
            "height": win.height,
            "title": win.title,
            "app_id": win.process,
        }
    except Exception as exc:
        LOGGER.debug("get_active_window_bounds failed: %s", exc)
        return None


def capture_window_crop(bounds: dict, output_path: str | None = None) -> Path:
    """Capture a cropped screenshot of the window region using grim."""
    x, y, w, h = bounds["x"], bounds["y"], bounds["width"], bounds["height"]
    path = Path(output_path or "tmp/wayland_crop.png")
    path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["grim", "-g", f"{w}x{h}+{x}+{y}", str(path)],
        check=True, capture_output=True, timeout=10,
    )
    LOGGER.info("Cropped capture: (%d,%d %dx%d) → %s", x, y, w, h, path)
    return path


def translate_to_absolute(
    window_bounds: dict, dx: int, dy: int, scale: float = 1.0
) -> tuple[int, int]:
    """Convert window-relative coordinates to absolute screen coordinates.

    Formula: Target = (Window_XY + relative_XY) * Scale
    Window_XY: logical coordinates from the compositor (hyprctl)
    dx, dy: pixel coordinates relative to the cropped image (physical px)
    Scale: monitor scale factor (e.g. 1.0, 1.25, 2.0)
    """
    target_x = int((window_bounds["x"] + dx) * scale)
    target_y = int((window_bounds["y"] + dy) * scale)
    return (target_x, target_y)


def click_at_absolute(x: int, y: int) -> bool:
    """Click at absolute screen coordinates via the backend input layer."""
    try:
        from .input import click

        result = click(x=x, y=y)
        LOGGER.info("Clicked at absolute (%d, %d): ok=%s", x, y, result.ok)
        return result.ok
    except Exception as exc:
        LOGGER.exception("Click failed: %s", exc)
        return False
