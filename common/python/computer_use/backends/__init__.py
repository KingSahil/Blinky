"""Backend registry for Blinky desktop automation.

One `ComputerUseBackend` implementation is selected per platform and cached as
a process-wide singleton.

Selection order:

1. `BLINKY_COMPUTER_USE_BACKEND` env override —
   `auto` (default) | `cua` | `native` | `hyprland` | `gnome` | `kde`.
2. On Windows / macOS: `cua` (cua-driver) when the driver is reachable,
   otherwise `native` — meaning "no Python backend; fall back to the Rust
   `SendInput` path".
3. On Linux: the existing desktop-environment detection
   (Hyprland → GNOME → KDE), unchanged.

`native` is a first-class result: it signals to callers that no backend-based
actuator exists and the legacy Rust path should be used. This is what makes the
cua-driver swap opt-in and reversible — if the driver is missing or unhealthy,
Blinky behaves exactly as it did before.
"""

from __future__ import annotations

import os
import platform
import sys

from utils.logging import get_logger

from .base import ActionResult, ComputerUseBackend, Screenshot, UIElement, WindowInfo

LOGGER = get_logger("blinky.backend")

_IS_WINDOWS = platform.system() == "Windows"
_IS_LINUX = platform.system() == "Linux"

_backend: ComputerUseBackend | None = None
_backend_key: str | None = None
_resolved = False


def _requested() -> str:
    return (os.environ.get("BLINKY_COMPUTER_USE_BACKEND") or "auto").strip().lower()


def _ensure_linux_backend_path() -> None:
    """Linux backends live in the platform python dir, added by main.py.

    When the backend package is imported outside main.py's sys.path setup
    (tests, tools), make sure the Linux dir is importable.
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    for candidate in (os.path.join(root, "linux", "python"), os.path.join(root, "windows", "python")):
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)


def _cua_available() -> bool:
    try:
        from .cua_driver import CuaDriverBackend
    except Exception as exc:  # pragma: no cover - import-time guard
        LOGGER.debug("cua backend import failed: %s", exc)
        return False

    try:
        return CuaDriverBackend().is_available()
    except Exception as exc:
        LOGGER.debug("cua-driver not available: %s", exc)
        return False


def _detect_linux_key() -> str:
    try:
        from backend import _detect_de  # type: ignore[import-not-found]

        return _detect_de()
    except Exception as exc:
        LOGGER.debug("Linux DE detection unavailable: %s", exc)
        return "hyprland"


def _resolve_key() -> str:
    requested = _requested()
    if requested != "auto":
        return requested

    if _IS_WINDOWS or platform.system() == "Darwin":
        return "cua" if _cua_available() else "native"

    if _IS_LINUX:
        return _detect_linux_key()

    return "native"


def _build(key: str) -> ComputerUseBackend | None:
    if key in {"native", "none", "off"}:
        return None

    if key == "cua":
        from .cua_driver import CuaDriverBackend

        return CuaDriverBackend()

    if not _IS_LINUX:
        LOGGER.warning("Backend %r is Linux-only; falling back to native.", key)
        return None

    _ensure_linux_backend_path()
    if key == "gnome":
        from backend.gnome import GnomeBackend  # type: ignore[import-not-found]

        return GnomeBackend()
    if key == "kde":
        from backend.kde import KdeBackend  # type: ignore[import-not-found]

        return KdeBackend()

    from backend.hyprland import HyprlandBackend  # type: ignore[import-not-found]

    return HyprlandBackend()


def get_backend() -> ComputerUseBackend | None:
    """Process-wide singleton backend, or None when the native path should be used."""
    global _backend, _backend_key, _resolved
    if not _resolved:
        key = _resolve_key()
        _backend_key = key
        try:
            _backend = _build(key)
        except Exception as exc:
            LOGGER.warning("Failed to build backend %r (%s); using native path.", key, exc)
            _backend = None
            _backend_key = "native"

        if _backend is not None:
            try:
                _backend.start()
            except Exception as exc:
                LOGGER.warning("Backend %r failed to start (%s); using native path.", key, exc)
                _backend = None
                _backend_key = "native"

        LOGGER.info("Computer-use backend: %s", _backend_key)
        _resolved = True

    return _backend


def get_backend_name() -> str:
    """Active backend key — 'cua', 'native', 'hyprland', 'gnome' or 'kde'."""
    get_backend()
    return _backend_key or "native"


def has_backend() -> bool:
    """True when a Python-side actuator is active (vs the legacy Rust path)."""
    return get_backend() is not None


def reset_backend() -> None:
    """Drop the cached singleton — for tests and after config changes."""
    global _backend, _backend_key, _resolved
    if _backend is not None:
        try:
            _backend.stop()
        except Exception:
            pass
    _backend = None
    _backend_key = None
    _resolved = False


__all__ = [
    "ActionResult",
    "ComputerUseBackend",
    "Screenshot",
    "UIElement",
    "WindowInfo",
    "get_backend",
    "get_backend_name",
    "has_backend",
    "reset_backend",
]
