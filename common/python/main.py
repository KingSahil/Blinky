from __future__ import annotations

from runtime_limits import configure_worker_threads
configure_worker_threads()

import json
import os
import platform
import re
import sys
import time
from pathlib import Path

# â”€â”€ sys.path setup: must run before any platform-specific imports â”€â”€
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

def _load_env_file() -> None:
    for candidate in [
        _SCRIPT_DIR.parent.parent / ".env",
        _SCRIPT_DIR.parent / ".env",
        Path.cwd() / ".env",
    ]:
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass
            break

_load_env_file()

from ai.client import ask_model, ask_text_model, get_provider_label
from ai.prompt import build_chat_prompt, build_preflight_prompt, build_prompt


def _emit_status(phase: str, message: str) -> None:
    """Emit a progress status event to stdout for the frontend."""
    out = sys.__stdout__ if hasattr(sys, '__stdout__') else sys.stdout
    print(json.dumps({"type": "status", "phase": phase, "message": message}), flush=True, file=out)


def _has_computer_use_action(question: str) -> bool:
    """Check if a query contains action verbs beyond just opening an app."""
    normalized = question.lower().strip()
    action_verbs = {
        "calculate", "compute", "type", "click", "press",
        "search", "search for", "find", "look up", "navigate to", "go to",
        "scroll", "select", "choose", "fill", "enter",
        "write", "input", "submit", "open a", "open the",
    }
    return any(verb in normalized for verb in action_verbs)
from app_context import get_app_context
from capture import capture_screen
from computer_use import try_run_agent_action, is_web_destination, looks_like_app_name
from computer_use.tools import normalize_app_name, APP_PROTOCOLS, APP_NAME_ALIASES
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
try:
    from uia import get_shell_ui_items
except ImportError:
    def get_shell_ui_items():
        return []
try:
    from ocr.icon_detect import detect_icons, is_available as icon_model_available
except ImportError:
    def detect_icons(image_path, conf_thresh=None, iou_thresh=None):
        return []
    def icon_model_available():
        return False
try:
    from utils.icon_text_merge import merge_icon_boxes
except ImportError:
    def merge_icon_boxes(visible_items, icon_boxes):
        return list(visible_items)
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

            # Skip browser address/URL bars to avoid highlighting them instead of page-level inputs
            is_url = text.startswith(("http://", "https://", "www.")) or re.search(r"^[a-z0-9-]+\.[a-z]{2,}", text)
            is_address_bar = item.get("is_address_bar", False) or is_url or any(
                phrase in text
                for phrase in {
                    "search or enter web address",
                    "search or enter address",
                    "address and search bar",
                    "search or type web address",
                    "search or type a web address",
                    "search or type url",
                    "enter search term or address",
                }
            )
            if is_address_bar:
                continue

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


def is_screen_explanation_question(question: str) -> bool:
    normalized = " ".join(question.lower().strip().split())
    if not normalized:
        return False
    patterns = [
        r"\bwhat(?:'s|\s+is)\s+on\s+(?:my\s+|the\s+)?screen\b",
        r"\bwhats\s+on\s+(?:my\s+|the\s+)?screen\b",
        r"\bwhat\s+do\s+you\s+see(?:\s+on\s+(?:my\s+|the\s+)?screen)?\b",
        r"\bdescribe\s+(?:my\s+|the\s+)?screen\b",
        r"\bexplain\s+(?:my\s+|the\s+)?screen\b",
        r"\bwhat\s+am\s+i\s+looking\s+at\b",
        r"\bread\s+(?:my\s+|the\s+)?screen\b",
        r"\bsummarize\s+(?:my\s+|the\s+)?screen\b",
        r"\btell\s+me\s+what(?:'s|\s+is)\s+on\s+(?:my\s+|the\s+)?screen\b",
        r"\bwhat\s+is\s+open\s+on\s+(?:my\s+|the\s+)?screen\b",
        r"\bwhat\s+windows\s+are\s+open\b",
        r"\bwhat\s+app\s+is\s+open\b",
    ]
    return any(re.search(pat, normalized) for pat in patterns)


def should_skip_preflight_for_local_fast_path(question: str) -> bool:
    normalized = " ".join(question.lower().strip().split())
    if not normalized:
        return False
    if is_followup_continuation_question(normalized):
        return True
    if is_screen_explanation_question(normalized):
        return True
    click_words = {
        "click", "select", "choose", "press", "tap", "change", "switch", "set",
        "find", "locate", "spot", "hit", "push", "where", "show", "point", "look"
    }
    words = normalized.split()
    first_word = words[0] if words else ""
    if first_word in click_words:
        return True
    if extract_locator_target(normalized) or extract_click_target(normalized):
        return True
    return False



def is_procedural_step_completed(
    step: dict[str, Any],
    completed_targets: set[str],
    completed_instructions: set[str],
) -> bool:
    tgt = str(step.get("target", "")).lower().strip()
    instr = str(step.get("instruction", "")).lower().strip()

    if not tgt and not instr:
        return True

    if tgt:
        if tgt in completed_targets:
            return True
        for c in completed_targets:
            c_str = str(c).lower().strip()
            if len(c_str) >= 3 and len(tgt) >= 3 and (tgt in c_str or c_str in tgt):
                return True

    if instr:
        if instr in completed_instructions:
            return True
        for i in completed_instructions:
            i_str = str(i).lower().strip()
            if len(i_str) >= 5 and len(instr) >= 5 and (instr in i_str or i_str in instr):
                return True

    return False


def is_web_research_question(question: str) -> bool:
    norm = " ".join(question.lower().strip().split())
    if not norm:
        return False
    if norm.startswith(("click ", "press ", "type ", "tap ", "select ", "choose ", "open ", "launch ", "start ")):
        return False
    research_indicators = [
        "contact number", "phone number", "phone numbers", "contact details", "address", "addresses",
        "best restaurant", "best restaurants", "best cafe", "best cafes", "top rated", "recommendations for",
        "best ", "top ", "cheapest ", "compare ", "comparison ", "vs ", " versus ",
        "what is the price", "how much is", "how much does", "price of ", "cost of ",
        "weather in", "weather today", "weather forecast",
        "who won", "latest news", "stock price", "reviews of", "reviews for",
        "buy ", "purchase ", "shopping ", "deal ", "discount ", "offer ",
    ]
    return any(ind in norm for ind in research_indicators)


