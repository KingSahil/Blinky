from __future__ import annotations

import os
import time
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

        # Speed tuning (measured on Hyprland, 2560x1440):
        #   default (OEM0, 2048px):      ~2.7s
        #   OEM1 LSTM-only, 1600px:      ~1.4-1.6s  ← this config
        # PSM stays at 3 (auto layout) — PSM 6 assumes one text block and
        # drops scattered UI elements (51 items vs 70 for PSM 3).
        max_dim = 1600
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

        data = self.pytesseract.image_to_data(
            img,
            output_type=self.pytesseract.Output.DICT,
            config="--oem 1",  # LSTM-only engine (faster than legacy+lstm)
        )

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

    mode = os.environ.get("BLINKY_SCREENSHOT_MODE", "ocr").strip().lower()
    if mode == "omniparser":
        try:
            from ocr.omniparser import OmniParserProvider
            _provider = OmniParserProvider()
            LOGGER.info("Using OmniParserProvider for OCR/Screen parsing")
            return _provider
        except Exception as exc:
            LOGGER.error("Failed to initialize OmniParserProvider, falling back to standard OCR: %s", exc)

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


def extract_visible_text(
    image_path: Path,
    crop_rect: tuple[int, int, int, int] | None = None,
) -> list[dict[str, Any]]:
    """Extract visible text using the active OCR provider.
    
    If crop_rect (x, y, w, h) is provided, OCR only parses that subregion
    and maps the bounding boxes back to screenshot-space, cutting OCR
    latency by 2x-3x for focused active-window tasks.
    """
    try:
        image_path = Path(image_path)
        actual_path = image_path
        offset_x, offset_y = 0, 0
        tmp_crop_path = None

        if crop_rect is not None:
            cx, cy, cw, ch = crop_rect
            if cw > 20 and ch > 20:
                try:
                    from PIL import Image
                    with Image.open(image_path) as img:
                        # Clamp crop bounds within image dimensions
                        left = max(0, min(cx, img.width - 1))
                        top = max(0, min(cy, img.height - 1))
                        right = max(left + 10, min(cx + cw, img.width))
                        bottom = max(top + 10, min(cy + ch, img.height))
                        
                        cropped = img.crop((left, top, right, bottom))
                        tmp_crop_path = image_path.parent / f"_ocr_crop_{int(time.time() * 1000)}.jpg"
                        cropped.save(tmp_crop_path, format="JPEG", quality=75, optimize=False)
                        actual_path = tmp_crop_path
                        offset_x, offset_y = left, top
                except Exception as crop_exc:
                    LOGGER.debug("OCR crop failed, falling back to full screen: %s", crop_exc)
                    actual_path = image_path
                    offset_x, offset_y = 0, 0

        try:
            provider = get_ocr_provider()
            items = provider.extract_text(actual_path)
            if items:
                if offset_x or offset_y:
                    for item in items:
                        item["x"] = int(item.get("x", 0)) + offset_x
                        item["y"] = int(item.get("y", 0)) + offset_y
                LOGGER.info("OCR Registry (%s) returned %s items (cropped: %s)", provider.__class__.__name__, len(items), bool(offset_x or offset_y))
                return items
        finally:
            if tmp_crop_path is not None and tmp_crop_path.exists():
                try:
                    tmp_crop_path.unlink()
                except OSError:
                    pass
    except Exception as exc:
        LOGGER.warning("OCR extraction failed in registry: %s", exc)

    return []
