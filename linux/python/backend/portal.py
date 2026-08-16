"""XDG Desktop Portal screenshot capture (compositor-agnostic fallback).

Salvaged and compacted from the old linux_capture.py — the portal is the
portable path that works on any Wayland compositor (Hyprland, GNOME, KDE)
at the cost of a permission prompt. Used only when grim is unavailable.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from utils.logging import get_logger

LOGGER = get_logger("blinky.backend.portal")


class PermissionDeniedError(Exception):
    pass


class TimeoutError(Exception):
    pass


class PortalCaptureError(Exception):
    pass


def capture_via_portal(timeout_seconds: int = 15) -> Path:
    """Capture via org.freedesktop.portal.Screenshot; return the temp file path."""
    try:
        return _capture_python_dbus(timeout_seconds)
    except ImportError:
        LOGGER.debug("dbus-python/PyGObject missing; using CLI dbus helper")
        return _capture_cli_dbus(timeout_seconds)


def _capture_python_dbus(timeout_seconds: int) -> Path:
    import urllib.parse

    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    token = f"blinky_{uuid.uuid4().hex}"
    portal = bus.get_object(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
    )
    screenshot_iface = dbus.Interface(portal, "org.freedesktop.portal.Screenshot")

    result: dict = {"response": None, "results": None}
    loop = GLib.MainLoop()
    sender = bus.get_unique_name().replace(":", "").replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    def signal_handler(response_code, results):
        result["response"] = int(response_code)
        result["results"] = results
        loop.quit()

    signal_match = bus.add_signal_receiver(
        signal_handler,
        signal_name="Response",
        dbus_interface="org.freedesktop.portal.Request",
        path=request_path,
    )

    try:
        screenshot_iface.Screenshot(
            "", {"interactive": dbus.Boolean(False), "handle_token": dbus.String(token)}
        )
    except Exception as e:
        signal_match.remove()
        raise PortalCaptureError(f"Failed to call Screenshot method: {e}")

    timed_out = [False]

    def timeout_callback():
        timed_out[0] = True
        loop.quit()
        return False

    GLib.timeout_add_seconds(timeout_seconds, timeout_callback)
    loop.run()
    signal_match.remove()

    if timed_out[0]:
        raise TimeoutError("Portal screenshot timed out")
    if result["response"] == 1:
        raise PermissionDeniedError("Screen capture permission denied by user")
    if result["response"] != 0:
        raise PortalCaptureError(f"Portal error code {result['response']}")

    results = result["results"] or {}
    uri = results.get("uri")
    if not uri:
        raise PortalCaptureError("No URI returned by portal")
    return Path(urllib.parse.unquote(urllib.parse.urlparse(str(uri)).path))


def _capture_cli_dbus(timeout_seconds: int) -> Path:
    """Fallback: spawn system python3 with an inline portal helper."""
    import urllib.parse

    inline_code = f"""
import sys, dbus, uuid, urllib.parse
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
try:
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    token = "blinky_" + uuid.uuid4().hex
    portal = bus.get_object('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop')
    iface = dbus.Interface(portal, 'org.freedesktop.portal.Screenshot')
    loop = GLib.MainLoop()
    result = {{'response': None, 'results': None}}
    sender = bus.get_unique_name().replace(':', '').replace('.', '_')
    path = f"/org/freedesktop/portal/desktop/request/{{sender}}/{{token}}"
    def handler(code, results):
        result['response'] = int(code); result['results'] = results; loop.quit()
    match = bus.add_signal_receiver(handler, signal_name='Response',
        dbus_interface='org.freedesktop.portal.Request', path=path)
    iface.Screenshot('', {{'interactive': dbus.Boolean(False), 'handle_token': dbus.String(token)}})
    GLib.timeout_add_seconds({timeout_seconds}, lambda: (loop.quit(), False)[1])
    loop.run(); match.remove()
    if result['response'] == 1: print('ERROR: PermissionDenied', file=sys.stderr); sys.exit(3)
    if result['response'] != 0: print('ERROR: portal', result['response'], file=sys.stderr); sys.exit(4)
    uri = (result['results'] or {{}}).get('uri')
    if not uri: print('ERROR: no uri', file=sys.stderr); sys.exit(5)
    print(urllib.parse.unquote(urllib.parse.urlparse(uri).path))
except Exception as e:
    print(f'ERROR: {{e}}', file=sys.stderr); sys.exit(1)
"""
    env_copy = {k: v for k, v in os.environ.items() if k in (
        "DBUS_SESSION_BUS_ADDRESS", "PATH", "DISPLAY", "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR", "USER", "HOME", "XDG_SESSION_TYPE",
    )}
    try:
        res = subprocess.run(
            ["/usr/bin/python3", "-c", inline_code],
            capture_output=True, text=True, check=True, shell=False, env=env_copy,
        )
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip()
        if "PermissionDenied" in err:
            raise PermissionDeniedError("Screen capture permission denied by user")
        raise PortalCaptureError(f"Portal helper failed: {err}")

    path = Path(res.stdout.strip())
    if not path.exists():
        raise PortalCaptureError("Portal produced no file")
    return path
