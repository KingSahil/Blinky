from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# ── sys.path setup: must run before any platform-specific imports ──
_SCRIPT_DIR = Path(__file__).resolve().parent
_COMMON_PY = str(_SCRIPT_DIR)
if _COMMON_PY not in sys.path:
    sys.path.insert(0, _COMMON_PY)

# Add platform-specific python directory with higher priority
if sys.platform == "win32":
    _PLATFORM_PY = str(_SCRIPT_DIR.parent.parent / "windows" / "python")
else:
    _PLATFORM_PY = str(_SCRIPT_DIR.parent.parent / "linux" / "python")
if os.path.isdir(_PLATFORM_PY) and _PLATFORM_PY not in sys.path:
    sys.path.insert(0, _PLATFORM_PY)

from ai.client import ask_model, ask_text_model, get_provider_label
from ai.prompt import build_chat_prompt, build_preflight_prompt, build_prompt
from app_context import get_app_context
from capture import capture_screen
from computer_use import try_run_agent_action, is_web_destination, looks_like_app_name
from ocr import extract_visible_text
from utils.logging import get_logger
from utils.matching import attach_matches, find_best_match_with_score
from utils.screen_elements import assign_screen_element_refs
from utils.ui_map_cache import UiMapCache, window_signature
try:
    from uia import get_visible_ui_text
except ImportError:
    def get_visible_ui_text(**kwargs):
        return []
from utils.window import get_active_window, get_ignored_overlay_rects

LOGGER = get_logger("blinky.main")
UI_MAP_CACHE = UiMapCache()


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
            step["target_ref"] = best_input.get("ref", "")
            step["match"] = {
                **best_input,
                "match_method": "ref",
                "is_exact_text": True,
                "ambiguous_candidate_count": 1,
            }

    return steps


