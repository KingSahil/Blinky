from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from utils.logging import get_logger

LOGGER = get_logger("clicky.ocr")


def extract_visible_text(image_path: Path) -> list[dict[str, Any]]:
    """Return OCR text boxes in screen coordinates.

    Windows OCR is attempted first when the optional WinRT package is available.
    EasyOCR is the practical hackathon fallback.
    """
    try:
        items = _windows_ocr(image_path)
        if items:
            LOGGER.info("Windows OCR returned %s items", len(items))
            return items
    except Exception as exc:
        LOGGER.warning("Windows OCR unavailable: %s", exc)

    return _easy_ocr(image_path)


def _windows_ocr(image_path: Path) -> list[dict[str, Any]]:
    # The WinRT Python packages are not installed on every machine. Keeping this
    # optional lets the MVP run reliably with EasyOCR while still preferring the
    # native OCR path when the host has it.
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


def _easy_ocr(image_path: Path) -> list[dict[str, Any]]:
    try:
        import easyocr

        reader = easyocr.Reader(["en"], gpu=True, verbose=False)
        results = reader.readtext(str(image_path), paragraph=False)
        items = []
        for box, text, confidence in results:
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            clean = str(text).strip()
            if not clean:
                continue
            items.append(
                {
                    "text": clean,
                    "x": int(min(xs)),
                    "y": int(min(ys)),
                    "width": int(max(xs) - min(xs)),
                    "height": int(max(ys) - min(ys)),
                    "confidence": round(float(confidence), 3),
                    "source": "ocr",
                }
            )
        LOGGER.info("EasyOCR returned %s items", len(items))
        return items
    except Exception as exc:
        LOGGER.exception("EasyOCR failed")
        # Last-resort visible marker so the rest of the demo can still exercise
        # Ollama and overlay plumbing without crashing.
        width, height = Image.open(image_path).size
        return [
            {
                "text": "No OCR text detected",
                "x": width // 3,
                "y": height // 3,
                "width": 240,
                "height": 36,
                "confidence": 0.0,
                "source": "ocr",
            }
        ]
