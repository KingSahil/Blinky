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

import json
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
    """Lazy-import pyatspi; returns the module or None.

    Falls back to a python3.14 helper subprocess when pyatspi isn't compiled
    for the current interpreter (Arch's python-atspi ships cpython-314
    bindings; the Blinky venv is 3.12). The helper is used by the query
    functions below.
    """
    global _ATSPI
    if _ATSPI is not None:
        return _ATSPI
    try:
        import pyatspi  # type: ignore

        _ATSPI = pyatspi
    except Exception as exc:  # ImportError or D-Bus failure
        LOGGER.debug("pyatspi unavailable in-process: %s", exc)
        _ATSPI = False
    return _ATSPI or None


def _helper_interpreter() -> str | None:
    """Find a python that can import pyatspi (Arch python-atspi is 3.14)."""
    for candidate in ("python3.14", "python3"):
        import shutil

        if shutil.which(candidate):
            try:
                import subprocess

                r = subprocess.run(
                    [candidate, "-c", "import pyatspi"],
                    capture_output=True, timeout=5,
                )
                if r.returncode == 0:
                    return candidate
            except Exception:
                continue
    return None


def _run_helper() -> str | None:
    """Path to the AT-SPI helper interpreter, cached."""
    global _HELPER
    if _HELPER is not None:
        return _HELPER or None
    _HELPER = _helper_interpreter() or ""
    return _HELPER or None


_HELPER: str | None = None

_HELPER_CODE = r"""
import json, sys
import pyatspi

def extents(node):
    # Return (x,y,w,h) bounding box, tolerating camelCase/snake_case API.
    try:
        e = node.get_extents(pyatspi.DESKTOP_COORDS)
    except AttributeError:
        try:
            e = node.getExtents(pyatspi.DESKTOP_COORDS)
        except Exception:
            return None
    x, y, w, h = e.x, e.y, e.width, e.height
    if w <= 0 or h <= 0:
        return None
    return int(x), int(y), int(w), int(h)

def walk(node, depth=0):
    if depth > 4:
        return
    try:
        name = node.name or ""
        role = str(node.getRole())
        bounds = extents(node)
        if bounds:
            items.append({
                "text": name, "role": role,
                "x": bounds[0], "y": bounds[1],
                "width": bounds[2], "height": bounds[3],
            })
        for i in range(min(node.childCount, 40)):
            try:
                walk(node[i], depth+1)
            except Exception:
                pass
    except Exception:
        pass

mode = sys.argv[1]
items = []
try:
    if mode == "windows" or mode == "active":
        desktop = pyatspi.Registry.getDesktop(0)
        for i in range(desktop.childCount):
            try:
                app = desktop[i]
                name = app.name or ""
                if not name:
                    continue
                xs, ys, ws, hs = [], [], [], []
                for j in range(min(app.childCount, 80)):
                    try:
                        b = extents(app[j])
                        if b:
                            xs.append(b[0]); ys.append(b[1]); ws.append(b[2]); hs.append(b[3])
                    except Exception:
                        pass
                if not ws:
                    # fall back to the app's own extent
                    b = extents(app)
                    if b:
                        xs, ys, ws, hs = [b[0]], [b[1]], [b[2]], [b[3]]
                    else:
                        continue
                items.append({
                    "title": name, "process": name,
                    "x": min(xs), "y": min(ys),
                    "width": max(x+e for x,e in zip(xs,ws)) - min(xs),
                    "height": max(y+e for y,e in zip(ys,hs)) - min(ys),
                })
            except Exception:
                pass
    elif mode == "elements":
        from pyatspi import Registry
        desktop = Registry.getDesktop(0)
        for i in range(desktop.childCount):
            walk(desktop[i], 0)
except Exception:
    pass

print(json.dumps(items[:400]))
"""


def _helper_call(mode: str) -> list[dict]:
    """Run the AT-SPI helper subprocess and return parsed JSON items."""
    interp = _run_helper()
    if not interp:
        return []
    try:
        import subprocess

        result = subprocess.run(
            [interp, "-c", _HELPER_CODE, mode],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            LOGGER.debug("AT-SPI helper failed: %s", result.stderr.strip()[:200])
            return []
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else []
    except Exception as exc:
        LOGGER.debug("AT-SPI helper error: %s", exc)
        return []


def is_available() -> bool:
    mod = _atspi()
    if mod:
        try:
            desktop = mod.Registry.getDesktop(0)
            return desktop is not None and desktop.childCount > 0
        except Exception as exc:
            LOGGER.debug("AT-SPI registry check failed: %s", exc)
    # In-process pyatspi unavailable → check via the python3.14 helper
    return bool(_run_helper())


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
    only nodes belonging to that app are returned. Falls back to the
    python3.14 helper when in-process pyatspi is unavailable.
    """
    mod = _atspi()
    if not mod or not is_available():
        if is_available() and _run_helper():
            return _elements_from_helper(pid)
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
                    continue
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
        if is_available() and _run_helper():
            windows = _windows_from_helper(mode="active")
            if windows:
                return windows[0]
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
        if is_available() and _run_helper():
            return _windows_from_helper(mode="windows")
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


def _windows_from_helper(mode: str) -> list[WindowInfo]:
    """Build WindowInfo list from the python3.14 AT-SPI helper output."""
    raw = _helper_call(mode)
    windows: list[WindowInfo] = []
    for r in raw:
        title = str(r.get("title") or r.get("process") or "")
        if not title:
            continue
        windows.append(
            WindowInfo(
                title=title,
                process=str(r.get("process") or title),
                supported=True,
                x=int(r.get("x") or 0),
                y=int(r.get("y") or 0),
                width=int(r.get("width") or 0),
                height=int(r.get("height") or 0),
                pid=r.get("pid"),
                window_id=f"atspi:{title}",
            )
        )
    return windows


def _elements_from_helper(pid: int | None = None) -> list[UIElement]:
    """Build UIElement list from the python3.14 AT-SPI helper output."""
    raw = _helper_call("elements")
    elements: list[UIElement] = []
    for r in raw:
        if pid is not None and r.get("pid") not in (pid, None):
            continue
        text = str(r.get("text") or "")
        role = str(r.get("role") or "")
        if not text and role in ("image", "separator", "unknown", "75"):
            continue
        elements.append(
            UIElement(
                text=text,
                x=int(r.get("x") or 0),
                y=int(r.get("y") or 0),
                width=int(r.get("width") or 0),
                height=int(r.get("height") or 0),
                source="atspi",
                role=role,
                confidence=1.0,
            )
        )
    return elements