def run(
    question: str,
    previous_question: str | None = None,
    progress: dict | None = None,
    conversation_history: list[dict] | None = None,
    web_search_enabled: bool = False,
    agent_mode: bool = False,
) -> dict:
    started = time.perf_counter()
    warnings: list[str] = []

    if web_search_enabled:
        return run_web_intelligence(question, conversation_history, started, warnings)

    locator_target = extract_locator_target(question)
    force_screen = should_force_screen_context(question, previous_question)

    preflight = None
    if force_screen:
        LOGGER.info("Skipping preflight for screen-context question")
    else:
        preflight_started = time.perf_counter()
        preflight = classify_request(question, previous_question, warnings, conversation_history)
        log_stage_timing("preflight", preflight_started)

    intent = "DESKTOP_AUTOMATION"
    extracted_params = {}
    is_continuation = False

    if preflight:
        intent = preflight.get("intent", "DESKTOP_AUTOMATION")
        extracted_params = preflight.get("extracted_params", {}) or {}
        is_continuation = preflight.get("is_continuation", False)
    elif previous_question and is_followup_continuation_question(question):
        is_continuation = True

    if agent_mode:
        direct_agent_result = None
        if intent == "MEDIA_PLAYBACK":
            song = extracted_params.get("song_name")
            if song:
                from computer_use.tools import play_spotify_track_tool
                direct_agent_result = play_spotify_track_tool(song)
        elif intent == "OPEN_APP":
            app = extracted_params.get("app_name")
            if app:
                if is_web_destination(app) or is_in_app_action(app) or not looks_like_app_name(app):
                    LOGGER.info("Overriding OPEN_APP intent in main.py for app '%s' to DESKTOP_AUTOMATION", app)
                    intent = "DESKTOP_AUTOMATION"
                else:
                    from computer_use.tools import open_app_tool
                    direct_agent_result = open_app_tool(app)
        elif intent == "SYSTEM_SHORTCUT":
            shortcut = extracted_params.get("shortcut")
            if shortcut:
                from computer_use.tools import shortcut_tool
                direct_agent_result = shortcut_tool(shortcut)

        if direct_agent_result is not None and not direct_agent_result.success:
            LOGGER.info("Direct agent tool execution failed (success=False), falling back to screen mode.")
            direct_agent_result = None

        if direct_agent_result is None:
            direct_agent_result = try_run_agent_action(question)
            if direct_agent_result is not None and not direct_agent_result.success:
                LOGGER.info("try_run_agent_action tool execution failed (success=False), falling back to screen mode.")
                direct_agent_result = None

        if direct_agent_result is not None:
            return build_agent_tool_result(direct_agent_result.to_dict(), started, warnings)

    effective_question = question
    latest_update = None
    if is_continuation and previous_question:
        effective_question = previous_question
        latest_update = question
    else:
        progress = None

    needs_screen = force_screen
    if preflight:
        needs_screen = bool(preflight.get("needs_screen", True))
        
    if is_continuation:
        needs_screen = True

    if not needs_screen:
        chat_started = time.perf_counter()
        chat_result = answer_without_screen(question, conversation_history)
        log_stage_timing("chat", chat_started)
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

    # 1. Lock the target window by PID and capture the screenshot only after
    # we know the request needs screen context.
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

    capture_started = time.perf_counter()
    screenshot = capture_screen()
    log_stage_timing("capture", capture_started)
    # Print the capture marker to stdout and flush immediately so Rust can restore windows
    print("__BLINKY_CAPTURED__", flush=True)

    locator_result = resolve_locator_fast_path(question, screenshot, target_pid, warnings, started)
    if locator_result is not None:
        return locator_result

    if locator_target:
        LOGGER.info("Locator deferred to screen AI for '%s'", locator_target)

    observation = observe_app_state(screenshot, target_pid)
    active_app = observation["active_app"]
    visible_items = observation["visible_items"]

    if not visible_items:
        warnings.append("No OCR text was detected. Try zooming in or opening a supported app.")

    if agent_mode:
        agent_result = try_run_agent_action(question, observation)
        if agent_result is not None:
            return build_agent_tool_result(agent_result.to_dict(), started, warnings, observation)

    prompt_started = time.perf_counter()
    prompt = build_prompt(
        question=effective_question,
        active_app=active_app,
        ocr_items=visible_items,
        app_context=observation.get("app_context", ""),
        progress=progress,
        latest_update=latest_update,
        conversation_history=conversation_history,
    )
    log_stage_timing("prompt_build", prompt_started)
    model_started = time.perf_counter()
    ai_result = ask_model(prompt=prompt, screenshot_path=screenshot.path)
    log_stage_timing("model", model_started)
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
        "app_context": observation.get("app_context", ""),
        "ocr": {"count": len(visible_items), "items": visible_items[:200]},
        "screenshot": {
            "path": str(screenshot.path),
            "width": screenshot.width,
            "height": screenshot.height,
            "screen_width": screenshot.screen_width,
            "screen_height": screenshot.screen_height,
        },
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings + ai_result.get("warnings", []),
        "is_continuation": is_continuation,
    }


def observe_app_state(screenshot, target_pid: int | None = None) -> dict:
    active_started = time.perf_counter()
    active_app = get_active_window(target_pid=target_pid)
    log_stage_timing("active_window", active_started)
    visible_items = get_or_build_visible_ui_map(active_app, screenshot, target_pid)
    app_context = get_app_context(active_app)
    return {
        "active_app": active_app,
        "visible_items": visible_items,
        "app_context": app_context,
        "screenshot": screenshot,
    }