def run(
    question: str,
    previous_question: str | None = None,
    progress: dict | None = None,
    conversation_history: list[dict] | None = None,
    web_search_enabled: bool = False,
    agent_mode: bool = False,
    ignored_rects: list[dict] | None = None,
    attached_image: str | None = None,
    attached_file: dict | None = None,
) -> dict:
    """
    RULE: Screenshots/OCR are ONLY taken when BOTH web_search_enabled=False
    AND agent_mode=False. The priority order is:
      1. web_search_enabled → SearXNG pipeline (no OCR, no screenshots)
      2. agent_mode        → MCP desktop automation (no OCR, no screenshots)
      3. default           → vision pipeline with screenshots + OCR
    """
    started = time.perf_counter()
    warnings: list[str] = []

    # Clean wake word prefixes from the incoming question (e.g., "Hey Blinky", "Blinky")
    question = question.strip()
    question = re.sub(r"^(?:hey\s+)?blinky[\s,.:;!?]*", "", question, flags=re.IGNORECASE).strip()

    # Fast-path: attached mobile image explain (Gemini/Groq vision).
    # Must run before any screen capture so a phone photo is described
    # instead of being treated as a file transfer.
    if attached_image:
        try:
            return run_attached_image_vision(question or "Explain what is in this image.", attached_image, started, warnings)
        except Exception as exc:
            LOGGER.warning("Attached-image vision failed: %s", exc)
            raise RuntimeError(f"Image analysis failed: {exc}") from exc

    # Deterministic intercept for RPC calls passed via question prefix
    if question.startswith("[NOTEBOOK_RPC:"):
        match = re.match(r"^\[NOTEBOOK_RPC:([^\]]+)\]\s*(.*)$", question, flags=re.DOTALL)
        if match:
            rpc_action = match.group(1).strip()
            params_str = match.group(2).strip()
            try:
                rpc_params = json.loads(params_str) if params_str else {}
            except Exception:
                rpc_params = {}
            res = handle_notebook_rpc(rpc_action, rpc_params)
            return {"summary": json.dumps(res), "steps": [], "warnings": warnings}

    # Deterministic intercept for Notebook Intelligence queries
    notebook_match = re.match(r"^\[NOTEBOOK:([^\]]+)\]\s*(.*)$", question, flags=re.DOTALL)
    if notebook_match:
        nb_id = notebook_match.group(1).strip()
        actual_query = notebook_match.group(2).strip()
        LOGGER.info(f"Deterministic routing to Notebook Intelligence for notebook_id={nb_id}")
        return run_notebook_intelligence(nb_id, actual_query, started, warnings, use_vector_search=True)

    if ignored_rects:
        from utils.window import set_ignored_overlay_rects
        set_ignored_overlay_rects(ignored_rects)

    # PATH 1: Web search — purely SearXNG, never touches the screen
    if web_search_enabled:
        return run_web_intelligence(question, conversation_history, started, warnings)

    from computer_use.dedicated_routes import resolve_dedicated_request, execute_dedicated_request
    dedicated = resolve_dedicated_request(question)
    if dedicated and dedicated["kind"] == "visual_guidance":
        agent_mode = False
        progress = None
        previous_question = None
    if dedicated and dedicated["kind"] == "web_search":
        return run_web_intelligence(question, conversation_history, started, warnings)
    if dedicated and dedicated["kind"] not in {"information", "web_search"}:
        direct = execute_dedicated_request(dedicated)
        if direct is not None:
            return build_agent_tool_result(direct.to_dict(), started, warnings)

    # Browser tasks must bypass desktop launchers and all legacy screen matching.
    from tools.browser_use_tool import resolve_browser_use_request
    browser_match = resolve_browser_use_request(question)
    if browser_match:
        return run_browser_use_tool(browser_match, started, warnings)

    # Accessibility actions execute before the legacy label-matching path.
    from computer_use.vercel_engine import should_route, run_desktop_request
    if should_route(question, agent_mode=agent_mode):
        return run_desktop_request(question, started, warnings, status=_emit_status)

    if agent_mode and not dedicated:
        direct_result = try_run_agent_action(question)
        if direct_result is not None:
            # If the tool is a media control/shortcut or was successful, return it immediately without falling back to preflight
            if direct_result.success or direct_result.tool in {"seek_spotify", "shortcut", "play_spotify", "play_youtube"}:
                return build_agent_tool_result(direct_result.to_dict(), started, warnings)

    locator_target = extract_locator_target(question)

    has_progress = progress is not None and bool(
        progress.get("completed_targets") or progress.get("completed_instructions")
    )
    skip_preflight = should_skip_preflight_for_local_fast_path(question) or has_progress

    # RULE: agent_mode NEVER forces screen context — it goes through preflight
    # for intent classification (COMPUTER_USE, OPEN_APP, etc.)
    if agent_mode:
        force_screen = False

    preflight = None
    if skip_preflight:
        LOGGER.info("Skipping preflight for local fast-path or continuation question")
    else:
        if agent_mode:
            _emit_status("analyzing", "Understanding your request...")
        preflight_started = time.perf_counter()
        preflight = classify_request(question, previous_question, warnings, conversation_history, agent_mode=agent_mode)
        log_stage_timing("preflight", preflight_started)

    intent = "SCREEN_EXPLANATION" if is_screen_explanation_question(question) else "DESKTOP_AUTOMATION"
    if dedicated and dedicated["kind"] == "visual_guidance":
        intent = "LOCATOR"
    extracted_params = {}
    is_continuation = False

    if preflight:
        intent = preflight.get("intent", "DESKTOP_AUTOMATION")
        extracted_params = preflight.get("extracted_params", {}) or {}
        is_continuation = preflight.get("is_continuation", False)
    elif previous_question and is_followup_continuation_question(question):
        is_continuation = True

    from computer_use.vercel_engine import desktop_enabled
    if desktop_enabled() and not dedicated and intent in {"DESKTOP_AUTOMATION", "COMPUTER_USE", "LOCATOR", "SCREEN_EXPLANATION"}:
        LOGGER.info("Routing classified %s through Vercel agent-desktop", intent)
        return run_desktop_request(question, started, warnings, status=_emit_status)

    # Auto-enable or disable modes based on classified intent
    if intent == "WEB_SEARCH" or is_web_research_question(question):
        LOGGER.info("Automatically enabling web search mode for classified intent: WEB_SEARCH / research query")
        web_search_enabled = True
    elif intent == "NOTEBOOK":
        LOGGER.info("Routing to Notebook Intelligence engine for intent: NOTEBOOK")
        notebook_id = extracted_params.get("notebook_id") or "default"
        return run_notebook_intelligence(notebook_id, question, started, warnings)
    elif intent == "PDF_ENGINE":
        LOGGER.info("Routing to Custom PDF Engine for intent: PDF_ENGINE")
        action = str(extracted_params.get("pdf_action") or "convert").lower()
        return run_pdf_tool(action, extracted_params, started, warnings)
    elif intent == "VIDEO_EDIT":
        LOGGER.info("Routing to AiCut video editor for intent: VIDEO_EDIT")
        return run_aicut_tool(extracted_params, question, started, warnings)
    elif intent == "WHATSAPP":
        LOGGER.info("Routing to WhatsApp tool for intent: WHATSAPP")
        wa_action = str(extracted_params.get("wa_action") or "status").lower().strip()
        wa_chat_name = extracted_params.get("wa_chat_name") or None
        wa_message = extracted_params.get("wa_message") or None
        return run_whatsapp_tool(wa_action, wa_chat_name, started, warnings, wa_message)
    elif intent == "SCREENSHOT":
        LOGGER.info("Routing to SCREENSHOT fast-path")
        return run_screenshot_tool(started, warnings)
    elif intent == "ESP32_LIGHT":
        LOGGER.info("Routing to ESP32 Light tool for intent: ESP32_LIGHT")
        return run_esp32_light_tool(extracted_params, started, warnings)
    elif intent == "SPREADSHEET":
        LOGGER.info("Routing to spreadsheet tool for intent: SPREADSHEET")
        if not extracted_params:
            extracted_params = {}
        if "raw_prompt" not in extracted_params:
            extracted_params["raw_prompt"] = question
        return run_spreadsheet_tool(extracted_params, started, warnings)
    elif intent == "DESKTOP_REFS":
        from computer_use.vercel_engine import run_desktop_request
        return run_desktop_request(question, started, warnings, status=_emit_status)
    elif intent == "BROWSER_USE":
        LOGGER.info("Routing to browser-use tool for intent: BROWSER_USE")
        return run_browser_use_tool(extracted_params, started, warnings)
    elif intent == "WINDOWS_USE":
        LOGGER.info("Routing to Windows-Use engine for intent: WINDOWS_USE")
        return run_windows_use_tool(extracted_params, question, started, warnings)
    elif intent == "OPEN_FOLDER":
        LOGGER.info("Routing to fast folder launcher for intent: OPEN_FOLDER")
        from computer_use.folder_launcher import open_folder_or_path
        res = open_folder_or_path(question)
        return build_agent_tool_result({
            "success": res.get("success", False),
            "tool": "open_folder",
            "message": res.get("message", "Folder opened."),
            "data": res,
        }, started, warnings)
    elif intent in {"COMPUTER_USE", "OPEN_APP", "MEDIA_PLAYBACK", "SYSTEM_SHORTCUT"}:

        LOGGER.info("Automatically enabling agent mode for classified intent: %s", intent)
        agent_mode = True
    elif intent in {"SCREEN_EXPLANATION", "LOCATOR"}:
        agent_mode = False

    if web_search_enabled:
        return run_web_intelligence(question, conversation_history, started, warnings)

    # Agent mode: every request is a fresh task. Continuation logic is for
    # vision-guided workflows only (screenshot-based step tracking).
    if agent_mode:
        is_continuation = False
        # Direct deterministic agent actions (open app, open & type, shortcut, media playback)
        direct_agent_result = try_run_agent_action(question)
        if direct_agent_result is not None and direct_agent_result.success:
            return build_agent_tool_result(direct_agent_result.to_dict(), started, warnings)

    direct_agent_result = None

    if agent_mode:
        # Reroute: if the query contains action verbs beyond just "open",
        # treat it as COMPUTER_USE so the full tool loop runs.
        if intent == "OPEN_APP" and _has_computer_use_action(question):
            LOGGER.info("Rerouting OPEN_APP → COMPUTER_USE (query contains action verbs)")
            intent = "COMPUTER_USE"

        from computer_use.agent import STOP_SPOTIFY_RE
        if STOP_SPOTIFY_RE.match(question.strip().rstrip("?.!,;:")):
            from computer_use.tools import shortcut_tool
            direct_agent_result = shortcut_tool("media_play_pause")
        elif intent == "MEDIA_PLAYBACK":
            from computer_use.agent import handle_media_playback_action
            direct_agent_result = handle_media_playback_action(extracted_params, question)
        elif intent == "OPEN_APP":
            app = extracted_params.get("app_name")
            if app:
                normalized = normalize_app_name(app)
                is_known_app = normalized in APP_PROTOCOLS or normalized in APP_NAME_ALIASES
                if is_known_app:
                    from computer_use.tools import open_app_tool
                    direct_agent_result = open_app_tool(app)
                elif is_web_destination(app) or is_in_app_action(app) or not looks_like_app_name(app):
                    # Web destinations or in-app actions are handled directly via try_run_agent_action fallback.
                    pass
                else:
                    from computer_use.tools import open_app_tool
                    direct_agent_result = open_app_tool(app)
        elif intent == "SYSTEM_SHORTCUT":
            shortcut = extracted_params.get("shortcut")
            if shortcut:
                from computer_use.tools import shortcut_tool
                direct_agent_result = shortcut_tool(shortcut)
        elif intent == "COMPUTER_USE":
            from computer_use.loop import run_computer_use_loop
            from computer_use.windows_use_engine import (
                execute_microsoft_store_search,
                extract_microsoft_store_install_search_query,
            )

            store_item = extract_microsoft_store_install_search_query(question)
            if store_item:
                # Store launch and search are stable, deterministic GUI steps.
                # Do them first; vision is only useful once the result cards
                # are visible and Blinky needs to choose the correct install control.
                _emit_status("action", "Opening Microsoft Store and searching...")
                search_result = execute_microsoft_store_search(store_item)
                if not search_result.get("success"):
                    return {
                        "success": False,
                        "summary": search_result.get("message", "Could not verify Microsoft Store search results."),
                        "steps": [],
                        "active_app": {"title": "Microsoft Store", "process": "", "supported": True},
                        "ocr": {"count": 0, "items": []},
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                        "provider": get_provider_label(),
                        "warnings": warnings,
                        "is_continuation": False,
                        "computer_use": True,
                    }

                _emit_status("analyzing", "Checking the Store results for the download button...")
                remaining_task = (
                    f"Microsoft Store is already open on verified search results for {store_item!r}. "
                    f"Continue from this screen. Identify the exact matching result and use its "
                    "Get, Download, or Install button to start the download. Do not reopen Store, "
                    "search again, or select a similarly named app. Verify the visible outcome "
                    f"and report it accurately. Original request: {question}"
                )
                loop_result = run_computer_use_loop(remaining_task)
            else:
                loop_result = run_computer_use_loop(question)
            if loop_result.get("success"):
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                # Normalize agent steps to include frontend-safe fields
                safe_steps = []
                for i, s in enumerate(loop_result.get("steps", [])):
                    safe_steps.append({
                        "step": i + 1,
                        "instruction": s.get("message", ""),
                        "target_text": "",
                        "target_ref": "",
                        "tool": s.get("tool", ""),
                        "args": s.get("args", {}),
                        "success": s.get("success", False),
                    })
                return {
                    "summary": loop_result.get("answer", "Task completed."),
                    "steps": safe_steps,
                    "active_app": {"title": "", "process": "", "supported": False},
                    "ocr": {"count": 0, "items": []},
                    "elapsed_ms": elapsed_ms,
                    "provider": get_provider_label(),
                    "warnings": warnings,
                    "is_continuation": False,
                    "computer_use": True,
                }
            if store_item:
                return {
                    "success": False,
                    "summary": loop_result.get("error", "Store results were searched, but the download was not confirmed."),
                    "steps": loop_result.get("steps", []),
                    "active_app": {"title": "Microsoft Store", "process": "", "supported": True},
                    "ocr": {"count": 0, "items": []},
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "provider": get_provider_label(),
                    "warnings": warnings,
                    "is_continuation": False,
                    "computer_use": True,
                }

        if direct_agent_result is not None and not direct_agent_result.success:
            direct_agent_result = None

        if direct_agent_result is None:
            direct_agent_result = try_run_agent_action(question)
            if direct_agent_result is not None and not direct_agent_result.success:
                direct_agent_result = None

        if direct_agent_result is not None:
            return build_agent_tool_result(direct_agent_result.to_dict(), started, warnings)

        # Procedural step planning via SearXNG & Groq text model + OmniParser UI grounding
        from computer_use.step_planner import generate_procedural_plan
        from computer_use.text_grounder import ground_step_to_screen

        active_app_quick = None
        try:
            active_app_quick = get_active_window()
        except Exception:
            pass

        is_screen_action = bool(
            extract_click_target(question)
            or extract_locator_target(question)
            or is_control_locator_question(question)
            or is_click_target_question(question)
        )

        plan = None
        if not is_screen_explanation_question(question) and not is_screen_action:
            plan = generate_procedural_plan(question, active_app=active_app_quick, conversation_history=conversation_history)
        if plan and plan.get("steps") and plan.get("source") != "fallback":
            completed_targets = {str(t).lower().strip() for t in progress.get("completed_targets", [])} if progress else set()
            completed_instructions = {str(i).lower().strip() for i in progress.get("completed_instructions", [])} if progress else set()
            failed_targets = {str(t).lower().strip() for t in progress.get("failed_targets", [])} if progress else set()
            failed_refs = {str(r).strip() for r in progress.get("failed_refs", [])} if progress else set()

            uncompleted_steps = [s for s in plan["steps"] if not is_procedural_step_completed(s, completed_targets, completed_instructions)]

            if not uncompleted_steps:
                # All steps in procedural plan have been completed!
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "summary": f"Autopilot successfully completed: {question}!",
                    "steps": [],
                    "active_app": active_app_quick or {"title": "", "process": "", "supported": True},
                    "ocr": {"count": 0, "items": []},
                    "elapsed_ms": elapsed_ms,
                    "provider": get_provider_label(),
                    "warnings": warnings,
                    "is_continuation": False,
                    "computer_use": True,
                }

            next_step = uncompleted_steps[0]

            # If the plan specifies an app/URI to open on step 1 and nothing is completed yet
            if not completed_targets and not completed_instructions and plan.get("app_to_open"):
                app_to_open = plan["app_to_open"]
                try:
                    if os.name == "nt" and ":" in app_to_open:
                        import subprocess
                        subprocess.Popen(f"start {app_to_open}", shell=True)
                        time.sleep(1.0)
                    else:
                        from computer_use.tools import open_app_tool
                        open_app_tool(app_to_open)
                        time.sleep(1.0)
                except Exception as exc:
                    LOGGER.warning("Failed to open plan app '%s': %s", app_to_open, exc)

            # Observe screen state (extracts UI elements via OmniParser / UIA / OCR)
            screenshot = capture_screen()
            print("__BLINKY_CAPTURED__", flush=True)
            observation = observe_app_state(screenshot)
            visible_items = observation["visible_items"]

            # Deepest visible step resolution:
            # Check remaining planned steps in reverse order (from deepest step to first)
            # to pick the furthest actionable step visible on screen (e.g. if already on Personalization page, pick Colors)
            grounded = None
            selected_step = next_step
            uncompleted_steps = [s for s in plan["steps"] if s.get("target", "").lower().strip() not in completed_targets]

            for candidate_step in reversed(uncompleted_steps):
                cand_grounded = ground_step_to_screen(
                    candidate_step,
                    visible_items,
                    observation.get("active_app"),
                    failed_refs=failed_refs,
                    failed_targets=failed_targets,
                    user_task=question,
                )
                if cand_grounded and cand_grounded.get("match", {}).get("score", 0) >= 0.80:
                    grounded = cand_grounded
                    selected_step = candidate_step
                    break

            if not grounded and uncompleted_steps:
                first_step = uncompleted_steps[0]
                grounded = ground_step_to_screen(
                    first_step,
                    visible_items,
                    observation.get("active_app"),
                    failed_refs=failed_refs,
                    failed_targets=failed_targets,
                    user_task=question,
                )
                selected_step = first_step

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if grounded:
                return {
                    "summary": plan.get("summary") or f"Step {selected_step.get('step')}: {selected_step.get('instruction')}",
                    "markdown_guide": plan.get("markdown_guide", ""),
                    "steps": [grounded],
                    "active_app": observation["active_app"],
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
                    "warnings": warnings,
                    "is_continuation": is_continuation,
                }
            else:
                fallback_step = {
                    "step": selected_step.get("step", 1),
                    "instruction": selected_step.get("instruction") or f"Click {selected_step.get('target')}",
                    "target_text": selected_step.get("target", ""),
                    "target_ref": "",
                }
                return {
                    "summary": plan.get("summary") or f"Step {selected_step.get('step')}: {selected_step.get('instruction')}",
                    "markdown_guide": plan.get("markdown_guide", ""),
                    "steps": [fallback_step],
                    "active_app": observation["active_app"],
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
                    "warnings": warnings,
                    "is_continuation": is_continuation,
                }

        if not is_screen_action:
            # AGENT MODE RULE: when agent automation is enabled and no plan matches, report failure cleanly.
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "summary": "I wasn't able to handle that request with desktop automation. Try rephrasing your request, or disable agent mode for screen-based guidance.",
                "steps": [],
                "active_app": {"title": "", "process": "", "supported": False},
                "ocr": {"count": 0, "items": []},
                "elapsed_ms": elapsed_ms,
                "provider": get_provider_label(),
                "warnings": warnings,
                "is_continuation": False,
                "agent_fallback": True,
            }

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

    # Locator fast-path: screenshot-only, no LLM. NEVER runs for app-opening
    # queries ("open X", "open X and Y") â€” those belong to the app launcher /
    # agent loop, and a fuzzy OCR match on the app name would click the wrong
    # thing (e.g. matching "search youtube.com" to the word "search").
    locator_result = None
    if not is_open_action_question(question):
        locator_result = resolve_locator_fast_path(question, screenshot, target_pid, warnings, started)
    if locator_result is not None:
        return locator_result

    if locator_target:
        LOGGER.info("Locator deferred to screen AI for '%s'", locator_target)

    # Deferred locator queries need icon boxes + shell items in the prompt
    # so the vision model can ground icon-only targets by sight.
    needs_icons = bool(
        locator_target
        or extract_click_target(question)
        or is_control_locator_question(question)
    )
    observation = observe_app_state(screenshot, target_pid, needs_icons)
    active_app = observation["active_app"]
    visible_items = observation["visible_items"]

    if not visible_items:
        warnings.append("No OCR text was detected. Try zooming in or opening a supported app.")

    if agent_mode:
        agent_result = try_run_agent_action(question, observation)
        if agent_result is not None:
            return build_agent_tool_result(agent_result.to_dict(), started, warnings, observation)

    # Check for procedural step plan first to avoid vision token consumption on standard multi-step tasks
    from computer_use.step_planner import generate_procedural_plan
    from computer_use.text_grounder import ground_step_to_screen

    procedural_plan = None
    if (
        not is_screen_explanation_question(effective_question)
        and not is_control_locator_question(effective_question)
        and not extract_locator_target(effective_question)
        and not extract_click_target(effective_question)
        and not is_click_target_question(effective_question)
    ):
        procedural_plan = generate_procedural_plan(effective_question, active_app=active_app, conversation_history=conversation_history)
    if procedural_plan and procedural_plan.get("steps") and procedural_plan.get("source") != "fallback":
        completed_targets = {str(t).lower().strip() for t in progress.get("completed_targets", [])} if progress else set()
        completed_instructions = {str(i).lower().strip() for i in progress.get("completed_instructions", [])} if progress else set()
        failed_targets = {str(t).lower().strip() for t in progress.get("failed_targets", [])} if progress else set()
        failed_refs = {str(r).strip() for r in progress.get("failed_refs", [])} if progress else set()

        uncompleted_steps = [s for s in procedural_plan["steps"] if not is_procedural_step_completed(s, completed_targets, completed_instructions)]

        if not uncompleted_steps:
            # All steps in procedural plan have been completed!
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "summary": f"Autopilot successfully completed: {effective_question}!",
                "steps": [],
                "active_app": active_app or {"title": "", "process": "", "supported": True},
                "ocr": {"count": 0, "items": []},
                "elapsed_ms": elapsed_ms,
                "provider": get_provider_label(),
                "warnings": warnings,
                "is_continuation": False,
                "computer_use": True,
            }

        next_step = uncompleted_steps[0]
        grounded = None
        selected_step = next_step

        for candidate_step in reversed(uncompleted_steps):
            cand_grounded = ground_step_to_screen(
                candidate_step,
                visible_items,
                active_app,
                failed_refs=failed_refs,
                failed_targets=failed_targets,
                user_task=effective_question,
            )
            if cand_grounded and cand_grounded.get("match", {}).get("score", 0) >= 0.80:
                grounded = cand_grounded
                selected_step = candidate_step
                break

        if not grounded and uncompleted_steps:
            first_step = uncompleted_steps[0]
            grounded = ground_step_to_screen(
                first_step,
                visible_items,
                active_app,
                failed_refs=failed_refs,
                failed_targets=failed_targets,
                user_task=effective_question,
            )
            selected_step = first_step

        if grounded:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "summary": procedural_plan.get("summary") or f"Step {selected_step.get('step')}: {selected_step.get('instruction')}",
                "steps": [grounded],
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
                "warnings": warnings,
                "is_continuation": is_continuation,
            }

    prompt_started = time.perf_counter()
    prompt, ref_items = build_prompt(
        question=effective_question,
        active_app=active_app,
        ocr_items=visible_items,
        app_context=observation.get("app_context", ""),
        progress=progress,
        latest_update=latest_update,
        conversation_history=conversation_history,
        return_ref_items=True,
    )
    log_stage_timing("prompt_build", prompt_started)
    model_started = time.perf_counter()
    ai_result = ask_model(prompt=prompt, screenshot_path=screenshot.path)
    log_stage_timing("model", model_started)
    LOGGER.info("AI Result: %s", json.dumps(ai_result, ensure_ascii=True))
    steps = attach_matches(ai_result.get("steps", []), ref_items)
    steps = skip_completed_navigation_steps(steps)

    # Fallback: if the AI returned a type/search instruction with empty target_text,
    # auto-match to the first visible search/filter/find input control on screen.
    steps = _fill_empty_search_targets(steps, visible_items)

    # Multi-highlight queries ("highlight steam and edge") keep one step per
    # target; single-action workflows stay single-step as before.
    multi_targets = extract_locator_targets(effective_question)
    if steps:
        steps = steps[: max(1, len(multi_targets))] if len(multi_targets) > 1 else steps[:1]

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


