"""AT-SPI accessibility tree bridge — DE-agnostic element source.

GNOME and KDE both expose their a11y trees via AT-SPI (D-Bus). This module
provides:
  - get_elements(pid=None)   → flatten the desktop tree into UIElement boxes
  - get_active_window()      → focused app WindowInfo (name + pid + bounds)
  - list_windows()           → all top-level app windows with bounds
  - is_available()           → pyatspi import + registry presence check

Designed to degrade gracefully: if pyatspi isn't installed, or the AT-SPI
registry is empty (Hyprland without a11y), every function returns []/None —
callers already fall back to OCR / hyprctl / portal paths.

NOTE: pyatspi is the Python binding from the `python-atspi` package (Arch).
Coordinates from AT-SPI are in logical pixels relative to the a11y client's
origin; we report them as-is and let the caller scale (same contract as the
hyprctl path).
"""

from __future__ import annotations

from typing import Any

from utils.logging import get_logger

from .abc import UIElement, WindowInfo

LOGGER = get_logger("blinky.backend.atspi")

# kwin/GNOME a11y often reports the full workspace as one giant role; cap the
# element walk to keep flattening cheap.
_MAX_ELEMENTS = 500
_MAX_DEPTH = 6

_ATSPI = None  # cached module (lazy import — pyatspi may be absent)


def _atspi():
    """Lazy-import pyatspi; returns the module or None."""
    global _ATSPI
    if _ATSPI is not None:
        return _ATSPI
    try:
        import pyatspi  # type: ignore

        _ATSPI = pyatspi
    except Exception as exc:  # ImportError or D-Bus failure
        LOGGER.debug("pyatspi unavailable: %s", exc)
        _ATSPI = False
    return _ATSPI or None


def is_available() -> bool:
    mod = _atspi()
    if not mod:
        return False
    try:
        desktop = mod.Registry.getDesktop(0)
        return desktop is not None and desktop.childCount > 0
    except Exception as exc:
        LOGGER.debug("AT-SPI registry check failed: %s", exc)
        return False


def _role_name(role) -> str:
    try:
        from pyatspi import ROLE_MAP

        return ROLE_MAP.get(role, str(role))
    except Exception:
        return str(role)


def _iter_children(node, depth: int = 0):
    """Yield node and descendants, bounded by depth/element caps."""
    if depth > _MAX_DEPTH:
        return
    try:
        yield node
        count = node.childCount
    except Exception:
        return
    for i in range(min(count, 50)):
        try:
            child = node[i]
        except Exception:
            continue
        yield from _iter_children(child, depth + 1)


def _node_bounds(node) -> tuple[int, int, int, int] | None:
    try:
        mod = _atspi()
        if not mod:
            return None
        extents = node.getExtents(mod.DESKTOP_COORDS)
        x, y, w, h = extents.x, extents.y, extents.width, extents.height
        if w <= 0 or h <= 0:
            return None
        return int(x), int(y), int(w), int(h)
    except Exception:
        return None


def _node_text(node) -> str:
    try:
        name = node.name or ""
    except Exception:
        name = ""
    if name:
        return name
    try:
        if node.getRole().startswith("text") or hasattr(node, "text"):
            ti = node.queryText()
            return ti.getText(0, ti.characterCount) or ""
    except Exception:
        pass
    return ""


def get_elements(pid: int | None = None) -> list[UIElement]:
    """Flatten the AT-SPI desktop tree into UIElement boxes.

    Filters to nodes with a bounding box + visible text. If pid is given,
    only nodes belonging to that app are returned.
    """
    mod = _atspi()
    if not mod or not is_available():
        return []

    from pyatspi import DESKTOP_COORDS  # type: ignore

    elements: list[UIElement] = []
    try:
        desktop = mod.Registry.getDesktop(0)
        for app in _iter_children(desktop):
            if pid is not None:
                try:
                    if app.pid != pid:
                        continue
                except Exception:
                    pass
            for node in _iter_children(app, depth=1):
                bounds = _node_bounds(node)
                if not bounds:
                    continue
                text = _node_text(node)
                role = _role_name(node.getRole())
                if not text and role in ("image", "separator", "unknown"):
                    continue
                x, y, w, h = bounds
                elements.append(
                    UIElement(
                        text=text,
                        x=x,
                        y=y,
                        width=w,
                        height=h,
                        source="atspi",
                        role=role,
                        confidence=1.0,
                    )
                )
                if len(elements) >= _MAX_ELEMENTS:
                    return elements
    except Exception as exc:
        LOGGER.debug("AT-SPI element walk failed: %s", exc)
        return []
    return elements


def get_active_window() -> WindowInfo | None:
    """Active app via AT-SPI (focused application). Computes aggregate bounds."""
    mod = _atspi()
    if not mod or not is_available():
        return None
    try:
        desktop = mod.Registry.getDesktop(0)
        focused_app = desktop.state.focused  # may not be reliable
        for app in _iter_children(desktop):
            try:
                if app.pid <= 0:
                    continue
            except Exception:
                continue
            # First top-level with the focused state, else first with a name
            if focused_app is not None and app.name != focused_app.name:
                continue
            try:
                name = app.name or ""
            except Exception:
                name = ""
            if not name:
                continue
            xs, ys, ws, hs = [], [], [], []
            for node in _iter_children(app, depth=1):
                b = _node_bounds(node)
                if b:
                    xs.append(b[0]); ys.append(b[1])
                    ws.append(b[2]); hs.append(b[3])
            if not ws:
                continue
            min_x, min_y = min(xs), min(ys)
            max_x = max(x + w for x, w in zip(xs, ws))
            max_y = max(y + h for y, h in zip(ys, hs))
            return WindowInfo(
                title=name,
                process=name,
                supported=True,
                x=min_x, y=min_y,
                width=max_x - min_x, height=max_y - min_y,
                pid=app.pid,
                window_id=f"atspi:{app.name}",
            )
    except Exception as exc:
        LOGGER.debug("AT-SPI active window failed: %s", exc)
        return None
    return None


def list_windows() -> list[WindowInfo]:
    """All top-level app windows via AT-SPI."""
    mod = _atspi()
    if not mod or not is_available():
        return []
    windows: list[WindowInfo] = []
    try:
        desktop = mod.Registry.getDesktop(0)
        for app in _iter_children(desktop):
            try:
                if app.pid <= 0:
                    continue
                name = app.name or ""
            except Exception:
                continue
            if not name:
                continue
            xs, ys, ws, hs = [], [], [], []
            for node in _iter_children(app, depth=1):
                b = _node_bounds(node)
                if b:
                    xs.append(b[0]); ys.append(b[1])
                    ws.append(b[2]); hs.append(b[3])
            if not ws:
                continue
            min_x, min_y = min(xs), min(ys)
            max_x = max(x + w for x, w in zip(xs, ws))
            max_y = max(y + h for y, h in zip(ys, hs))
            windows.append(
                WindowInfo(
                    title=name,
                    process=name,
                    supported=True,
                    x=min_x, y=min_y,
                    width=max_x - min_x, height=max_y - min_y,
                    pid=app.pid,
                    window_id=f"atspi:{app.name}",
                )
            )
    except Exception as exc:
        LOGGER.debug("AT-SPI window list failed: %s", exc)
        return []
    return windows
