"""Platform-neutral actuator facade for Blinky computer use.

Exposes the same function names and dict shapes that `computer_use.linux_mcp`
(and `backend.linux_mcp_compat`) exposed, so `tools.py` and `loop.py` can call
one import on every platform instead of branching on `IS_LINUX`.

Dispatch:

  - **Linux**  → delegates to `computer_use.linux_mcp`, which drives the
                 Hyprland/GNOME/KDE backend. Behaviour is unchanged.
  - **Windows / macOS** → drives the `cua-driver` backend in the background.
  - **native fallback** → when no Python backend is available (driver missing,
                 unhealthy, or `BLINKY_COMPUTER_USE_BACKEND=native`), every
                 call returns a structured failure so callers fall back to the
                 legacy Rust `SendInput` path. This is what makes the swap
                 reversible.

Coordinate space: **true screen pixels**, the same space as Blinky's dxcam
captures and OCR boxes. Clicks go through cua-driver's `scope="desktop"` path.
"""

from __future__ import annotations

import base64
import platform
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.computer_use.actuator")

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"

# pywinauto-style media names → backend media vocabulary
_MEDIA_KEY_MAP = {
    "media_play_pause": "play",
    "media_stop": "stop",
    "media_next": "next",
    "media_prev": "prev",
    "play": "play",
    "pause": "pause",
    "next": "next",
    "prev": "prev",
}


# ── Result helpers (match the old MCP dict shape) ──────────────────


def _ok_result(action: str, message: str = "", **extra: Any) -> dict[str, Any]:
    return {"ok": True, "action": action, "message": message, **extra}


def _fail_result(action: str, message: str = "") -> dict[str, Any]:
    return {"ok": False, "action": action, "message": message}


def _check_ok(result: Any) -> bool:
    if isinstance(result, dict):
        return result.get("ok", result.get("success", True))
    return True


def _no_backend(action: str) -> dict[str, Any]:
    return _fail_result(action, "No computer-use backend active; using the native path.")


# ── Backend resolution ─────────────────────────────────────────────


def _cua_backend():
    """Return the active cua-driver backend, or None."""
    try:
        from computer_use.backends import get_backend, get_backend_name
    except Exception as exc:  # pragma: no cover - import guard
        LOGGER.debug("backend registry unavailable: %s", exc)
        return None

    if get_backend_name() != "cua":
        return None
    return get_backend()


def _linux_module():
    """Return the Linux delegate module, or None when not on Linux."""
    if not IS_LINUX:
        return None
    try:
        from computer_use import linux_mcp

        return linux_mcp
    except Exception as exc:
        LOGGER.warning("Linux actuator unavailable: %s", exc)
        return None


def _window_to_dict(w: Any) -> dict[str, Any]:
    return {
        "title": w.title,
        "app_id": w.process,
        "process": w.process,
        "pid": w.pid,
        "x": w.x,
        "y": w.y,
        "width": w.width,
        "height": w.height,
        "window_id": w.window_id,
        "bounds": {"x": w.x, "y": w.y, "width": w.width, "height": w.height},
        # False for minimized / off-screen windows: they have no rendered
        # content, so capture and element walks come back empty.
        "supported": w.supported,
        "focused": False,
        "hidden": not w.supported,
    }


def _element_to_dict(el: Any) -> dict[str, Any]:
    return {
        "text": el.text,
        "role": el.role,
        "x": el.x,
        "y": el.y,
        "width": el.width,
        "height": el.height,
        "source": el.source,
        "confidence": el.confidence,
        "automation_id": el.automation_id,
        "extra": el.extra,
    }


# ── Windows / apps ─────────────────────────────────────────────────


def list_windows() -> list[dict[str, Any]]:
    backend = _cua_backend()
    if backend is not None:
        try:
            return [_window_to_dict(w) for w in backend.list_windows()]
        except Exception as exc:
            LOGGER.warning("cua list_windows failed: %s", exc)
            return []

    linux = _linux_module()
    if linux is not None:
        return linux.list_windows()
    return []


