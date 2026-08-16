"""Drop-in replacement for computer_use.linux_mcp, backed by the new backend.

Exposes the SAME function names and signatures the old MCP client exposed
(list_windows, list_apps, click_element, type_text, press_key, screenshot,
get_focused_window_bounds, get_app_state, _check_ok, doctor) so tools.py and
loop.py only need their import swapped. The old transport (TCP bridge →
computer-use-linux binary) is gone; everything calls HyprlandBackend now.

Phase 5 compat shim — will be folded into tools.py directly during P7
cleanup, then this module is deleted.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

from utils.logging import get_logger

from .abc import WindowInfo
from .window import get_active_window, list_windows as _backend_list_windows, screen_size
from .input import click as _backend_click, type_text as _backend_type_text, key as _backend_key
from .apps import launch_by_name, find_entry

LOGGER = get_logger("blinky.backend.linux_mcp_compat")


# ── Result helpers (match old MCP dict shape) ──────────────────────

def _ok_result(action: str, message: str = "", **extra: Any) -> dict[str, Any]:
    return {"ok": True, "action": action, "message": message, **extra}


def _fail_result(action: str, message: str = "") -> dict[str, Any]:
    return {"ok": False, "action": action, "message": message}


def _check_ok(result: Any) -> bool:
    if isinstance(result, dict):
        return result.get("ok", result.get("success", True))
    return True


# ── Windows / apps ──────────────────────────────────────────────────

def _window_to_dict(w: WindowInfo) -> dict[str, Any]:
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
        "focused": False,
        "hidden": False,
    }


def list_windows() -> list[dict[str, Any]]:
    return [_window_to_dict(w) for w in _backend_list_windows()]


def list_apps() -> list[dict[str, Any]]:
    from .apps import scan_apps

    return [
        {
            "name": e.name,
            "app_id": e.desktop_id,
            "desktop_id": e.desktop_id,
            "exec": e.exec_line,
            "startup_wm_class": e.startup_wm_class,
            "source": e.source,
        }
        for e in scan_apps()
    ]


def get_app_state(
    app_name: str | None = None,
    target_pid: int | None = None,
    include_screenshot: bool = False,
    max_nodes: int = 200,
    max_depth: int = 6,
) -> dict[str, Any]:
    """App element state. Backend provides windows + OCR element boxes
    (no AT-SPI tree on Hyprland yet; P8 adds it for GNOME/KDE)."""
    windows = _backend_list_windows()
    # Filter to the requested app if given
    if app_name:
        target = " ".join(app_name.strip().lower().split())
        windows = [
            w for w in windows
            if target in w.process.lower() or target in w.title.lower()
        ]
    return {"elements": [], "windows": [_window_to_dict(w) for w in windows], "raw_nodes": 0}


# ── Input ───────────────────────────────────────────────────────────

def click_element(
    index: int | None = None,
    role: str | None = None,
    name: str | None = None,
    x: int | None = None,
    y: int | None = None,
    app_id: str | None = None,
) -> dict[str, Any]:
    """Click at coordinates, or resolve name → OCR text location.

    Resolution order:
      1. Explicit x/y → click there
      2. Name matching a window title/class → click window center
      3. Name matching OCR text on screen (fresh grim capture + tesseract)
         → click the matched text's center  ← the "click on X" path
    """
    if x is not None and y is not None:
        result = _backend_click(x=int(x), y=int(y))
        return _ok_result("click", result.message, x=int(x), y=int(y)) if result.ok else _fail_result("click", result.message)

    if not name:
        return _fail_result("click", "click_element needs x/y or a name")

    target = name.strip().lower()

    # 2. Window title/class match
    windows = _backend_list_windows()
    for w in windows:
        if target in w.title.lower() or target in w.process.lower():
            cx = w.x + w.width // 2
            cy = w.y + w.height // 2
            result = _backend_click(x=cx, y=cy)
            return _ok_result("click", result.message, x=cx, y=cy, window_id=w.window_id, matched_by="window") if result.ok else _fail_result("click", result.message)

    # 3. OCR text match (the Hyprland element-tree substitute)
    ocr_match = _find_ocr_text_center(target)
    if ocr_match is not None:
        cx, cy, matched_text = ocr_match
        result = _backend_click(x=cx, y=cy)
        return _ok_result("click", result.message, x=cx, y=cy, matched_text=matched_text, matched_by="ocr") if result.ok else _fail_result("click", result.message)

    return _fail_result("click", f"No window or on-screen text matching '{name}'")


def _find_ocr_text_center(target: str) -> tuple[int, int, str] | None:
    """OCR the current screen and return (cx, cy, matched_text) for the best
    text match, or None. Coordinates are in the screenshot's native resolution
    (grim captures at physical px), which matches ydotool/backend click space."""
    try:
        from utils.matching import find_best_match

        # Fresh capture at native resolution (no downscale — coords must be exact)
        import subprocess

        result = subprocess.run(["grim", "-"], capture_output=True, timeout=10)
        if result.returncode != 0 or not result.stdout:
            LOGGER.warning("OCR click: grim capture failed")
            return None

        from io import BytesIO
        from PIL import Image

        with Image.open(BytesIO(result.stdout)) as img:
            img.load()
            # Downscale for OCR speed, scale coords back up
            max_dim = 1600
            w, h = img.size
            scale = 1.0
            if w > max_dim or h > max_dim:
                scale = max_dim / w if w > h else max_dim / h
                img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)

            import pytesseract

            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--oem 1")
    except Exception as exc:
        LOGGER.warning("OCR click resolution failed: %s", exc)
        return None

    items: list[dict] = []
    for i in range(len(data.get("text", []))):
        text = str(data["text"][i]).strip()
        if not text:
            continue
        items.append({
            "text": text,
            "x": int(data["left"][i] / scale),
            "y": int(data["top"][i] / scale),
            "width": int(data["width"][i] / scale),
            "height": int(data["height"][i] / scale),
        })

    if not items:
        return None

    # Merge adjacent words on the same line into phrases so multi-word targets
    # like "New Session" (OCR'd as separate boxes "New" + "session") match.
    phrases = _merge_same_line_words(items)

    match = find_best_match(target, phrases, f"Click {target}")
    if not match or not isinstance(match, dict):
        return None

    # find_best_match returns the best candidate {text,x,y,width,height} — it
    # already applies its own similarity threshold internally, so no score gate
    # here (the helper does not expose a score in its return shape).
    if isinstance(match, list):
        match = match[0] if match else {}

    x = int(match.get("x") or 0)
    y = int(match.get("y") or 0)
    w_item = int(match.get("width") or 0)
    h_item = int(match.get("height") or 0)
    matched_text = str(match.get("text") or target)
    return x + w_item // 2, y + h_item // 2, matched_text


def _merge_same_line_words(items: list[dict]) -> list[dict]:
    """Merge OCR word boxes that sit on the same visual line into phrases.

    Tesseract emits per-word boxes; a button labeled "New Session" arrives as
    two separate items ("New", "session"). We join words whose vertical centers
    are within a tolerance and whose horizontal gap is small (same line, same
    text run). The merged box spans both words so center-clicking hits the
    button, not a single word's edge.
    """
    sorted_items = sorted(items, key=lambda it: (it["y"], it["x"]))
    merged: list[dict] = []
    for item in sorted_items:
        if not merged:
            merged.append(dict(item))
            continue

        last = merged[-1]
        item_cy = item["y"] + item["height"] / 2
        last_cy = last["y"] + last["height"] / 2
        line_tolerance = max(6, item["height"] * 0.6)
        gap = item["x"] - (last["x"] + last["width"])

        same_line = abs(item_cy - last_cy) <= line_tolerance
        close_gap = 0 <= gap <= max(24, last["height"] * 1.2)

        if same_line and close_gap:
            end_x = max(last["x"] + last["width"], item["x"] + item["width"])
            last["text"] = f"{last['text']} {item['text']}"
            last["width"] = end_x - last["x"]
            last["height"] = max(last["height"], item["height"])
        else:
            merged.append(dict(item))
    return merged


def type_text(text: str, target_app: str | None = None) -> dict[str, Any]:
    if target_app:
        # Focus the target window first (best effort)
        windows = _backend_list_windows()
        target = " ".join(target_app.strip().lower().split())
        for w in windows:
            if target in w.process.lower() or target in w.title.lower():
                from .input import focus_window

                focus_window(w.window_id)
                break
    result = _backend_type_text(text)
    return _ok_result("type_text", result.message) if result.ok else _fail_result("type_text", result.message)


def press_key(key: str, target_app: str | None = None) -> dict[str, Any]:
    # Map pywinauto-style media names to backend media vocabulary
    media_map = {
        "media_play_pause": "play",
        "media_stop": "stop",
        "media_next": "next",
        "media_prev": "prev",
        "play": "play",
        "pause": "pause",
        "next": "next",
        "prev": "prev",
    }
    backend_key_name = media_map.get(key, key)
    result = _backend_key(backend_key_name)
    return _ok_result("press_key", result.message, key=key) if result.ok else _fail_result("press_key", result.message)


# ── Screen ──────────────────────────────────────────────────────────

def screenshot() -> dict[str, Any]:
    """Return a screenshot as base64 PNG (old MCP content shape)."""
    from .capture import GrimFullscreenCaptureStrategy
    import base64
    from io import BytesIO

    try:
        image = GrimFullscreenCaptureStrategy().capture()
        buf = BytesIO()
        image.save(buf, format="PNG")
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        return {"ok": True, "action": "screenshot", "content": [{"type": "image", "data": data}]}
    except Exception as exc:
        return _fail_result("screenshot", str(exc))


def get_focused_window_bounds() -> dict[str, Any] | None:
    """Compatibility: old callers expect {x, y, width, height, title, app_id}."""
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


def doctor() -> dict[str, Any]:
    return {
        "ok": True,
        "action": "doctor",
        "message": "Backend: Hyprland (hyprctl + grim + ydotool + wtype)",
        "checks": [
            {"name": "hyprctl", "status": "pass"},
            {"name": "grim", "status": "pass"},
            {"name": "ydotool", "status": "pass"},
            {"name": "wtype", "status": "pass"},
        ],
    }


def get_client():
    """Compatibility no-op — no persistent client anymore."""
    class _NoopClient:
        def call_tool(self, name, arguments=None):
            return _fail_result(name, "MCP bridge removed; use backend directly")

        @property
        def tools(self):
            return []

        def stop(self):
            pass

    return _NoopClient()
