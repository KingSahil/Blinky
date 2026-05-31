from __future__ import annotations

from utils.logging import get_logger

LOGGER = get_logger("blinky.uia")


def get_visible_ui_text(window=None, target_pid: int | None = None) -> list[dict]:
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
                if not element.is_visible():
                    continue
            except Exception:
                pass

            try:
                ctype = element.element_info.control_type
                if ctype not in ALLOWED_CONTROL_TYPES:
                    continue
            except Exception:
                continue

            text = _element_text(element)
            if not text:
                continue

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
                {
                    "text": text,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "confidence": 0.98,
                    "source": "uia",
                }
            )

        # Debug: log sidebar-region elements so we can verify positions
        sidebar_items = [i for i in items if i["x"] <= 100]
        LOGGER.info(
            "UIA: %d sidebar-region elements (x<=100) out of %d total",
            len(sidebar_items), len(items),
        )
        for si in sidebar_items[:15]:
            LOGGER.info(
                "UIA sidebar: %-60s  x=%d y=%d w=%d h=%d",
                repr(si["text"][:55]), si["x"], si["y"], si["width"], si["height"],
            )

        LOGGER.info("UI Automation returned %d visible text items total", len(items))
        return _dedupe(items)

    except Exception as exc:
        LOGGER.warning("UI Automation text extraction failed: %s", exc)
        return []


def _element_text(element) -> str:
    try:
        name = element.window_text() or element.element_info.name or ""
        help_text = ""
        try:
            help_text = element.element_info.help_text or ""
        except Exception:
            pass
        # Prefer help_text (tooltip/accessible description) when available.
        text = help_text if help_text.strip() else name
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
