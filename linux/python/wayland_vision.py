"""Deprecated wayland_vision shim — replaced by backend.vision.

Phase 7: re-exports the same functions over Hyprland-native implementations
(hyprctl scale, grim crop, backend input). Deleted entirely with the final
cleanup once tools.py imports are re-pointed.
"""

from __future__ import annotations

from backend.vision import (  # type: ignore[import-not-found]
    capture_window_crop,
    click_at_absolute,
    get_active_window_bounds,
    get_screen_scale,
    translate_to_absolute,
)

__all__ = [
    "capture_window_crop",
    "click_at_absolute",
    "get_active_window_bounds",
    "get_screen_scale",
    "translate_to_absolute",
]
