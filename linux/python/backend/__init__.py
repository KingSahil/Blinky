"""Backend package for Blinky Linux desktop automation.

Registers three implementations of the same ComputerUseBackend ABC:
  - HyprlandBackend  (Hyprland / wlroots — primary, Hyprland-first)
  - GnomeBackend     (GNOME Shell / Mutter — phase 8)
  - KdeBackend       (KDE Plasma / KWin — phase 8)

`get_backend()` auto-detects the running desktop environment (via
backend.system) and returns the matching singleton, defaulting to Hyprland.
Compositor-agnostic modules (input, capture, apps, atspi) are shared.
"""

from __future__ import annotations

import os

from utils.logging import get_logger

from .abc import ActionResult, ComputerUseBackend, Screenshot, UIElement, WindowInfo
from .hyprland import HyprlandBackend

LOGGER = get_logger("blinky.backend")


def _detect_de() -> str:
    """Return the long-form backend key: 'hyprland' | 'gnome' | 'kde' | 'generic'."""
    profile = None
    try:
        from .system import get_system_profile_cached

        profile = get_system_profile_cached()
    except Exception as exc:
        LOGGER.debug("system profile unavailable: %s", exc)

    if profile is not None:
        compositor = (profile.compositor or "").lower()
        de = (profile.de or "").lower()
        if "hypr" in compositor or "hypr" in de:
            return "hyprland"
        if "gnome" in de or "ubuntu" in de or "mutter" in compositor:
            return "gnome"
        if "kde" in de or "plasma" in de or "kwin" in compositor:
            return "kde"

    # Env fallbacks (portal/system may fail before XDG vars are set)
    de_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if "hypr" in de_env:
        return "hyprland"
    if "gnome" in de_env or "ubuntu" in de_env:
        return "gnome"
    if "kde" in de_env or "plasma" in de_env:
        return "kde"
    if session == "wayland":
        return "hyprland"  # default wlroots-family backend
    return "hyprland"


_backend: ComputerUseBackend | None = None


def get_backend() -> ComputerUseBackend:
    """Process-wide singleton backend, auto-selected by the running DE."""
    global _backend
    if _backend is None:
        key = _detect_de()
        if key == "gnome":
            from .gnome import GnomeBackend

            backend: ComputerUseBackend = GnomeBackend()
        elif key == "kde":
            from .kde import KdeBackend

            backend = KdeBackend()
        else:
            backend = HyprlandBackend()
        LOGGER.info("Selected backend: %s", type(backend).__name__)
        backend.start()
        _backend = backend
    return _backend


def get_backend_name() -> str:
    return type(get_backend()).__name__


__all__ = [
    "ActionResult",
    "ComputerUseBackend",
    "GnomeBackend",
    "HyprlandBackend",
    "KdeBackend",
    "Screenshot",
    "UIElement",
    "WindowInfo",
    "get_backend",
    "get_backend_name",
]