def observe_app_state(screenshot, target_pid: int | None = None, include_icons: bool = False) -> dict:
    active_started = time.perf_counter()
    active_app = get_active_window(target_pid=target_pid)
    log_stage_timing("active_window", active_started)
    visible_items = get_or_build_visible_ui_map(active_app, screenshot, target_pid, include_icons)
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


def get_or_build_visible_ui_map(active_app: dict, screenshot, target_pid: int | None = None, include_icons: bool = False) -> list[dict]:
    if include_icons:
        # A plain (icon-less) entry may already be cached for this screen;
        # enrich it in place so locator queries never force an OCR/UIA rescan.
        plain_signature = window_signature(active_app, screenshot, target_pid, False)
        plain_cached = UI_MAP_CACHE.load(plain_signature)
        if plain_cached is not None:
            visible_items = _apply_icon_pass(plain_cached, screenshot)
            visible_items.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
            try:
                from utils.screen_annotator import save_parsed_ui_screenshot
                save_parsed_ui_screenshot(screenshot.path, visible_items)
            except Exception:
                pass
            return visible_items
    signature = window_signature(active_app, screenshot, target_pid, include_icons)

    def build_items() -> list[dict]:
        return _build_visible_ui_map(active_app, screenshot, target_pid, include_icons)

    visible_items = UI_MAP_CACHE.get_or_build(signature, build_items)
    visible_items.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
    try:
        from utils.screen_annotator import save_parsed_ui_screenshot
        save_parsed_ui_screenshot(screenshot.path, visible_items)
    except Exception:
        pass
    return visible_items


