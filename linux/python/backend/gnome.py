"""GnomeBackend — GNOME Shell (Mutter) desktop automation via AT-SPI + portal.

Same ComputerUseBackend contract as HyprlandBackend. The compositor-specific
pieces are isolated:
  - Windows/elements: AT-SPI (GNOME exposes a full a11y tree)
  - Capture: XDG portal screenshot (no grim on GNOME Wayland by default)
  - Input: ydotool/wtype (uinput — compositor-agnostic), xdotool when XWayland
  - Focus: org.gnome.Shell.Eval (portal.activate_window path)

Everything degrades gracefully — is_available() is the honest gate; callers
fall back to OCR/hyprctl paths when GNOME-specific sources are missing.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from utils.logging import get_logger

from .abc import ActionResult, ComputerUseBackend, Screenshot, UIElement, WindowInfo
from . import atspi
from .capture import WaylandPortalCaptureStrategy

LOGGER = get_logger("blinky.backend.gnome")


class GnomeBackend(ComputerUseBackend):
    """Desktop automation backend for GNOME Shell (Mutter, Wayland)."""

    def __init__(self) -> None:
        self._started = False

    # ── Lifecycle ──────────────────────────────────────────────
    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def is_available(self) -> bool:
        """GNOME is present if the shell DBus name resolves OR AT-SPI has apps."""
        import shutil
        import subprocess

        if shutil.which("gdbus"):
            try:
                result = subprocess.run(
                    ["gdbus", "call", "--session", "--dest", "org.gnome.Shell",
                     "--object-path", "/org/gnome/Shell", "--method",
                     "org.freedesktop.DBus.Peer.Ping"],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0:
                    LOGGER.info("GNOME Shell detected via DBus")
                    return True
            except Exception:
                pass
        return atspi.is_available()

    # ── Screen ──────────────────────────────────────────────────
    def capture(self, *, window: bool = False) -> Screenshot:
        strategy = WaylandPortalCaptureStrategy()
        image = strategy.capture()

        captures_dir = Path("screenshots")
        captures_dir.mkdir(parents=True, exist_ok=True)
        path = captures_dir / f"screen-gnome-{int(time.time() * 1000)}.jpg"

        screen_w, screen_h = image.width, image.height
        try:
            resample = image.Resampling.LANCZOS
        except AttributeError:
            resample = image.LANCZOS
        image.thumbnail((1920, 1080), resample=resample)
        image = image.convert("RGB")
        image.save(path, format="JPEG", quality=75, optimize=True)

        return Screenshot(
            path=path,
            width=image.width,
            height=image.height,
            screen_width=screen_w,
            screen_height=screen_h,
        )

    def screen_size(self) -> tuple[int, int]:
        # Best effort: from portal ImageGrab width/height (whole screen)
        try:
            import subprocess

            result = subprocess.run(
                ["xdpyinfo"], capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "dimensions:" in line:
                        dims = line.split("dimensions:")[1].split()[0]
                        w, h = dims.split("x")
                        return int(w), int(h)
        except Exception:
            pass
        return 1920, 1080

    # ── Windows / apps ──────────────────────────────────────────
    def get_active_window(self) -> WindowInfo | None:
        return atspi.get_active_window()

    def list_windows(self) -> list[WindowInfo]:
        return atspi.list_windows()

    def list_apps(self) -> list[dict[str, object]]:
        from .apps import scan_apps

        return [
            {
                "name": e.name,
                "desktop_id": e.desktop_id,
                "exec": e.exec_line,
                "startup_wm_class": e.startup_wm_class,
                "source": e.source,
            }
            for e in scan_apps()
        ]

    def launch_app(self, app_name: str) -> ActionResult:
        from .apps import launch_by_name

        return launch_by_name(app_name)

    # ── Elements (AT-SPI tree — GNOME exposes full a11y) ────────
    def get_elements(self, pid: int | None = None) -> list["UIElement"]:
        return atspi.get_elements(pid=pid)

    # ── Input (ydotool/wtype are compositor-agnostic) ───────────
    def click(
        self,
        *,
        x: int,
        y: int,
        button: str = "left",
        click_count: int = 1,
    ) -> ActionResult:
        from .input import click as _click

        return _click(x, y, button=button, click_count=click_count)

    def scroll(
        self,
        *,
        direction: str,
        amount: int = 3,
        x: int | None = None,
        y: int | None = None,
    ) -> ActionResult:
        from .input import scroll as _scroll

        return _scroll(direction, amount=amount, x=x, y=y)

    def type_text(self, text: str) -> ActionResult:
        from .input import type_text as _type_text

        return _type_text(text)

    def key(self, keys: str) -> ActionResult:
        from .input import key as _key

        return _key(keys)

    def focus_window(self, window_id: str) -> ActionResult:
        from .input import focus_window as _focus_window

        return _focus_window(window_id)

    def system_profile_hint(self) -> str:
        """GNOME-specific guidance for the system prompt."""
        return (
            "- Focus model: click-to-focus (GNOME). mouse(click) a window to focus it."
        )


# ── Singleton accessor ──────────────────────────────────────────────

_backend: GnomeBackend | None = None


def get_backend() -> GnomeBackend:
    global _backend
    if _backend is None:
        _backend = GnomeBackend()
    return _backend
