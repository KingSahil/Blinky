"""
Text-Based UI Grounder for Blinky Agent Mode.

Grounds procedural steps against OmniParser / UIA / OCR visible items
using fast text matching, fuzzy similarity, and Groq text model disambiguation.
Runs entirely on text data — completely avoids vision model screenshot token limits.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any

from ai.client import ask_text_model
from utils.logging import get_logger
from utils.screen_elements import assign_screen_element_refs, screen_element_name

LOGGER = get_logger("blinky.computer_use.text_grounder")


def calculate_text_similarity(s1: str, s2: str) -> float:
    """Calculate normalized similarity ratio between two strings."""
    if not s1 or not s2:
        return 0.0
    s1_clean = re.sub(r"[^\w\s]", "", s1.lower()).strip()
    s2_clean = re.sub(r"[^\w\s]", "", s2.lower()).strip()
    if not s1_clean or not s2_clean:
        return 0.0
    if s1_clean == s2_clean:
        return 1.0
    if s1_clean in s2_clean or s2_clean in s1_clean:
        return 0.9
    return difflib.SequenceMatcher(None, s1_clean, s2_clean).ratio()


def ground_step_to_screen(
    planned_step: dict[str, Any],
    visible_items: list[dict[str, Any]],
    active_app: dict[str, Any] | None = None,
    failed_refs: set[str] | None = None,
    failed_targets: set[str] | None = None,
    user_task: str = "",
) -> dict[str, Any] | None:
    """
    Ground a procedural step (target, action, instruction) to an exact visible screen element
    extracted by OmniParser, UIA, or OCR.
    """
    if not visible_items:
        LOGGER.warning("ground_step_to_screen called with empty visible_items")
        return None

    failed_refs_set = {str(r).strip() for r in (failed_refs or set())}
    failed_targets_set = {str(t).lower().strip() for t in (failed_targets or set())}

    target = str(planned_step.get("target", "")).strip()
    instruction = str(planned_step.get("instruction", "")).strip()
    action = str(planned_step.get("action", "click")).lower().strip()

    if not target and not instruction:
        return None

    # Ignore items that belong to Blinky's own floating UI
    blinky_ignored_terms = {
        "blinky app", "blinky command", "ctrl + shift", "space", "enter", "ask anything",
        "groq", "ollama", "shortcut key", "theme: ember", "about: v1.0.0", "action guide",
        "blinky"
    }

    filtered_visible = []
    for it in visible_items:
        if str(it.get("source", "")).lower() == "blinky":
            continue
        # Strictly ignore items that failed on previous actions in this task
        item_ref = str(it.get("ref", "")).strip()
        if item_ref and item_ref in failed_refs_set:
            continue
        text_val = str(it.get("text", "")).lower().strip()
        if any(term in text_val for term in blinky_ignored_terms):
            continue
        if text_val and text_val in failed_targets_set:
            continue
        filtered_visible.append(it)

    if not filtered_visible:
        return None

    # Ensure all visible items have @ref assigned
    ref_items = assign_screen_element_refs(filtered_visible)

    target_lower = target.lower()
    instruction_lower = instruction.lower()

    # Safety: Window titlebar control buttons that should NEVER be clicked unless explicitly asked
    window_control_keywords = {"close", "close window", "minimize", "maximize", "restore", "system close"}
    is_explicit_window_control = any(w in target_lower or w in instruction_lower for w in ["close window", "minimize", "maximize", "exit", "quit"])

    best_item: dict[str, Any] | None = None
    best_score = 0.0

    # 1. First pass: Heuristic matching (exact match, contains, fuzzy similarity)
    # If there were previous failures, we require higher confidence or prefer AI re-evaluation
    for item in ref_items:
        text = screen_element_name(item) or str(item.get("text", "")).strip()
        if not text:
            continue

        text_lower = text.lower()

        # Reject accidental clicks on window close/minimize/maximize buttons
        if not is_explicit_window_control:
            if text_lower in window_control_keywords or text_lower.startswith("close ") or "close settings" in text_lower or text_lower.endswith(" close button"):
                continue

        score = 0.0

        # Exact target match
        if target_lower and text_lower == target_lower:
            score = 1.05
        elif target_lower and text_lower.startswith(target_lower):
            # Text starts with target (e.g. "Colors - Accent color, transparency effects" starts with "colors")
            score = 0.98
        elif target_lower and re.search(rf"\b{re.escape(target_lower)}\b", text_lower):
            # Target is a distinct word within the text
            len_ratio = len(target_lower) / max(len(target_lower), len(text_lower))
            score = 0.88 + (0.1 * len_ratio)
        elif target_lower and (target_lower in text_lower or text_lower in target_lower):
            len_ratio = min(len(target_lower), len(text_lower)) / max(len(target_lower), len(text_lower))
            score = 0.80 + (0.1 * len_ratio)
        else:
            sim = calculate_text_similarity(target_lower or instruction_lower, text_lower)
            if sim >= 0.70:
                score = sim * 0.85

        # Prioritize interactive / clickable controls or OmniParser detected buttons
        ctype = str(item.get("control_type", "")).lower()
        is_interactive = bool(item.get("clickable")) or str(item.get("source", "")).lower() == "omniparser" or ctype in ("button", "menuitem", "tabitem", "listitem", "hyperlink", "icon", "combobox", "radiobutton", "checkbox", "group")
        is_static_text = ctype in ("text", "textblock", "label", "static", "heading", "title", "header") and not item.get("clickable")

        if action in ("click", "press"):
            if is_interactive:
                score += 0.15
            elif is_static_text:
                # Heavy penalty for static non-clickable headers/labels when seeking a click action
                score -= 0.35
        elif action == "type" and (item.get("input") or ctype in ("edit", "textbox", "searchbox", "combobox")):
            score += 0.20

        if score > best_score:
            best_score = score
            best_item = item

    # If heuristic match is confident (>= 0.75) and no previous failure occurred, return immediately
    if best_item is not None and best_score >= 0.75 and not failed_refs_set and not failed_targets_set:
        LOGGER.info(
            "Grounded step target '%s' to '%s' (@%s) via heuristic match (score=%.2f)",
            target,
            screen_element_name(best_item),
            best_item.get("ref", ""),
            best_score,
        )
        return _build_grounded_step(planned_step, best_item, best_score)

    # 2. Second pass: Disambiguate / Self-Heal using fast Groq text LLM (pure text prompt, zero screenshots)
    try:
        compact_lines = []
        for it in ref_items[:60]:
            name = screen_element_name(it)
            if name:
                compact_lines.append(
                    f"{it.get('ref')} role={it.get('control_type', 'Control')} name=\"{name}\" source={it.get('source', '')}"
                )

        if compact_lines:
            failure_note = ""
            if failed_refs_set or failed_targets_set:
                failure_note = f"\nCRITICAL NOTE: Previous attempts to interact with {list(failed_targets_set)} (ref IDs: {list(failed_refs_set)}) had no effect or failed. DO NOT select those. Find the alternative element that actually accomplishes the task.\n"

            disambiguate_prompt = f"""You are Blinky's Intelligent UI Grounder & Self-Healing Decision Maker.
