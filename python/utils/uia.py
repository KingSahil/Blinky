from __future__ import annotations

from utils.logging import get_logger

LOGGER = get_logger("blinky.uia")


def get_visible_ui_text(window=None, target_pid: int | None = None, include_unlabeled: bool = False) -> list[dict]:
    """Read visible UI Automation text from the active window.

    *window* — optional pre-resolved pywinauto element (skips Z-order scan).
    *target_pid* — preferred: restrict the Z-order scan to this process ID so
               that focus changes during the OCR phase don't affect which window
               is scanned. A fresh COM element is resolved each call, avoiding
               the stale-descriptor bug that occurs when an element is cached
               for > ~15 s.

    Windows UI Automation returns element bounding rectangles in
    screen-absolute coordinates (logical pixels). These are in the same space
    as the overlay window and match the screenshot after the scaleX/scaleY
    transform applied in Overlay.tsx.
    """
    import os
    if os.name != "nt":
        return []

    try:
        from utils.window import get_target_window_element

        active = get_target_window_element(window=window, target_pid=target_pid)
        if not active:
            LOGGER.warning("No target window resolved for UIA query")
            return []

        process_name = ""
        try:
            import psutil
            process_name = psutil.Process(active.process_id()).name().lower()
            LOGGER.info("UIA: active process = '%s'", process_name)
        except Exception as exc:
            LOGGER.warning("UIA: failed to resolve process name: %s", exc)

        # Restrict traversal to interactive control types to prune layout panels
        # and wrappers. Speeds up UIA tree scanning ~50x.
        ALLOWED_CONTROL_TYPES = {
            "Button",
            "TabItem",
            "MenuItem",
            "TreeItem",
            "Edit",
            "Hyperlink",
            "ListItem",
            "HeaderItem",
            "Custom",
            "Image",
            "Pane",
        }

        items: list[dict] = []

        for element in active.descendants():
            if len(items) >= 400:
                LOGGER.info("UIA: Traversal capped at 400 items to prevent massive tree scanning")
                break
                
            try:
                ctype = element.element_info.control_type
                if ctype not in ALLOWED_CONTROL_TYPES:
                    continue
            except Exception:
                continue

            text = _element_text(element, ctype)
            if not text and not (include_unlabeled and ctype in {"Button", "Image", "Hyperlink"}):
                continue

            try:
                if not element.is_visible():
                    continue
            except Exception:
                pass

            rect = element.rectangle()
            width = max(0, int(rect.width()))
            height = max(0, int(rect.height()))
            if width < 4 or height < 4:
                continue

            # Skip elements with clearly invalid coordinates (off-screen)
            x = int(rect.left)
            y = int(rect.top)
            if x < -1000 or y < -1000:
                continue

            items.append(
                _uia_item(
                    text=text,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    source="uia",
                    control_type=ctype,
                    automation_id=_element_metadata(element, "automation_id"),
                )
            )

        # Capture Blinky's own settings button in its floating window header!
        try:
            from pywinauto import Desktop
            for w in Desktop(backend="uia").windows():
                pname = ""
                try:
                    import psutil
                    pname = psutil.Process(w.process_id()).name().lower()
                except Exception:
                    pass
                if "blinky" in pname or "blinky" in (w.window_text() or "").lower():
                    for el in w.descendants():
                        try:
                            if el.element_info.control_type not in {"Button", "Image", "Pane"}:
                                continue
                            text = _element_text(el, el.element_info.control_type)
                            if not text or "settings" not in text.lower():
                                continue
                            if not el.is_visible():
                                continue
                            rect = el.rectangle()
                            width = max(0, int(rect.width()))
                            height = max(0, int(rect.height()))
                            if width < 4 or height < 4:
                                continue
                            x = int(rect.left)
                            y = int(rect.top)
                            items.append(_uia_item(
                                text=text,
                                x=x,
                                y=y,
                                width=width,
                                height=height,
                                source="blinky",
                                control_type=el.element_info.control_type,
                                automation_id=_element_metadata(el, "automation_id"),
                            ))
                            LOGGER.info("UIA: Captured Blinky control element '%s' at (%d, %d)", text, x, y)
                        except Exception:
                            continue
                    break
        except Exception as exc:
            LOGGER.warning("UIA: failed to scan Blinky window controls: %s", exc)

        # Debug: log sidebar-region elements only when verbose logging is enabled.
        sidebar_items = [i for i in items if i["x"] <= 100]
        LOGGER.debug(
            "UIA: %d sidebar-region elements (x<=100) out of %d total",
            len(sidebar_items), len(items),
        )
        for si in sidebar_items[:15]:
            LOGGER.debug(
                "UIA sidebar: %-60s  x=%d y=%d w=%d h=%d",
                repr(si["text"][:55]), si["x"], si["y"], si["width"], si["height"],
            )

        LOGGER.info("UI Automation returned %d visible text items total", len(items))
        return _dedupe(items)

    except Exception as exc:
        LOGGER.warning("UI Automation text extraction failed: %s", exc)
        return []


def _element_text(element, control_type: str = "") -> str:
    try:
        name = element.window_text() or element.element_info.name or ""
        help_text = ""
        try:
            help_text = element.element_info.help_text or ""
        except Exception:
            pass
        automation_id = _element_metadata(element, "automation_id")
        # Prefer help_text (tooltip/accessible description) when available.
        text = help_text if help_text.strip() else name
        if not str(text).strip() and control_type in {"Button", "MenuItem", "TabItem", "TreeItem", "Hyperlink", "Edit", "Image"}:
            text = automation_id
    except Exception:
        return ""
    return _readable_metadata_text(str(text))


def _uia_item(
    *,
    text: str,
    x: int,
    y: int,
    width: int,
    height: int,
    source: str,
    control_type: str,
    automation_id: str = "",
) -> dict:
    item = {
        "text": text,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "source": source,
        "control_type": control_type,
    }
    if automation_id:
        item["automation_id"] = automation_id
    return item


def _element_metadata(element, field: str) -> str:
    try:
        value = getattr(element.element_info, field, "") or ""
    except Exception:
        return ""
    return str(value).strip()


def _readable_metadata_text(value: str) -> str:
    import re

    text = re.sub(r"[_\-]+", " ", value)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return " ".join(text.strip().split())


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