def _apply_icon_pass(items: list[dict], screenshot) -> list[dict]:
    """Enrich cached/plain items with icon boxes without rescanning OCR/UIA."""
    if not _icons_enabled():
        return items
    icon_boxes = get_icon_boxes_for_screenshot(screenshot)
    if not icon_boxes:
        return items
    merged = merge_icon_boxes(list(items), icon_boxes, screenshot)
    textless = [
        item for item in merged
        if not str(item.get("text", "")).strip()
        and str(item.get("source", "")).lower() == "icon"
    ]
    if textless:
        recover_icon_labels(textless, screenshot)
    return assign_screen_element_refs(merged)


def _build_visible_ui_map(active_app: dict, screenshot, target_pid: int | None, include_icons: bool) -> list[dict]:
    ocr_started = time.perf_counter()
    crop_rect = _get_active_window_crop_rect(screenshot)
    ocr_items = extract_visible_text(screenshot.path, crop_rect=crop_rect)
    ocr_items = filter_ignored_overlay_items(ocr_items, screenshot)
    log_stage_timing("ocr", ocr_started)
    uia_started = time.perf_counter()
    # include_unlabeled=True keeps icon-only controls (taskbar pins,
    # WhatsApp sidebar) so the vision model can identify them by sight.
    uia_items = get_visible_ui_text(target_pid=target_pid, include_unlabeled=True)
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

    uia_items_filtered = filter_ignored_overlay_items(uia_items_filtered, screenshot)

    if include_icons:
        merged = augment_visible_items(ocr_items_filtered, uia_items_filtered, screenshot)
    else:
        merged = merge_visible_items(ocr_items_filtered, uia_items_filtered)
    merged = assign_screen_element_refs(merged)
    merged.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
    try:
        from utils.screen_annotator import save_parsed_ui_screenshot
        save_parsed_ui_screenshot(screenshot.path, merged)
    except Exception:
        pass
    return merged


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
    agent_mode: bool = False,
) -> dict | None:
    from computer_use.agent import is_web_destination, is_in_app_action, looks_like_app_name
    from computer_use.tools import normalize_app_name, APP_PROTOCOLS, APP_NAME_ALIASES
    is_mocked = getattr(ask_text_model, "_mock_name", None) is not None or "Mock" in type(ask_text_model).__name__
    from computer_use.dedicated_routes import resolve_dedicated_request
    dedicated = resolve_dedicated_request(question)
    if dedicated and dedicated["kind"] == "information":
        return {"intent": "INFORMATIONAL_CHAT", "needs_screen": False, "is_continuation": False, "extracted_params": {}}
    if dedicated and dedicated["kind"] == "visual_guidance":
        return {"intent": "LOCATOR", "needs_screen": True, "is_continuation": False, "extracted_params": {}}
    from computer_use.dedicated_routes import appearance_request
    if not dedicated and appearance_request(question):
        return {"intent": "DESKTOP_REFS", "needs_screen": False, "is_continuation": False, "extracted_params": {"task": question}}
    if dedicated and dedicated["kind"] == "web_search":
        return {"intent": "WEB_SEARCH", "needs_screen": False, "is_continuation": False, "extracted_params": {"query": dedicated["query"]}}
    from tools.browser_use_tool import resolve_browser_use_request
    browser_match = resolve_browser_use_request(question)
    if browser_match:
        return {"intent": "BROWSER_USE", "needs_screen": False,
                "is_continuation": False, "extracted_params": browser_match}
    from tools.vercel_desktop_tool import resolve_vercel_desktop_request
    desktop_match = resolve_vercel_desktop_request(question)
    if desktop_match:
        return {"intent": "DESKTOP_REFS", "needs_screen": False,
                "is_continuation": False, "extracted_params": desktop_match}
    if not is_mocked:
        # Compound Store searches must win before the broad OPEN_APP matcher; the
        # latter otherwise strips the search action and leaves it in an agent loop.
        try:
            from computer_use.windows_use_engine import resolve_windows_use_request
            wu_match = resolve_windows_use_request(question)
            if wu_match and wu_match.get("action") == "microsoft_store_search":
                return {
                    "intent": "WINDOWS_USE",
                    "needs_screen": False,
                    "is_continuation": False,
                    "extracted_params": wu_match,
                }
        except Exception as exc:
            LOGGER.debug("Fast-path Microsoft Store search resolution failed: %s", exc)

        # PRIORITY FIX: Check OPEN_APP before WINDOWS_USE to use fast launcher
        # Simple "open X" commands should use the optimized open_app_tool, not slow UI automation
        try:
            from computer_use.agent import OPEN_APP_RE, cleanup_app_name, looks_like_app_name
            from computer_use.tools import is_web_destination, is_in_app_action
            app_open_match = OPEN_APP_RE.match(question.strip().rstrip("?.!,;:"))
            if app_open_match:
                app_cand = cleanup_app_name(app_open_match.group("app"))
                if (
                    app_cand
                    and looks_like_app_name(app_cand)
                    and not _has_computer_use_action(question)
                    and not is_web_destination(app_cand)
                    and not is_in_app_action(app_cand)
                ):
                    return {
                        "intent": "OPEN_APP",
                        "needs_screen": False,
                        "is_continuation": False,
                        "extracted_params": {"app_name": app_cand},
                    }
        except Exception as exc:
            LOGGER.debug("Fast-path OPEN_APP resolution failed: %s", exc)

    # WINDOWS_USE now checked second - only for complex UI automation that's not simple app opening
    try:
        from computer_use.windows_use_engine import resolve_windows_use_request
        wu_match = resolve_windows_use_request(question)
        if wu_match:
            return {
                "intent": "WINDOWS_USE",
                "needs_screen": False,
                "is_continuation": False,
                "extracted_params": wu_match,
            }
    except Exception as exc:
        LOGGER.debug("Fast-path WINDOWS_USE resolution failed: %s", exc)
    try:
        from tools.aicut_tool import resolve_aicut_request
        aicut_match = resolve_aicut_request(question)
        if aicut_match and aicut_match.get("action") != "explorer_context":
            return {
                "intent": "VIDEO_EDIT",
                "needs_screen": False,
                "is_continuation": False,
                "extracted_params": aicut_match,
            }
    except Exception as exc:
        LOGGER.debug("Fast-path AiCut resolution failed: %s", exc)
    try:
        from tools.whatsapp_tool import resolve_whatsapp_request, resolve_whatsapp_send_request
        send_match = resolve_whatsapp_send_request(question)
        if send_match:
            chat_name, message = send_match
            return {
                "intent": "WHATSAPP",
                "needs_screen": False,
                "is_continuation": False,
                "extracted_params": {
                    "wa_action": "send",
                    "wa_chat_name": chat_name,
                    "wa_message": message,
                }
            }
        wa_match = resolve_whatsapp_request(question)
        if wa_match:
            action, chat_name = wa_match
            return {
                "intent": "WHATSAPP",
                "needs_screen": False,
                "is_continuation": False,
                "extracted_params": {
                    "wa_action": action,
                    "wa_chat_name": chat_name,
                }
            }
    except Exception as exc:
        LOGGER.debug("Fast-path WhatsApp resolution failed: %s", exc)
    try:
        from tools.spreadsheet_tool import resolve_spreadsheet_request
        sheet_match = resolve_spreadsheet_request(question)
        if sheet_match:
            return {
                "intent": "SPREADSHEET",
                "needs_screen": False,
                "is_continuation": False,
                "extracted_params": sheet_match,
            }
    except Exception as exc:
        LOGGER.debug("Fast-path SPREADSHEET resolution failed: %s", exc)
    # Fast-path Screenshot / Screen capture
    cleaned_lower = question.lower().strip().rstrip("?.!,;:")
    if any(k in cleaned_lower for k in {
        "capture screenshot", "take screenshot", "get screenshot", 
        "capture current pc screen", "capture screen", "pc screenshot",
        "take a screenshot", "screenshot of current pc screen", "take a screenshot of my screen",
        "take a screenshot of current pc screen", "screenshot current pc screen",
    }) or cleaned_lower in {"screenshot", "take screenshot", "capture screen", "screen capture"}:
        return {
            "intent": "SCREENSHOT",
            "extracted_params": {},
            "needs_screen": False,
            "is_continuation": False,
        }

    try:
        from tools.esp32_light_tool import resolve_light_request
        light_match = resolve_light_request(question)
        if light_match:
            return {
                "intent": "ESP32_LIGHT",
                "needs_screen": False,
                "is_continuation": False,
                "extracted_params": light_match,
            }
    except Exception as exc:
        LOGGER.debug("Fast-path ESP32 light resolution failed: %s", exc)
    try:
        from tools.pdf_tool import resolve_pdf_request
        pdf_match = resolve_pdf_request(question)
        if pdf_match:
            return {
                "intent": "PDF_ENGINE",
                "needs_screen": False,
                "is_continuation": False,
                "extracted_params": pdf_match,
            }
    except Exception as exc:
        LOGGER.debug("Fast-path PDF resolution failed: %s", exc)

    # Fast-path Laya System 1 Neural Router + Structural Classification (~30ms local)
    is_mocked = getattr(ask_text_model, "_mock_name", None) is not None or "Mock" in type(ask_text_model).__name__
    if not is_mocked:
        try:
            from ai.laya_router import get_preflight_from_laya
            laya_preflight = get_preflight_from_laya(question, previous_question)
            if laya_preflight and (laya_preflight.get("confidence", 0.0) >= 0.50 or laya_preflight.get("source") == "structural_guard"):
                LOGGER.info(
                    "Laya System 1 preflight resolved intent '%s' (conf=%.2f, source=%s)",
                    laya_preflight.get("intent"),
                    laya_preflight.get("confidence", 0.0),
                    laya_preflight.get("source"),
                )
                return laya_preflight
        except Exception as exc:
            LOGGER.debug("Laya preflight classification failed: %s", exc)

    try:
        payload = ask_text_model(build_preflight_prompt(question, previous_question, conversation_history))
    except Exception as exc:
        LOGGER.warning("Preflight classification failed; falling back to screen mode: %s", exc)
        warnings.append(f"Preflight classification failed: {exc}")
        return None

    intent = payload.get("intent")
    extracted_params = payload.get("extracted_params", {}) or {}
    if intent == "ESP32_LIGHT":
        from tools.esp32_light_tool import resolve_light_request
        confirmed = resolve_light_request(question)
        if confirmed is None:
            intent, extracted_params = "INFORMATIONAL_CHAT", {}
        else:
            extracted_params = confirmed
    
    # Safety check: if intent is OPEN_APP but targets web UI, an in-app
    # feature/action, or a query, override to DESKTOP_AUTOMATION (only if not in agent_mode).
    # But if it's a known app (has app protocol or is in app name aliases), don't override!
    if intent == "OPEN_APP" and not agent_mode:
        app_name = extracted_params.get("app_name", "")
        if app_name:
            normalized = normalize_app_name(app_name)
            is_known_app = normalized in APP_PROTOCOLS or normalized in APP_NAME_ALIASES
            if is_web_destination(app_name) or is_in_app_action(app_name) or (not is_known_app and not looks_like_app_name(app_name)):
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