Select the exact screen element that accomplishes this step:
Overall Task: {user_task or instruction or target}
Step: {instruction or target}
Target: {target}
Action: {action}
{failure_note}
Visible UI items on screen:
{chr(10).join(compact_lines)}

Which @ref corresponds to the correct target element?
Respond ONLY with a JSON object:
{{"target_ref": "@ref", "reasoning": "why this item is the correct target"}}
"""
            llm_res = ask_text_model(disambiguate_prompt, max_tokens=150)
            if isinstance(llm_res, dict) and llm_res.get("target_ref"):
                chosen_ref = str(llm_res.get("target_ref", "")).strip()
                for it in ref_items:
                    if it.get("ref") == chosen_ref:
                        LOGGER.info("Grounded step target '%s' to @%s via Groq text re-thinker", target, chosen_ref)
                        return _build_grounded_step(planned_step, it, 0.95)
    except Exception as exc:
        LOGGER.warning("Groq text grounding disambiguation failed: %s", exc)

    # If heuristic had a moderate match (>= 0.60), fall back to it
    if best_item is not None and best_score >= 0.60:
        return _build_grounded_step(planned_step, best_item, best_score)

    LOGGER.info("No confident on-screen match found for step target '%s'", target)
    return None


def _build_grounded_step(
    planned_step: dict[str, Any],
    item: dict[str, Any],
    score: float,
) -> dict[str, Any]:
    display_name = screen_element_name(item) or str(item.get("text", "")).strip()
    match_dict = {
        "ref": str(item.get("ref", "")),
        "x": int(item.get("x", 0)),
        "y": int(item.get("y", 0)),
        "width": int(item.get("width", 0)),
        "height": int(item.get("height", 0)),
        "source": item.get("source", "omniparser"),
        "control_type": item.get("control_type", "Control"),
        "score": round(score, 3),
        "text_similarity": round(score, 3),
        "is_exact_text": score >= 0.95,
        "match_method": "text_grounder",
    }
    return {
        "step": planned_step.get("step", 1),
        "instruction": planned_step.get("instruction") or f"Click {display_name}",
        "target_text": display_name or planned_step.get("target", ""),
        "planned_target": str(planned_step.get("target", "")).strip(),
        "target_ref": str(item.get("ref", "")),
        "match": match_dict,
        "action": planned_step.get("action", "click"),
        "text_to_type": planned_step.get("text_to_type", ""),
        "key": planned_step.get("key", ""),
    }
