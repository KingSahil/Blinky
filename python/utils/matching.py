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

    # Special active window titlebar layout/settings button fallback:
    if "settings button left" in target_norm or "layout button" in target_norm or ("settings" in target_norm and "blinky" not in target_norm):
        top_right_buttons = []
        for item in ocr_items:
            # Exclude Blinky's own items by ensuring they are from the UIA active window (source is "uia")
            if item.get("source") == "uia" and float(item.get("y") or 0) <= 60:
                if item.get("control_type") == "Button":
                    top_right_buttons.append(item)
        
        # 1. First priority: look for a button whose text contains 'settings' or 'gear'
        for btn in top_right_buttons:
            btn_text = str(btn.get("text", "")).lower()
            if "settings" in btn_text or "gear" in btn_text:
                from utils.logging import get_logger
                get_logger("blinky.matching").info("Semantic Settings Button Priority Match: matched '%s' at (%d, %d)", btn.get("text"), btn["x"], btn["y"])
                return btn

        # 2. Second priority: look for a button whose text contains 'layout' or 'customize'
        for btn in top_right_buttons:
            btn_text = str(btn.get("text", "")).lower()
            if any(k in btn_text for k in {"layout", "customize", "control", "panel"}):
                from utils.logging import get_logger
                get_logger("blinky.matching").info("Semantic Layout Button Priority Match: matched '%s' at (%d, %d)", btn.get("text"), btn["x"], btn["y"])
                return btn

        # 3. Third priority: fall back by index (index 4 is 5th button (Settings), index 3 is 4th button (Layout))
        top_right_buttons.sort(key=lambda i: float(i.get("x") or 0), reverse=True)
        if "settings" in target_norm:
            if len(top_right_buttons) >= 5:
                layout_btn = top_right_buttons[4]
                from utils.logging import get_logger
                get_logger("blinky.matching").info("Semantic Settings Button Index Match: matched '%s' at (%d, %d)", layout_btn.get("text"), layout_btn["x"], layout_btn["y"])
                return layout_btn
        if len(top_right_buttons) >= 4:
            layout_btn = top_right_buttons[3]
            from utils.logging import get_logger
            get_logger("blinky.matching").info("Semantic Layout Button Index Match: matched '%s' at (%d, %d)", layout_btn.get("text"), layout_btn["x"], layout_btn["y"])
            return layout_btn

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

