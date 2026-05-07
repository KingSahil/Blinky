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
    path = captures_dir / f"screen-{int(time.time() * 1000)}.png"

    try:
        import dxcam

        camera = dxcam.create(output_color="RGB")
        frame = camera.grab()
        if frame is None:
            raise RuntimeError("dxcam returned no frame")

        from PIL import Image

        image = Image.fromarray(frame)
        image.save(path)
        LOGGER.info("Captured screen with dxcam: %s", path)
        return Screenshot(path=path, width=image.width, height=image.height)
    except Exception as exc:
        LOGGER.warning("dxcam capture failed, using ImageGrab: %s", exc)
        image = ImageGrab.grab(all_screens=False)
        image.save(path)
        return Screenshot(path=path, width=image.width, height=image.height)
