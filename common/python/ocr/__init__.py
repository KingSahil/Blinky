from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.ocr")


class OcrProvider(ABC):
    @abstractmethod
    def extract_text(self, image_path: Path) -> list[dict[str, Any]]:
        pass


class PytesseractOcrProvider(OcrProvider):
    def __init__(self) -> None:
        self.available = shutil.which("tesseract") is not None
        if not self.available:
            LOGGER.warning("tesseract binary not found in system path! PytesseractOcrProvider will be disabled.")
            return

        try:
            import pytesseract
            self.pytesseract = pytesseract
            _ = self.pytesseract.get_tesseract_version()
            LOGGER.info("Pytesseract initialized successfully.")
        except Exception as exc:
            self.available = False
            LOGGER.warning("pytesseract Python module failed to initialize: %s", exc)

    def extract_text(self, image_path: Path) -> list[dict[str, Any]]:
        if not self.available:
            return []

        from PIL import Image
        img = Image.open(image_path)

        max_dim = 2048
        w, h = img.size
        scale = 1.0
        if w > max_dim or h > max_dim:
            if w > h:
                scale = max_dim / w
                new_size = (max_dim, int(h * scale))
            else:
                scale = max_dim / h
                new_size = (int(w * scale), max_dim)
            img = img.resize(new_size, Image.Resampling.BILINEAR)
            LOGGER.info("Downscaled image for OCR from %dx%d to %dx%d (scale: %f)", w, h, img.width, img.height, scale)

        data = self.pytesseract.image_to_data(img, output_type=self.pytesseract.Output.DICT)

        items: list[dict[str, Any]] = []
        n_boxes = len(data['text'])
        for i in range(n_boxes):
            text = data['text'][i].strip()
            if not text:
                continue

            orig_x = int(data['left'][i] / scale)
            orig_y = int(data['top'][i] / scale)
            orig_w = int(data['width'][i] / scale)
            orig_h = int(data['height'][i] / scale)
            conf = float(data['conf'][i]) / 100.0 if 'conf' in data else 0.8

            items.append({
                "text": text,
                "x": orig_x,
                "y": orig_y,
                "width": orig_w,
                "height": orig_h,
                "confidence": conf,
                "source": "ocr"
            })

        return items


class MockOcrProvider(OcrProvider):
    def extract_text(self, image_path: Path) -> list[dict[str, Any]]:
        LOGGER.warning(
            "No functional OCR Engine detected. On Linux, please install tesseract-ocr "
            "(e.g., `sudo dnf install tesseract` or `sudo apt-get install tesseract-ocr`) "
            "and pyproject requirements. Returning empty OCR list."
        )
        return []


_provider: OcrProvider | None = None


def get_ocr_provider() -> OcrProvider:
    global _provider
    if _provider is not None:
        return _provider

    if os.name == "nt":
        try:
            from winrt_ocr import WinRtOcrProvider
            _provider = WinRtOcrProvider()
            LOGGER.info("Using WinRtOcrProvider for OCR")
            return _provider
        except Exception as exc:
            LOGGER.warning("Failed to load WinRtOcrProvider, checking pytesseract: %s", exc)

    pytess = PytesseractOcrProvider()
    if pytess.available:
        _provider = pytess
        LOGGER.info("Using PytesseractOcrProvider for OCR")
    else:
        _provider = MockOcrProvider()
        LOGGER.warning("Using MockOcrProvider (Failsafe)")

    return _provider


def extract_visible_text(image_path: Path) -> list[dict[str, Any]]:
    try:
        provider = get_ocr_provider()
        items = provider.extract_text(image_path)
        if items:
            LOGGER.info("OCR Registry (%s) returned %s items", provider.__class__.__name__, len(items))
            return items
    except Exception as exc:
        LOGGER.warning("OCR extraction failed in registry: %s", exc)

    return []