def list_apps() -> list[dict[str, Any]]:
    backend = _cua_backend()
    if backend is not None:
        try:
            return backend.list_apps()
        except Exception as exc:
            LOGGER.warning("cua list_apps failed: %s", exc)
            return []

    linux = _linux_module()
    if linux is not None:
        return linux.list_apps()
    return []


def _resolve_target_window(app_name: str | None, backend: Any) -> Any | None:
    """Best window for an app name: substring match on process or title.

    Prefers windows that are actually actionable — a minimized window has no
    rendered content, so element walks and captures come back empty.
    """
    try:
        windows = backend.list_windows()
    except Exception:
        return None

    if app_name:
        target = " ".join(app_name.strip().lower().split())
        matches = [
            w
            for w in windows
            if target in (w.process or "").lower() or target in (w.title or "").lower()
        ]
        if matches:
            return next((w for w in matches if w.supported), matches[0])
        return None

    active = backend.get_active_window()
    if active is not None:
        return active
    return next((w for w in windows if w.supported), None)


def get_app_state(
    app_name: str | None = None,
    target_pid: int | None = None,
    include_screenshot: bool = False,
    max_nodes: int = 200,
    max_depth: int = 6,
) -> dict[str, Any]:
    """Element tree + windows for an app.

    On Windows this walks the real UIA tree via cua-driver, which is a large
    upgrade over OCR-only element discovery.
    """
    backend = _cua_backend()
    if backend is None:
        linux = _linux_module()
        if linux is not None:
            return linux.get_app_state(
                app_name=app_name,
                target_pid=target_pid,
                include_screenshot=include_screenshot,
                max_nodes=max_nodes,
                max_depth=max_depth,
            )
        return {"elements": [], "windows": [], "raw_nodes": 0}

    windows: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    degraded: dict[str, Any] | None = None
    try:
        all_windows = backend.list_windows()
        if app_name:
            target = " ".join(app_name.strip().lower().split())
            all_windows = [
                w
                for w in all_windows
                if target in (w.process or "").lower() or target in (w.title or "").lower()
            ]
        windows = [_window_to_dict(w) for w in all_windows]

        chosen = None
        if target_pid is not None:
            chosen = next((w for w in all_windows if w.pid == target_pid), None)
        if chosen is None:
            chosen = _resolve_target_window(app_name, backend)

        if chosen is not None and chosen.window_id:
            raw = backend.get_window_elements(chosen.window_id, pid=chosen.pid)
            elements = [_element_to_dict(el) for el in raw[:max_nodes]]
            degraded = getattr(backend, "last_snapshot_degraded", None)
    except Exception as exc:
        LOGGER.warning("cua get_app_state failed: %s", exc)

    result: dict[str, Any] = {
        "elements": elements,
        "windows": windows,
        "raw_nodes": len(elements),
    }
    if degraded:
        # Element data is not authoritative — the caller should fall back to the
        # OCR / visual path (minimized window or non-UIA surface).
        result["degraded"] = True
        result["degraded_reason"] = degraded.get("reason")
    return result


# ── Input ──────────────────────────────────────────────────────────