def build_agent_tool_result(
    agent_action: dict,
    started: float,
    warnings: list[str],
    observation: dict | None = None,
) -> dict:
    active_app = {"title": "", "process": "", "supported": False}
    visible_items: list[dict] = []
    screenshot_payload = None
    app_context = ""

    if observation:
        active_app = observation.get("active_app", active_app)
        visible_items = observation.get("visible_items", [])
        app_context = observation.get("app_context", "")
        screenshot = observation.get("screenshot")
        if screenshot:
            screenshot_payload = {
                "path": str(screenshot.path),
                "width": screenshot.width,
                "height": screenshot.height,
                "screen_width": screenshot.screen_width,
                "screen_height": screenshot.screen_height,
            }
    else:
        try:
            time.sleep(0.5)
            active_app = get_active_window()
            app_context = get_app_context(active_app)
        except Exception:
            pass

    summary = str(agent_action.get("message") or "Agent action completed.").strip()
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    result = {
        "summary": summary,
        "steps": [],
        "active_app": active_app,
        "app_context": app_context,
        "ocr": {"count": len(visible_items), "items": visible_items[:200]},
        "elapsed_ms": elapsed_ms,
        "provider": "local",
        "warnings": warnings,
        "is_continuation": False,
        "agent_action": agent_action,
    }
    if screenshot_payload:
        result["screenshot"] = screenshot_payload
    return result


def get_or_build_visible_ui_map(active_app: dict, screenshot, target_pid: int | None = None) -> list[dict]:
    signature = window_signature(active_app, screenshot, target_pid=target_pid)

    def build_items() -> list[dict]:
        ocr_started = time.perf_counter()
        ocr_items = extract_visible_text(screenshot.path)
        ocr_items = filter_ignored_overlay_items(ocr_items, screenshot)
        log_stage_timing("ocr", ocr_started)
        uia_started = time.perf_counter()
        uia_items = get_visible_ui_text(target_pid=target_pid)
        log_stage_timing("uia", uia_started)

        if os.name != "nt":
            # On Linux (GNOME/Wayland), the system status bar is at the very top (y < 35 in optimized screenshot pixels).
            # We filter out these elements to prevent accidental matching of system tray clocks, status indicators, or active app labels.
            ocr_items_filtered = [item for item in ocr_items if item.get("y", 0) >= 35]
            uia_items_filtered = [item for item in uia_items if item.get("y", 0) >= 35]
        else:
            ocr_items_filtered = ocr_items
            uia_items_filtered = uia_items

        # UIA returns coordinates in screen-absolute space (physical pixel dimensions).
        # The screenshot is scaled down to fit within 1920x1080 (thumbnail).
        # The overlay then scales everything back up by (window.innerWidth / screenshot.width).
        # To make both scales cancel correctly, we must first convert UIA coords
        # from screen space -> screenshot space before the overlay sees them.
        if screenshot.screen_width != screenshot.width or screenshot.screen_height != screenshot.height:
            uia_items_filtered = scale_uia_items_to_screenshot(uia_items_filtered, screenshot)

        merged = assign_screen_element_refs(merge_visible_items(ocr_items_filtered, uia_items_filtered))
        merged.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
        return merged

    visible_items = UI_MAP_CACHE.get_or_build(signature, build_items)
    visible_items.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
    return visible_items


# All query resolution is handled automatically by the AI model.


def is_in_app_action(app_name: str) -> bool:
    app_lower = app_name.lower().strip()
    in_app_keywords = {
        "tab", "tabs", "settings", "menu", "sidebar", "extensions", "status", "profile",
        "chat", "chats", "bookmark", "bookmarks", "download", "downloads", "folder", "folders",
        "file", "files", "history", "recent", "preferences", "terminal", "console"
    }
    return any(re.search(rf"\b{re.escape(word)}\b", app_lower) for word in in_app_keywords)


