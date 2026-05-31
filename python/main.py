from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from ai.client import ask_model, get_provider_label
from ai.prompt import build_prompt
from capture.screen import capture_screen
from ocr.extract import extract_visible_text
from utils.logging import get_logger
from utils.matching import attach_matches
from utils.uia import get_visible_ui_text
from utils.window import get_active_window

LOGGER = get_logger("blinky.main")


def run(question: str) -> dict:
    started = time.perf_counter()
    warnings: list[str] = []

    # Lock the target window by PID *before* the long OCR pass starts.
    # Caching the pywinauto element itself would cause a stale COM descriptor
    # after ~15 s; caching the PID is stable and forces a fresh element
    # lookup when UIA runs.
    from utils.window import get_target_window_element
    _initial = get_target_window_element()
    target_pid: int | None = None
    try:
        target_pid = _initial.process_id() if _initial else None
    except Exception:
        pass

    screenshot = capture_screen()
    active_app = get_active_window(target_pid=target_pid)
    ocr_items = extract_visible_text(screenshot.path)
    uia_items = get_visible_ui_text(target_pid=target_pid)



    # UIA returns coordinates in screen-absolute space (physical pixel dimensions).
    # The screenshot is scaled down to fit within 1920×1080 (thumbnail).
    # The overlay then scales everything back up by (window.innerWidth / screenshot.width).
    # To make both scales cancel correctly, we must first convert UIA coords
    # from screen space → screenshot space before the overlay sees them.
    if screenshot.screen_width != screenshot.width or screenshot.screen_height != screenshot.height:
        sx = screenshot.width  / screenshot.screen_width
        sy = screenshot.height / screenshot.screen_height
        LOGGER.info(
            "Scaling UIA coords from screen (%dx%d) → screenshot (%dx%d)  sx=%.4f sy=%.4f",
            screenshot.screen_width, screenshot.screen_height,
            screenshot.width, screenshot.height, sx, sy,
        )
        scaled: list[dict] = []
        for item in uia_items:
            scaled.append({
                **item,
                "x":      int(item["x"]      * sx),
                "y":      int(item["y"]      * sy),
                "width":  max(1, int(item["width"]  * sx)),
                "height": max(1, int(item["height"] * sy)),
            })
        uia_items = scaled

    visible_items = merge_visible_items(ocr_items, uia_items)

    # Try high-speed local intent classifier first to bypass LLM hallucinations/latency
    local_match = try_local_intent_match(question, visible_items)
    if local_match:
        LOGGER.info("Local Classifier intercepted and successfully resolved query!")
        ai_result = local_match
        steps = local_match["steps"]
    else:
        if not visible_items:
            warnings.append("No OCR text was detected. Try zooming in or opening a supported app.")

        prompt = build_prompt(
            question=question,
            active_app=active_app,
            ocr_items=visible_items,
        )
        ai_result = ask_model(prompt=prompt, screenshot_path=screenshot.path)
        steps = attach_matches(ai_result.get("steps", []), visible_items)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": ai_result.get("summary", "I found a short path using the visible controls."),
        "steps": steps,
        "active_app": active_app,
        "ocr": {"count": len(visible_items), "items": visible_items},
        "screenshot": {
            "path": str(screenshot.path),
            "width": screenshot.width,
            "height": screenshot.height,
        },
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings + ai_result.get("warnings", []),
    }


def try_local_intent_match(question: str, visible_items: list[dict]) -> dict | None:
    q = question.lower().strip()
    
    # Generic system/menu terms that should not be matched as arbitrary substrings
    generic_menu_terms = {"file", "edit", "view", "go", "run", "terminal", "help", "window", "search"}
    
    matches = []
    # Fast exact and keyword scan for visible file explorer items or sidebar items
    for item in visible_items:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        text_lower = text.lower()
        
        # Match if the target element name is a word/phrase inside the question
        if len(text_lower) > 2 and text_lower in q:
            # If it is a generic term (like "file"), only match it if the query is specifically about that menu
            if text_lower in generic_menu_terms:
                is_exact_menu_query = q == text_lower or f"click {text_lower}" in q or f"{text_lower} menu" in q or f"open {text_lower}" in q
                if not is_exact_menu_query:
                    continue
                    
            # Differentiate queries asking where a folder/file/button is located vs casual text
            is_targeting_query = any(kw in q for kw in ["where is", "click", "find", "show me", "where's", "open", "locate"])
            is_name_query = text_lower == q or f"{text_lower} folder" in q or f"{text_lower} file" in q or f"{text_lower} button" in q
            
            if is_targeting_query or is_name_query:
                matches.append((len(text_lower), item, text))
                
    if matches:
        # Sort matches by text length descending so that the longest (most specific) match is preferred
        # e.g., "app.tsx" (len 7) is chosen over "file" (len 4)
        matches.sort(key=lambda x: x[0], reverse=True)
        best_len, best_item, best_text = matches[0]
        
        LOGGER.info("Local Intent Match: successfully resolved '%s' directly (most specific of %d matches)", best_text, len(matches))
        return {
            "summary": f"The '{best_text}' item is already visible on the screen! I have highlighted it for you.",
            "steps": [
                {
                    "step": 1,
                    "instruction": f"Click the {best_text} item.",
                    "target_text": best_text,
                    "match": best_item,
                }
            ],
            "warnings": []
        }
    return None


def merge_visible_items(ocr_items: list[dict], uia_items: list[dict]) -> list[dict]:
    # Index OCR items by text and approximate Y coordinate to search them quickly
    ocr_by_key = {}
    for ocr in ocr_items:
        text_lower = str(ocr.get("text", "")).lower().strip()
        y_bucket = int(ocr.get("y", 0) / 12)
        ocr_by_key[(text_lower, y_bucket)] = ocr
        ocr_by_key[(text_lower, y_bucket - 1)] = ocr
        ocr_by_key[(text_lower, y_bucket + 1)] = ocr

    merged: list[dict] = []
    seen: set[tuple] = set()
    
    # 1. Add all UIA items. If a UIA item matches a precise OCR item on the same line,
    # we override the coordinates with the pixel-perfect OCR coordinates!
    for item in uia_items:
        text_lower = str(item.get("text", "")).lower().strip()
        y_bucket = int(item.get("y", 0) / 12)
        
        ocr_match = ocr_by_key.get((text_lower, y_bucket))
        if ocr_match:
            LOGGER.info("Precise Calibration: UIA '%s' bound mapped to OCR: x=%d -> x=%d", item.get("text"), item["x"], ocr_match["x"])
            item["x"] = ocr_match["x"]
            item["y"] = ocr_match["y"]
            item["width"] = ocr_match["width"]
            item["height"] = ocr_match["height"]
            item["source"] = "ocr"  # Promote source to ocr to bypass UIA wide-capping layouts
            
        key = (text_lower, int(item.get("x", 0) / 8), int(item.get("y", 0) / 8))
        if key not in seen:
            seen.add(key)
            merged.append(item)
            
    # 2. Add remaining standalone OCR items
    for item in ocr_items:
        text_lower = str(item.get("text", "")).lower().strip()
        key = (text_lower, int(item.get("x", 0) / 8), int(item.get("y", 0) / 8))
        if key not in seen:
            seen.add(key)
            merged.append(item)
            
    return merged


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        question = str(payload.get("question", "")).strip()
        if not question:
            raise ValueError("Question is required.")

        result = run(question)
        print(json.dumps(result, ensure_ascii=True))
    except Exception as exc:
        LOGGER.exception("Worker failed")
        print(json.dumps({"error": str(exc), "steps": [], "warnings": [str(exc)]}))
        sys.exit(1)


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    main()