def click_element(
    index: int | None = None,
    role: str | None = None,
    name: str | None = None,
    x: int | None = None,
    y: int | None = None,
    app_id: str | None = None,
) -> dict[str, Any]:
    """Click at coordinates, by element index, or by matching a name.

    Resolution order (Windows / cua-driver):
      1. Explicit x/y → background click there.
      2. `name` → fuzzy-match the active window's UIA element tree, click the
         element center. This is more reliable than OCR because the tree
         carries roles and exact frames.
      3. `name` → window title/class match → click the window center.
      4. `index` → element at that index from the last snapshot.
    """
    backend = _cua_backend()
    if backend is None:
        linux = _linux_module()
        if linux is not None:
            return linux.click_element(index=index, role=role, name=name, x=x, y=y, app_id=app_id)
        if IS_WINDOWS:
            if x is not None and y is not None:
                try:
                    from pywinauto.mouse import click
                    click(button="left", coords=(int(x), int(y)))
                    return _ok_result("click", f"Clicked at ({x}, {y}) via native input", x=int(x), y=int(y))
                except Exception as exc:
                    return _fail_result("click", f"Native click failed: {exc}")
            if name:
                try:
                    from uia import get_visible_ui_text
                    from utils.matching import find_best_match
                    items = get_visible_ui_text(include_unlabeled=True)
                    match = find_best_match(name, items, f"Click {name}")
                    if match:
                        from computer_use.tools import click_item_center
                        click_item_center(match)
                        return _ok_result("click", f"Clicked {name}", matched_text=match.get("text", name))
                except Exception as exc:
                    LOGGER.warning("Native UIA click fallback failed: %s", exc)
        return _no_backend("click_element")

    try:
        if x is not None and y is not None:
            result = backend.click(x=int(x), y=int(y))
            if result.ok:
                return _ok_result("click", result.message, x=int(x), y=int(y))
            if IS_WINDOWS:
                try:
                    from pywinauto.mouse import click
                    click(button="left", coords=(int(x), int(y)))
                    return _ok_result("click", f"Clicked at ({x}, {y}) via native fallback", x=int(x), y=int(y))
                except Exception:
                    pass
            return _fail_result("click", result.message)

        chosen = _resolve_target_window(app_id, backend)

        # Name → UIA element match
        if name and chosen is not None and chosen.window_id:
            elements = backend.get_window_elements(chosen.window_id, pid=chosen.pid)
            if elements:
                match = _match_element(name, elements)
                if match is not None:
                    cx, cy = match.center()
                    result = backend.click(x=cx, y=cy)
                    return (
                        _ok_result(
                            "click",
                            result.message,
                            x=cx,
                            y=cy,
                            matched_text=match.text,
                            matched_role=match.role,
                            matched_by="uia",
                            window_id=chosen.window_id,
                        )
                        if result.ok
                        else _fail_result("click", result.message)
                    )

        # Index → element at that position in the last snapshot
        if index is not None and chosen is not None and chosen.window_id:
            elements = backend.get_window_elements(chosen.window_id, pid=chosen.pid)
            if 0 <= int(index) < len(elements):
                target_el = elements[int(index)]
                cx, cy = target_el.center()
                result = backend.click(x=cx, y=cy)
                return (
                    _ok_result(
                        "click",
                        result.message,
                        x=cx,
                        y=cy,
                        matched_text=target_el.text,
                        matched_by="index",
                        window_id=chosen.window_id,
                    )
                    if result.ok
                    else _fail_result("click", result.message)
                )

        # Name → window title/class match
        if name:
            target = name.strip().lower()
            for w in backend.list_windows():
                if target in (w.title or "").lower() or target in (w.process or "").lower():
                    cx = w.x + w.width // 2
                    cy = w.y + w.height // 2
                    result = backend.click(x=cx, y=cy)
                    return (
                        _ok_result(
                            "click",
                            result.message,
                            x=cx,
                            y=cy,
                            window_id=w.window_id,
                            matched_by="window",
                        )
                        if result.ok
                        else _fail_result("click", result.message)
                    )
    except Exception as exc:
        LOGGER.exception("cua click_element failed")
        return _fail_result("click", str(exc))

    return _fail_result("click", f"No element, window or on-screen text matching '{name or index}'")


def _match_element(name: str, elements: list[Any]) -> Any | None:
    """Fuzzy-match a name against UIA elements, preferring actionable ones."""
    try:
        from utils.matching import find_best_match_with_score
    except Exception:
        find_best_match_with_score = None  # type: ignore[assignment]

    # Only consider elements that carry a label — unlabeled nodes are noise.
    candidates = [el for el in elements if (el.text or "").strip()]
    if not candidates:
        return None

    if find_best_match_with_score is not None:
        items = [
            {
                "text": el.text,
                "x": el.x,
                "y": el.y,
                "width": el.width,
                "height": el.height,
                "role": el.role,
                "control_type": el.role,
                "automation_id": el.automation_id,
            }
            for el in candidates
        ]
        best = find_best_match_with_score(name, items, f"Click {name}")
        if best:
            text = str(best.get("text") or "")
            for el in candidates:
                if el.text == text:
                    return el

    # Plain case-insensitive fallback
    lowered = name.strip().lower()
    for el in candidates:
        if el.text.strip().lower() == lowered:
            return el
    for el in candidates:
        if lowered in el.text.strip().lower():
            return el
    return None