def classify_request(
    question: str,
    previous_question: str | None,
    warnings: list[str],
    conversation_history: list[dict] | None = None,
) -> dict | None:
    try:
        payload = ask_text_model(build_preflight_prompt(question, previous_question, conversation_history))
    except Exception as exc:
        LOGGER.warning("Preflight classification failed; falling back to screen mode: %s", exc)
        warnings.append(f"Preflight classification failed: {exc}")
        return None

    intent = payload.get("intent")
    extracted_params = payload.get("extracted_params", {}) or {}
    
    # Safety check: if intent is OPEN_APP but targets web UI, an in-app
    # feature/action, or a query, override to DESKTOP_AUTOMATION.
    if intent == "OPEN_APP":
        app_name = extracted_params.get("app_name", "")
        if app_name and (is_web_destination(app_name) or is_in_app_action(app_name) or not looks_like_app_name(app_name)):
            LOGGER.info("Overriding OPEN_APP intent with app_name '%s' to DESKTOP_AUTOMATION", app_name)
            intent = "DESKTOP_AUTOMATION"

    if intent:
        needs_screen = intent == "DESKTOP_AUTOMATION"
    else:
        needs_screen = bool(payload.get("needs_screen", True))
        intent = "DESKTOP_AUTOMATION" if needs_screen else "INFORMATIONAL_CHAT"
    is_continuation = bool(payload.get("is_continuation", False))
    return {
        "intent": intent,
        "needs_screen": needs_screen,
        "is_continuation": is_continuation,
        "extracted_params": extracted_params
    }


def answer_without_screen(question: str, conversation_history: list[dict] | None = None) -> dict:
    payload = ask_text_model(build_chat_prompt(question, conversation_history))
    summary = str(payload.get("summary", "")).strip()
    if not summary:
        raise RuntimeError("The chat model returned an empty reply.")
    return {"summary": summary, "steps": []}


def run_web_intelligence(
    question: str,
    conversation_history: list[dict] | None,
    started: float,
    warnings: list[str],
) -> dict:
    import asyncio
    from wil.pipeline import WILPipeline

    def on_status(phase: str, data: dict) -> None:
        message = data.get("message", f"Web search stage: {phase}")
        print(json.dumps({"type": "status", "phase": phase, "message": message}), flush=True)
        LOGGER.info("WIL pipeline status [%s]: %s", phase, message)

    def on_chunk(chunk: str) -> None:
        if chunk.strip().startswith("[Synthesis Error"):
            return
        print(json.dumps({"type": "chunk", "message": chunk}), flush=True)

    result = asyncio.run(
        WILPipeline().run(
            query=question,
            conversation_history=conversation_history,
            on_status=on_status,
            on_chunk=on_chunk,
        )
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": str(result.get("synthesized_response", "")).strip(),
        "steps": [],
        "active_app": {"title": "", "process": "", "supported": False},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
        "web": {
            "needs_web_search": result.get("needs_web_search", True),
            "searxng_offline": result.get("searxng_offline", False),
            "sources": result.get("sources", []),
        },
    }


