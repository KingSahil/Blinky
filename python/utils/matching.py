import re
from difflib import SequenceMatcher


def attach_matches(steps: list[dict], ocr_items: list[dict]) -> list[dict]:
    matched_steps = []
    for step in steps:
        target = str(step.get("target_text", "")).strip()
        instruction = str(step.get("instruction", "")).strip()
        match = find_best_match(target, ocr_items, instruction) if target else None
        matched_steps.append({**step, "match": match})
    return matched_steps


def find_best_match(target: str, ocr_items: list[dict], instruction: str = "") -> dict | None:
    # Fallback: if target is empty, extract candidate targets from the instruction
    if not target.strip() and instruction.strip():
        candidates = _instruction_target_candidates(instruction)
        for cand in candidates:
            res = _find_best_match_core(cand, ocr_items, instruction)
            if res:
                return res

    if _should_prefer_instruction_target(target, instruction):
        for candidate in _instruction_target_candidates(instruction):
            match = _find_best_match_core(candidate, ocr_items, instruction)
            if match:
                return match

    best = None
    for candidate in _target_candidates(target):
        match = _find_best_match_core(candidate, ocr_items, instruction)
        if match:
            best = match
            break
    return best


def _find_best_match_core(target: str, ocr_items: list[dict], instruction: str = "") -> dict | None:
    target_norm = _normalize(target)
    if not target_norm:
        return None

    best_item = None
    best_score = 0.0
    instruction_lower = instruction.lower()
    wants_text_input = _wants_text_input(instruction_lower)

    # Special titlebar close button high-priority matching fallback:
    if target_norm in {"close button", "close", "close window"}:
        top_right_close = None
        for item in ocr_items:
            t = str(item.get("text", "")).lower().strip()
            x = float(item.get("x") or 0)
            y = float(item.get("y") or 0)
            # Typically close button is at the extreme top right (y <= 60, x >= 400)
            if y <= 60 and x >= 400:
                if t in {"close", "✕", "x", "✖", "cancel"} or (item.get("control_type") == "Button" and x >= 600):
                    if not top_right_close or x > top_right_close["x"]:
                        top_right_close = item
        if top_right_close:
            from utils.logging import get_logger
            get_logger("blinky.matching").info("Semantic Close Button Match: matched '%s' at (%d, %d)", top_right_close.get("text"), top_right_close["x"], top_right_close["y"])
            return top_right_close

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
        control_type = str(item.get("control_type", "")).lower()
        automation_id = str(item.get("automation_id", "")).lower()
        
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
        is_input_control = _is_input_control(text_norm, control_type, automation_id)
        
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
        if wants_text_input and is_input_control:
            context_bonus += 0.18

        # 4. Blinky Source Penalty: de-prioritize Blinky's own UI elements
        source_penalty = -0.40 if source == "blinky" else 0.0
        interactive_bonus = 0.0
        wants_control = any(
            hint in instruction_lower
            for hint in {"icon", "button", "tab", "menu", "sidebar", "activity bar", "control"}
        )
        if wants_control and source == "uia" and control_type in {"button", "image", "tabitem", "menuitem"}:
            interactive_bonus += 0.24
        if wants_control and source == "ocr":
            interactive_bonus -= 0.08
        if ("sidebar" in instruction_lower or "activity bar" in instruction_lower or "left" in instruction_lower) and x <= 72:
            interactive_bonus += 0.12
        if wants_text_input:
            if is_input_control:
                interactive_bonus += 0.30
            elif control_type in {"text", "image", "button", "tabitem", "menuitem"}:
                interactive_bonus -= 0.18

        # 5. Exact Match Bonus: give strong preference to exact case-insensitive matches
        exact_match_bonus = 0.30 if text_norm == target_norm else 0.0

        weighted = score * 0.94 + confidence * 0.06 + source_bonus + size_bonus + context_bonus + source_penalty + interactive_bonus + exact_match_bonus
        if weighted > best_score:
            best_score = weighted
            best_item = item

    if best_score < 0.52:
        return None

    return best_item


def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _wants_text_input(instruction_lower: str) -> bool:
    return any(
        hint in instruction_lower
        for hint in {
            "type",
            "enter",
            "search",
            "filter",
            "find",
            "input",
            "text field",
            "search bar",
            "marketplace search",
        }
    )


def _is_input_control(text_norm: str, control_type: str, automation_id: str) -> bool:
    if control_type in {"edit", "textbox", "combobox"}:
        return True
    searchable_text = f"{text_norm} {automation_id}"
    return any(hint in searchable_text for hint in {"search", "filter", "find"})


def _should_prefer_instruction_target(target: str, instruction: str) -> bool:
    instruction_norm = _normalize(instruction)
    target_norm = _normalize(target)
    if not instruction_norm or not target_norm or _wants_text_input(instruction_norm):
        return False

    action_hint = any(
        hint in instruction_norm
        for hint in {"click", "open", "select", "show", "locate", "point to", "find"}
    )
    control_hint = any(
        hint in instruction_norm
        for hint in {"icon", "button", "tab", "menu", "sidebar", "activity bar", "panel", "view"}
    )
    if not action_hint or not control_hint:
        return False

    if target_norm in instruction_norm:
        return False
    return not any(candidate in instruction_norm for candidate in _target_candidates(target))


def _instruction_target_candidates(instruction: str) -> list[str]:
    candidates = re.findall(r"['\"`]([^'\"`]+)['\"`]", instruction)

    patterns = [
        r"\b(?:click|open|select|show|locate|find)\s+(?:the\s+)?(.+?)\s+(?:icon|button|tab|menu|panel|view)\b",
        r"\bpoint\s+to\s+(?:the\s+)?(.+?)\s+(?:icon|button|tab|menu|panel|view)\b",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, instruction, flags=re.IGNORECASE):
            cleaned = _clean_instruction_candidate(match)
            if cleaned:
                candidates.append(cleaned)

    if not candidates:
        words = instruction.split()
        # Skip first word as it's often capitalized simply as the start of the sentence.
        for word in words[1:]:
            cleaned = _clean_instruction_candidate(word)
            if cleaned and cleaned[0].isupper() and cleaned.lower() not in _INSTRUCTION_STOP_WORDS:
                candidates.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _normalize(candidate)
        if key and key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def _clean_instruction_candidate(value: str) -> str:
    cleaned = value.strip(".,;:!?\"'()[]")
    cleaned = re.sub(r"\s+on\s+the\s+.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+in\s+the\s+.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+from\s+the\s+.*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _target_candidates(target: str) -> list[str]:
    normalized = _normalize(target)
    candidates = [normalized] if normalized else []
    generic_ui_words = {
        "icon",
        "button",
        "tab",
        "menu",
        "item",
        "control",
        "left",
        "right",
        "sidebar",
        "side",
        "bar",
        "activity",
        "panel",
    }
    stripped = " ".join(word for word in normalized.split() if word not in generic_ui_words)
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    return candidates


_INSTRUCTION_STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "about",
    "option",
    "button",
    "item",
    "tab",
    "menu",
    "sidebar",
}

