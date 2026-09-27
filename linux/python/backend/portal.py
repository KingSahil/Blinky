"""XDG Desktop Portal screenshot capture (compositor-agnostic fallback).

Salvaged and compacted from the old linux_capture.py — the portal is the
portable path that works on any Wayland compositor (Hyprland, GNOME, KDE)
at the cost of a permission prompt. Used only when grim is unavailable.
"""

from __future__ import annotations

import os
import subprocess
import sys
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


def capture_via_portal(timeout_seconds: int = 15, interactive: bool = True) -> Path:
    """Capture via org.freedesktop.portal.Screenshot; return the temp file path.

    interactive=True lets GNOME/KDE show the user-consent dialog (non-interactive
    Screenshot requests are DENIED by xdg-desktop-portal-gnome). This is the
    first capture on a new compositor; subsequent ones may be remembered.
    """
    try:
        return _capture_python_dbus(timeout_seconds, interactive=interactive)
    except ImportError:
        LOGGER.debug("dbus-python/PyGObject missing; using CLI dbus helper")
        return _capture_cli_dbus(timeout_seconds, interactive=interactive)


def activate_window(window_id: str) -> bool:
    """Best-effort focus via per-DE DBus paths that don't need consent.

    Tries:
      - GNOME: org.gnome.Shell.Eval (focus by app id/title)
      - KDE:   org.kde.KWin (activateWindow via script)
    Returns True on any success. Falls back gracefully.
    """
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    try:
        if "gnome" in de or "ubuntu" in de:
            return _gnome_activate(window_id)
        if "kde" in de or "plasma" in de:
            return _kde_activate(window_id)
    except Exception as exc:
        LOGGER.debug("activate_window (%s) failed: %s", de, exc)
    return False


def _gnome_activate(window_id: str) -> bool:
    """GNOME: org.gnome.Shell.Eval — search window actors by title/meta info."""
    hashed_title = window_id.split(":", 1)[-1] if ":" in window_id else window_id
    js = (
        "global.get_window_actors().find(a => { const t = "
        "a.meta_window.get_title() || ''; const wm = "
        "a.meta_window.get_wm_class() || ''; return "
        f"(t.includes({hashed_title!r}) || wm.includes({hashed_title!r})); "
        "})?.meta_window.activate(global.get_current_time()) ?? false"
    )
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.gnome.Shell",
             "--object-path", "/org/gnome/Shell",
             "--method", "org.gnome.Shell.Eval", js],
            capture_output=True, text=True, timeout=6,
        )
        return result.returncode == 0 and "false" not in result.stdout
    except Exception as exc:
        LOGGER.debug("gnome activate failed: %s", exc)
        return False


def _kde_activate(window_id: str) -> bool:
    """KDE: KWin scripting DBus — activateWindow by caption or atomId."""
    hashed = window_id.split(":", 1)[-1] if ":" in window_id else window_id
    script = (
        "const w = workspace.windowList().find(win => "
        f"win.caption.includes('{hashed}') || String(win.atomId) === '{hashed}'); "
        "if (w) { w.activate(); call('done'); } else { call('miss'); }"
    )
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.kde.KWin",
             "--object-path", "/KWin",
             "--method", "org.kde.KWin.Scripting.loadScript", script, str(uuid.uuid4())],
            capture_output=True, text=True, timeout=6,
        )
        return result.returncode == 0 and "miss" not in result.stdout
    except Exception as exc:
        LOGGER.debug("kde activate failed: %s", exc)
        return False


def _capture_python_dbus(timeout_seconds: int, interactive: bool = True) -> Path:
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
            "",
            {
                "interactive": dbus.Boolean(interactive),
                "handle_token": dbus.String(token),
            },
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


def _capture_cli_dbus(timeout_seconds: int, interactive: bool = True) -> Path:
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
    iface.Screenshot('', {{'interactive': dbus.Boolean({interactive}), 'handle_token': dbus.String(token)}})
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


# ── ScreenCast portal → PipeWire (GNOME/KDE Wayland native capture) ────
# GNOME 50 gates the shell Screenshot API and auto-denies headless portal
# Screenshot requests. The sanctioned path is the ScreenCast portal, which
# gives a PipeWire stream after one consent prompt — exactly what GNOME's own
# screen recorder uses.


