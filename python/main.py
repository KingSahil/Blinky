from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from ai.client import ask_model, ask_text_model, get_provider_label
from ai.prompt import build_chat_prompt, build_preflight_prompt, build_prompt
from capture.screen import capture_screen
from ocr.extract import extract_visible_text
from utils.logging import get_logger
from utils.matching import attach_matches
from utils.uia import get_visible_ui_text
from utils.window import get_active_window

from capture.screen import capture_screen
from ocr.extract import extract_visible_text
from utils.logging import get_logger
from utils.matching import attach_matches
from utils.uia import get_visible_ui_text
from utils.window import get_active_window

LOGGER = get_logger("blinky.main")


def skip_completed_navigation_steps(steps: list[dict]) -> list[dict]:
    if len(steps) >= 2:
        first_step = steps[0]
        second_step = steps[1]
        
        if second_step.get("match") is not None:
            first_instruction = str(first_step.get("instruction", "")).lower()
            is_navigation = (
                any(k in first_instruction for k in {"click", "open", "navigate", "select", "go to", "show"}) and 
                any(k in first_instruction for k in {"tab", "sidebar", "menu", "icon", "panel", "button", "view"})
            )
            if is_navigation:
                LOGGER.info(
                    "Generic Step Skipping: Skipping first step '%s' because second step's target '%s' is already visible.",
                    first_step.get("instruction"),
                    second_step.get("target_text")
                )
                skipped = steps[1:]
                for idx, step in enumerate(skipped, start=1):
                    step["step"] = idx
                return skipped
    return steps


def _fill_empty_search_targets(steps: list[dict], visible_items: list[dict]) -> list[dict]:
    """If any step has a type/search/filter instruction but empty target_text and no match,
    auto-find the first visible search/filter/find input on screen and attach it."""
    _search_hints = {"type", "search", "filter", "find", "enter", "input", "marketplace"}

    for step in steps:
        target = str(step.get("target_text", "")).strip()
        if target or step.get("match") is not None:
            continue  # already has a target or a match

        instruction_lower = str(step.get("instruction", "")).lower()
        if not any(hint in instruction_lower for hint in _search_hints):
            continue  # not a search/type instruction

        # Find the best visible search input control
        best_input = None
        for item in visible_items:
            text = str(item.get("text", "")).lower().strip()
            control_type = str(item.get("control_type", "")).lower()
            is_input = control_type in {"edit", "textbox", "combobox"}
            has_search_keyword = any(k in text for k in {"search", "filter", "find"})

            if is_input or has_search_keyword:
                # Prefer items that are both input controls AND have search keywords
                if is_input and has_search_keyword:
                    best_input = item
                    break  # perfect match, stop
                elif best_input is None:
                    best_input = item

        if best_input:
            LOGGER.info(
                "Search Target Fallback: Auto-attaching visible search input '%s' to step '%s'",
                best_input.get("text"),
                step.get("instruction"),
            )
            step["target_text"] = best_input.get("text", "")
            step["match"] = best_input

    return steps


def run(question: str, previous_question: str | None = None, progress: dict | None = None) -> dict:
    started = time.perf_counter()
    warnings: list[str] = []

    # 1. Lock the target window by PID and capture the screenshot immediately at the start of execution.
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
    # Print the capture marker to stdout and flush immediately so Rust can restore windows
    print("__BLINKY_CAPTURED__", flush=True)

    # 2. Run the preflight classifier
    preflight = classify_request(question, previous_question, warnings)
    
    is_continuation = False
    if preflight:
        is_continuation = bool(preflight.get("is_continuation", False))
        
    effective_question = question
    latest_update = None
    if is_continuation and previous_question:
        effective_question = previous_question
        latest_update = question
    else:
        progress = None

    needs_screen = True
    if preflight:
        needs_screen = bool(preflight.get("needs_screen", True))
        
    if is_continuation:
        needs_screen = True

    if not needs_screen:
        chat_result = answer_without_screen(question)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "summary": chat_result["summary"],
            "steps": [],
            "active_app": {"title": "", "process": "", "supported": False},
            "ocr": {"count": 0, "items": []},
            "elapsed_ms": elapsed_ms,
            "provider": get_provider_label(),
            "warnings": warnings,
            "is_continuation": is_continuation,
        }

    # 3. Read active app, OCR text, and UIA controls
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

    # Sort all visible items in spatial reading order (top-to-bottom, left-to-right)
    # with a 10-pixel Y bucket tolerance for elements on the same horizontal line.
    visible_items.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))

    if not visible_items:
        warnings.append("No OCR text was detected. Try zooming in or opening a supported app.")

    prompt = build_prompt(
        question=effective_question,
        active_app=active_app,
        ocr_items=visible_items,
        progress=progress,
        latest_update=latest_update,
    )
    ai_result = ask_model(prompt=prompt, screenshot_path=screenshot.path)
    LOGGER.info("AI Result: %s", json.dumps(ai_result, ensure_ascii=True))
    steps = attach_matches(ai_result.get("steps", []), visible_items)
    steps = skip_completed_navigation_steps(steps)

    # Fallback: if the AI returned a type/search instruction with empty target_text,
    # auto-match to the first visible search/filter/find input control on screen.
    steps = _fill_empty_search_targets(steps, visible_items)

    if steps:
        steps = steps[:1]

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": ai_result.get("summary", "I found a short path using the visible controls."),
        "steps": steps,
        "active_app": active_app,
        "ocr": {"count": len(visible_items), "items": visible_items[:200]},
        "screenshot": {
            "path": str(screenshot.path),
            "width": screenshot.width,
            "height": screenshot.height,
        },
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings + ai_result.get("warnings", []),
        "is_continuation": is_continuation,
    }