def run_aicut_tool(
    params: dict,
    question: str,
    started: float,
    warnings: list[str],
) -> dict:
    """Call AiCut video editor and return a Blinky-formatted result."""
    from tools.aicut_tool import run_aicut, format_aicut_summary
    action = params.get("action", "video edit")
    _emit_status("aicut", f"Editing video with AiCut ({action})...")
    res = run_aicut(params)
    summary = format_aicut_summary(res, question)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": summary,
        "steps": [],
        "active_app": {"title": "AiCut Video Editor", "process": "AIVideoEditor.exe", "supported": True},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
        "aicut": res,
    }


def run_whatsapp_tool(
    action: str,
    chat_name: str | None,
    started: float,
    warnings: list[str],
    message: str | None = None,
) -> dict:
    """Call whatsapp_tool.py as a subprocess and return a Blinky-formatted result."""
    import subprocess
    import sys as _sys

    tool_path = Path(__file__).resolve().parent / "tools" / "whatsapp_tool.py"
    args_dict: dict = {"action": action}
    if chat_name:
        args_dict["chat_name"] = chat_name
    if message:
        args_dict["message"] = message

    LOGGER.info("Running WhatsApp tool: action=%s chat_name=%s", action, chat_name)
    _emit_status("whatsapp", f"Connecting to WhatsApp backend ({action})...")

    try:
        proc = subprocess.run(
            [_sys.executable, str(tool_path), json.dumps(args_dict)],
            capture_output=True,
            text=True,
            timeout=130,
            cwd=str(tool_path.parent),
        )
        stdout = proc.stdout.strip()
        LOGGER.debug("whatsapp_tool stdout: %s", stdout)
        LOGGER.debug("whatsapp_tool stderr: %s", proc.stderr.strip())

        if not stdout:
            error_detail = proc.stderr.strip() or "No output from WhatsApp tool."
            summary = f"WhatsApp tool returned no output. {error_detail}"
        else:
            try:
                result_data = json.loads(stdout)
                if "error" in result_data:
                    summary = f"WhatsApp error: {result_data['error']}"
                elif action == "summarize" or action == "summarise":
                    raw_summary = result_data.get("summary", "")
                    if raw_summary:
                        summary = raw_summary
                    else:
                        summary = json.dumps(result_data, indent=2)
                elif action == "chats":
                    chats = result_data.get("chats", [])
                    if chats:
                        chat_lines = "\n".join(
                            f"- {c.get('name', c.get('id', '?'))}" for c in chats[:20]
                        )
                        summary = f"Found {len(chats)} WhatsApp chats:\n{chat_lines}"
                    else:
                        summary = "No WhatsApp chats found. Make sure you are connected."
                elif action == "status":
                    status_val = result_data.get("status", "")
                    if status_val == "connected":
                        summary = "WhatsApp is connected and ready."
                    elif status_val == "qr":
                        summary = "WhatsApp is waiting for QR code scan. Open the WhatsApp Connection window in Blinky to scan."
                    elif status_val == "disconnected":
                        summary = "WhatsApp is not connected. Use the WhatsApp button in Blinky settings to connect."
                    else:
                        summary = f"WhatsApp status: {status_val or json.dumps(result_data)}"
                elif action == "send":
                    if result_data.get("sent"):
                        summary = f"Sent WhatsApp message to {result_data.get('chat_name', chat_name or 'the chat')}."
                    else:
                        summary = json.dumps(result_data, indent=2)
                else:
                    summary = json.dumps(result_data, indent=2)
            except json.JSONDecodeError:
                summary = stdout
    except subprocess.TimeoutExpired:
        summary = "WhatsApp tool timed out. The backend may be busy or not running."
    except Exception as exc:
        summary = f"Failed to run WhatsApp tool: {exc}"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": summary,
        "steps": [],
        "active_app": {"title": "", "process": "", "supported": False},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
    }


def run_esp32_light_tool(
    params: dict,
    started: float,
    warnings: list[str],
) -> dict:
    """Execute ESP32 Light command and return a Blinky-formatted result."""
    from tools.esp32_light_tool import handle_request
    _emit_status("esp32_light", "Controlling ESP32 physical light...")
    res = handle_request(params)
    if res.get("success"):
        summary = res.get("message", "Light updated successfully.")
    else:
        summary = f"Failed to control light: {res.get('error', 'ESP32 unreachable')}"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": summary,
        "steps": [],
        "active_app": {"title": "", "process": "", "supported": False},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
    }


def run_spreadsheet_tool(
    params: dict,
    started: float,
    warnings: list[str],
) -> dict:
    """Execute spreadsheet tool in Microsoft Excel and return a Blinky-formatted result."""
    from tools.spreadsheet_tool import handle_request
    action = params.get("action", "")
    if action == "type_in_cell":
        cell = params.get("cell", "A1")
        _emit_status("spreadsheet", f"Focusing Microsoft Excel and writing in cell {cell}...")
    elif action == "type_in_cells":
        cells_desc = ", ".join(c.get("cell", "") for c in params.get("cells", []))
        _emit_status("spreadsheet", f"Focusing Microsoft Excel and writing in cells {cells_desc}...")
    elif action == "format":
        _emit_status("spreadsheet", "Formatting Microsoft Excel worksheet: auto-fitting columns and styling text...")
    else:
        _emit_status("spreadsheet", "Opening Microsoft Excel spreadsheet...")
    res = handle_request(params)
    summary = res.get("message", "Microsoft Excel action completed.")
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    app_label = "Microsoft Excel"
    app_proc = "excel"
    return {
        "summary": summary,
        "steps": [],
        "active_app": {"title": app_label, "process": app_proc, "supported": True},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
    }


def run_browser_use_tool(
    params: dict,
    started: float,
    warnings: list[str],
) -> dict:
    """Execute autonomous browser-use task in Microsoft Edge and return a Blinky-formatted result."""
    from tools.browser_use_tool import run_browser_task
    import asyncio

    _emit_status("browser", "Inspecting your connected browser...")
    task = params.get("task") or params.get("raw_prompt") or "Open browser and perform task."
    cdp_url = params.get("cdp_url")
    res = {"success": False}
    try:
        from computer_use.cursor_bridge import emit_cursor_protocol_event
        res = asyncio.run(run_browser_task(task, cdp_url=cdp_url, cursor_sink=emit_cursor_protocol_event))
        summary = res.get("result", "Browser task completed.")
    except Exception as exc:
        summary = f"Browser-use task failed: {exc}"
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    app_label = "Connected browser"
    app_proc = ""
    return {
        "summary": summary,
        "steps": res.get("guidance_steps", []),
        "active_app": {"title": app_label, "process": app_proc, "supported": True},
        "success": bool(res.get("success", False)),
        "engine": res.get("engine", "browser_use"),
        "debug_dir": res.get("debug_dir", ""),
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
    }


def run_windows_use_tool(
    params: dict,
    question: str,
    started: float,
    warnings: list[str],
) -> dict:
    """Execute Windows-Use native UI automation and return a Blinky-formatted result."""
    from computer_use.windows_use_engine import handle_windows_use_request
    _emit_status("windows_use", "Executing Windows UI automation...")
    try:
        res = handle_windows_use_request(params)
        summary = res.get("message", "Windows UI action completed.")
        if not res.get("success", True):
            warnings.append(summary)
    except Exception as exc:
        summary = f"Windows-Use action failed: {exc}"
        res = {"success": False}
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    app_name = str(params.get("app") or "Notepad").title()
    app_proc = f"{params.get('app', 'notepad')}.exe"
    return {
        "summary": summary,
        "steps": [],
        "active_app": {"title": app_name, "process": app_proc, "supported": True},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
        "windows_use": True,
        "success": bool(res.get("success", True)),
    }


