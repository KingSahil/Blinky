"""
Wayland-native vision pipeline for Blinky on KDE Plasma.

Flow:
  1. KWin → active window bounds + scale factor
  2. grim → crop-capture window only (no portal prompts)
  3. LLM vision → finds target at (dx, dy) relative to crop
  4. Translate → absolute = window_xy + scaled(dx, dy)
  5. ydotool → click at absolute coordinates
"""

from __future__ import annotations

import os
import subprocess
import json
import time
from pathlib import Path
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.wayland_vision")


def get_screen_scale() -> float:
    """Get the display scale factor from kscreen-doctor."""
    try:
        result = subprocess.run(
            ["kscreen-doctor", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        data = json.loads(result.stdout)
        for output in data.get("outputs", []):
            if output.get("enabled"):
                return float(output.get("scale", 1.0))
    except Exception:
        pass
    return 1.0


def get_active_window_bounds() -> dict | None:
    """Get the active window bounds from KWin via MCP focused_window."""
    try:
        from computer_use.linux_mcp import get_client
        client = get_client()
        result = client.call_tool("focused_window", {})
        LOGGER.info("focused_window raw result: %s", result)
        window = result.get("focused_window", result) if isinstance(result, dict) else {}
        LOGGER.info("focused_window parsed window: %s", window)
        bounds = window.get("bounds", {})
        LOGGER.info("focused_window parsed bounds: %s", bounds)
        if bounds and bounds.get("width", 0) > 0:
            return {
                "x": bounds.get("x", 0),
                "y": bounds.get("y", 0),
                "width": bounds.get("width", 0),
                "height": bounds.get("height", 0),
                "title": window.get("title", ""),
                "app_id": window.get("app_id", ""),
            }
        else:
            LOGGER.warning("focused_window: no valid bounds (width=0 or missing)")
    except Exception as e:
        LOGGER.debug("get_active_window_bounds: %s", e)
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


def ask_vision_for_coordinates(image_path: Path, question: str) -> tuple[int, int] | None:
    """Ask the vision LLM to find a target element's pixel coordinates in the image.
    Returns (dx, dy) relative to the image's top-left corner, or None."""
    from ai.client import ask_model

    prompt = f"""Look at this screenshot of an application window. The user wants to: {question}

Find EXACTLY the target element and return the pixel coordinates of its CENTER,
relative to the image's top-left corner. The coordinates must be integers.

Return valid JSON only:
{{"found": true, "element": "name of element", "x": 150, "y": 200}}
If you cannot find it: {{"found": false, "reason": "why"}}"""

    try:
        response = ask_model(prompt, image_path)
        if not response.get("found"):
            LOGGER.info("Vision model could not find target: %s", response.get("reason", ""))
            return None
        dx = int(response.get("x", 0))
        dy = int(response.get("y", 0))
        LOGGER.info("Vision model found '%s' at (%d, %d)", response.get("element", "?"), dx, dy)
        return (dx, dy)
    except Exception as e:
        LOGGER.exception("Vision coordinate extraction failed")
        return None


def translate_to_absolute(
    window_bounds: dict, dx: int, dy: int, scale: float = 1.0
) -> tuple[int, int]:
    """Convert window-relative coordinates to absolute physical screen coordinates.

    Formula: Target = (Window_XY + relative_XY) * Scale

    Window_XY: logical coordinates from KWin compositor
    dx, dy: pixel coordinates relative to the cropped image (physical pixels)
    Scale: monitor scale factor from kscreen-doctor (e.g. 1.0, 1.25, 2.0)
    """
    target_x = int((window_bounds["x"] + dx) * scale)
    target_y = int((window_bounds["y"] + dy) * scale)
    return (target_x, target_y)


def click_at_absolute(x: int, y: int) -> bool:
    """Click at absolute screen coordinates via ydotool."""
    try:
        subprocess.run(
            ["ydotool", "click", str(x), str(y)],
            capture_output=True, timeout=5,
        )
        LOGGER.info("Clicked at absolute (%d, %d)", x, y)
        return True
    except Exception as e:
        LOGGER.exception("Click failed")
        return False


def run_wayland_vision_pipeline(
    question: str,
    click: bool = True,
) -> dict[str, Any]:
    """Full vision pipeline: capture window → find target → click.

    Returns a dict with:
      - success: bool
      - window_bounds: dict or None
      - image_path: str or None
      - target_coords: (dx, dy) or None
      - absolute_coords: (abs_x, abs_y) or None
      - clicked: bool
      - error: str or None
    """
    scale = get_screen_scale()

    # Step 1: Get active window bounds
    bounds = get_active_window_bounds()
    if not bounds:
        return {"success": False, "error": "Could not get active window bounds"}

    # Step 2: Crop-capture
    try:
        image_path = capture_window_crop(bounds)
    except Exception as e:
        return {"success": False, "error": f"Crop capture failed: {e}", "window_bounds": bounds}

    # Step 3: LLM vision
    coords = ask_vision_for_coordinates(image_path, question)
    if not coords:
        return {
            "success": False,
            "error": "Vision model could not find the target",
            "window_bounds": bounds,
            "image_path": str(image_path),
        }

    dx, dy = coords
    abs_x, abs_y = translate_to_absolute(bounds, dx, dy, scale)

    result = {
        "success": True,
        "window_bounds": bounds,
        "image_path": str(image_path),
        "target_coords": (dx, dy),
        "absolute_coords": (abs_x, abs_y),
        "scale": scale,
    }

    # Step 5: Click
    if click:
        result["clicked"] = click_at_absolute(abs_x, abs_y)

    return result
