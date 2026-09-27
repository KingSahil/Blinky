"""cua-driver backend — background desktop automation for Blinky.

Implements `ComputerUseBackend` on top of `cua-driver` (trycua/cua), the same
open-source driver Hermes Agent uses. This is what replaces Blinky's foreground
`SendInput` actuator on Windows.

Why it matters
--------------
The previous path (Rust `SendInput` via `click_screen_point`) moves the real
cursor, steals keyboard focus, and can switch virtual desktops. cua-driver
drives the desktop **in the background**:

  - Cursor never moves — a cosmetic overlay cursor shows where actions land.
  - Focus is never stolen; the target window is never raised.
  - Works on backgrounded / minimized / off-desktop windows.

Delivery model
--------------
`delivery_mode="background"` is the mandatory first attempt. The driver does a
UIA hit-test at the target point and invokes through the accessibility channel;
it only falls back to `PostMessage` for canvas/video/WebGL surfaces. When
background delivery is genuinely impossible the driver returns a structured
`background_unavailable` error rather than silently fronting the window.

We honour that contract: we do NOT pass `foreground` preemptively. Escalation
happens only in response to that specific error, and only when
`allow_foreground` is enabled (env `BLINKY_CUA_ALLOW_FOREGROUND`, default on)
so behaviour never regresses below today's always-foreground SendInput path.

Coordinate space
----------------
Everything here is in **true screen pixels** — the space reported by
`get_desktop_state` (`screenshot_width` x `screenshot_height`, e.g. 2560x1600
at scale_factor 1.5). Clicks use `scope="desktop"` with `pid` omitted, which
cua-driver documents as screen-absolute coordinates.

Note this module's earlier claim — that desktop scope "deliberately sidesteps the
window-local downscaled-pixel space that `scope="window"` uses" — was **wrong**, and
that myth cost real debugging time in the Rust bridge. `scope="window"` takes
**physical window pixels**: on a 2560x1528 window with a 1456 screenshot cap the
`frame` extents still reach 2560x1528, so no downscaling is involved. See
`windows/src-tauri/src/platform/cua.rs::window_local`. Desktop scope is used here for
a different and real reason: it is the only scope this backend's callers expect.

Transport
---------
`cua-driver call <tool> '<json>'` over the running daemon, rather than raw MCP
stdio. Simple, debuggable, and reuses the daemon's element-index cache. The
`_CuaTransport` seam exists so a persistent MCP client can drop in later
without touching the backend.

**This is currently the slow path**: one process per call, ~1.45s of pure startup
before any work. The Rust bridge keeps a persistent `cua-driver mcp` child instead
and runs the same ladder in ~0.4s. Any multi-call sequence added here will pay that
cost per step, so the MCP drop-in is worth doing before this path grows.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from utils.logging import get_logger

from .base import ActionResult, ComputerUseBackend, Screenshot, UIElement, WindowInfo

LOGGER = get_logger("blinky.backend.cua")

# Known install locations, checked after PATH.
_WINDOWS_FALLBACKS = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Cua" / "cua-driver" / "bin" / "cua-driver.exe",
)
_POSIX_FALLBACKS = (
    Path.home() / ".cua-driver" / "bin" / "cua-driver",
    Path("/usr/local/bin/cua-driver"),
)

_DEFAULT_TIMEOUT_S = 30.0
# get_window_state walks a UIA tree; Chromium needs headroom.
_SLOW_TOOLS = {"get_window_state", "get_accessibility_tree", "get_desktop_state"}
_SLOW_TIMEOUT_S = 60.0

# Errors that mean "retry this exact action with delivery_mode=foreground".
_BACKGROUND_UNAVAILABLE_MARKERS = (
    "background_unavailable",
    "background delivery",
    "background is unavailable",
)

# Errors that mean the named lifecycle session expired and needs reviving.
_DEAD_SESSION_MARKERS = (
    "has ended",
    "session has ended",
    "was rejected",
    "revive it",
)

_SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "blinky_cua"


def _resolve_binary() -> str | None:
    """Locate the cua-driver executable: env override → PATH → known paths."""
    override = os.environ.get("CUA_DRIVER_CMD") or os.environ.get("HERMES_CUA_DRIVER_CMD")
    if override and Path(override).exists():
        return override

    found = shutil.which("cua-driver")
    if found:
        return found

    for candidate in (*_WINDOWS_FALLBACKS, *_POSIX_FALLBACKS):
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def _strip_extended_prefix(raw: str) -> Path:
    """Drop the Windows `\\\\?\\` extended-length prefix so Path works."""
    if raw.startswith("\\\\?\\"):
        raw = raw[4:]
    return Path(raw)


class _CuaDriverError(RuntimeError):
    """Raised when cua-driver returns a structured failure."""

    def __init__(self, tool: str, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool = tool
        self.message = message
        self.payload = payload or {}


class _CuaTransport:
    """Thin wrapper over the `cua-driver` CLI, which proxies the daemon.

    Sessions are **opt-in**. cua-driver's named lifecycle sessions expire
    (`session 'x' has ended; tool call was rejected`), and a stale id poisons
    every subsequent call — which previously made the whole backend look
    unhealthy and silently drop to the native path. By default we therefore
    omit `session` and let each call use the transport's implicit session.

    When a session *is* configured we recover automatically: a dead-session
    error triggers `start_session` and one retry.
    """

    def __init__(self, binary: str, session: str | None = None) -> None:
        self.binary = binary
        self.session = session

    def call(self, tool: str, payload: dict[str, Any] | None = None, *, _retry: bool = True) -> dict[str, Any]:
        args = dict(payload or {})
        if self.session:
            args.setdefault("session", self.session)

        try:
            return self._invoke(tool, args)
        except _CuaDriverError as exc:
            if _retry and self.session and _is_dead_session(exc):
                LOGGER.info("cua-driver session %r expired; reviving.", self.session)
                if self._revive():
                    return self.call(tool, payload, _retry=False)
            raise

    def _revive(self) -> bool:
        """Re-open the named lifecycle session. Best effort."""
        try:
            proc = subprocess.run(
                [self.binary, "call", "start_session", json.dumps({"session": self.session})],
                capture_output=True,
                text=True,
                timeout=_DEFAULT_TIMEOUT_S,
                encoding="utf-8",
                errors="replace",
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            LOGGER.warning("Failed to revive cua-driver session: %s", exc)
            return False

        if proc.returncode == 0:
            return True
        LOGGER.warning("Reviving cua-driver session failed: %s", (proc.stderr or "").strip()[:200])
        return False

    def _invoke(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        timeout = _SLOW_TIMEOUT_S if tool in _SLOW_TOOLS else _DEFAULT_TIMEOUT_S
        cmd = [self.binary, "call", tool, json.dumps(args)]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise _CuaDriverError(tool, f"timed out after {timeout:.0f}s") from exc
        except OSError as exc:
            raise _CuaDriverError(tool, f"could not execute driver: {exc}") from exc

        stdout = (proc.stdout or "").strip()
        parsed: dict[str, Any] | None = None
        if stdout:
            try:
                candidate = json.loads(stdout)
                if isinstance(candidate, dict):
                    parsed = candidate
            except json.JSONDecodeError:
                # Some tools emit progress lines before the payload; take the last
                # balanced JSON object we can find.
                parsed = _last_json_object(stdout)

        if proc.returncode != 0:
            detail = ""
            if parsed:
                detail = str(parsed.get("error") or parsed.get("message") or "")
            detail = detail or (proc.stderr or "").strip() or f"exit code {proc.returncode}"
            raise _CuaDriverError(tool, detail, parsed)

        if parsed is None:
            raise _CuaDriverError(tool, f"unparseable driver output: {stdout[:200]!r}")

        if parsed.get("isError"):
            message = str(parsed.get("error") or parsed.get("message") or "driver reported an error")
            raise _CuaDriverError(tool, message, parsed)

        return parsed


def _last_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort recovery of the final JSON object in noisy stdout."""
    depth = 0
    start: int | None = None
    last: dict[str, Any] | None = None
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    candidate = json.loads(text[start : index + 1])
                    if isinstance(candidate, dict):
                        last = candidate
                except json.JSONDecodeError:
                    pass
                start = None
    return last