def run_attached_image_vision(question: str, attached_image_b64: str, started: float, warnings: list[str]) -> dict:
    """Describe a mobile-attached image via Groq/Gemini vision without screen capture."""
    _emit_status("vision", "Analyzing attached image...")
    prompt = question.strip() or "Explain what is in this image in detail."
    # Strip data-URI prefix for the echo field; vision helper accepts both.
    b64_clean = attached_image_b64.strip()
    if "base64," in b64_clean:
        b64_clean = b64_clean.split("base64,", 1)[1].strip()
    try:
        from ai.gemini_client import ask_gemini_vision
        res = ask_gemini_vision(prompt, attached_image_b64)
        summary = str(res.get("text", "")).strip() or "I could not describe this image."
    except Exception as exc:
        summary = f"Image analysis failed: {exc}"
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": summary,
        "steps": [],
        "screenshot_b64": b64_clean,
        "active_app": {"title": "", "process": "", "supported": False},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
        "computer_use": True,
    }


def run_screenshot_tool(started: float, warnings: list[str]) -> dict:
    """Capture desktop screenshot immediately and return base64 without screen scanning/OCR."""
    import base64
    from capture import capture_screen

    _emit_status("screenshot", "Capturing PC screen...")
    shot = capture_screen()
    b64_data = ""
    try:
        with open(shot.path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
    except Exception as exc:
        LOGGER.warning("Failed to encode screenshot: %s", exc)
        warnings.append(f"Screenshot encode error: {exc}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": "Captured screenshot of current PC screen.",
        "steps": [],
        "screenshot": str(shot.path),
        "screenshot_b64": b64_data,
        "active_app": {"title": "", "process": "", "supported": False},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
    }


def run_pdf_tool(
    action: str,
    params: dict,
    started: float,
    warnings: list[str],
) -> dict:
    """Execute Custom PDF Engine action and return a Blinky-formatted result."""
    from tools.pdf_tool import handle_pdf_action
    _emit_status("pdf_engine", f"Executing PDF action: {action}...")
    try:
        res = handle_pdf_action(action, params)
        if res.get("success"):
            output = res.get("output_path") or res.get("output_csv") or "PDF operation completed."
            summary = f"PDF Action '{action}' completed successfully: {output}"
        else:
            summary = f"PDF Action '{action}' failed: {res.get('error', 'Unknown error')}"
    except Exception as exc:
        summary = f"PDF Action error: {exc}"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": summary,
        "steps": [],
        "active_app": {"title": "", "process": "", "supported": False},
        "ocr": {"count": 0, "items": []},
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
        "is_continuation": False,
    }


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


def run_notebook_intelligence(
    notebook_id: str,
    question: str,
    started: float,
    warnings: list[str],
    use_vector_search: bool = False,
) -> dict:
    from notebooks.notebook_manager import NotebookManager
    from notebooks.okf_context_builder import build_okf_prompt_context
    from notebooks.vector_store import VectorStore
    from ai.client import ask_text_model

    _emit_status("notebook", "Querying Notebook grounded context...")
    manager = NotebookManager()
    notebook = manager.get_notebook(notebook_id)
    if not notebook:
        if notebook_id == "default":
            notebook = manager.create_notebook("Default Knowledge Hub", "Personal research notes and uploaded documents")
            notebook["id"] = "default"
            manager.data["default"] = notebook
            manager._save_store()
        else:
            return {
                "summary": f"Notebook '{notebook_id}' not found.",
                "steps": [],
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "warnings": warnings + [f"Notebook {notebook_id} not found"],
            }

    active_sources = [s for s in notebook.get("sources", []) if s.get("active", True)]
    if not active_sources:
        return {
            "summary": "I don't have any active document sources in this Knowledge Hub yet. Please use '+ Add Source' on the left to upload your PDF, Markdown, or text files so I can ground my answers directly on them!",
            "steps": [],
            "source_count": 0,
            "use_vector_search": use_vector_search,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "provider": get_provider_label(),
            "warnings": warnings,
        }

    vector_matches = None
    if use_vector_search:
        try:
            v_store = VectorStore()
            active_source_names = [s.get("source_name") for s in active_sources if s.get("source_name")]
            vector_matches = v_store.search_top_k(notebook_id, question, top_k=5, active_sources=active_source_names)
        except Exception as e:
            LOGGER.warning(f"Vector search failed, falling back: {e}")
            vector_matches = None

    context_payload = build_okf_prompt_context(notebook, question, vector_matches=vector_matches)
    system_prompt = context_payload["system_prompt"]
    user_prompt = context_payload["user_prompt"]

    try:
        response = ask_text_model(f"{system_prompt}\n\n{user_prompt}")
        if isinstance(response, dict):
            if response.get("answer"):
                answer = response["answer"]
            elif response.get("response"):
                answer = response["response"]
            elif response.get("summary"):
                answer = response["summary"]
            else:
                # Convert raw dictionary fields into formatted Markdown
                lines = []
                for k, v in response.items():
                    title = k.replace("_", " ").title()
                    if k.lower() == "source":
                        lines.append(f"**Source:** `[Source: {v}]`")
                    elif isinstance(v, list):
                        lines.append(f"### {title}")
                        for item in v:
                            lines.append(f"- {item}")
                    elif isinstance(v, dict):
                        lines.append(f"### {title}")
                        for sub_k, sub_v in v.items():
                            lines.append(f"- **{sub_k.replace('_', ' ').title()}:** {sub_v}")
                    else:
                        lines.append(f"**{title}:** {v}")
                answer = "\n\n".join(lines)
        else:
            answer = str(response)
    except Exception as exc:
        answer = f"Error processing notebook query: {exc}"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "summary": str(answer).strip(),
        "steps": [],
        "source_count": context_payload["source_count"],
        "use_vector_search": use_vector_search,
        "elapsed_ms": elapsed_ms,
        "provider": get_provider_label(),
        "warnings": warnings,
    }


