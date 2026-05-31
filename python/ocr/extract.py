from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from utils.logging import get_logger

LOGGER = get_logger("blinky.ocr")


def extract_visible_text(image_path: Path) -> list[dict[str, Any]]:
    """Return OCR text boxes in screen coordinates using Windows native WinRT OCR."""
    try:
        items = _windows_ocr(image_path)
        if items:
            LOGGER.info("Windows OCR returned %s items", len(items))
            return items
    except Exception as exc:
        LOGGER.warning("Windows OCR unavailable: %s", exc)

    return []


def _windows_ocr(image_path: Path) -> list[dict[str, Any]]:
    import asyncio
    import winrt.windows.graphics.imaging as imaging
    import winrt.windows.media.ocr as ocr
    import winrt.windows.storage as storage
    import winrt.windows.storage.streams as streams

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
