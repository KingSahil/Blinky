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


class WinRtOcrProvider(OcrProvider):
    def extract_text(self, image_path: Path) -> list[dict[str, Any]]:
        import asyncio
        import winrt.windows.graphics.imaging as imaging
        import winrt.windows.media.ocr as ocr
        import winrt.windows.storage as storage

        async def read() -> list[dict[str, Any]]:
            file = await storage.StorageFile.get_file_from_path_async(str(image_path.resolve()))
            stream = await file.open_async(storage.FileAccessMode.READ)
            decoder = await imaging.BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()
            engine = ocr.OcrEngine.try_create_from_user_profile_languages()
            result = await engine.recognize_async(bitmap)
            items: list[dict[str, Any]] = []
            for line in result.lines:
                for word in line.words:
                    box = word.bounding_rect
                    items.append(
                        {
                            "text": word.text,
                            "x": int(box.x),
                            "y": int(box.y),
                            "width": int(box.width),
                            "height": int(box.height),
                            "confidence": 0.92,
                            "source": "ocr",
                        }
                    )
            stream.close()
            return items

        return asyncio.run(read())


class PytesseractOcrProvider(OcrProvider):
    def __init__(self) -> None:
        # Check if tesseract binary is actually in system path
        self.available = shutil.which("tesseract") is not None
        if not self.available:
            LOGGER.warning("tesseract binary not found in system path! PytesseractOcrProvider will be disabled.")
            return
        
        try:
            import pytesseract
            self.pytesseract = pytesseract
            # Perform a quick warmup/version query
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
        
        # Performance optimization: Downscale or crop high-res frames before OCR (keep standard 1080p at full resolution)
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

        # Run pytesseract with word boxes
        data = self.pytesseract.image_to_data(img, output_type=self.pytesseract.Output.DICT)
        
        items: list[dict[str, Any]] = []
        n_boxes = len(data['text'])
        for i in range(n_boxes):
            text = data['text'][i].strip()
            if not text:
                continue
            
            # Map coordinate back to original space
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


# Initialize appropriate provider statically/lazily
_provider: OcrProvider | None = None

def get_ocr_provider() -> OcrProvider:
    global _provider
    if _provider is not None:
        return _provider

    if os.name == "nt":
        try:
            _provider = WinRtOcrProvider()
            LOGGER.info("Using WinRtOcrProvider for OCR")
            return _provider
        except Exception as exc:
            LOGGER.warning("Failed to load WinRtOcrProvider, checking pytesseract: %s", exc)

    # Linux / macOS or Windows fallback
    pytess = PytesseractOcrProvider()
    if pytess.available:
        _provider = pytess
        LOGGER.info("Using PytesseractOcrProvider for OCR")
    else:
        _provider = MockOcrProvider()
        LOGGER.warning("Using MockOcrProvider (Failsafe)")
    
    return _provider


def extract_visible_text(image_path: Path) -> list[dict[str, Any]]:
    """Return OCR text boxes in screen coordinates using modular OCR registry."""
    try:
        provider = get_ocr_provider()
        items = provider.extract_text(image_path)
        if items:
            LOGGER.info("OCR Registry (%s) returned %s items", provider.__class__.__name__, len(items))
            return items
    except Exception as exc:
        LOGGER.warning("OCR extraction failed in registry: %s", exc)

    return []