def resolve_locator_fast_path(question: str, screenshot, target_pid: int | None, warnings: list[str], started: float) -> dict | None:
    target = extract_locator_target(question) or extract_click_target(question)
    if not target:
        return None

    active_started = time.perf_counter()
    active_app = get_active_window(target_pid=target_pid)
    log_stage_timing("locator.active_window", active_started)
    uia_started = time.perf_counter()
    wants_control = is_control_locator_question(question)
    uia_items = get_visible_ui_text(target_pid=target_pid, include_unlabeled=True)
    log_stage_timing("locator.uia", uia_started)

    if screenshot.screen_width != screenshot.width or screenshot.screen_height != screenshot.height:
        uia_items = scale_uia_items_to_screenshot(uia_items, screenshot)

    uia_items.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
    match_items = locator_match_items(question, uia_items)
    instruction = f"Locate the {target} control."
    if match_items:
        match_result = find_best_match_with_score(target, match_items, instruction)
        if match_result:
            if should_accept_locator_match(question, match_result):
                return build_locator_result(
                    question,
                    target,
                    match_result["item"],
                    uia_items,
                    active_app,
                    screenshot,
                    warnings,
                    started,
                    match_result,
                )
            LOGGER.info(
                "Locator deferred to AI for '%s' reason=low_control_confidence score=%.3f text_similarity=%.3f candidate_count=%d",
                target,
                match_result["score"],
                match_result["text_similarity"],
                match_result["candidate_count"],
            )
            return None

    ocr_started = time.perf_counter()
    ocr_items = extract_visible_text(screenshot.path)
    ocr_items = filter_ignored_overlay_items(ocr_items, screenshot)
    log_stage_timing("locator.ocr", ocr_started)
    if os.name != "nt":
        ocr_items = [item for item in ocr_items if item.get("y", 0) >= 35]
        uia_items = [item for item in uia_items if item.get("y", 0) >= 35]

    visible_items = assign_screen_element_refs(merge_visible_items(ocr_items, uia_items))
    visible_items.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
    match_result = find_best_match_with_score(target, locator_match_items(question, visible_items), instruction)
    if match_result:
        if should_accept_locator_match(question, match_result):
            return build_locator_result(
                question,
                target,
                match_result["item"],
                visible_items,
                active_app,
                screenshot,
                warnings,
                started,
                match_result,
            )
        LOGGER.info(
            "Locator deferred to AI for '%s' reason=low_control_confidence score=%.3f text_similarity=%.3f candidate_count=%d",
            target,
            match_result["score"],
            match_result["text_similarity"],
            match_result["candidate_count"],
        )
        return None

    if wants_control or icon_like_control_candidates(locator_match_items(question, uia_items)):
        LOGGER.info("Locator deferred to AI for '%s' reason=icon_or_control_needs_ai", target)
        return None

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    LOGGER.info("Locator local path did not find '%s' after checking %d visible items", target, len(visible_items))
    return {
        "summary": f"I could not find {target} on the current screen.",
        "steps": [],
        "active_app": active_app,
        "ocr": {"count": len(visible_items), "items": visible_items[:80]},
        "screenshot": {
            "path": str(screenshot.path),
            "width": screenshot.width,
            "height": screenshot.height,
            "screen_width": screenshot.screen_width,
            "screen_height": screenshot.screen_height,
        },
        "elapsed_ms": elapsed_ms,
        "provider": "local",
        "warnings": warnings,
        "is_continuation": False,
    }


def locator_match_items(question: str, items: list[dict]) -> list[dict]:
    return items if "blinky" in question.lower() else [item for item in items if item.get("source") != "blinky"]


def is_control_locator_question(question: str) -> bool:
    normalized = question.lower()
    return any(
        hint in normalized
        for hint in {
            "button",
            "icon",
            "control",
            "tab",
            "menu",
            "sidebar",
            "side bar",
            "activity bar",
            "search bar",
            "input",
            "text field",
            "field",
        }
    )


def should_accept_locator_match(question: str, match_result: dict) -> bool:
    if not is_control_locator_question(question):
        return bool(match_result["is_exact_text"] or match_result["text_similarity"] >= 0.86 or match_result["score"] >= 0.82)

    control_type = str(match_result.get("control_type", "")).lower()
    source = str(match_result.get("source", "")).lower()
    is_interactive = source == "uia" and control_type in {"button", "image", "tabitem", "menuitem", "edit", "textbox", "combobox"}
    if not is_interactive:
        return False
    if int(match_result.get("ambiguous_candidate_count") or match_result.get("candidate_count") or 0) > 1:
        return False
    if bool(match_result.get("is_exact_text")):
        return float(match_result.get("score") or 0) >= 0.9
    return float(match_result.get("score") or 0) >= 0.95 and float(match_result.get("text_similarity") or 0) >= 0.86


def icon_like_control_candidates(items: list[dict]) -> list[dict]:
    candidates = []
    for item in items:
        if item.get("source") == "blinky":
            continue
        control_type = str(item.get("control_type", "")).lower()
        if control_type not in {"button", "image", "hyperlink"}:
            continue
        width = float(item.get("width") or 0)
        height = float(item.get("height") or 0)
        if width < 12 or height < 12 or width > 120 or height > 120:
            continue
        candidates.append(item)
    return candidates