def screen_cast_capture(timeout_seconds: int = 30) -> Path:
    """Full portal ScreenCast session → PipeWire → one 60fps frame as PNG.

    Returns a temp PNG path. Raises PermissionDeniedError if the user denies
    the shared-screen consent dialog.
    """
    import subprocess
    import tempfile
    import uuid

    token = f"blinky_{uuid.uuid4().hex[:8]}"
    bus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")

    inline = (
        """
import sys, json, uuid, os, subprocess, tempfile
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
portal = bus.get_object('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop')

def wait_response(iface, token):
    loop = GLib.MainLoop()
    out = {'r': None}
    sender = bus.get_unique_name().replace(':', '').replace('.', '_')
    path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
    def cb(code, results):
        out['r'] = (int(code), results); loop.quit()
    m = bus.add_signal_receiver(cb, signal_name='Response',
        dbus_interface='org.freedesktop.portal.Request', path=path)
    GLib.timeout_add_seconds(_TIMEOUT, lambda: (loop.quit(), False)[1])
    loop.run(); m.remove()
    if out['r'] is None:
        raise RuntimeError('portal response timeout')
    return out['r']

sc = dbus.Interface(portal, 'org.freedesktop.portal.ScreenCast')
# 1. CreateSession(options) — single a{sv} arg with handle_token
code, res = wait_response(
    sc.CreateSession(dbus.Dictionary({'handle_token': dbus.String('sc1')}, 'sv')),
    'sc1')
if code != 0:
    print('ERR session', code, file=sys.stderr); sys.exit(3)
session = str(res.get('session_handle', ''))

# 2. SelectSources(session, sources a{sv}, options a{sv})
wait_response(sc.SelectSources(session,
    dbus.Dictionary({'types': dbus.UInt32(0x1)}, 'sv'),
    dbus.Dictionary({'handle_token': dbus.String('sc2')}, 'sv')), 'sc2')

# 3. Start(session, parent_window '', options) → PipeWire node
code, res = wait_response(sc.Start(session, '',
    dbus.Dictionary({'handle_token': dbus.String('sc3')}, 'sv')), 'sc3')
if code != 0:
    print('ERR start', code, file=sys.stderr); sys.exit(4)
streams = res.get('streams', [])
if not streams:
    print('ERR no streams', file=sys.stderr); sys.exit(5)
node_id = int(streams[0][0])
pipewire_fd = None
for k, v in res.items():
    pass
# 4. gst: grab one frame from the PipeWire node
out_path = tempfile.mktemp(suffix='.png', prefix='blinky_sc_')
pipeline = (
    'pipewiresrc path=%(path)s keepalive-time=0 num-buffers=1 '
    '! videoconvert ! pngenc ! filesink location=%(out)s'
).replace('%(path)s', str(node_id)).replace('%(out)s', out_path)
rc = subprocess.run(['gst-launch-1.0', '-q'] + pipeline.split(),
    capture_output=True, timeout=_TIMEOUT)
if rc.returncode != 0:
    print('ERR gst', rc.stderr.decode(errors='replace')[-300:], file=sys.stderr); sys.exit(6)
print(out_path)
"""
    ).replace('_TIMEOUT', str(timeout_seconds))

    env_copy = {
        "DBUS_SESSION_BUS_ADDRESS": bus_addr,
        "DISPLAY": os.environ.get("DISPLAY", ""),
        "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", ""),
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", ""),
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    try:
        res = subprocess.run(
            [sys.executable, "-c", inline],
            capture_output=True, text=True, timeout=timeout_seconds + 10,
            env=env_copy,
        )
    except subprocess.TimeoutExpired:
        raise PortalCaptureError("ScreenCast capture timed out")
    if res.returncode != 0:
        err = res.stderr.strip()
        if "ERR session" in err:
            raise PermissionDeniedError("ScreenCast session permission denied")
        if "ERR start" in err:
            raise PermissionDeniedError("ScreenCast stream permission denied")
        raise PortalCaptureError(f"ScreenCast failed: {err[-200:]}")
    path = Path(res.stdout.strip())
    if not path.exists():
        raise PortalCaptureError("ScreenCast produced no file")
    return path
