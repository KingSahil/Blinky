from __future__ import annotations

from difflib import SequenceMatcher


def attach_matches(steps: list[dict], ocr_items: list[dict]) -> list[dict]:
    matched_steps = []
    for step in steps:
        target = str(step.get("target_text", "")).strip()
        match = find_best_match(target, ocr_items) if target else None
        matched_steps.append({**step, "match": match})
    return matched_steps


def find_best_match(target: str, ocr_items: list[dict]) -> dict | None:
    target_norm = _normalize(target)
    if not target_norm:
        return None

    best_item = None
    best_score = 0.0

    for item in ocr_items:
        text_norm = _normalize(str(item.get("text", "")))
        if not text_norm:
            continue

        if text_norm == target_norm:
            score = 1.0
        elif target_norm in text_norm or text_norm in target_norm:
            score = 0.86
        else:
            score = SequenceMatcher(None, target_norm, text_norm).ratio()
            if score < 0.65:
                continue

        confidence = float(item.get("confidence") or 0)
        source = str(item.get("source", "")).lower()
        # OCR boxes are captured from the exact screenshot pixels used by the
        # overlay, so prefer OCR over UIA for final on-screen placement.
        source_bonus = 0.02 if source == "ocr" else 0.0
        weighted = score * 0.94 + confidence * 0.06 + source_bonus
        if weighted > best_score:
            best_score = weighted
            best_item = item

    if best_score < 0.52:
        return None

    return best_item


def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())