def type_text(text: str, target_app: str | None = None) -> dict[str, Any]:
    backend = _cua_backend()
    if backend is None:
        linux = _linux_module()
        if linux is not None:
            return linux.type_text(text, target_app=target_app)
        return _no_backend("type_text")

    try:
        result = backend.type_text(text)
        return (
            _ok_result("type_text", result.message, text=text, target_app=target_app)
            if result.ok
            else _fail_result("type_text", result.message)
        )
    except Exception as exc:
        LOGGER.exception("cua type_text failed")
        return _fail_result("type_text", str(exc))


def press_key(key: str, target_app: str | None = None) -> dict[str, Any]:
    backend = _cua_backend()
    if backend is None:
        linux = _linux_module()
        if linux is not None:
            return linux.press_key(key, target_app=target_app)
        return _no_backend("press_key")

    backend_key = _MEDIA_KEY_MAP.get(key, key)
    try:
        result = backend.key(backend_key)
        return (
            _ok_result("press_key", result.message, key=key)
            if result.ok
            else _fail_result("press_key", result.message)
        )
    except Exception as exc:
        LOGGER.exception("cua press_key failed")
        return _fail_result("press_key", str(exc))


# ── Screen ─────────────────────────────────────────────────────────


def screenshot() -> dict[str, Any]:
    """Screenshot as base64 PNG (the old MCP content shape)."""
    backend = _cua_backend()
    if backend is None:
        linux = _linux_module()
        if linux is not None:
            return linux.screenshot()
        return _no_backend("screenshot")

    try:
        shot = backend.capture()
        data = base64.b64encode(shot.path.read_bytes()).decode("ascii")
        return {
            "ok": True,
            "action": "screenshot",
            "content": [{"type": "image", "data": data}],
            "width": shot.width,
            "height": shot.height,
            "path": str(shot.path),
        }
    except Exception as exc:
        LOGGER.warning("cua screenshot failed: %s", exc)
        return _fail_result("screenshot", str(exc))


def get_focused_window_bounds() -> dict[str, Any] | None:
    backend = _cua_backend()
    if backend is None:
        linux = _linux_module()
        if linux is not None:
            return linux.get_focused_window_bounds()
        return None

    try:
        win = backend.get_active_window()
    except Exception as exc:
        LOGGER.debug("cua get_active_window failed: %s", exc)
        return None

    if win is None:
        return None
    return {
        "x": win.x,
        "y": win.y,
        "width": win.width,
        "height": win.height,
        "title": win.title,
        "app_id": win.process,
        "pid": win.pid,
        "window_id": win.window_id,
    }


def doctor() -> dict[str, Any]:
    backend = _cua_backend()
    if backend is None:
        linux = _linux_module()
        if linux is not None:
            return linux.doctor()
        return {
            "ok": False,
            "action": "doctor",
            "message": "No computer-use backend active.",
            "checks": [],
        }

    report = backend.doctor()
    return {
        "ok": bool(report.get("available")),
        "action": "doctor",
        "message": f"Backend: cua-driver ({report.get('version') or 'unknown version'})",
        "checks": report.get("checks") or [],
        "binary": report.get("binary"),
        "error": report.get("error"),
    }


def get_client():
    """Compatibility no-op — kept so legacy callers don't break."""

    class _NoopClient:
        def call_tool(self, name, arguments=None):
            return _fail_result(name, "MCP bridge removed; use the actuator directly")

        @property
        def tools(self):
            return []

        def stop(self):
            pass

    return _NoopClient()


def backend_name() -> str:
    """Active backend key — 'cua', 'hyprland', 'gnome', 'kde' or 'native'."""
    try:
        from computer_use.backends import get_backend_name

        return get_backend_name()
    except Exception:
        return "native"


__all__ = [
    "backend_name",
    "click_element",
    "doctor",
    "get_app_state",
    "get_client",
    "get_focused_window_bounds",
    "list_apps",
    "list_windows",
    "press_key",
    "screenshot",
    "type_text",
]
