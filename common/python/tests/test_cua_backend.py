"""Tests for the cua-driver computer-use backend.

These run without the driver installed: the transport is stubbed so we assert
on the *payloads* Blinky sends (delivery mode, scope, escalation) rather than on
a live desktop. The one test that needs the real binary skips itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from computer_use.backends.cua_driver import (
    CuaDriverBackend,
    _CuaDriverError,
    _is_background_unavailable,
    _is_dead_session,
    _last_json_object,
    _strip_extended_prefix,
)


class FakeTransport:
    """Records calls and replays canned responses."""

    def __init__(self, responses: dict[str, object] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, payload: dict | None = None) -> dict:
        args = dict(payload or {})
        self.calls.append((tool, args))

        response = self.responses.get(tool)
        if isinstance(response, list):
            # Pop successive responses so a retry can return something different.
            response = response.pop(0) if response else {}
        if isinstance(response, Exception):
            raise response
        return response if response is not None else {}

    def last(self, tool: str) -> dict:
        for called_tool, args in reversed(self.calls):
            if called_tool == tool:
                return args
        raise AssertionError(f"{tool} was never called; calls={self.calls}")


def make_backend(**kwargs) -> tuple[CuaDriverBackend, FakeTransport]:
    backend = CuaDriverBackend(binary="fake-cua-driver")
    transport = FakeTransport(kwargs.pop("responses", None))
    backend._transport = transport
    backend._started = True
    for key, value in kwargs.items():
        setattr(backend, key, value)
    return backend, transport


def _background_unavailable() -> _CuaDriverError:
    return _CuaDriverError(
        "click",
        "background_unavailable: this target drops posted events",
        {"error": "background_unavailable"},
    )


# ── Pure helpers ───────────────────────────────────────────────────


def test_strip_extended_prefix_removes_windows_prefix() -> None:
    assert _strip_extended_prefix("\\\\?\\C:\\tmp\\shot.png") == Path("C:/tmp/shot.png")


def test_strip_extended_prefix_leaves_plain_path_alone() -> None:
    assert _strip_extended_prefix("C:\\tmp\\shot.png") == Path("C:/tmp/shot.png")


def test_last_json_object_ignores_leading_noise() -> None:
    noisy = 'progress 10%\nprogress 90%\n{"ok": true, "n": 3}\n'
    assert _last_json_object(noisy) == {"ok": True, "n": 3}


def test_last_json_object_returns_none_without_json() -> None:
    assert _last_json_object("no json here") is None


def test_is_background_unavailable_detects_marker() -> None:
    assert _is_background_unavailable(_background_unavailable()) is True


def test_is_background_unavailable_ignores_other_errors() -> None:
    assert _is_background_unavailable(_CuaDriverError("click", "pid has no on-screen window")) is False


# ── Input payloads ─────────────────────────────────────────────────


def test_click_uses_desktop_scope_and_background_delivery() -> None:
    backend, transport = make_backend()

    result = backend.click(x=120, y=340)

    assert result.ok is True
    payload = transport.last("click")
    # Desktop scope = screen-absolute pixels, which is what Blinky's OCR/dxcam
    # pipeline already produces.
    assert payload["scope"] == "desktop"
    assert payload["delivery_mode"] == "background"
    assert (payload["x"], payload["y"]) == (120, 340)
    assert "pid" not in payload


def test_click_clamps_click_count() -> None:
    backend, transport = make_backend()

    backend.click(x=1, y=1, click_count=9)

    assert transport.last("click")["count"] == 3


def test_click_never_fronts_preemptively() -> None:
    """A plain failure must not trigger a foreground retry."""
    backend, transport = make_backend(
        responses={"click": _CuaDriverError("click", "pid has no on-screen window")}
    )

    result = backend.click(x=5, y=5)

    assert result.ok is False
    assert [tool for tool, _ in transport.calls] == ["click"]
    assert transport.calls[0][1]["delivery_mode"] == "background"


def test_click_escalates_only_on_background_unavailable() -> None:
    backend, transport = make_backend(
        responses={"click": [_background_unavailable(), {"clicked": True}]}
    )

    result = backend.click(x=7, y=8)

    assert result.ok is True
    assert result.data.get("escalated") is True
    modes = [args["delivery_mode"] for tool, args in transport.calls if tool == "click"]
    assert modes == ["background", "foreground"]


def test_click_does_not_escalate_when_foreground_disabled() -> None:
    backend, transport = make_backend(
        responses={"click": _background_unavailable()},
        allow_foreground=False,
    )

    result = backend.click(x=7, y=8)

    assert result.ok is False
    assert result.data.get("background_unavailable") is True
    assert [tool for tool, _ in transport.calls] == ["click"]


def test_key_routes_combination_to_hotkey() -> None:
    backend, transport = make_backend()

    backend.key("ctrl+s")

    tool, payload = transport.calls[-1]
    assert tool == "hotkey"
    assert payload["keys"] == ["ctrl", "s"]


def test_key_routes_single_key_to_press_key() -> None:
    backend, transport = make_backend()

    backend.key("escape")

    tool, payload = transport.calls[-1]
    assert tool == "press_key"
    assert payload["key"] == "escape"


def test_key_rejects_empty_spec() -> None:
    backend, _ = make_backend()

    assert backend.key("   ").ok is False


def test_scroll_passes_direction_and_amount() -> None:
    backend, transport = make_backend()

    backend.scroll(direction="down", amount=-4)

    payload = transport.last("scroll")
    assert payload["scope"] == "desktop"
    assert payload["direction"] == "down"
    # Negative amounts are normalised to a magnitude.
    assert payload["amount"] == 4


def test_type_text_sends_text_without_pid() -> None:
    backend, transport = make_backend()

    backend.type_text("hello")

    payload = transport.last("type_text")
    assert payload["text"] == "hello"
    assert "pid" not in payload


# ── Window / element mapping ───────────────────────────────────────


def test_list_windows_reads_nested_bounds() -> None:
    backend, _ = make_backend(
        responses={
            "list_windows": {
                "windows": [
                    {
                        "title": "Editor",
                        "app_name": "code.exe",
                        "pid": 42,
                        "window_id": 99,
                        "is_on_screen": True,
                        "bounds": {"x": 10, "y": 20, "width": 800, "height": 600},
                    }
                ]
            }
        }
    )

    windows = backend.list_windows()

    assert len(windows) == 1
    win = windows[0]
    assert (win.title, win.process, win.pid, win.window_id) == ("Editor", "code.exe", 42, "99")
    assert (win.x, win.y, win.width, win.height) == (10, 20, 800, 600)


def test_list_windows_falls_back_to_legacy_array() -> None:
    backend, _ = make_backend(
        responses={
            "list_windows": {
                "_legacy_windows": [
                    {"title": "Old", "pid": 1, "window_id": 2, "x": 0, "y": 0, "width": 5, "height": 6}
                ]
            }
        }
    )

    windows = backend.list_windows()

    assert [w.title for w in windows] == ["Old"]
    assert windows[0].width == 5


def test_get_active_window_skips_driver_overlay() -> None:
    backend, _ = make_backend(
        responses={
            "list_windows": {
                "windows": [
                    {
                        "title": "Cua.AgentCursorOverlay.default",
                        "app_name": "Cua.AgentCursorOverlay",
                        "pid": 7,
                        "window_id": 1,
                        "is_on_screen": True,
                    },
                    {
                        "title": "Real App",
                        "app_name": "real.exe",
                        "pid": 8,
                        "window_id": 2,
                        "is_on_screen": True,
                    },
                ]
            }
        }
    )

    active = backend.get_active_window()

    assert active is not None
    assert active.title == "Real App"


def test_get_window_elements_offsets_frames_to_screen_absolute() -> None:
    backend, _ = make_backend(
        responses={
            "get_window_state": {
                "snapshot_id": "s00000009",
                "window_bounds": {"x": 100, "y": 50, "width": 800, "height": 600},
                "elements": [
                    {
                        "element_index": 0,
                        "role": "Button",
                        "label": "Save",
                        "frame": {"x": 12, "y": 30, "w": 40, "h": 20},
                    }
                ],
            }
        }
    )

    elements = backend.get_window_elements("2", pid=8)

    assert len(elements) == 1
    el = elements[0]
    # Window-local frame (12, 30) + window origin (100, 50)
    assert (el.x, el.y) == (112, 80)
    assert (el.width, el.height) == (40, 20)
    assert el.text == "Save"
    assert el.role == "Button"
    assert el.source == "uia"
    # Snapshot cached so click_element can address by index.
    assert backend._snapshots[(8, 2)] == "s00000009"


def test_click_element_uses_cached_snapshot() -> None:
    backend, transport = make_backend(
        responses={"get_window_state": {"snapshot_id": "s00000001", "window_bounds": {}, "elements": []}}
    )
    backend.get_window_elements("2", pid=8)

    backend.click_element(element_index=3, window_id="2", pid=8)

    payload = transport.last("click")
    assert payload["element_index"] == 3
    assert payload["snapshot_id"] == "s00000001"
    assert payload["delivery_mode"] == "background"
    # Element-addressed clicks are window-scoped, never desktop-scoped.
    assert payload["scope"] == "window"


def test_doctor_reports_unavailable_without_binary() -> None:
    backend = CuaDriverBackend(binary="")

    report = backend.doctor()

    assert report["available"] is False
    assert "not found" in report["error"]


def test_doctor_flags_failing_check() -> None:
    backend, _ = make_backend(
        responses={
            "health_report": {
                "checks": [
                    {"name": "binary_version", "status": "pass", "message": "cua-driver 0.28.1"},
                    {"name": "ax_capability", "status": "fail", "message": "UIA unreachable"},
                ]
            }
        }
    )

    report = backend.doctor()

    assert report["available"] is False
    assert report["version"] == "cua-driver 0.28.1"


def test_is_dead_session_detects_marker() -> None:
    err = _CuaDriverError(
        "health_report",
        "session 'blinky' has ended; tool call 'health_report' was rejected. Call start_session",
    )
    assert _is_dead_session(err) is True


def test_is_dead_session_ignores_other_errors() -> None:
    assert _is_dead_session(_CuaDriverError("click", "pid has no on-screen window")) is False


def test_backend_uses_no_session_by_default(monkeypatch) -> None:
    monkeypatch.delenv("BLINKY_CUA_SESSION", raising=False)

    backend = CuaDriverBackend(binary="fake")

    # A named session can expire and poison every later call, so we omit it.
    assert backend._session is None


def test_backend_session_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BLINKY_CUA_SESSION", "custom-session")

    backend = CuaDriverBackend(binary="fake")

    assert backend._session == "custom-session"


def test_transport_omits_session_when_unset() -> None:
    from computer_use.backends.cua_driver import _CuaTransport

    transport = _CuaTransport("fake", session=None)
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return SimpleNamespace(returncode=0, stdout='{"ok": true}', stderr="")

    with patch("computer_use.backends.cua_driver.subprocess.run", side_effect=fake_run):
        transport.call("get_screen_size")

    sent = json.loads(captured[0][3])
    assert "session" not in sent


def test_transport_revives_expired_session_and_retries() -> None:
    from computer_use.backends.cua_driver import _CuaTransport

    transport = _CuaTransport("fake", session="blinky")
    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        tool = cmd[2]
        calls.append(tool)
        if tool == "health_report":
            # First attempt reports the session as dead; after revival it works.
            if "start_session" not in calls:
                return SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr="session 'blinky' has ended; tool call was rejected. Call start_session",
                )
            return SimpleNamespace(returncode=0, stdout='{"checks": []}', stderr="")
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    with patch("computer_use.backends.cua_driver.subprocess.run", side_effect=fake_run):
        result = transport.call("health_report")

    assert result == {"checks": []}
    assert calls == ["health_report", "start_session", "health_report"]


def test_transport_raises_when_revival_fails() -> None:
    from computer_use.backends.cua_driver import _CuaTransport

    transport = _CuaTransport("fake", session="blinky")

    def fake_run(cmd, **kwargs):
        if cmd[2] == "start_session":
            return SimpleNamespace(returncode=1, stdout="", stderr="cannot revive")
        return SimpleNamespace(
            returncode=1, stdout="", stderr="session 'blinky' has ended; tool call was rejected"
        )

    with patch("computer_use.backends.cua_driver.subprocess.run", side_effect=fake_run):
        with pytest.raises(_CuaDriverError):
            transport.call("health_report")


# ── Registry / fallback behaviour ──────────────────────────────────


def test_registry_honours_native_override(monkeypatch) -> None:
    import computer_use.backends as backends

    monkeypatch.setenv("BLINKY_COMPUTER_USE_BACKEND", "native")
    backends.reset_backend()
    try:
        assert backends.get_backend() is None
        assert backends.get_backend_name() == "native"
        assert backends.has_backend() is False
    finally:
        backends.reset_backend()
        monkeypatch.delenv("BLINKY_COMPUTER_USE_BACKEND", raising=False)


def test_tools_gate_returns_failure_when_native(monkeypatch) -> None:
    import computer_use.backends as backends
    from computer_use.tools import list_windows_tool

    monkeypatch.setenv("BLINKY_COMPUTER_USE_BACKEND", "native")
    backends.reset_backend()
    try:
        result = list_windows_tool()
        # On Linux the gate is intentionally bypassed (linux_mcp owns that path).
        import platform

        if platform.system() == "Linux":
            assert result.tool == "list_windows"
        else:
            assert result.success is False
            assert "native path" in result.message
    finally:
        backends.reset_backend()
        monkeypatch.delenv("BLINKY_COMPUTER_USE_BACKEND", raising=False)


def test_actuator_result_helpers() -> None:
    from computer_use.actuator import _check_ok, _fail_result, _ok_result

    assert _check_ok(_ok_result("click")) is True
    assert _check_ok(_fail_result("click", "nope")) is False
    assert _ok_result("click", "done", x=1)["x"] == 1
    # A bare dict without an "ok" key is treated as success (legacy shape).
    assert _check_ok({"message": "legacy"}) is True


def test_minimized_window_marked_unsupported() -> None:
    backend, _ = make_backend(
        responses={
            "list_windows": {
                "windows": [
                    {
                        "title": "Minimized",
                        "app_name": "a.exe",
                        "pid": 1,
                        "window_id": 10,
                        "is_on_screen": True,
                        "minimized": True,
                        "bounds": {"x": -32000, "y": -32000, "width": 237, "height": 39},
                    },
                    {
                        "title": "Visible",
                        "app_name": "b.exe",
                        "pid": 2,
                        "window_id": 20,
                        "is_on_screen": True,
                        "minimized": False,
                        "bounds": {"x": 0, "y": 0, "width": 800, "height": 600},
                    },
                ]
            }
        }
    )

    windows = {w.title: w for w in backend.list_windows()}

    # A minimized window has no rendered content — capture and element walks
    # both come back empty, so it must not be offered as an actionable target.
    assert windows["Minimized"].supported is False
    assert windows["Visible"].supported is True


def test_degraded_snapshot_is_flagged() -> None:
    backend, _ = make_backend(
        responses={
            "get_window_state": {
                "snapshot_id": "s1",
                "degraded": True,
                "degraded_reason": "ax_tree_empty: the UIA walk returned no actionable elements.",
                "screenshot_error": "cannot capture minimized window",
                "window_bounds": {"x": -32000, "y": -32000, "width": 237, "height": 39},
                "elements": [],
            }
        }
    )

    elements = backend.get_window_elements("10", pid=1)

    assert elements == []
    assert backend.last_snapshot_degraded is not None
    assert "ax_tree_empty" in backend.last_snapshot_degraded["reason"]


def test_healthy_snapshot_clears_degraded_flag() -> None:
    backend, _ = make_backend(
        responses={
            "get_window_state": {
                "snapshot_id": "s2",
                "window_bounds": {"x": 0, "y": 0, "width": 100, "height": 100},
                "elements": [{"element_index": 0, "role": "Button", "label": "Go", "frame": {"x": 1, "y": 2, "w": 3, "h": 4}}],
            }
        }
    )

    backend.get_window_elements("20", pid=2)

    assert backend.last_snapshot_degraded is None


def test_get_app_state_surfaces_degradation() -> None:
    from computer_use import actuator

    class StubBackend:
        last_snapshot_degraded = {"reason": "ax_tree_empty"}

        def list_windows(self):
            from computer_use.backends.base import WindowInfo

            return [WindowInfo(title="Min", process="a.exe", pid=1, window_id="10", supported=False)]

        def get_active_window(self):
            return None

        def get_window_elements(self, window_id, pid=None):
            return []

    with patch.object(actuator, "_cua_backend", return_value=StubBackend()):
        state = actuator.get_app_state(app_name="a")

    assert state["elements"] == []
    assert state["degraded"] is True
    assert state["degraded_reason"] == "ax_tree_empty"


def test_resolve_target_window_prefers_supported() -> None:
    from computer_use import actuator
    from computer_use.backends.base import WindowInfo

    class StubBackend:
        def list_windows(self):
            return [
                WindowInfo(title="App (minimized)", process="app.exe", pid=1, window_id="1", supported=False),
                WindowInfo(title="App", process="app.exe", pid=2, window_id="2", supported=True),
            ]

        def get_active_window(self):
            return None

    chosen = actuator._resolve_target_window("app", StubBackend())

    assert chosen is not None
    assert chosen.window_id == "2"


# ── Live driver (skipped when absent) ──────────────────────────────


@pytest.mark.skipif(
    CuaDriverBackend()._binary is None,
    reason="cua-driver not installed",
)
def test_live_driver_health_and_screen_size() -> None:
    backend = CuaDriverBackend()

    assert backend.is_available() is True

    width, height = backend.screen_size()
    assert width > 0 and height > 0
    assert backend._scale_factor > 0


@pytest.mark.skipif(
    CuaDriverBackend()._binary is None,
    reason="cua-driver not installed",
)
def test_live_driver_lists_windows() -> None:
    backend = CuaDriverBackend()

    windows = backend.list_windows()

    assert isinstance(windows, list)
    for win in windows:
        assert win.title
        assert win.window_id
