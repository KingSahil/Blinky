from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageGrab

from utils.logging import get_logger

LOGGER = get_logger("clicky.capture")


@dataclass
class Screenshot:
    path: Path
    width: int
    height: int


def capture_screen() -> Screenshot:
    """Capture the primary display with dxcam, falling back to PIL ImageGrab."""
    captures_dir = Path("tmp") / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    path = captures_dir / f"screen-{int(time.time() * 1000)}.jpg"

    from PIL import Image
    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        resample_filter = Image.LANCZOS

    image = None
    try:
        import dxcam

        camera = dxcam.create(output_color="RGB")
        frame = camera.grab()
        if frame is None:
            raise RuntimeError("dxcam returned no frame")

        image = Image.fromarray(frame)
        LOGGER.info("Captured screen with dxcam")
    except Exception as exc:
        LOGGER.warning("dxcam capture failed, using ImageGrab: %s", exc)
        image = ImageGrab.grab(all_screens=False)

    image.thumbnail((1920, 1080), resample=resample_filter)
    image = image.convert("RGB")
    image.save(path, format="JPEG", quality=75, optimize=True)
    LOGGER.info("Saved optimized screenshot: %s (size: %dx%d)", path, image.width, image.height)

    return Screenshot(path=path, width=image.width, height=image.height)
