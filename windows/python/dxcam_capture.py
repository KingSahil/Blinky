from __future__ import annotations

from abc import ABC, abstractmethod
from PIL import Image

from utils.logging import get_logger

LOGGER = get_logger("blinky.capture")


class CaptureError(Exception):
    pass


class CaptureStrategy(ABC):
    @abstractmethod
    def capture(self) -> Image.Image:
        pass


class DXCamCaptureStrategy(CaptureStrategy):
    def capture(self) -> Image.Image:
        import dxcam
        camera = dxcam.create(output_color="RGB")
        frame = camera.grab()
        if frame is None:
            raise CaptureError("dxcam returned no frame")
        return Image.fromarray(frame)
