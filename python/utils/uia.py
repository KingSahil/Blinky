from __future__ import annotations

from utils.logging import get_logger

LOGGER = get_logger("clicky.uia")


def get_visible_ui_text() -> list[dict]:
    """Read visible UI Automation text from the active window.

    This complements OCR for IDE sidebars, tabs, and tree rows where OCR can be
    noisy but Windows UI Automation knows the element name and rectangle.
    """
    try:
        from pywinauto import Desktop

        active = Desktop(backend="uia").get_active()
        items: list[dict] = []
        for element in active.descendants():
            text = _element_text(element)
            if not text:
                continue

            rect = element.rectangle()
            width = max(0, int(rect.width()))
            height = max(0, int(rect.height()))
            if width < 4 or height < 4:
                continue

            items.append(
                {
                    "text": text,
                    "x": int(rect.left),
                    "y": int(rect.top),
                    "width": width,
                    "height": height,
                    "confidence": 0.98,
                    "source": "uia",
                }
            )

        LOGGER.info("UI Automation returned %s visible text items", len(items))
        return _dedupe(items)
    except Exception as exc:
        LOGGER.warning("UI Automation text extraction failed: %s", exc)
        return []


def _element_text(element) -> str:
    try:
        text = element.window_text() or element.element_info.name or ""
    except Exception:
        return ""

    return " ".join(str(text).strip().split())


def _dedupe(items: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique: list[dict] = []
    for item in items:
        key = (item["text"].lower(), item["x"], item["y"], item["width"], item["height"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
