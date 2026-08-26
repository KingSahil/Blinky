"""Deprecated MCP client — replaced by the compositor backend.

Phase 5: all functions now delegate to `backend.linux_mcp_compat` (which
implements the same signatures over HyprlandBackend: hyprctl + grim +
ydotool + wtype). This module is kept as a re-export shim so callers
(tools.py, loop.py) need zero changes. Deleted entirely in phase 7.
"""

from __future__ import annotations

from typing import Any

from backend.linux_mcp_compat import (  # type: ignore[import-not-found]
    _check_ok,
    click_element,
    doctor,
    get_app_state,
    get_client,
    get_focused_window_bounds,
    list_apps,
    list_windows,
    press_key,
    screenshot,
    type_text,
)

__all__ = [
    "list_windows",
    "list_apps",
    "get_app_state",
    "click_element",
    "type_text",
    "press_key",
    "screenshot",
    "get_focused_window_bounds",
    "doctor",
    "get_client",
    "_check_ok",
]
