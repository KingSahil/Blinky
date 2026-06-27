from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageGrab
from utils.logging import get_logger

LOGGER = get_logger("blinky.capture")


@dataclass
class Screenshot:
    path: Path
    width: int
    height: int
    screen_width: int
    screen_height: int


class CaptureError(Exception):
    pass


class PermissionDeniedError(CaptureError):
    pass


class TimeoutError(CaptureError):
    pass


def capture_screen() -> Screenshot:
    captures_dir = Path("screenshots")
    captures_dir.mkdir(parents=True, exist_ok=True)
    path = captures_dir / f"screen-{int(time.time() * 1000)}.jpg"

    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        resample_filter = Image.LANCZOS

    image = None
    if os.name == "nt":
        try:
            from dxcam_capture import DXCamCaptureStrategy

            strategy = DXCamCaptureStrategy()
            image = strategy.capture()
            LOGGER.info("Captured screen with DXCamCaptureStrategy")
        except Exception as exc:
            LOGGER.warning(
                "DXCamCaptureStrategy failed, falling back to PIL ImageGrab: %s", exc
            )
            image = ImageGrab.grab(all_screens=False)
    else:
        try:
            from linux_capture import LinuxCaptureStrategyFactory

            strategy = LinuxCaptureStrategyFactory.get_strategy()
            image = strategy.capture()
            LOGGER.info("Captured screen with %s", strategy.__class__.__name__)
        except Exception as exc:
            LOGGER.exception("Linux screen capture failed")
            raise CaptureError(f"Linux screen capture failed: {exc}") from exc

    screen_w, screen_h = image.width, image.height

    if os.name != "nt" and not image.getbbox():
        LOGGER.warning(
            "Captured screen is completely black! This typically occurs on Linux under a Wayland session "
            "because Wayland restricts background/third-party screen capture. "
            "Action: Please log out, click the gear icon in the bottom-right corner of the login screen, "
            "select 'GNOME on Xorg' (X11 session), and log back in to enable visual telemetry and screen capturing."
        )

    image.thumbnail((1920, 1080), resample=resample_filter)
    image = image.convert("RGB")
    image.save(path, format="JPEG", quality=75, optimize=True)
    LOGGER.info(
        "Saved optimized screenshot: %s (size: %dx%d, screen: %dx%d)",
        path,
        image.width,
        image.height,
        screen_w,
        screen_h,
    )

    return Screenshot(
        path=path,
        width=image.width,
        height=image.height,
        screen_width=screen_w,
        screen_height=screen_h,
    )
