from __future__ import annotations

import os
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from PIL import Image, ImageGrab

from utils.logging import get_logger

LOGGER = get_logger("blinky.capture")


class CaptureError(Exception):
    pass


class PermissionDeniedError(CaptureError):
    pass


class TimeoutError(CaptureError):
    pass


class CaptureStrategy(ABC):
    @abstractmethod
    def capture(self) -> Image.Image:
        pass


class LinuxCaptureStrategy(CaptureStrategy):
    def capture(self) -> Image.Image:
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        LOGGER.info("Linux session detected: %s", session_type)

        try:
            temp_path = Path("tmp") / "gnome-screenshot-temp.png"
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            env_copy = {}
            for key in ["DBUS_SESSION_BUS_ADDRESS", "PATH", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "USER", "HOME", "XDG_SESSION_TYPE"]:
                if key in os.environ:
                    env_copy[key] = os.environ[key]
            res = subprocess.run(
                ["gnome-screenshot", "-f", str(temp_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                env=env_copy
            )
            if temp_path.exists():
                img = Image.open(temp_path)
                img.load()
                temp_path.unlink()
                LOGGER.info("Captured screen via gnome-screenshot")
                return img
        except Exception as exc:
            LOGGER.debug("gnome-screenshot capture failed: %s", exc)

        for tool in ["maim", "scrot"]:
            try:
                temp_path = Path("tmp") / f"{tool}-temp.png"
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run([tool, str(temp_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if temp_path.exists():
                    img = Image.open(temp_path)
                    img.load()
                    temp_path.unlink()
                    LOGGER.info("Captured screen via %s", tool)
                    return img
            except Exception as exc:
                LOGGER.debug("%s capture failed: %s", tool, exc)

        LOGGER.info("Falling back to standard PIL ImageGrab")
        return ImageGrab.grab(all_screens=False)


class WaylandPortalIPCOrchestrator:
    def __init__(self, timeout_seconds: int = 15):
        self.timeout_seconds = timeout_seconds

    def capture_via_portal(self) -> Path:
        try:
            return self._capture_via_python_dbus()
        except ImportError:
            LOGGER.debug("dbus-python or PyGObject not available; falling back to CLI dbus wrapper.")
            return self._capture_via_cli_dbus()

    def _capture_via_python_dbus(self) -> Path:
        import dbus
        import uuid
        import urllib.parse
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib

        DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()

        def try_capture(interactive_mode):
            token = f"blinky_{uuid.uuid4().hex}"
            try:
                portal = bus.get_object('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop')
                screenshot_iface = dbus.Interface(portal, 'org.freedesktop.portal.Screenshot')
            except Exception as e:
                return False, f"Failed to access XDG Desktop Portal: {e}"

            options = {
                'interactive': dbus.Boolean(interactive_mode),
                'handle_token': dbus.String(token)
            }

            loop = GLib.MainLoop()
            result = {'response': None, 'results': None}

            sender = bus.get_unique_name().replace(':', '').replace('.', '_')
            request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

            def signal_handler(response_code, results):
                result['response'] = int(response_code)
                result['results'] = results
                loop.quit()

            signal_match = bus.add_signal_receiver(
                signal_handler,
                signal_name="Response",
                dbus_interface="org.freedesktop.portal.Request",
                path=request_path
            )

            try:
                screenshot_iface.Screenshot("", options)
            except Exception as e:
                signal_match.remove()
                return False, f"Failed to call Screenshot method: {e}"

            timed_out = [False]
            def timeout_callback():
                timed_out[0] = True
                loop.quit()
                return False

            GLib.timeout_add_seconds(self.timeout_seconds, timeout_callback)

            try:
                loop.run()
            finally:
                signal_match.remove()

            if timed_out[0]:
                return False, "Timeout"

            response_code = result['response']
            if response_code is None:
                return False, "No response received"

            if response_code == 1:
                return False, "PermissionDenied"
            elif response_code != 0:
                return False, f"Portal error code {response_code}"

            results = result['results']
            if not results or 'uri' not in results:
                return False, "No URI found in results"

            return True, str(results['uri'])

        success, res_val = try_capture(False)
        if not success:
            if res_val == "PermissionDenied":
                raise PermissionDeniedError("Screen capture permission was denied by the user.")
            LOGGER.info("Non-interactive portal screenshot failed (%s). Retrying with interactive prompt...", res_val)
            success, res_val = try_capture(True)
            if not success:
                if res_val == "PermissionDenied":
                    raise PermissionDeniedError("Screen capture permission was denied by the user.")
                elif res_val == "Timeout":
                    raise TimeoutError("Wayland Portal screen capture request timed out.")
                else:
                    raise CaptureError(f"Wayland Portal capture failed: {res_val}")

        uri = res_val
        parsed = urllib.parse.urlparse(uri)
        return Path(urllib.parse.unquote(parsed.path))

    def _capture_via_cli_dbus(self) -> Path:
        import urllib.parse

        inline_code = f"""
import sys
import os
import dbus
import uuid
import urllib.parse
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

try:
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    
    def try_capture(interactive_mode):
        token = "blinky_" + uuid.uuid4().hex
        portal = bus.get_object('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop')
        screenshot_iface = dbus.Interface(portal, 'org.freedesktop.portal.Screenshot')

        options = {{
            'interactive': dbus.Boolean(interactive_mode),
            'handle_token': dbus.String(token)
        }}

        loop = GLib.MainLoop()
        result = {{'response': None, 'results': None}}

        sender = bus.get_unique_name().replace(':', '').replace('.', '_')
        request_path = f"/org/freedesktop/portal/desktop/request/{{sender}}/{{token}}"

        def signal_handler(response_code, results):
            result['response'] = int(response_code)
            result['results'] = results
            loop.quit()

        signal_match = bus.add_signal_receiver(
            signal_handler,
            signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            path=request_path
        )

        try:
            screenshot_iface.Screenshot("", options)
        except Exception as e:
            signal_match.remove()
            return False, f"Call failed: {{e}}"

        timed_out = [False]
        def timeout_callback():
            timed_out[0] = True
            loop.quit()
            return False

        GLib.timeout_add_seconds({self.timeout_seconds}, timeout_callback)
        loop.run()
        signal_match.remove()

        if timed_out[0]:
            return False, "Timeout"
        if result['response'] == 1:
            return False, "PermissionDenied"
        if result['response'] != 0:
            return False, f"Portal error code {{result['response']}}"
        if not result['results'] or 'uri' not in result['results']:
            return False, "No URI returned"

        return True, str(result['results']['uri'])

    success, res_val = try_capture(False)
    if not success:
        if res_val == "PermissionDenied":
            print("ERROR: PermissionDenied", file=sys.stderr)
            sys.exit(3)
        else:
            success, res_val = try_capture(True)
            if not success:
                if res_val == "PermissionDenied":
                    print("ERROR: PermissionDenied", file=sys.stderr)
                    sys.exit(3)
                elif res_val == "Timeout":
                    print("ERROR: Timeout", file=sys.stderr)
                    sys.exit(2)
                else:
                    print(f"ERROR: {{res_val}}", file=sys.stderr)
                    sys.exit(4)

    uri = res_val
    parsed = urllib.parse.urlparse(uri)
    path = urllib.parse.unquote(parsed.path)
    print(path)
    sys.exit(0)
except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
    sys.exit(1)
"""

        try:
            env_copy = {}
            for key in ["DBUS_SESSION_BUS_ADDRESS", "PATH", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "USER", "HOME", "XDG_SESSION_TYPE"]:
                if key in os.environ:
                    env_copy[key] = os.environ[key]

            res = subprocess.run(
                ["/usr/bin/python3", "-c", inline_code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                shell=False,
                env=env_copy
            )
            captured_path = Path(res.stdout.strip())
            return captured_path
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip()
            if "PermissionDenied" in err_msg:
                raise PermissionDeniedError("Screen capture permission was denied by the user.")
            elif "Timeout" in err_msg:
                raise TimeoutError("Wayland Portal screen capture request timed out.")
            else:
                raise CaptureError(f"System python capture helper failed: {err_msg}")


class WaylandPortalCaptureStrategy:
    def __init__(self, orchestrator: WaylandPortalIPCOrchestrator = None):
        self.orchestrator = orchestrator or WaylandPortalIPCOrchestrator()

    def capture(self) -> Image.Image:
        temp_path = None
        try:
            temp_path = self.orchestrator.capture_via_portal()
            if not temp_path or not temp_path.exists():
                raise CaptureError("Portal captured file does not exist or was not returned.")

            with open(temp_path, "rb") as f:
                img_data = f.read()

            from io import BytesIO
            with Image.open(BytesIO(img_data)) as img:
                img.load()
                return img.copy()
        except Exception as e:
            if isinstance(e, (PermissionDeniedError, TimeoutError, CaptureError)):
                raise e
            raise CaptureError(f"Wayland Portal capture failed: {e}")
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as ex:
                    LOGGER.warning(f"Failed to delete temporary portal capture file {temp_path}: {ex}")


class KWinGrimCaptureStrategy(CaptureStrategy):
    """Capture only the active window's bounding box using grim on Wayland KDE.
    No portal permission prompts needed — grim captures directly via wlroots."""

    def capture(self) -> Image.Image:
        try:
            from window_linux import _kwin_active_window
            win = _kwin_active_window()
        except ImportError:
            win = None

        if not win or not win.get("width"):
            raise CaptureError("KWin active window not available for grim capture")

        x, y, w, h = win["x"], win["y"], win["width"], win["height"]
        temp_path = Path("tmp") / "wayland_crop.png"
        temp_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run(
                ["grim", "-g", f"{x},{y} {w}x{h}", str(temp_path)],
                check=True, capture_output=True, timeout=10,
            )
        except FileNotFoundError:
            raise CaptureError(
                "grim not installed. Install with: sudo dnf install grim"
            )
        except subprocess.CalledProcessError as e:
            raise CaptureError(f"grim capture failed: {e.stderr.decode()}")

        if not temp_path.exists():
            raise CaptureError("grim did not produce output file")

        img = Image.open(temp_path)
        img.load()
        temp_path.unlink()
        LOGGER.info("Captured active window via grim: (%d,%d %dx%d)", x, y, w, h)
        return img


class LinuxCaptureStrategyFactory:
    _cached_portal_available = None

    @classmethod
    def is_portal_available(cls) -> bool:
        if cls._cached_portal_available is not None:
            return cls._cached_portal_available

        if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
            cls._cached_portal_available = False
            return False

        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            bus.get_object('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop')
            cls._cached_portal_available = True
            return True
        except Exception:
            pass

        try:
            res = subprocess.run(
                ["gdbus", "introspect", "--session", "--dest", "org.freedesktop.portal.Desktop", "--object-path", "/org/freedesktop/portal/desktop"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2,
                shell=False
            )
            cls._cached_portal_available = (res.returncode == 0)
        except Exception:
            cls._cached_portal_available = False

        return cls._cached_portal_available

    @classmethod
    def get_strategy(cls):
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        is_wayland = (session_type == "wayland" or bool(wayland_display))

        if is_wayland:
            # Try grim-based cropped capture first (no portal prompts)
            try:
                subprocess.run(["which", "grim"], capture_output=True, check=True, timeout=2)
                LOGGER.info("Wayland detected, grim available. Using KWinGrimCaptureStrategy.")
                return KWinGrimCaptureStrategy()
            except Exception:
                LOGGER.debug("grim not available on Wayland")

            if cls.is_portal_available():
                LOGGER.info("Wayland session detected and Desktop Portal is available. Using WaylandPortalCaptureStrategy.")
                return WaylandPortalCaptureStrategy()
            else:
                LOGGER.warning("Wayland session detected but Desktop Portal is NOT available. Falling back to default Linux stack.")

        return LinuxCaptureStrategy()
