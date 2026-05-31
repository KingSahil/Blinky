import re
from difflib import SequenceMatcher


def attach_matches(steps: list[dict], ocr_items: list[dict]) -> list[dict]:
    matched_steps = []
    for step in steps:
        target = str(step.get("target_text", "")).strip()
        instruction = str(step.get("instruction", "")).strip()
        match = find_best_match(target, ocr_items, instruction) if (target or instruction) else None
        matched_steps.append({**step, "match": match})
    return matched_steps


def find_best_match(target: str, ocr_items: list[dict], instruction: str = "") -> dict | None:
    # Fallback: if target is empty, extract candidate targets from the instruction
    if not target.strip() and instruction.strip():
        # 1. Look for quoted terms first (e.g., click 'Status')
        candidates = re.findall(r"['\"`]([^'\"`]+)['\"`]", instruction)
        
        # 2. Look for capitalized words (excluding common stop words)
        if not candidates:
            words = instruction.split()
            # Skip first word as it's often capitalized simply as the start of the sentence
            for w in words[1:]:
                w_clean = w.strip(".,;:!?\"'()[]")
                if (w_clean and w_clean[0].isupper() and 
                    w_clean.lower() not in {"the", "a", "an", "and", "or", "to", "in", "on", "at", "by", "for", "with", "about", "option", "button", "item", "tab", "menu", "sidebar"}):
                    candidates.append(w_clean)
                    
        for cand in candidates:
            res = _find_best_match_core(cand, ocr_items, instruction)
            if res:
                return res

    return _find_best_match_core(target, ocr_items, instruction)


def _find_best_match_core(target: str, ocr_items: list[dict], instruction: str = "") -> dict | None:
    target_norm = _normalize(target)
    if not target_norm:
        return None

    best_item = None
    best_score = 0.0
    instruction_lower = instruction.lower()

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
        
        # 1. OCR Source Bonus
        source_bonus = 0.02 if source == "ocr" else 0.0
        
        # 2. Size Bonus: prefer larger clickable elements over tiny status icons/bullets
        width = float(item.get("width") or 0)
        height = float(item.get("height") or 0)
        size_bonus = min(0.05, (width * height) / 10000.0)
        
        # 3. Contextual Spatial Bonus: match spatial hints in the instruction
        context_bonus = 0.0
        x = float(item.get("x") or 0)
        y = float(item.get("y") or 0)
        
        if "sidebar" in instruction_lower or "left" in instruction_lower:
            if x <= 120:  # sidebar region
                context_bonus += 0.20
        if "top" in instruction_lower or "header" in instruction_lower or "menu" in instruction_lower:
            if y <= 120:  # top region
                context_bonus += 0.10
        if "bottom" in instruction_lower:
            if y >= 600:  # bottom region
                context_bonus += 0.10
        if "right" in instruction_lower:
            if x >= 500:  # right region
                context_bonus += 0.10

        weighted = score * 0.94 + confidence * 0.06 + source_bonus + size_bonus + context_bonus
        if weighted > best_score:
            best_score = weighted
            best_item = item

    if best_score < 0.52:
        return None

    return best_item



def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())