def build_locator_result(
    question: str,
    target: str,
    match: dict,
    visible_items: list[dict],
    active_app: dict,
    screenshot,
    warnings: list[str],
    started: float,
    match_result: dict | None = None,
) -> dict:
    match_with_metadata = {**match}
    if match_result:
        match_with_metadata.update({
            "score": match_result.get("score", 1.0),
            "text_similarity": match_result.get("text_similarity", 1.0),
            "is_exact_text": match_result.get("is_exact_text", True),
            "match_method": "text" if match_result.get("match_method") != "ref" else "ref",
            "candidate_count": match_result.get("candidate_count", 1),
            "ambiguous_candidate_count": match_result.get("ambiguous_candidate_count", 1),
        })
    else:
        match_with_metadata.update({
            "score": 1.0,
            "text_similarity": 1.0,
            "is_exact_text": True,
            "match_method": "ref" if match.get("ref") else "text",
            "candidate_count": 1,
            "ambiguous_candidate_count": 1,
        })

    step = {
        "step": 1,
        "instruction": local_target_instruction(question, target),
        "target_text": str(match.get("text") or target),
        "target_ref": str(match.get("ref", "")),
        "match": match_with_metadata,
    }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if match_result:
        LOGGER.info(
            "Locator accepted local match '%s' to '%s' score=%.3f text_similarity=%.3f candidate_count=%d",
            target,
            match.get("text"),
            match_result["score"],
            match_result["text_similarity"],
            match_result["candidate_count"],
        )
    else:
        LOGGER.info("Locator fast path matched '%s' to '%s'", target, match.get("text"))
    return {
        "summary": f"I found the {target} in the active app.",
        "steps": [step],
        "active_app": active_app,
        "ocr": {"count": len(visible_items), "items": visible_items[:80]},
        "screenshot": {
            "path": str(screenshot.path),
            "width": screenshot.width,
            "height": screenshot.height,
            "screen_width": screenshot.screen_width,
            "screen_height": screenshot.screen_height,
        },
        "elapsed_ms": elapsed_ms,
        "provider": "local",
        "warnings": warnings,
        "is_continuation": False,
    }