def _is_background_unavailable(exc: _CuaDriverError) -> bool:
    haystack = f"{exc.message} {json.dumps(exc.payload)[:2000]}".lower()
    return any(marker in haystack for marker in _BACKGROUND_UNAVAILABLE_MARKERS)


def _is_dead_session(exc: _CuaDriverError) -> bool:
    haystack = f"{exc.message} {json.dumps(exc.payload)[:2000]}".lower()
    return any(marker in haystack for marker in _DEAD_SESSION_MARKERS)


class CuaDriverBackend(ComputerUseBackend):
    """Background computer-use backend backed by cua-driver."""

    def __init__(
        self,
        binary: str | None = None,
        *,
        session: str | None = None,
        allow_foreground: bool | None = None,
    ) -> None:
        self._binary = _resolve_binary() if binary is None else (binary or None)

        # Sessions are opt-in: a named lifecycle session can expire and then
        # rejects every call, which would silently disable the backend.
        if session is None:
            session = os.environ.get("BLINKY_CUA_SESSION") or None
        self._session = session

        self._transport: _CuaTransport | None = None
        self._started = False

        if allow_foreground is None:
            allow_foreground = os.environ.get("BLINKY_CUA_ALLOW_FOREGROUND", "1") not in {"0", "false", "False"}
        self.allow_foreground = allow_foreground

        self._screen_size_cache: tuple[int, int] | None = None
        self._scale_factor: float = 1.0
        # (pid, window_id) -> snapshot_id from the last get_window_state call.
        self._snapshots: dict[tuple[int, int], str] = {}
        # Set when the last get_window_state came back degraded (minimized
        # window, non-UIA surface) so callers know the element list is not
        # authoritative and should fall back to the visual path.
        self.last_snapshot_degraded: dict[str, Any] | None = None

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        if self._started:
            return
        if not self._binary:
            raise _CuaDriverError("start", "cua-driver not found (set CUA_DRIVER_CMD or add it to PATH)")
        self._transport = _CuaTransport(self._binary, session=self._session)
        self._started = True
        LOGGER.info("CuaDriverBackend ready (binary=%s, session=%s)", self._binary, self._session)

    def stop(self) -> None:
        self._started = False
        self._transport = None
        self._snapshots.clear()
        self._screen_size_cache = None

    def is_available(self) -> bool:
        if not self._binary:
            return False
        try:
            report = self._call("health_report")
        except _CuaDriverError as exc:
            LOGGER.warning("cua-driver health check failed: %s", exc)
            return False
        checks = report.get("checks") or []
        if not isinstance(checks, list) or not checks:
            return True
        return not any(isinstance(c, dict) and c.get("status") == "fail" for c in checks)

    # ── Internals ──────────────────────────────────────────────────

    @property
    def transport(self) -> _CuaTransport:
        if self._transport is None:
            self.start()
        assert self._transport is not None
        return self._transport

    def _call(self, tool: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.transport.call(tool, payload)

    def _screenshot_path(self, stem: str) -> Path:
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        return _SCREENSHOT_DIR / f"{stem}_{int(time.time() * 1000)}.png"

    # ── Screen ─────────────────────────────────────────────────────

    def screen_size(self) -> tuple[int, int]:
        if self._screen_size_cache is None:
            data = self._call("get_screen_size")
            self._screen_size_cache = (int(data.get("width", 0)), int(data.get("height", 0)))
            self._scale_factor = float(data.get("scale_factor", 1.0) or 1.0)
        return self._screen_size_cache

    def capture(self, *, window: bool = False) -> Screenshot:
        if not window:
            return self._capture_desktop()

        active = self.get_active_window()
        if active is None or active.pid is None or not active.window_id:
            LOGGER.info("capture(window=True): no active window, falling back to desktop")
            return self._capture_desktop()
        return self._capture_window(active)

    def _capture_desktop(self) -> Screenshot:
        out = self._screenshot_path("desktop")
        data = self._call("get_desktop_state", {"screenshot_out_file": str(out)})

        raw_path = data.get("screenshot_file_path")
        path = _strip_extended_prefix(str(raw_path)) if raw_path else out

        return Screenshot(
            path=path,
            width=int(data.get("screenshot_width", 0)),
            height=int(data.get("screenshot_height", 0)),
            screen_width=int(data.get("screen_width", 0)),
            screen_height=int(data.get("screen_height", 0)),
        )

    def _capture_window(self, win: WindowInfo) -> Screenshot:
        pid = int(win.pid or 0)
        window_id = int(win.window_id)
        data = self._call(
            "get_window_state",
            {
                "pid": pid,
                "window_id": window_id,
                "include_accessibility_tree": False,
            },
        )
        return self._screenshot_from_window_state(data)

    def _screenshot_from_window_state(self, data: dict[str, Any]) -> Screenshot:
        path: Path | None = None
        raw_path = data.get("screenshot_file_path")
        if raw_path:
            path = _strip_extended_prefix(str(raw_path))
        else:
            b64 = data.get("screenshot_png_b64")
            if b64:
                path = self._screenshot_path("window")
                path.write_bytes(base64.b64decode(b64))

        bounds = data.get("window_bounds") or {}
        if path is None:
            raise _CuaDriverError("get_window_state", "response carried no screenshot")

        width = int(data.get("screenshot_width", 0) or bounds.get("width", 0) or 0)
        height = int(data.get("screenshot_height", 0) or bounds.get("height", 0) or 0)
        screen_w, screen_h = self.screen_size()

        return Screenshot(
            path=path,
            width=width,
            height=height,
            screen_width=screen_w,
            screen_height=screen_h,
        )

    # ── Windows / apps ─────────────────────────────────────────────

    @staticmethod
    def _window_from_item(item: dict[str, Any]) -> WindowInfo | None:
        """Normalize one cua-driver window record.

        The richer `windows` array nests geometry under `bounds`; the older
        `_legacy_windows` array flattens it. Both are accepted.
        """
        title = str(item.get("title") or "")
        if not title:
            return None

        bounds = item.get("bounds")
        if not isinstance(bounds, dict):
            bounds = item

        return WindowInfo(
            title=title,
            process=str(item.get("app_name") or item.get("process") or item.get("owner") or ""),
            # A minimized or off-screen window has no rendered content, so it
            # can't be captured or element-walked — mark it unsupported so
            # callers pick a different target instead of getting empty results.
            supported=bool(item.get("is_on_screen", True)) and not bool(item.get("minimized", False)),
            x=int(bounds.get("x", 0) or 0),
            y=int(bounds.get("y", 0) or 0),
            width=int(bounds.get("width", 0) or 0),
            height=int(bounds.get("height", 0) or 0),
            pid=int(item["pid"]) if item.get("pid") is not None else None,
            window_id=str(item.get("window_id", "") or ""),
        )

    def list_windows(self) -> list[WindowInfo]:
        data = self._call("list_windows")
        raw = data.get("windows")
        if not isinstance(raw, list):
            raw = data.get("_legacy_windows") or []

        windows: list[WindowInfo] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            win = self._window_from_item(item)
            if win is not None:
                windows.append(win)
        return windows

    @staticmethod
    def _is_driver_overlay(item: dict[str, Any]) -> bool:
        """Skip cua-driver's own overlay-cursor window when picking a target."""
        haystack = f"{item.get('app_name', '')} {item.get('title', '')}".lower()
        return "agentcursoroverlay" in haystack or "cua.agentcursor" in haystack

    def get_active_window(self) -> WindowInfo | None:
        """Frontmost on-screen window.

        cua-driver has no dedicated "frontmost" accessor. `list_windows`
        returns windows in z-order (frontmost first), so we take the first
        on-screen entry that isn't the driver's own overlay cursor.
        """
        try:
            data = self._call("list_windows")
        except _CuaDriverError as exc:
            LOGGER.debug("list_windows unavailable: %s", exc)
            return None

        raw = data.get("windows")
        if not isinstance(raw, list):
            raw = data.get("_legacy_windows") or []

        for item in raw:
            if not isinstance(item, dict) or self._is_driver_overlay(item):
                continue
            if not item.get("is_on_screen", True) or item.get("minimized"):
                continue
            win = self._window_from_item(item)
            if win is not None:
                return win
        return None

    def list_apps(self) -> list[dict[str, Any]]:
        data = self._call("list_apps")
        raw = data.get("apps")
        if not isinstance(raw, list):
            raw = data.get("installed_apps") or []
        apps: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            apps.append(
                {
                    "name": str(item.get("name") or item.get("display_name") or ""),
                    "desktop_id": str(item.get("desktop_id") or item.get("app_id") or ""),
                    "exec": str(item.get("exec") or item.get("path") or ""),
                    "startup_wm_class": str(item.get("process") or ""),
                    "source": "native",
                    "running": bool(item.get("running", False)),
                    "pid": item.get("pid"),
                }
            )
        return apps

    def launch_app(self, app_name: str) -> ActionResult:
        try:
            data = self._call("launch_app", {"app_name": app_name})
        except _CuaDriverError as exc:
            return ActionResult(False, "open_app", exc.message, {"app_name": app_name})

        return ActionResult(
            True,
            "open_app",
            f"Launched {app_name} in the background.",
            {"app_name": app_name, "result": data},
        )

    # ── Input ──────────────────────────────────────────────────────

    def click(
        self,
        *,
        x: int,
        y: int,
        button: str = "left",
        click_count: int = 1,
    ) -> ActionResult:
        payload: dict[str, Any] = {
            "scope": "desktop",
            "x": int(x),
            "y": int(y),
            "button": button,
            "count": max(1, min(3, int(click_count))),
        }
        return self._dispatch_input("click", payload, action="click")

    def scroll(
        self,
        *,
        direction: str,
        amount: int = 3,
        x: int | None = None,
        y: int | None = None,
    ) -> ActionResult:
        payload: dict[str, Any] = {
            "scope": "desktop",
            "direction": direction,
            "amount": max(1, abs(int(amount))),
        }
        if x is not None and y is not None:
            payload["x"] = int(x)
            payload["y"] = int(y)
        return self._dispatch_input("scroll", payload, action="scroll")

    def type_text(self, text: str) -> ActionResult:
        return self._dispatch_input("type_text", {"text": text}, action="type_text")

    def key(self, keys: str) -> ActionResult:
        """Single key or a combination like `ctrl+s`.

        `press_key` handles one key; `hotkey` handles combinations. Blinky's
        callers pass both forms, so we route on the presence of `+`.
        """
        normalized = (keys or "").strip()
        if not normalized:
            return ActionResult(False, "key", "empty key spec", {})

        if "+" in normalized:
            parts = [part.strip() for part in normalized.split("+") if part.strip()]
            payload = {"keys": parts}
            tool = "hotkey"
        else:
            payload = {"key": normalized}
            tool = "press_key"

        return self._dispatch_input(tool, payload, action="key")

    def focus_window(self, window_id: str) -> ActionResult:
        try:
            payload: dict[str, Any] = {"window_id": int(window_id)}
        except (TypeError, ValueError):
            return ActionResult(False, "focus_window", f"invalid window_id: {window_id!r}", {})

        # bring_to_front is the one operation that legitimately changes z-order.
        # Blinky only calls it when the user explicitly targets a window.
        try:
            data = self._call("bring_to_front", payload)
        except _CuaDriverError as exc:
            return ActionResult(False, "focus_window", exc.message, payload)

        return ActionResult(True, "focus_window", f"Brought window {window_id} to front.", {"result": data})

    def _dispatch_input(self, tool: str, payload: dict[str, Any], *, action: str) -> ActionResult:
        """Send an input action, honouring cua-driver's escalation contract.

        We always try `background` first. `foreground` is only attempted in
        response to an explicit `background_unavailable` error, and only when
        `allow_foreground` is on — never preemptively, because fronting the
        window steals the user's focus.
        """
        payload.setdefault("delivery_mode", "background")
        try:
            data = self._call(tool, payload)
        except _CuaDriverError as exc:
            if not _is_background_unavailable(exc):
                return ActionResult(False, action, exc.message, {"payload": payload, "error": exc.payload})

            if not self.allow_foreground:
                return ActionResult(
                    False,
                    action,
                    f"{exc.message} (background unavailable; foreground escalation disabled)",
                    {"payload": payload, "background_unavailable": True},
                )

            LOGGER.info("Escalating %s to foreground delivery (background unavailable)", tool)
            escalated = dict(payload)
            escalated["delivery_mode"] = "foreground"
            try:
                data = self._call(tool, escalated)
            except _CuaDriverError as retry_exc:
                return ActionResult(
                    False,
                    action,
                    retry_exc.message,
                    {"payload": escalated, "escalated": True, "error": retry_exc.payload},
                )
            return ActionResult(
                True,
                action,
                f"{action} completed (foreground escalation).",
                {"result": data, "escalated": True},
            )

        return ActionResult(True, action, f"{action} completed.", {"result": data})

    # ── Element enumeration (cua-driver's strong suit) ─────────────

    def get_window_elements(self, window_id: str, pid: int | None = None) -> list[UIElement]:
        """UIA elements for one window, in screen-absolute pixels.

        Also caches the `snapshot_id` so `click_element` can address elements by
        index — the background-safe path cua-driver recommends over raw pixels.
        """
        try:
            wid = int(window_id)
        except (TypeError, ValueError):
            return []

        if pid is None:
            for win in self.list_windows():
                if win.window_id == str(window_id):
                    pid = win.pid
                    break
        if pid is None:
            return []

        try:
            data = self._call("get_window_state", {"pid": int(pid), "window_id": wid})
        except _CuaDriverError as exc:
            LOGGER.warning("get_window_state failed for pid=%s window=%s: %s", pid, wid, exc)
            return []

        snapshot_id = data.get("snapshot_id")
        if snapshot_id:
            self._snapshots[(int(pid), wid)] = str(snapshot_id)

        # A degraded snapshot means the element data is NOT authoritative —
        # usually a minimized window or a non-UIA (canvas/WebGL) surface. Say so
        # loudly; callers should fall back to the OCR/visual path rather than
        # trusting an empty list.
        self.last_snapshot_degraded: dict[str, Any] | None = None
        if data.get("degraded"):
            self.last_snapshot_degraded = {
                "window_id": wid,
                "pid": int(pid),
                "reason": data.get("degraded_reason"),
                "screenshot_error": data.get("screenshot_error"),
                "escalation": data.get("escalation"),
            }
            LOGGER.warning(
                "cua get_window_state degraded for pid=%s window=%s: %s",
                pid,
                wid,
                str(data.get("degraded_reason"))[:200],
            )

        bounds = data.get("window_bounds") or {}
        origin_x = int(bounds.get("x", 0) or 0)
        origin_y = int(bounds.get("y", 0) or 0)

        elements: list[UIElement] = []
        for item in data.get("elements") or []:
            if not isinstance(item, dict):
                continue
            frame = item.get("frame") or {}
            label = str(item.get("label") or item.get("value") or "").strip()
            elements.append(
                UIElement(
                    text=label,
                    x=origin_x + int(frame.get("x", 0) or 0),
                    y=origin_y + int(frame.get("y", 0) or 0),
                    width=int(frame.get("w", 0) or 0),
                    height=int(frame.get("h", 0) or 0),
                    source="uia",
                    role=str(item.get("role") or ""),
                    automation_id=str(item.get("automation_id") or ""),
                    confidence=1.0,
                    extra={
                        "element_index": item.get("element_index"),
                        "element_token": item.get("element_token"),
                        "snapshot_id": snapshot_id,
                        "window_id": wid,
                        "pid": int(pid),
                        "enabled": item.get("enabled"),
                        "actions": item.get("actions") or [],
                        # Raw window-local frame, in case callers need to
                        # re-derive coordinates themselves.
                        "raw_frame": frame,
                    },
                )
            )
        return elements

    def click_element(
        self,
        *,
        element_index: int,
        window_id: str,
        pid: int | None = None,
        snapshot_id: str | None = None,
        button: str = "left",
        click_count: int = 1,
    ) -> ActionResult:
        """Click by UIA element index — no cursor move, no focus steal.

        Requires a prior `get_window_elements` call for the same window, which
        is where the `snapshot_id` comes from.
        """
        try:
            wid = int(window_id)
        except (TypeError, ValueError):
            return ActionResult(False, "click_element", f"invalid window_id: {window_id!r}", {})

        if pid is None:
            for win in self.list_windows():
                if win.window_id == str(window_id):
                    pid = win.pid
                    break
        if pid is None:
            return ActionResult(False, "click_element", "could not resolve pid for window", {})

        snap = snapshot_id or self._snapshots.get((int(pid), wid))
        payload: dict[str, Any] = {
            # Element-addressed clicks are window-scoped by definition — the
            # element_index belongs to a (pid, window_id) snapshot.
            "scope": "window",
            "pid": int(pid),
            "window_id": wid,
            "element_index": int(element_index),
            "button": button,
            "count": max(1, min(3, int(click_count))),
        }
        if snap:
            payload["snapshot_id"] = snap

        return self._dispatch_input("click", payload, action="click_element")

    # ── Diagnostics ────────────────────────────────────────────────

    def doctor(self) -> dict[str, Any]:
        """Structured health report, straight from cua-driver's health_report."""
        report: dict[str, Any] = {
            "backend": type(self).__name__,
            "binary": self._binary,
            "session": self._session,
            "available": False,
        }
        if not self._binary:
            report["error"] = "cua-driver not found"
            return report

        try:
            data = self._call("health_report")
        except _CuaDriverError as exc:
            report["error"] = exc.message
            return report

        checks = data.get("checks") or []
        report["available"] = not any(
            isinstance(c, dict) and c.get("status") == "fail" for c in checks
        )
        report["checks"] = checks
        report["version"] = next(
            (
                c.get("message")
                for c in checks
                if isinstance(c, dict) and c.get("name") == "binary_version"
            ),
            None,
        )
        return report

    def cursor_position(self) -> tuple[int, int] | None:
        try:
            data = self._call("get_cursor_position")
        except _CuaDriverError:
            return None
        if "x" not in data or "y" not in data:
            return None
        return int(data["x"]), int(data["y"])

    def set_agent_cursor(self, enabled: bool) -> ActionResult:
        """Show/hide cua-driver's cosmetic overlay cursor.

        Purely visual — captures, clicks and typing all work without it. This is
        the analogue of Blinky's own agent-cursor toggle.
        """
        try:
            data = self._call("set_agent_cursor_enabled", {"enabled": bool(enabled)})
        except _CuaDriverError as exc:
            return ActionResult(False, "set_agent_cursor", exc.message, {})
        return ActionResult(True, "set_agent_cursor", f"Agent cursor {'shown' if enabled else 'hidden'}.", {"result": data})

    def move_agent_cursor(self, x: int, y: int) -> ActionResult:
        """Move the cosmetic overlay cursor to (x, y).

        Deliberately does NOT move the real OS cursor — that is the whole point
        of the background model. Use this to *point* at something (Blinky's
        tutor behaviour); use `click` to actually act.
        """
        try:
            data = self._call("move_cursor", {"x": int(x), "y": int(y)})
        except _CuaDriverError as exc:
            return ActionResult(False, "move", exc.message, {})
        return ActionResult(True, "move", f"Agent cursor moved to ({x}, {y}).", {"result": data})


__all__ = ["CuaDriverBackend"]
