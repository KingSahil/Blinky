"""
MCP client for computer-use-linux — connects to the persistent TCP bridge
managed by the Tauri backend (mcp_bridge.rs).

The bridge spawns `computer-use-linux mcp` once at app startup and keeps it
alive for the session. This ensures portal permissions prompt only once.

Protocol: line-delimited JSON-RPC 2.0 over TCP (same as stdin/stdout).
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.linux_mcp")

CONNECT_TIMEOUT = 5
CALL_TIMEOUT = 30


class LinuxMCPError(Exception):
    """Error from the computer-use-linux MCP server."""


class LinuxMCPClient:
    """MCP client connected to the persistent TCP bridge."""

    def __init__(self) -> None:
        self._sock: socket.socket | None = None
        self._sock_file: Any = None  # file-like wrapper for line reading
        self._lock = threading.Lock()
        self._request_id = 0
        self._tools: list[dict[str, Any]] = []
        self._started = False

    def _port_file(self) -> str:
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        return os.path.join(runtime, "blinky_mcp_port")

    def _read_port(self) -> int:
        port_file = self._port_file()
        if not os.path.exists(port_file):
            raise LinuxMCPError(
                f"MCP bridge not running. Port file missing: {port_file}"
            )
        with open(port_file) as f:
            return int(f.read().strip())

    def start(self) -> None:
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._start_impl()

    def _start_impl(self) -> None:
        port = self._read_port()

        LOGGER.info("Connecting to MCP bridge on 127.0.0.1:%d", port)

        # Retry in case the bridge thread hasn't bound the port yet
        last_err = None
        for attempt in range(10):
            try:
                self._sock = socket.create_connection(
                    ("127.0.0.1", port), timeout=CONNECT_TIMEOUT
                )
                break
            except (ConnectionRefusedError, OSError) as e:
                last_err = e
                if attempt < 9:
                    time.sleep(0.3)
        else:
            raise LinuxMCPError(
                f"Failed to connect to MCP bridge: {last_err}"
            )

        self._sock_file = self._sock.makefile("rw", buffering=1)

        try:
            self._initialize()
            self._fetch_tools()
            self._started = True
            LOGGER.info("MCP bridge ready (%d tools)", len(self._tools))
        except Exception:
            self.stop()
            raise

    def _initialize(self) -> None:
        init_result = self._rpc_call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "blinky", "version": "0.1.0"},
            },
        )
        LOGGER.debug("MCP initialize: %s", json.dumps(init_result, default=str))
        self._rpc_notify("notifications/initialized")

    def _fetch_tools(self) -> None:
        result = self._rpc_call("tools/list", {})
        self._tools = result.get("tools", [])

    def stop(self) -> None:
        with self._lock:
            if self._sock:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._sock.close()
                self._sock = None
                self._sock_file = None
            self._started = False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _rpc_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = self._next_id()
        request = json.dumps(
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        )
        return self._send_request(request, req_id, method)

    def _rpc_notify(self, method: str) -> None:
        self._send_raw(json.dumps({"jsonrpc": "2.0", "method": method}))

    def _send_raw(self, payload: str) -> None:
        assert self._sock
        self._sock.sendall((payload + "\n").encode())

    def _send_request(
        self, request: str, req_id: int, method: str
    ) -> dict[str, Any]:
        assert self._sock_file

        self._send_raw(request)

        deadline = time.monotonic() + CALL_TIMEOUT
        while time.monotonic() < deadline:
            line = self._sock_file.readline()
            if not line:
                raise LinuxMCPError(
                    f"MCP connection closed during {method}"
                )

            try:
                msg = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            msg_id = msg.get("id")
            if msg_id == req_id:
                if "error" in msg:
                    err = msg["error"]
                    raise LinuxMCPError(
                        f"MCP error {err.get('code')}: {err.get('message')}"
                    )
                return msg.get("result", {})

        raise TimeoutError(
            f"MCP call '{method}' timed out after {CALL_TIMEOUT}s"
        )

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        if not self._started:
            self.start()

        result = self._rpc_call(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
        content = result.get("content", [])
        if content and len(content) > 0:
            first = content[0]
            text = first.get("text", "")
            if text:
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text
        return result

    @property
    def tools(self) -> list[dict[str, Any]]:
        if not self._started:
            self.start()
        return self._tools

    @property
    def is_ready(self) -> bool:
        return self._started


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_client: LinuxMCPClient | None = None


def get_client() -> LinuxMCPClient:
    global _client
    if _client is None:
        _client = LinuxMCPClient()
    return _client


# ---------------------------------------------------------------------------
# High-level tool wrappers
# ---------------------------------------------------------------------------


def _check_ok(result: dict[str, Any]) -> bool:
    if isinstance(result, dict):
        return result.get("ok", result.get("success", True))
    return True


def list_windows() -> list[dict[str, Any]]:
    client = get_client()
    result = client.call_tool("list_windows", {})
    if isinstance(result, dict):
        return result.get("windows", [])
    return []


def list_apps() -> list[dict[str, Any]]:
    client = get_client()
    result = client.call_tool("list_apps", {})
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("apps", result.get("applications", []))
    return []


def get_app_state(
    app_name: str | None = None,
    target_pid: int | None = None,
    include_screenshot: bool = False,
    max_nodes: int = 200,
    max_depth: int = 6,
) -> dict[str, Any]:
    """Get accessibility tree.
    First calls MCP get_app_state to populate the click-element cache,
    then augments with absolute coordinates via KWin window positions."""
    import subprocess
    import os

    # Call MCP get_app_state first to populate the bridge's cache for click_element
    try:
        client = get_client()
        client.call_tool("get_app_state", {"app_name": app_name or "", "max_nodes": max_nodes, "max_depth": max_depth})
    except Exception:
        pass

    binary = os.path.expanduser("~/.cargo/bin/computer-use-linux")
    try:
        result = subprocess.run(
            [binary, "state", app_name or ""],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"elements": [], "windows": []}
        raw_elements = json.loads(result.stdout)
    except Exception:
        return {"elements": [], "windows": []}

    # Get window positions from KWin to compute absolute coordinates
    windows = list_windows()
    window_map: dict[int, dict] = {}
    for w in windows:
        pid = w.get("pid")
        if pid:
            window_map[pid] = w

    # Augment elements with absolute positions
    elements = []
    for e in raw_elements:
        node = dict(e)
        local_bounds = node.get("bounds")
        if local_bounds and isinstance(local_bounds, dict):
            # Try to find matching window by name/app_id
            for w in windows:
                app_id = str(w.get("app_id", "")).lower()
                title = str(w.get("title", "")).lower()
                node_name = str(node.get("name", "")).lower()
                if node_name and (node_name in app_id or node_name in title or app_id in node_name):
                    wb = w.get("bounds", {})
                    node["absolute_bounds"] = {
                        "x": wb.get("x", 0) + local_bounds.get("x", 0),
                        "y": wb.get("y", 0) + local_bounds.get("y", 0),
                        "width": local_bounds.get("width", 0),
                        "height": local_bounds.get("height", 0),
                    }
                    break
        elements.append(node)

    return {
        "elements": elements,
        "windows": windows,
        "raw_nodes": len(raw_elements),
    }


def click_element(
    index: int | None = None,
    role: str | None = None,
    name: str | None = None,
    x: int | None = None,
    y: int | None = None,
    app_id: str | None = None,
) -> dict[str, Any]:
    client = get_client()
    args: dict[str, Any] = {}
    if index is not None:
        args["element_index"] = index
    if role is not None:
        args["role"] = role
    if name is not None:
        args["name"] = name
    if x is not None and y is not None:
        args["x"] = x
        args["y"] = y
    if app_id:
        args["app_id"] = app_id

    return client.call_tool("click", args)


def type_text(
    text: str, target_app: str | None = None
) -> dict[str, Any]:
    client = get_client()
    args: dict[str, Any] = {"text": text}
    if target_app:
        args["app_id"] = target_app
    return client.call_tool("type_text", args)


def press_key(
    key: str, target_app: str | None = None
) -> dict[str, Any]:
    client = get_client()
    key_lower = key.lower().strip()

    typeable_chars = {"=", "+", "-", "*", "/", ".", ",", " "}
    if len(key_lower) == 1 and key_lower in typeable_chars:
        return type_text(key, target_app=target_app)

    key_map = {
        "esc": "escape",
        "return": "enter",
        "del": "delete",
        "backspace": "backspace",
        " ": "space",
    }
    normalized = key_map.get(key_lower, key_lower)
    args: dict[str, Any] = {"key": normalized}
    if target_app:
        args["app_id"] = target_app
    return client.call_tool("press_key", args)


def screenshot() -> dict[str, Any]:
    client = get_client()
    return client.call_tool("screenshot", {})


def get_focused_window_bounds() -> dict | None:
    """Thin wrapper around wayland_vision.get_active_window_bounds().

    Adds MCP-specific error handling. Returns None if the window bounds
    cannot be obtained (no focused window, MCP not running, etc.).
    """
    try:
        from wayland_vision import get_active_window_bounds
        bounds = get_active_window_bounds()
        LOGGER.info("get_active_window_bounds returned: %s", bounds)
        if bounds and isinstance(bounds, dict):
            required = {"x", "y", "width", "height"}
            if required.issubset(bounds.keys()):
                return {
                    "x": int(bounds["x"]),
                    "y": int(bounds["y"]),
                    "width": int(bounds["width"]),
                    "height": int(bounds["height"]),
                    "title": bounds.get("title", ""),
                    "app_id": bounds.get("app_id", ""),
                }
            else:
                LOGGER.warning("get_active_window_bounds: missing required keys. Got: %s", list(bounds.keys()))
    except Exception as e:
        LOGGER.warning("get_focused_window_bounds failed: %s", e)
    return None


def doctor() -> dict[str, Any]:
    client = get_client()
    return client.call_tool("doctor", {})


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

import atexit


@atexit.register
def _stop_client() -> None:
    global _client
    if _client is not None:
        _client.stop()
        _client = None