def extract_locator_target(question: str) -> str | None:
    text = " ".join(question.strip().split())
    if not text:
        return None

    patterns = [
        r"^where\s+(?:is|are)\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"^where\s+can\s+i\s+find\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"^where\s+do\s+i\s+find\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"^show\s+me\s+where\s+(?:the\s+)?(.+?)\s+(?:is|are)(?:\?|$)",
        r"^show\s+me\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"^point\s+to\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"^locate\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"^highlight\s+(?:the\s+)?(.+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_locator_target(match.group(1))
    return None


def extract_click_target(question: str) -> str | None:
    text = " ".join(question.strip().split())
    if not text:
        return None

    patterns = [
        r"^(?:click|select|choose|press)\s+(?:on\s+)?(?:the\s+)?(.+?)(?:\?|$)",
        r"^(?:tap)\s+(?:on\s+)?(?:the\s+)?(.+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_locator_target(match.group(1))
    return None


def is_click_target_question(question: str) -> bool:
    return extract_click_target(question) is not None


def local_target_instruction(question: str, target: str) -> str:
    if is_click_target_question(question):
        return f"Click {target}."
    return f"Here is the {target}."


def should_force_screen_context(question: str, previous_question: str | None = None) -> bool:
    normalized = " ".join(question.lower().strip().split())
    if not normalized:
        return False

    if is_general_chat_question(normalized):
        return False
    if extract_locator_target(normalized):
        return True
    if previous_question and is_followup_continuation_question(normalized):
        return True

    screen_action_words = {
        "click",
        "open",
        "select",
        "choose",
        "install",
        "download",
        "enable",
        "disable",
        "configure",
        "setup",
        "set up",
        "run",
        "launch",
        "navigate",
        "find",
        "search",
        "locate",
        "highlight",
        "show",
        "where",
        "button",
        "icon",
        "menu",
        "tab",
        "sidebar",
        "side bar",
        "control",
        "settings",
        "extension",
        "folder",
        "file",
        "screen",
        "window",
        "app",
    }
    return any(word in normalized for word in screen_action_words)


def is_followup_continuation_question(question: str) -> bool:
    normalized = normalize_question_text(question)
    return normalized in {
        "next",
        "what next",
        "what now",
        "now what",
        "continue",
        "go on",
        "done",
        "finished",
        "show next step",
        "what to do",
        "what do i do",
        "how do i proceed",
        "how to proceed",
    }


def is_general_chat_question(question: str) -> bool:
    normalized = normalize_question_text(question)
    greetings = {
        "hi",
        "hello",
        "hey",
        "yo",
        "how are you",
        "how r u",
        "how are u",
        "how are you doing",
        "what can you do",
        "what do you do",
        "who are you",
        "who r u",
        "thanks",
        "thank you",
    }
    return normalized in greetings


def normalize_question_text(question: str) -> str:
    return " ".join(re.sub(r"[?!.]+$", "", question.lower().strip()).split())


def normalize_conversation_history(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    history: list[dict] = []
    for item in value[-10:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        content = " ".join(str(item.get("content", "")).split())
        if role not in {"student", "blinky"} or not content:
            continue
        history.append({"role": role, "content": content[:1000]})
    return history


def clean_locator_target(value: str) -> str | None:
    cleaned = value.strip(" .,!?:;\"'`()[]")
    cleaned = re.sub(r"\s+(?:in|on|from)\s+the\s+.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:button|icon|tab|menu|control|panel|view|folder)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .,!?:;\"'`()[]")
    return cleaned or None


def scale_uia_items_to_screenshot(uia_items: list[dict], screenshot) -> list[dict]:
    sx = screenshot.width / screenshot.screen_width
    sy = screenshot.height / screenshot.screen_height
    LOGGER.info(
        "Scaling UIA coords from screen (%dx%d) -> screenshot (%dx%d)  sx=%.4f sy=%.4f",
        screenshot.screen_width,
        screenshot.screen_height,
        screenshot.width,
        screenshot.height,
        sx,
        sy,
    )
    return [
        {
            **item,
            "x": int(item["x"] * sx),
            "y": int(item["y"] * sy),
            "width": max(1, int(item["width"] * sx)),
            "height": max(1, int(item["height"] * sy)),
        }
        for item in uia_items
    ]


def log_stage_timing(stage: str, started: float) -> None:
    LOGGER.info("Timing: %s took %dms", stage, int((time.perf_counter() - started) * 1000))


def filter_ignored_overlay_items(items: list[dict], screenshot) -> list[dict]:
    rects = get_ignored_overlay_rects()
    if not rects:
        return items

    sx = screenshot.width / screenshot.screen_width
    sy = screenshot.height / screenshot.screen_height
    scaled_rects = [
        {
            "x": rect["x"] * sx,
            "y": rect["y"] * sy,
            "width": rect["width"] * sx,
            "height": rect["height"] * sy,
        }
        for rect in rects
    ]
    filtered = [item for item in items if not _item_center_in_any_rect(item, scaled_rects)]
    removed = len(items) - len(filtered)
    if removed:
        LOGGER.info("Filtered %d OCR items inside ignored overlay windows", removed)
    return filtered


def _item_center_in_any_rect(item: dict, rects: list[dict]) -> bool:
    cx = float(item.get("x") or 0) + float(item.get("width") or 0) / 2
    cy = float(item.get("y") or 0) + float(item.get("height") or 0) / 2
    return any(
        cx >= rect["x"] and
        cy >= rect["y"] and
        cx <= rect["x"] + rect["width"] and
        cy <= rect["y"] + rect["height"]
        for rect in rects
    )



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
        conversation_history = normalize_conversation_history(payload.get("conversation_history"))
        web_search_enabled = bool(payload.get("web_search_enabled", False))
        agent_mode = bool(payload.get("agent_mode", False))
        if not question:
            raise ValueError("Question is required.")

        result = run(question, previous_question, progress, conversation_history, web_search_enabled, agent_mode)
        print(json.dumps(result, ensure_ascii=True))
    except Exception as exc:
        LOGGER.exception("Worker failed")
        print(json.dumps({"error": str(exc), "steps": [], "warnings": [str(exc)]}))
        sys.exit(1)


if __name__ == "__main__":
    main()
