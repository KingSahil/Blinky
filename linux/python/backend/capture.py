"""Screen capture strategies for Blinky on Linux (Hyprland-first).

Cascade (Phase 1):
  1. GrimFullscreenCaptureStrategy — wlroots-native, no portal prompt on Hyprland
  2. GrimWindowCropCaptureStrategy — active-window crop via hyprctl bounds
  3. WaylandPortalCaptureStrategy — compositor-agnostic fallback (salvaged
     from the old linux_capture.py; needed for GNOME/KDE in phase 8)

grim is preferred over portal because it is headless, deterministic, and
prompt-free on Hyprland; the portal is retained as the portable fallback.
"""

from __future__ import annotations

import os
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image
from utils.logging import get_logger

from .window import get_active_window, get_monitors

LOGGER = get_logger("blinky.backend.capture")


class CaptureError(Exception):
    pass


class CaptureStrategy(ABC):
    @abstractmethod
    def capture(self) -> Image.Image:
        pass


# ── grim strategies (wlroots-native, Hyprland-first) ─────────────────


class GrimFullscreenCaptureStrategy(CaptureStrategy):
    """Full-screen capture via grim (no portal prompt on wlroots compositors)."""

    def capture(self) -> Image.Image:
        monitors = get_monitors()
        if not monitors:
            raise CaptureError("No monitor geometry available for grim capture")

        # Single monitor: grim without args captures the whole output set.
        # Multi-monitor: capture each monitor and stitch horizontally.
        if len(monitors) == 1:
            return self._grim(["-o", monitors[0]["name"]])

        images: list[Image.Image] = []
        for m in sorted(monitors, key=lambda mm: mm["x"]):
            images.append(self._grim(["-o", m["name"]]))
        if not images:
            raise CaptureError("grim produced no frames")
        width = sum(img.width for img in images)
        height = max(img.height for img in images)
        canvas = Image.new("RGB", (width, height))
        x = 0
        for img in images:
            canvas.paste(img, (x, 0))
            x += img.width
        return canvas

    def _grim(self, extra_args: list[str]) -> Image.Image:
        try:
            result = subprocess.run(
                ["grim", *extra_args, "-"],
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            raise CaptureError("grim not installed. Install with: sudo pacman -S grim")
        except subprocess.TimeoutExpired:
            raise CaptureError("grim capture timed out")
        if result.returncode != 0 or not result.stdout:
            raise CaptureError(f"grim capture failed: {result.stderr.decode(errors='replace')}")

        from io import BytesIO

        with Image.open(BytesIO(result.stdout)) as img:
            img.load()
            return img.copy()


class GrimWindowCropCaptureStrategy(CaptureStrategy):
    """Capture only the active window's bounding box (grim + hyprctl bounds)."""

    def capture(self) -> Image.Image:
        win = get_active_window()
        if not win or not win.width or not win.height:
            raise CaptureError("Active window not available for grim crop")

        # Scale-aware: grim geometry is in physical px; hyprctl bounds are logical.
        scale = 1.0
        monitors = get_monitors()
        for m in monitors:
            if m["x"] <= win.x < m["x"] + m["width"]:
                scale = m["scale"]
                break

        x = int(win.x * scale)
        y = int(win.y * scale)
        w = int(win.width * scale)
        h = int(win.height * scale)

        try:
            result = subprocess.run(
                ["grim", "-g", f"{x},{y} {w}x{h}", "-"],
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            raise CaptureError("grim not installed")
        except subprocess.TimeoutExpired:
            raise CaptureError("grim window crop timed out")
        if result.returncode != 0 or not result.stdout:
            raise CaptureError(f"grim window crop failed: {result.stderr.decode(errors='replace')}")

        from io import BytesIO

        with Image.open(BytesIO(result.stdout)) as img:
            img.load()
            return img.copy()


# ── Portal fallback (salvaged from linux_capture.py, compositor-agnostic) ──


class WaylandPortalCaptureStrategy(CaptureStrategy):
    """XDG Desktop Portal screenshot — portable fallback for GNOME/KDE.

    interactive=True lets the DE show the user-consent dialog (non-interactive
    Screenshot requests are denied by xdg-desktop-portal-gnome).
    """

    def __init__(self, timeout_seconds: int = 15):
        self.timeout_seconds = timeout_seconds

    def capture(self) -> Image.Image:
        from .portal import capture_via_portal

        path = capture_via_portal(timeout_seconds=self.timeout_seconds, interactive=True)
        with Image.open(path) as img:
            img.load()
            return img.copy()


# ── Fallback chain ────────────────────────────────────────────────────


class FallbackCaptureStrategy(CaptureStrategy):
    def __init__(self, strategies: list[CaptureStrategy]):
        self.strategies = strategies

    def capture(self) -> Image.Image:
        errors: list[str] = []
        for strategy in self.strategies:
            try:
                image = strategy.capture()
                LOGGER.info("Captured screen with %s", strategy.__class__.__name__)
                return image
            except Exception as exc:
                errors.append(f"{strategy.__class__.__name__}: {exc}")
                LOGGER.warning("Capture strategy %s failed: %s", strategy.__class__.__name__, exc)
        raise CaptureError("All Linux capture strategies failed: " + "; ".join(errors))


# ── Factory ───────────────────────────────────────────────────────────


class CaptureStrategyFactory:
    """Compositor-aware strategy selection. Hyprland-first; portal fallback."""

    _cache: dict[str, bool] = {}

    @classmethod
    def _tool_available(cls, tool: str) -> bool:
        if tool in cls._cache:
            return cls._cache[tool]
        try:
            subprocess.run(["which", tool], capture_output=True, check=True, timeout=2)
            cls._cache[tool] = True
        except Exception:
            cls._cache[tool] = False
        return cls._cache[tool]

    @classmethod
    def _is_wayland(cls) -> bool:
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        return session_type == "wayland" or bool(wayland_display)

    @classmethod
    def get_strategy(cls) -> CaptureStrategy:
        if not cls._is_wayland():
            # X11/XWayland fallback — grim works on X11 too via the compositor,
            # but PIL ImageGrab is the simplest X11 path.
            from PIL import ImageGrab

            return _X11GrabStrategy()

        strategies: list[CaptureStrategy] = []

        if cls._tool_available("grim"):
            LOGGER.info("Wayland + grim available: grim first, window-crop second")
            strategies.append(GrimFullscreenCaptureStrategy())
            strategies.append(GrimWindowCropCaptureStrategy())

        strategies.append(WaylandPortalCaptureStrategy())

        return FallbackCaptureStrategy(strategies)


class _X11GrabStrategy(CaptureStrategy):
    def capture(self) -> Image.Image:
        from PIL import ImageGrab

        return ImageGrab.grab(all_screens=False)