def handle_notebook_rpc(action: str, params: dict) -> dict:
    """Handle RPC actions for Notebook management and mobile API Key sync."""
    from notebooks.notebook_manager import NotebookManager
    manager = NotebookManager()

    if action == "notebook_create":
        title = params.get("title", "Untitled Notebook")
        description = params.get("description", "")
        return {"success": True, "notebook": manager.create_notebook(title, description)}

    elif action == "notebook_list":
        return {"success": True, "notebooks": manager.list_notebooks()}

    elif action == "notebook_get":
        nb_id = params.get("notebook_id", "")
        nb = manager.get_notebook(nb_id)
        return {"success": nb is not None, "notebook": nb}

    elif action == "notebook_add_source":
        nb_id = params.get("notebook_id", "")
        source_name = params.get("source_name", "document.txt")
        content = params.get("content", "")
        file_type = params.get("file_type", "txt")
        try:
            res = manager.add_source_to_notebook(nb_id, source_name, content, file_type=file_type)
        except Exception as exc:
            LOGGER.error(f"notebook_add_source failed for {source_name}: {exc}")
            return {"success": False, "error": str(exc)}
        return {"success": res is not None, "source": res}

    elif action == "notebook_toggle_source":
        nb_id = params.get("notebook_id", "")
        source_id = params.get("source_id", "")
        active = bool(params.get("active", True))
        ok = manager.toggle_source_active(nb_id, source_id, active)
        return {"success": ok}

    elif action == "notebook_delete":
        nb_id = params.get("notebook_id", "")
        ok = manager.delete_notebook(nb_id)
        return {"success": ok}

    elif action == "sync_api_keys":
        import os
        import time
        import base64
        import json
        raw_keys = {
            "groq_key": os.environ.get("GROQ_API_KEY", ""),
            "openai_key": os.environ.get("OPENAI_API_KEY", ""),
            "gemini_key": os.environ.get("GEMINI_API_KEY", ""),
            "deepseek_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        }
        json_bytes = json.dumps(raw_keys).encode("utf-8")
        encoded_token = base64.b64encode(json_bytes).decode("utf-8")
        return {
            "success": True,
            "keys": raw_keys,
            "encoded_payload": encoded_token,
            "synced_at": time.time(),
        }

    return {"success": False, "error": f"Unknown notebook action: {action}"}




def _icons_enabled() -> bool:
    return os.environ.get("BLINKY_ICON_DETECT", "1").strip() not in {"0", "false", "no", "off"}



def _get_active_window_crop_rect(screenshot) -> tuple[int, int, int, int] | None:
    """Calculate active window bounding box in screenshot pixel space for targeted fast-path OCR."""
    try:
        active_rect = _active_window_rect()
        if not active_rect:
            return None
        left, top, right, bottom = active_rect
        w = right - left
        h = bottom - top
        if w < 100 or h < 100:
            return None
            
        sx = screenshot.width / screenshot.screen_width
        sy = screenshot.height / screenshot.screen_height
        
        cx = int(left * sx)
        cy = int(top * sy)
        cw = int(w * sx)
        ch = int(h * sy)
        
        # If the window occupies more than 92% of the screen, full-screen OCR is cleaner
        if cw * ch >= (screenshot.width * screenshot.height * 0.92):
            return None
            
        return (cx, cy, cw, ch)
    except Exception as exc:
        LOGGER.debug("Could not calculate active window crop: %s", exc)
        return None

def _active_window_rect() -> tuple[int, int, int, int] | None:
    """Active window rect in screen coords, or None when it is the desktop."""
    try:
        from utils.window import get_target_window_element
        el = get_target_window_element()
        if el is None:
            return None
        try:
            if str(getattr(el.element_info, "class_name", "") or "") in {"Progman", "WorkerW"}:
                return None  # Desktop focused: its icons are all visible.
        except Exception:
            pass
        rect = el.rectangle()
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    except Exception as exc:
        LOGGER.debug("Active window rect unavailable: %s", exc)
        return None


def partition_occluded_shell_items(shell_items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split shell items into (visible, occluded-by-active-window).

    Desktop icons report UIA bounds even when a maximized window covers
    them; highlighting those boxes would point at empty window space, so
    only the taskbar (always visible) skips the check. Coordinates must be
    in screen space (call before screenshot scaling).
    """
    desktop_items = [item for item in shell_items if item.get("shell_region") == "desktop"]
    if not desktop_items:
        return list(shell_items), []
    active_rect = _active_window_rect()
    if active_rect is None:
        return list(shell_items), []
    left, top, right, bottom = active_rect
    visible: list[dict] = []
    occluded: list[dict] = []
    for item in shell_items:
        if item.get("shell_region") != "desktop":
            visible.append(item)
            continue
        try:
            cx = float(item.get("x") or 0) + float(item.get("width") or 0) / 2
            cy = float(item.get("y") or 0) + float(item.get("height") or 0) / 2
        except (TypeError, ValueError):
            visible.append(item)
            continue
        if left + 2 <= cx <= right - 2 and top + 2 <= cy <= bottom - 2:
            occluded.append(item)
        else:
            visible.append(item)
    if occluded:
        LOGGER.info("Filtered %d occluded desktop icons covered by the active window", len(occluded))
    return visible, occluded


def get_shell_items_scaled(screenshot) -> list[dict]:
    """Visible taskbar/desktop UIA items mapped into screenshot pixel space."""
    visible, _ = get_shell_items_scaled_partitioned(screenshot)
    return visible


def get_shell_items_scaled_partitioned(screenshot) -> tuple[list[dict], list[dict]]:
    """(visible, occluded) shell items in screenshot pixel space."""
    try:
        shell_items = get_shell_ui_items()
    except Exception as exc:
        LOGGER.debug("Shell UIA scan failed: %s", exc)
        return [], []
    if not shell_items:
        return [], []
    visible, occluded = partition_occluded_shell_items(shell_items)
    if screenshot.screen_width != screenshot.width or screenshot.screen_height != screenshot.height:
        visible = scale_uia_items_to_screenshot(visible, screenshot)
        occluded = scale_uia_items_to_screenshot(occluded, screenshot)
    return visible, occluded


def get_icon_boxes_for_screenshot(screenshot) -> list[dict]:
    """Generic icon boxes (picture part, no text) in screenshot pixel space."""
    if not _icons_enabled():
        return []
    if not icon_model_available():
        return []
    try:
        started = time.perf_counter()
        boxes = detect_icons(screenshot.path)
        log_stage_timing("icons", started)
        return boxes
    except Exception as exc:
        LOGGER.debug("Icon detection failed: %s", exc)
        return []


def _word_run_around(line: list[dict], best: dict) -> list[dict]:
    """Expand from the best word to gap-adjacent neighbors on the same line."""
    if best not in line:
        return [best]
    idx = line.index(best)
    run = [best]
    # Expand left while the gap to the previous word is small.
    i = idx - 1
    while i >= 0:
        gap = int(best.get("x", 0)) - (int(line[i].get("x", 0)) + int(line[i].get("width", 0)))
        bound = max(30, int(line[i].get("height", 10)))
        if gap < 0 or gap > bound:
            break
        run.insert(0, line[i])
        best = line[i]
        i -= 1
    # Expand right from the run's last word.
    j = line.index(run[-1]) + 1
    while j < len(line):
        prev = run[-1]
        gap = int(line[j].get("x", 0)) - (int(prev.get("x", 0)) + int(prev.get("width", 0)))
        bound = max(30, int(line[j].get("height", 10)))
        if gap < 0 or gap > bound:
            break
        run.append(line[j])
        j += 1
    return run


def recover_icon_labels(icon_items: list[dict], screenshot, limit: int = 20) -> int:
    """Re-OCR the label strip under textless desktop icons in place.

    Full-screen OCR often drops small desktop labels (e.g. "Steam").
    Cropping the strip below each icon picture and OCR'ing it zoomed
    recovers those labels. Returns the number of labels recovered.
    """
    candidates = [
        item for item in icon_items
        if not str(item.get("text", "")).strip()
        and str(item.get("source", "")).lower() == "icon"
    ]
    if not candidates:
        return 0
    # Desktop grid lives on the left; taskbar/sidebar icons have no labels.
    scr_w = int(screenshot.width or 0)
    scr_h = int(screenshot.height or 0)
    taskbar_top = scr_h - int(scr_h * 0.08) if scr_h else 0
    desktop_side = max(int(scr_w * 0.35), 420) if scr_w else 420
    targets = [
        item for item in candidates
        if int(item.get("x", 0)) <= desktop_side
        and int(item.get("y", 0)) + int(item.get("height", 0)) <= taskbar_top
        # Desktop icons are roughly square, 24-120px; web thumbnails are wider.
        and 24 <= int(item.get("width", 0)) <= 120
        and 24 <= int(item.get("height", 0)) <= 120
    ][:limit]
    if not targets:
        return 0

    try:
        from PIL import Image
    except Exception as exc:
        LOGGER.debug("Label recovery skipped (no PIL): %s", exc)
        return 0

    try:
        full = Image.open(screenshot.path).convert("RGB")
    except Exception as exc:
        LOGGER.debug("Label recovery skipped (cannot open screenshot): %s", exc)
        return 0

    recovered = 0
    for item in targets:
        try:
            ix, iy = int(item.get("x", 0)), int(item.get("y", 0))
            iw, ih = int(item.get("width", 0)), int(item.get("height", 0))
            # Label sits under the picture and is often wider than the
            # detected picture box, so pad a full icon width on each side
            # and start mid-picture to never clip the label's top rows.
            x1 = max(0, ix - iw)
            y1 = max(0, iy + int(ih * 0.55))
            x2 = min(full.width, ix + iw * 2)
            y2 = min(full.height, y1 + ih)
            if x2 - x1 < 20 or y2 - y1 < 12:
                continue
            crop = full.crop((x1, y1, x2, y2))
            crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            tmp_path = Path(screenshot.path).parent / f"_iconlabel_{ix}_{y1}.png"
            try:
                crop.save(tmp_path)
                words = extract_visible_text(tmp_path)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            words = [w for w in words if str(w.get("text", "")).strip()]
            if not words:
                continue
            # The crop spans neighbor icons too, so keep only the word run
            # nearest the icon's horizontal center (crop coords are 2x).
            icon_cx = (ix + iw / 2 - x1) * 2
            words.sort(key=lambda w: int(w.get("y", 0)))
            top_y = int(words[0].get("y", 0))
            top_line = [w for w in words if abs(int(w.get("y", 0)) - top_y) <= 16]
            top_line.sort(key=lambda w: int(w.get("x", 0)))
            if not top_line:
                continue
            best = min(
                top_line,
                key=lambda w: abs(int(w.get("x", 0)) + int(w.get("width", 0)) / 2 - icon_cx),
            )
            line = _word_run_around(top_line, best)
            # Wrapped labels ("Rocket / League") continue on the next line.
            if len(words) > len(top_line):
                rest = [w for w in words if w not in top_line]
                rest.sort(key=lambda w: int(w.get("y", 0)))
                next_y = int(rest[0].get("y", 0))
                if 8 < next_y - top_y <= 60:
                    next_line = [w for w in rest if abs(int(w.get("y", 0)) - next_y) <= 16]
                    next_line.sort(key=lambda w: int(w.get("x", 0)))
                    if next_line and min(
                        abs(int(w.get("x", 0)) + int(w.get("width", 0)) / 2 - icon_cx)
                        for w in next_line
                    ) <= iw:
                        line = [*line, *next_line]
            label = " ".join(str(w.get("text", "")).strip() for w in line).strip()
            # Desktop labels are short ("Steam", "Visual Studio Code");
            # longer lines are window content, not icon labels.
            if len(label) < 2 or len(label) > 20:
                continue
            lx1 = min(int(w.get("x", 0)) // 2 + x1 for w in line)
            ly1 = min(int(w.get("y", 0)) // 2 + y1 for w in line)
            lx2 = max((int(w.get("x", 0)) + int(w.get("width", 0))) // 2 + x1 for w in line)
            ly2 = max((int(w.get("y", 0)) + int(w.get("height", 0))) // 2 + y1 for w in line)
            item["text"] = label
            item["x"] = min(ix, lx1)
            item["y"] = min(iy, ly1)
            item["width"] = max(ix + iw, lx2) - item["x"]
            item["height"] = max(iy + ih, ly2) - item["y"]
            item["confidence"] = max(float(item.get("confidence") or 0), 0.85)
            recovered += 1
            LOGGER.info("Label recovery: icon at (%d,%d) -> '%s'", ix, iy, label)
        except Exception as exc:
            LOGGER.debug("Label recovery failed for one icon: %s", exc)
    return recovered


def augment_visible_items(
    ocr_items: list[dict],
    uia_items: list[dict],
    screenshot,
) -> list[dict]:
    """Merge OCR + UIA (+shell taskbar/desktop) and fuse icon boxes.

    Returns items *without* screen refs; callers apply
    :func:`assign_screen_element_refs` afterwards.
    """
    shell_items = get_shell_items_scaled(screenshot)
    uia_all = [*uia_items, *shell_items] if shell_items else uia_items
    merged = merge_visible_items(ocr_items, uia_all)
    icon_boxes = get_icon_boxes_for_screenshot(screenshot)
    if icon_boxes:
        merged = merge_icon_boxes(merged, icon_boxes, screenshot)
        textless = [item for item in merged if str(item.get("source", "")).lower() == "icon"]
        if textless:
            recover_icon_labels(textless, screenshot)
    return merged


def _occluded_behind_message(target: str, occluded_item: dict, active_app: dict) -> str | None:
    """Honest message when the target exists but is covered by the active app."""
    text = str(occluded_item.get("text") or target).strip()
    app_title = str((active_app or {}).get("title", "")).strip() or "the open window"
    return f"I found {text} on your desktop, but {app_title} is covering it. Minimize it and ask again."


def resolve_locator_fast_path(question: str, screenshot, target_pid: int | None, warnings: list[str], started: float) -> dict | None:
    # Single full-map pass: UIA (active window + visible shell) + OCR +
    # open-source icon model + label recovery. Every outcome saves the same
    # annotated screenshot analysts inspect, so fast hits and misses share
    # one consistent item world (no UIA-only partial maps).
    targets = extract_locator_targets(question)
    if not targets:
        click_target = extract_click_target(question)
        targets = [click_target] if click_target else []
    if not targets:
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

    uia_items = filter_ignored_overlay_items(uia_items, screenshot)
    shell_visible, shell_occluded = get_shell_items_scaled_partitioned(screenshot)
    shell_visible = filter_ignored_overlay_items(shell_visible, screenshot)
    uia_all = [*uia_items, *shell_visible] if shell_visible else uia_items

    ocr_started = time.perf_counter()
    crop_rect = _get_active_window_crop_rect(screenshot)
    ocr_items = extract_visible_text(screenshot.path, crop_rect=crop_rect)
    ocr_items = filter_ignored_overlay_items(ocr_items, screenshot)
    log_stage_timing("locator.ocr", ocr_started)
    if os.name != "nt":
        ocr_items = [item for item in ocr_items if item.get("y", 0) >= 35]
        uia_all = [item for item in uia_all if item.get("y", 0) >= 35]

    merged = merge_visible_items(ocr_items, uia_all)
    visible_items = assign_screen_element_refs(merged)
    visible_items.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
    pool = locator_match_items(question, visible_items)

    # Lazy Icon Detection: Check if all targets are already satisfied with high confidence
    # by OCR and UIA accessibility tree. If so, completely bypass heavy ONNX/YOLO execution!
    needs_icon_pass = False
    for target in targets:
        instruction = f"Locate the {target} control."
        match_result = find_best_match_with_score(target, pool, instruction) if pool else None
        if not match_result or not should_accept_locator_match(question, match_result):
            needs_icon_pass = True
            break

    if needs_icon_pass:
        icon_boxes = get_icon_boxes_for_screenshot(screenshot)
        if icon_boxes:
            merged = merge_icon_boxes(merged, icon_boxes, screenshot)
            textless = [item for item in merged if str(item.get("source", "")).lower() == "icon"]
            if textless:
                recover_icon_labels(textless, screenshot)
            visible_items = assign_screen_element_refs(merged)
            visible_items.sort(key=lambda item: (int(item.get("y", 0) / 10), item.get("x", 0)))
            pool = locator_match_items(question, visible_items)

    resolved: list[tuple[str, dict, dict | None]] = []
    occluded_notes: list[str] = []
    for target in targets:
        instruction = f"Locate the {target} control."
        match_result = find_best_match_with_score(target, pool, instruction) if pool else None
        if match_result and should_accept_locator_match(question, match_result):
            resolved.append((target, match_result["item"], match_result))
        elif match_result:
            LOGGER.info(
                "Locator deferred to AI for '%s' reason=low_control_confidence score=%.3f text_similarity=%.3f candidate_count=%d",
                target,
                match_result["score"],
                match_result["text_similarity"],
                match_result["candidate_count"],
            )
            return None
        else:
            occluded_match = (
                find_best_match_with_score(target, shell_occluded, instruction)
                if shell_occluded else None
            )
            if (
                occluded_match
                and (occluded_match["is_exact_text"] or occluded_match["text_similarity"] >= 0.82)
            ):
                note = _occluded_behind_message(target, occluded_match["item"], active_app)
                if note:
                    occluded_notes.append(note)
    if resolved:
        return build_multi_locator_result(question, resolved, visible_items, active_app, screenshot, warnings, started)
    if occluded_notes:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _save_parsed_for_analysis(screenshot, visible_items)
        return {
            "summary": " ".join(occluded_notes),
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

    icon_pool = [item for item in pool if str(item.get("source", "")).lower() in {"icon", "omniparser"}]
    if wants_control or icon_like_control_candidates(pool) or icon_pool:
        LOGGER.info("Locator deferred to AI for '%s' reason=icon_or_control_needs_ai", "|".join(targets))
        return None

    if is_open_action_question(question):
        return None

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    missing = ", ".join(targets)
    LOGGER.info("Locator local path did not find '%s' after checking %d visible items", missing, len(visible_items))
    _save_parsed_for_analysis(screenshot, visible_items)
    return {
        "summary": f"I could not find {missing} on the current screen.",
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


def _save_parsed_for_analysis(screenshot, visible_items: list[dict]) -> None:
    """Write the @ref-annotated screenshot analysts inspect for misses."""
    try:
        from utils.screen_annotator import save_parsed_ui_screenshot
        save_parsed_ui_screenshot(screenshot.path, visible_items)
    except Exception as exc:
        LOGGER.debug("Parsed screenshot save failed: %s", exc)


def build_multi_locator_result(
    question: str,
    resolved: list[tuple[str, dict, dict | None]],
    visible_items: list[dict],
    active_app: dict,
    screenshot,
    warnings: list[str],
    started: float,
) -> dict:
    """One highlight step per matched locator target (multi-highlight)."""
    _save_parsed_for_analysis(screenshot, visible_items)
    steps = []
    found: list[str] = []
    for idx, (target, match, match_result) in enumerate(resolved, start=1):
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
        steps.append({
            "step": idx,
            "instruction": local_target_instruction(question, target),
            "target_text": str(match.get("text") or target),
            "target_ref": str(match.get("ref", "")),
            "match": match_with_metadata,
        })
        found.append(target)
        LOGGER.info("Locator accepted local match '%s' to '%s'", target, match.get("text"))
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    on_screen = any(isinstance(m, dict) and m.get("shell_region") for _, m, _ in resolved)
    if len(found) == 1:
        where = "on your screen" if on_screen else "in the active app"
        summary = f"I found the {found[0]} {where}."
    else:
        summary = f"I found {', '.join(found)} on your screen."
    return {
        "summary": summary,
        "steps": steps,
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
        return bool(match_result["is_exact_text"] or match_result["text_similarity"] >= 0.82 or match_result["score"] >= 0.78)

    control_type = str(match_result.get("control_type", "")).lower()
    source = str(match_result.get("source", "")).lower()
    is_interactive = (
        (source == "uia" and control_type in {"button", "image", "tabitem", "menuitem", "edit", "textbox", "combobox", "listitem", "custom"})
        or (source == "omniparser")
        or (source == "icon" and control_type in {"image", "button"})
        or (source in {"ocr", "winrt"} and match_result.get("is_exact_text"))
    )
    if not is_interactive:
        return False
    if int(match_result.get("ambiguous_candidate_count") or match_result.get("candidate_count") or 0) > 1:
        return False
    if bool(match_result.get("is_exact_text")):
        return float(match_result.get("score") or 0) >= 0.8
    return float(match_result.get("score") or 0) >= 0.82 and float(match_result.get("text_similarity") or 0) >= 0.78


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
    return build_multi_locator_result(
        question, [(target, match, match_result)], visible_items, active_app, screenshot, warnings, started,
    )


def extract_locator_targets(question: str) -> list[str]:
    """Split multi-item locator queries ("highlight steam and edge")."""
    single = extract_locator_target(question)
    if not single:
        return []
    parts = re.split(r"\s+(?:and|&)\s+|\s*,\s*", single)
    targets = [clean_locator_target(part) for part in parts]
    targets = [t for t in targets if t]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for target in targets:
        key = target.lower()
        if key not in seen:
            seen.add(key)
            unique.append(target)
    return unique or ([single] if single else [])


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
        r"^find\s+(?:me\s+)?(?:the\s+)?(.+?)(?:\?|$)",
        r"^search\s+(?:for\s+)?(?:the\s+)?(.+?)(?:\?|$)",
        r"^look\s+for\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"^spot\s+(?:the\s+)?(.+?)(?:\?|$)",
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
        r"^(?:click|select|choose|press|tap|hit|push)\s+(?:on\s+)?(?:the\s+)?(.+?)(?:\?|$)",
        r"^(?:change|switch|set|turn)\s+(?:(?:dark|light|custom|theme|mode)\s+)?to\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"^(?:change|switch|set)\s+(?:from\s+\w+\s+)?to\s+(?:the\s+)?(.+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_locator_target(match.group(1))
    return None



def is_open_action_question(question: str) -> bool:
    normalized = " ".join(question.lower().strip().split())
    return normalized.startswith(("open ", "launch ", "start "))


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
    # Drop location hints in parentheses FIRST (before char-stripping eats
    # the closing paren): "steam (on desktop)" -> "steam".
    cleaned = re.sub(r"\s*\([^()]{1,40}\)", " ", value).strip()
    cleaned = cleaned.strip(" .,!?:;\"'`()[]")
    cleaned = re.sub(r"\s+(?:in|on|from)\s+the\s+.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:on\s+desktop|on\s+taskbar|in\s+taskbar|on\s+the\s+desktop)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:button|icon|tab|menu|control|panel|view|folder)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .,!?:;\"'`()[]")
    return cleaned or None


# NOTE: icon-only targets (e.g. the WhatsApp Status rail icon) carry no
# text, so they can never match by label. They are intentionally NOT guessed
# by position here: a wrong positional guess highlights the wrong button
# with full confidence. Instead the fast path defers to the vision model,
# which identifies the icon from the screenshot (see prompt.py), with the
# open-source icon boxes included as "Visible Image N" handles.


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
    max_area = (screenshot.width * screenshot.height) * 0.5
    scaled_rects = []
    for rect in rects:
        rx = rect["x"] * sx
        ry = rect["y"] * sy
        rw = rect["width"] * sx
        rh = rect["height"] * sy
        if rw * rh >= max_area or (rw >= screenshot.width * 0.7 and rh >= screenshot.height * 0.7):
            LOGGER.warning("Discarded oversized ignored overlay rect (%dx%d) to protect screen scanning", int(rw), int(rh))
            continue
        scaled_rects.append({
            "x": rx,
            "y": ry,
            "width": rw,
            "height": rh,
        })
    if not scaled_rects:
        return items

    filtered = [item for item in items if not _item_center_in_any_rect(item, scaled_rects)]
    removed = len(items) - len(filtered)
    if removed:
        LOGGER.info("Filtered %d items inside ignored overlay windows", removed)
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
        if payload.get("action") in ("test_ai_model", "ping_model"):
            from ai.model_tester import ping_ai_model
            res = ping_ai_model(
                provider=payload.get("provider", "groq"),
                api_key=payload.get("api_key"),
                model=payload.get("model"),
                custom_url=payload.get("custom_url"),
            )
            print(json.dumps(res, ensure_ascii=True))
            return

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
        ignored_rects = payload.get("ignored_rects")
        attached_image = payload.get("attached_image") or payload.get("attachedImage")
        attached_file = payload.get("attached_file") or payload.get("attachedFile")
        if not question and not attached_image:
            raise ValueError("Question is required.")

        result = run(question or "Explain what is in this image.", previous_question, progress, conversation_history, web_search_enabled, agent_mode, ignored_rects, attached_image, attached_file)
        print(json.dumps(result, ensure_ascii=True))
    except Exception as exc:
        LOGGER.exception("Worker failed")
        print(json.dumps({"error": str(exc), "steps": [], "warnings": [str(exc)]}))
        sys.exit(1)


if __name__ == "__main__":
    main()