# All query resolution is handled automatically by the AI model.


def classify_request(question: str, previous_question: str | None, warnings: list[str]) -> dict | None:
    try:
        payload = ask_text_model(build_preflight_prompt(question, previous_question))
    except Exception as exc:
        LOGGER.warning("Preflight classification failed; falling back to screen mode: %s", exc)
        warnings.append(f"Preflight classification failed: {exc}")
        return None

    needs_screen = bool(payload.get("needs_screen", True))
    is_continuation = bool(payload.get("is_continuation", False))
    return {"needs_screen": needs_screen, "is_continuation": is_continuation}


def answer_without_screen(question: str) -> dict:
    payload = ask_text_model(build_chat_prompt(question))
    summary = str(payload.get("summary", "")).strip()
    if not summary:
        raise RuntimeError("The chat model returned an empty reply.")
    return {"summary": summary, "steps": []}



def merge_visible_items(ocr_items: list[dict], uia_items: list[dict]) -> list[dict]:
    # Extract all UIA input/edit controls first
    uia_inputs = [
        item for item in uia_items 
        if str(item.get("control_type", "")).lower() in {"edit", "textbox", "combobox"}
    ]
    
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
        
        # Don't calibrate input/edit controls to OCR text, because we want to highlight the full input box.
        is_input = str(item.get("control_type", "")).lower() in {"edit", "textbox", "combobox"}
        ocr_match = ocr_by_key.get((text_lower, y_bucket)) if not is_input else None
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
            
    # 2. Add remaining standalone OCR items.
    # If an OCR item falls inside a UIA input/edit control, expand it to the full input control's bounds
    # and mark it as an input control type, so that highlights cover the entire search/input bar.
    for item in ocr_items:
        text_lower = str(item.get("text", "")).lower().strip()
        
        ox, oy = item.get("x", 0), item.get("y", 0)
        ow, oh = item.get("width", 0), item.get("height", 0)
        
        for u_input in uia_inputs:
            ux, uy = u_input.get("x", 0), u_input.get("y", 0)
            uw, uh = u_input.get("width", 0), u_input.get("height", 0)
            
            # Check containment with 8px padding
            if (ox >= ux - 8 and oy >= uy - 8 and 
                ox + ow <= ux + uw + 8 and oy + oh <= uy + uh + 8):
                LOGGER.info("Calibrating OCR text '%s' inside UIA input control to full bounds", item.get("text"))
                item["x"] = ux
                item["y"] = uy
                item["width"] = uw
                item["height"] = uh
                item["control_type"] = u_input.get("control_type")
                break
                
        key = (text_lower, int(item.get("x", 0) / 8), int(item.get("y", 0) / 8))
        if key not in seen:
            seen.add(key)
            merged.append(item)
            
    return merged


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        question = str(payload.get("question", "")).strip()
        previous_question = payload.get("previous_question")
        if previous_question is not None:
            previous_question = str(previous_question).strip()
        progress = payload.get("progress")
        if not isinstance(progress, dict):
            progress = {}
        if not question:
            raise ValueError("Question is required.")

        result = run(question, previous_question, progress)
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
