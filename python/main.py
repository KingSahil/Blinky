from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from ai.client import ask_model, get_provider_label
from ai.local_intents import answer_local_question
from ai.prompt import build_prompt
from capture.screen import capture_screen
from ocr.extract import extract_visible_text
from utils.logging import get_logger
from utils.matching import attach_matches
from utils.uia import get_visible_ui_text
from utils.window import get_active_window

LOGGER = get_logger("clicky.main")


def run(question: str) -> dict:
    started = time.perf_counter()
    warnings: list[str] = []

    screenshot = capture_screen()
    active_app = get_active_window()
    ocr_items = extract_visible_text(screenshot.path)
    uia_items = get_visible_ui_text()
    visible_items = merge_visible_items(ocr_items, uia_items)

    if not visible_items:
        warnings.append("No OCR text was detected. Try zooming in or opening a supported app.")

    ai_result = answer_local_question(question, visible_items)
    if ai_result is None:
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


def merge_visible_items(ocr_items: list[dict], uia_items: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple] = set()
    # Keep OCR coordinates first because they are in screenshot pixel space and
    # align best with overlay placement. UIA remains as a fallback source.
    for item in [*ocr_items, *uia_items]:
        key = (
            str(item.get("text", "")).lower(),
            int(item.get("x", 0) / 8),
            int(item.get("y", 0) / 8),
        )
        if key in seen:
            continue
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
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        LOGGER.exception("Worker failed")
        print(json.dumps({"error": str(exc), "steps": [], "warnings": [str(exc)]}))
        sys.exit(1)


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    main()
