"""
Multi-step tool execution loop.
Recipes inject knowledge into LLM context — never blind replay.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.computer_use.loop")

MAX_TOOL_CALLS = 10

_SCREENSHOT_MODE: str | None = None


def _get_screenshot_mode() -> str:
    global _SCREENSHOT_MODE
    if _SCREENSHOT_MODE is None:
        _SCREENSHOT_MODE = os.getenv("BLINKY_SCREENSHOT_MODE", "ocr").strip().lower()
    return _SCREENSHOT_MODE


_APP_INVENTORY: list[str] | None = None


def _get_app_inventory() -> list[str]:
    global _APP_INVENTORY
    if _APP_INVENTORY is not None:
        return _APP_INVENTORY

    result: list[str] = []
    def _collect():
        global _APP_INVENTORY
        try:
            from app_inventory import get_app_inventory
            apps = get_app_inventory()
            _APP_INVENTORY = apps
            result.extend(apps)
        except Exception as e:
            LOGGER.warning("App inventory collection failed: %s", e)
            _APP_INVENTORY = []

    t = threading.Thread(target=_collect, daemon=True)
    t.start()
    t.join(timeout=5)
    if t.is_alive():
        LOGGER.warning("App inventory collection timed out")
        _APP_INVENTORY = []

    return _APP_INVENTORY or []


def _emit_status(phase: str, message: str) -> None:
    out = sys.__stdout__ if hasattr(sys, "__stdout__") else sys.stdout
    print(json.dumps({"type": "status", "phase": phase, "message": message}), flush=True, file=out)


# ── Tool definitions ────────────────────────────────────────────

from .tools import (
    ToolResult,
    open_app_tool_linux,
    list_windows_tool,
    get_app_state_tool,
    click_element_tool,
    type_text_tool,
    press_key_tool,
    screenshot_tool,
    mouse_tool,
)

TOOL_MAP = {
    "open_app": open_app_tool_linux,
    "list_windows": list_windows_tool,
    "get_app_state": get_app_state_tool,
    "click_element": click_element_tool,
    "type_text": type_text_tool,
    "press_key": press_key_tool,
    "screenshot": screenshot_tool,
    "mouse": mouse_tool,
}

from . import config as vision_config
from . import metrics as vision_metrics
from .vision_planner import plan_action
from .vision_verifier import verify_action
from .recovery import diagnose_failure
from .tools import capture_screenshot, checksum_frame


def _describe_action(tool_name: str, args: dict[str, Any]) -> str:
    descriptions = {
        "open_app": f"Opening {args.get('app_name', 'app')}...",
        "list_windows": "Looking at open windows...",
        "get_app_state": f"Inspecting {args.get('app_name', 'app')}...",
        "click_element": f"Clicking {args.get('name', 'element')}...",
        "type_text": f"Typing '{args.get('text', '')}'...",
        "press_key": f"Pressing {args.get('key', 'key')}...",
        "screenshot": "Taking a screenshot...",
        "mouse": f"Mouse {args.get('action', 'action')}...",
    }
    return descriptions.get(tool_name, f"Running {tool_name}...")


def _essential_tool_schemas() -> list[dict]:
    return [
        {"name": "open_app", "description": "Launch a desktop app by name (calculator, firefox, terminal, settings, files, etc.)",
         "inputSchema": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]}},
        {"name": "list_windows", "description": "List all open windows with titles and positions",
         "inputSchema": {"type": "object", "properties": {}}},
        # {"name": "get_app_state", "description": "Inspect an app's UI elements (buttons, fields, labels) — returns roles, names, positions",
        #  "inputSchema": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]}},
        {"name": "click_element", "description": "Click a UI element by label via AT-SPI. Returns error if element not found — use mouse(x,y) as fallback.",
         "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}}},
        {"name": "type_text", "description": "Type text into the focused app",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
        {"name": "press_key", "description": "Press a keyboard key: enter, escape, tab",
         "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}},
        {"name": "screenshot", "description": "Take a screenshot — returns OCR text items with relative coordinates and window bounds. Use after typing/clicking to confirm the result.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "mouse", "description": "Virtual mouse control. Move cursor, click, or scroll at absolute screen coordinates.",
         "inputSchema": {"type": "object", "properties": {
             "action": {"type": "string", "enum": ["move", "click", "scroll"], "description": "move=cursor, click=click at xy, scroll=scroll wheel"},
             "x": {"type": "integer", "description": "X coordinate (for move/click)"},
             "y": {"type": "integer", "description": "Y coordinate (for move/click)"},
             "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button for click (default: left)"},
             "scroll_amount": {"type": "integer", "description": "Scroll amount: positive=down, negative=up (default: 3)"},
         }, "required": ["action"]}},
    ]


def _format_tools_compact(tools: list[dict]) -> str:
    lines: list[str] = []
    for t in tools:
        name = t.get("name", "unknown")
        desc = t.get("description", "")
        schema = t.get("inputSchema") or {}
        props = schema.get("properties", {})
        required = schema.get("required", [])
        params = [f"{p}?" if p not in required else p for p in props]
        lines.append(f"{name}({', '.join(params)}) — {desc}")
    return "\n".join(lines)


# ── Prompt ──────────────────────────────────────────────────────

def build_system_prompt(
    recipe_context: str | None = None,
    app_inventory: list[str] | None = None,
    has_vision: bool = False,
) -> str:
    """Build the system prompt from the YAML config file."""
    from prompts import get_prompts

    prompts = get_prompts()
    tools_str = _format_tools_compact(_essential_tool_schemas())

    # Build the system prompt from the template
    system_template = prompts.get("system", "")
    prompt = system_template.format(tools=tools_str)

    # Append app inventory if provided
    if app_inventory:
        inventory_template = prompts.get("app_inventory", "")
        inventory_lines = "\n".join(f"- {app}" for app in app_inventory[:50])
        prompt += "\n\n" + inventory_template.format(inventory=inventory_lines)

    # Append vision note if applicable
    if has_vision:
        vision_note = prompts.get("vision_note", "")
        if vision_note:
            prompt += "\n\n" + vision_note.strip()

    # Append recipe context if provided
    if recipe_context:
        prompt += recipe_context

    return prompt


def get_prompt(key: str, **kwargs: Any) -> str:
    """Get a specific prompt from the config, with optional formatting."""
    from prompts import get_prompts

    prompts = get_prompts()
    template = prompts.get(key, "")
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
    return template


# ── Recipe integration ──────────────────────────────────────────

_FAILURE_INDICATORS = {
    "failed", "unable", "cannot", "can't", "could not", "couldn't",
    "error", "permission denied", "sorry", "not found", "no such",
    "does not exist", "doesn't exist", "timed out", "timeout",
}

_NON_VERBAL_INDICATORS = {
    "no text detected", "may not have been", "window may not",
    "not visible", "could not find", "unable to see",
    "screenshot detected no", "no ocr",
}

_recipe_registry: Any = None


def _get_recipe_registry():
    global _recipe_registry
    if _recipe_registry is not None:
        return _recipe_registry
    try:
        from .recipes import RecipeRegistry
        import os
        # common/python/computer_use → go up 3 to project root
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        recipes_dir = os.path.join(root, ".brain", "ARTIFACTS", "recipes")
        _recipe_registry = RecipeRegistry(recipes_dir)
    except Exception:
        _recipe_registry = False
    return _recipe_registry


def _is_successful_completion(answer: str, steps: list[dict[str, Any]]) -> bool:
    if not steps:
        return False
    if not any(s.get("success") for s in steps):
        return False
    answer_lower = answer.lower()
    for indicator in _FAILURE_INDICATORS:
        if indicator in answer_lower:
            return False
    for indicator in _NON_VERBAL_INDICATORS:
        if indicator in answer_lower:
            return False
    return True


# ── Tool calling ────────────────────────────────────────────────

_last_window_bounds: dict[str, Any] | None = None


def _get_fresh_window_bounds() -> dict[str, Any] | None:
    """Get fresh window bounds at action time to avoid stale coordinates."""
    try:
        from computer_use.linux_mcp import get_focused_window_bounds
        return get_focused_window_bounds()
    except Exception:
        return _last_window_bounds


def _get_screen_dims() -> tuple[int, int]:
    """Return (width, height) of the physical display in pixels.

    Tries: wayland_vision → wlr-randr → screenshot → 1920×1080 fallback.
    """
    # 1. Try wayland_vision's get_focused_window_bounds (window fills screen minus panels)
    try:
        from computer_use.linux_mcp import get_focused_window_bounds
        b = get_focused_window_bounds()
        if b and b.get("width") and b.get("height"):
            return int(b["width"]), int(b["height"])
    except Exception:
        pass

    # 2. Try xrandr (works on X11 and via XWayland)
    try:
        import subprocess
        r = subprocess.run(["xrandr"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if " connected " in line and "x" in line:
                    parts = line.strip().split()
                    for p in parts:
                        if "x" in p and "+" in p and p.replace("x","").replace("+","").isdigit():
                            res = p.split("+")[0]
                            w_str, h_str = res.split("x", 1)
                            return int(w_str), int(h_str)
    except Exception:
        pass

    # 3. Try reading dimensions from a screenshot
    try:
        from PIL import Image
        from computer_use.tools import capture_screenshot
        ss = capture_screenshot()
        if ss:
            with Image.open(ss) as img:
                return img.size
    except Exception:
        pass

    return 1920, 1080


def _convert_ocr_coords(args: dict[str, Any]) -> dict[str, Any]:
    """Convert OCR-relative coordinates to absolute screen coordinates."""
    from ai.client import has_vision_capability
    from .tools import _is_relative_coordinate, translate_relative_to_absolute, _to_int

    name_param = args.get("name")
    LOGGER.debug("Coordinate conversion check: name_param=%s, x=%s, y=%s", name_param, args.get("x"), args.get("y"))
    if name_param and isinstance(name_param, dict):
        if _is_relative_coordinate(name_param):
            LOGGER.info("OCR relative coordinates detected in name param: %s", json.dumps(name_param, default=str)[:200])
            bounds = _get_fresh_window_bounds()
            LOGGER.info("Fresh window bounds for conversion: %s", bounds)
            scale = 1.0
            try:
                from .tools import _WAYLAND_VISION_AVAILABLE, get_screen_scale
                if _WAYLAND_VISION_AVAILABLE:
                    scale = get_screen_scale()
                    LOGGER.info("Screen scale factor: %s", scale)
            except Exception:
                pass
            converted = translate_relative_to_absolute(name_param, bounds, scale)
            abs_bounds = converted.get("absolute_bounds", {})
            LOGGER.info("Converted coordinates: %s", json.dumps(abs_bounds))
            if abs_bounds:
                args["x"] = abs_bounds.get("x", args.get("x"))
                args["y"] = abs_bounds.get("y", args.get("y"))
                LOGGER.info("Updated args with absolute coords: x=%s, y=%s", args.get("x"), args.get("y"))

    x = args.get("x")
    y = args.get("y")
    if x is not None and y is not None:
        args["x"] = _to_int(x)
        args["y"] = _to_int(y)

    return args


def _call_tool(name: str, fn: Any, args: dict[str, Any]) -> ToolResult:
    try:
        if name in ("click_element",):
            args = _convert_ocr_coords(args)
            return fn(
                name=args.get("name"),
                role=args.get("role"),
                index=args.get("index"),
                x=args.get("x"),
                y=args.get("y"),
            )
        elif name == "open_app":
            return fn(app_name=args.get("app_name", ""))
        elif name == "list_windows":
            return fn()
        elif name == "get_app_state":
            return fn(app_name=args.get("app_name", ""))
        elif name == "type_text":
            return fn(text=args.get("text", ""), target_app=args.get("target_app"))
        elif name == "press_key":
            return fn(key=args.get("key", ""), target_app=args.get("target_app"))
        elif name == "screenshot":
            return fn()
        elif name == "mouse":
            x_val = args.get("x")
            y_val = args.get("y")
            from .tools import _to_int as _to_int_mouse
            if x_val is not None and not isinstance(x_val, int) and not isinstance(x_val, bool) and 0 < x_val <= 1:
                sw, sh = _get_screen_dims()
                x_val = int(x_val * sw)
                if y_val is not None:
                    y_val = int(y_val * sh)
            return fn(
                action=args.get("action", ""),
                x=_to_int_mouse(x_val) if x_val is not None else None,
                y=_to_int_mouse(y_val) if y_val is not None else None,
                button=args.get("button", "left"),
                scroll_amount=args.get("scroll_amount", 3),
            )
        else:
            return ToolResult(False, name, f"Unknown tool: {name}", {})
    except TypeError as e:
        return ToolResult(False, name, f"Invalid arguments: {e}", {"args": args})


# ── Main loop ───────────────────────────────────────────────────

def run_computer_use_loop(
    question: str,
    max_calls: int = MAX_TOOL_CALLS,
) -> dict[str, Any]:
    """Execute a multi-step desktop automation task.
    Recipes inject knowledge into the LLM prompt — never blind replay."""

    if platform.system() != "Linux":
        return {"success": False, "error": "Computer use is only supported on Linux.", "steps": []}

    from ai.client import ask_text_model, has_vision_capability

    # Inject recipe knowledge into system prompt
    recipe_context: str | None = None
    matched_recipe_id: str | None = None
    registry = _get_recipe_registry()
    if registry:
        matches = registry.match_query(question)
        if matches:
            matched_recipe_id = matches[0][0]
            recipe_context = registry.get_context(matched_recipe_id)
            if recipe_context:
                _emit_status("analyzing", "Applying learned knowledge...")
                LOGGER.info("Injecting recipe knowledge from %s", matched_recipe_id)

    app_inventory = _get_app_inventory()
    has_vision = has_vision_capability()
    system_prompt = build_system_prompt(
        recipe_context=recipe_context,
        app_inventory=app_inventory,
        has_vision=has_vision,
    )
    conversation = [f"SYSTEM: {system_prompt}", f"USER: {question}"]
    steps_taken: list[dict[str, Any]] = []

    LOGGER.info("=== AGENT LOOP START ===")
    LOGGER.info("Question: %s", question)
    LOGGER.info("Max calls: %d", max_calls)
    LOGGER.info("App inventory: %d apps", len(app_inventory) if app_inventory else 0)
    LOGGER.info("Has vision: %s", has_vision)
    LOGGER.info("Recipe context: %s", "yes" if recipe_context else "no")
    LOGGER.info("System prompt length: %d chars", len(system_prompt))

    _emit_status("analyzing", "Analyzing your request...")

    _consecutive_same_tool = 0
    _last_tool_name = ""
    _inspection_count = 0
    _consecutive_vision_failures = 0
    _recovery_count = 0
    _root_cause_counts: dict[str, int] = {}
    _vision_observations: list[str] = []
    _loop_counter = 0
    _last_tool_call = ("", {})

    # ── Vision-guided initial planning ──
    _emit_status("analyzing", "Analyzing screen with vision...")
    ss_path = capture_screenshot()
    if ss_path and has_vision:
        planner_result = plan_action(
            screenshot_path=ss_path,
            query=question,
            history=_vision_observations,
            tool_schema={name: {} for name in TOOL_MAP},
        )
        if "error" not in planner_result:
            plan_note = f"[Vision Observation] Vision Planner suggests: {planner_result.get('action')}({json.dumps(planner_result.get('args', {}))}) — {planner_result.get('reasoning', '')}"
            conversation.append(plan_note)
            _vision_observations.append(plan_note)
            _emit_status("planning", f"Planning: {planner_result.get('action')}")
        else:
            LOGGER.warning("Vision planner unavailable: %s", planner_result.get("error"))
            _consecutive_vision_failures += 1
    else:
        LOGGER.info("Skipping vision plan: ss_path=%s, has_vision=%s", ss_path, has_vision)

    for iteration in range(max_calls + 1):
        if iteration >= max_calls:
            LOGGER.info("=== MAX CALLS REACHED (%d) ===", max_calls)
            _emit_status("error", "Maximum steps reached.")
            return {"success": False, "error": f"Reached maximum tool calls ({max_calls}).", "steps": steps_taken}

        LOGGER.info("--- Iteration %d/%d ---", iteration + 1, max_calls)
        LOGGER.info("Conversation length: %d messages", len(conversation))
        _emit_status("planning" if iteration == 0 else "thinking",
                     "Planning actions..." if iteration == 0 else "Deciding next step...")

        prompt = "\n\n".join(conversation) + "\n\nWhat is your next action? Output JSON only."
        LOGGER.debug("Prompt to LLM (%d chars): %.200s...", len(prompt), prompt)

        try:
            response = ask_text_model(prompt, max_tokens=500)
            LOGGER.info("LLM response: %s", json.dumps(response, default=str)[:500])
        except Exception as exc:
            LOGGER.exception("LLM call failed on iteration %d", iteration)
            return {"success": False, "error": f"LLM call failed: {exc}", "steps": steps_taken}

        if "tool" in response:
            tool_name = response.get("tool", "")
            args = response.get("args", {})
            LOGGER.info("Tool call #%d: %s(%s)", iteration + 1, tool_name, args)
            LOGGER.info("Tool args detail: %s", json.dumps(args, default=str)[:300])
            _emit_status("action", _describe_action(tool_name, args))

            # Repetition detector: track consecutive same-tool calls
            if tool_name == _last_tool_name:
                _consecutive_same_tool += 1
                LOGGER.info("Consecutive same-tool: %s x%d", tool_name, _consecutive_same_tool)
            else:
                _consecutive_same_tool = 1
                _last_tool_name = tool_name

            # Track inspection-only loops (list_windows, get_app_state, screenshot without action)
            _inspection_tools = {"list_windows", "get_app_state", "screenshot"}
            if tool_name in _inspection_tools:
                _inspection_count += 1
                LOGGER.info("Inspection count: %d (tool=%s)", _inspection_count, tool_name)
            else:
                _inspection_count = 0

            # If stuck in inspection loop, force the LLM to take action
            if _inspection_count >= 3 and iteration < max_calls - 1:
                LOGGER.warning("Inspection loop detected (%d inspections) — pushing LLM to take action", _inspection_count)
                conversation.append(
                    get_prompt("inspection_loop", count=_inspection_count)
                )
                _inspection_count = 0
                continue

            # If calling the same tool 3+ times in a row, suggest something different
            if _consecutive_same_tool >= 3 and iteration < max_calls - 1:
                LOGGER.warning("Repeated tool call detected: %s called %d times", tool_name, _consecutive_same_tool)
                conversation.append(
                    get_prompt("repeated_tool", tool_name=tool_name, count=_consecutive_same_tool)
                )
                continue

            # Loop detection: identical tool call (same name + same args)
            current_call = (tool_name, json.dumps(args, sort_keys=True))
            if current_call == _last_tool_call:
                _loop_counter += 1
            else:
                _loop_counter = 0
            _last_tool_call = current_call

            if _loop_counter >= vision_config.LOOP_DETECTION_THRESHOLD and iteration < max_calls - 1:
                LOGGER.warning("Loop detected: %s called with identical args %d times", tool_name, _loop_counter + 1)
                recovery_result = diagnose_failure(
                    screenshot_path=capture_screenshot(),
                    failed_action=tool_name,
                    error="Loop detected: same tool call repeated",
                    history=_vision_observations[-3:] if _vision_observations else None,
                )
                _recovery_count += 1
                rc = recovery_result.get("root_cause_category", "unknown")
                _root_cause_counts[rc] = _root_cause_counts.get(rc, 0) + 1

                if _recovery_count >= vision_config.MAX_FAILURES:
                    return {
                        "success": False,
                        "error": f"Failed after {_recovery_count} recovery attempts. Root causes: {json.dumps(_root_cause_counts)}",
                        "steps": steps_taken,
                    }

                recovery_note = (
                    f"[Vision Observation] Recovery: {recovery_result.get('diagnosis', '')}. "
                    f"Suggestion: {recovery_result.get('suggestion', '')}"
                )
                conversation.append(recovery_note)
                _vision_observations.append(recovery_note)

                if recovery_result.get("requires_replan", False):
                    replan_path = capture_screenshot()
                    if replan_path and has_vision:
                        planner_result = plan_action(
                            screenshot_path=replan_path,
                            query=question,
                            history=_vision_observations,
                            tool_schema={name: {} for name in TOOL_MAP},
                        )
                        if "error" not in planner_result:
                            plan_note = f"[Vision Observation] Re-plan: {planner_result.get('action')}({json.dumps(planner_result.get('args', {}))}) — {planner_result.get('reasoning', '')}"
                            conversation.append(plan_note)
                            _vision_observations.append(plan_note)
                else:
                    for act in recovery_result.get("actions", []):
                        act_note = f"[Vision Observation] Suggested next: {act.get('tool')}({json.dumps(act.get('args', {}))})"
                        conversation.append(act_note)
                        _vision_observations.append(act_note)
                continue

            tool_fn = TOOL_MAP.get(tool_name)
            if not tool_fn:
                LOGGER.warning("Unknown tool requested: %s", tool_name)
                conversation.append(f"ASSISTANT: Unknown tool '{tool_name}'. Available: {list(TOOL_MAP.keys())}")
                continue

            try:
                result = _call_tool(tool_name, tool_fn, args)
                LOGGER.info("Tool result: success=%s, message=%s", result.success, result.message[:200])
                if result.details:
                    LOGGER.info("Tool result details keys: %s", list(result.details.keys()))
            except Exception as exc:
                LOGGER.exception("Tool execution failed")
                result = ToolResult(False, tool_name, str(exc), {"args": args})

            steps_taken.append({"tool": tool_name, "args": args, "success": result.success, "message": result.message})

            # Store window_bounds from screenshot for coordinate conversion
            if tool_name == "screenshot" and result.details:
                wb = result.details.get("window_bounds")
                if isinstance(wb, dict):
                    global _last_window_bounds
                    _last_window_bounds = wb
                    LOGGER.info("Window bounds stored: %s", json.dumps(wb))
                else:
                    LOGGER.info("No window bounds in screenshot result")
                LOGGER.info("Screenshot details: image_path=%s, ocr_items_count=%d, has_vision=%s",
                           result.details.get("image_path", "none"),
                           len(result.details.get("ocr_items", [])),
                           result.details.get("has_vision", False))

            # Append OCR items to conversation if present
            if tool_name == "screenshot" and result.details:
                ocr_items = result.details.get("ocr_items")
                if isinstance(ocr_items, list) and ocr_items:
                    LOGGER.info("OCR items received: %d items", len(ocr_items))
                    for i, item in enumerate(ocr_items[:10]):
                        LOGGER.debug("OCR item %d: text=%s, x=%s, y=%s, w=%s, h=%s, conf=%s",
                                   i, item.get("text"), item.get("x"), item.get("y"),
                                   item.get("width"), item.get("height"), item.get("confidence"))
                    screen_content = "SCREEN CONTENT:\n"
                    for item in ocr_items[:50]:
                        text = item.get("text", "")
                        ix = item.get("x", 0)
                        iy = item.get("y", 0)
                        screen_content += f'  SOURCE: OCR (screen text, may not reflect actual content) — "{text}" at ({ix}, {iy})\n'
                    conversation.append(screen_content)
                    LOGGER.info("OCR content appended to conversation (%d items)", min(len(ocr_items), 50))

                    img_path = result.details.get("image_path")
                    if img_path and has_vision:
                        if isinstance(img_path, str) and os.path.exists(img_path):
                            conversation.append(f"The screenshot image is available at {img_path}")
                            LOGGER.info("Vision image path appended: %s", img_path)
                        else:
                            LOGGER.warning("Screenshot image path unavailable: %s", img_path)
                else:
                    LOGGER.info("No OCR items detected in screenshot")
                    conversation.append("SCREEN CONTENT: No text detected. The window may not be focused or may have no visible text. Try list_windows to confirm the app is open, then click on it to focus, then screenshot again.")

            conversation.append(f"ASSISTANT: Tool call: {tool_name}({json.dumps(args)})")
            conversation.append(f"TOOL RESULT [{tool_name}]: {'SUCCESS' if result.success else 'FAILED'}. {result.message}")
            if result.details:
                d = json.dumps(result.details, default=str).replace("ydotool_socket", "").replace("socket connection error", "")
                conversation.append(f"TOOL DATA: {d[:1000]}")

            # ── Vision-guided verification after visual actions only ──
            ACTION_TOOLS = {"open_app", "click_element"}
            if tool_name in ACTION_TOOLS:
                _emit_status("analyzing", "Verifying action with vision...")

                stable_path = None
                if result.success:
                    # Poll for screen stability after a successful action
                    poll_start = time.time()
                    prev_checksum = None
                    stable_count = 0

                    while (time.time() - poll_start) * 1000 < vision_config.SCREENSHOT_POLL_TIMEOUT_MS:
                        time.sleep(vision_config.SCREENSHOT_POLL_INTERVAL_MS / 1000)
                        frame_path = capture_screenshot()
                        if frame_path is None:
                            continue
                        csum = checksum_frame(frame_path)
                        if csum is None:
                            continue
                        if prev_checksum is not None and csum == prev_checksum:
                            stable_count += 1
                            if stable_count >= vision_config.SCREENSHOT_STABLE_FRAMES:
                                stable_path = frame_path
                                break
                        else:
                            stable_count = 0
                        prev_checksum = csum

                    if stable_path is None:
                        LOGGER.info("Pixel stability not achieved within %dms, using best-effort screenshot", vision_config.SCREENSHOT_POLL_TIMEOUT_MS)
                # Take a single screenshot for failed actions or fallback
                if stable_path is None:
                    stable_path = capture_screenshot()

                if stable_path and has_vision:
                    expected = _describe_action(tool_name, args)
                    verifier_result = verify_action(
                        screenshot_path=stable_path,
                        action_taken=expected,
                        expected_outcome=expected,
                        query=question,
                    )

                    if verifier_result.get("confidence", 1.0) <= vision_config.VISION_CONFIDENCE_HIGH and \
                       verifier_result.get("confidence", 1.0) > vision_config.VISION_CONFIDENCE_LOW:
                        LOGGER.info("Borderline confidence (%.2f) — re-verifying with fresh screenshot", verifier_result.get("confidence"))
                        second_path = capture_screenshot()
                        if second_path:
                            time.sleep(0.2)
                            verifier_result = verify_action(
                                screenshot_path=second_path,
                                action_taken=expected,
                                expected_outcome=expected,
                                query=question,
                            )

                    if verifier_result.get("verified", False):
                        obs = f"[Vision Observation] Action verified: {verifier_result.get('observation', '')}"
                        conversation.append(obs)
                        _vision_observations.append(obs)
                        _consecutive_vision_failures = 0
                    else:
                        obs_text = verifier_result.get("observation", "")
                        LOGGER.warning("Verification failed: %s", obs_text)

                        # If vision model errored (not a genuine verification failure), fall back to OCR
                        if "model error" in obs_text.lower() or "Screenshot unavailable" in obs_text:
                            LOGGER.info("Vision model error — falling back to OCR auto-screenshot")
                            _consecutive_vision_failures += 1
                            if result.success:
                                try:
                                    auto_ss = _call_tool("screenshot", TOOL_MAP["screenshot"], {})
                                    if auto_ss.success and auto_ss.details:
                                        auto_ocr = auto_ss.details.get("ocr_items")
                                        if isinstance(auto_ocr, list) and auto_ocr:
                                            screen_content = "SCREEN CONTENT (after your action):\n"
                                            for item in auto_ocr[:50]:
                                                text = item.get("text", "")
                                                ix = item.get("x", 0)
                                                iy = item.get("y", 0)
                                                screen_content += f'  SOURCE: OCR (screen text) — "{text}" at ({ix}, {iy})\n'
                                            conversation.append(screen_content)
                                except Exception:
                                    pass
                            continue

                        recovery_result = diagnose_failure(
                            screenshot_path=stable_path,
                            failed_action=tool_name,
                            error=None,
                            history=_vision_observations[-3:] if _vision_observations else None,
                        )
                        _recovery_count += 1
                        rc = recovery_result.get("root_cause_category", "unknown")
                        _root_cause_counts[rc] = _root_cause_counts.get(rc, 0) + 1

                        if _recovery_count >= vision_config.MAX_FAILURES:
                            LOGGER.error("Max recoveries reached (%d)", _recovery_count)
                            _emit_status("error", f"Task failed after {_recovery_count} recovery attempts.")
                            return {
                                "success": False,
                                "error": f"Failed after {_recovery_count} recovery attempts. Root causes: {json.dumps(_root_cause_counts)}",
                                "steps": steps_taken,
                            }

                        recovery_note = (
                            f"[Vision Observation] Recovery: {recovery_result.get('diagnosis', '')}. "
                            f"Suggestion: {recovery_result.get('suggestion', '')}"
                        )
                        conversation.append(recovery_note)
                        _vision_observations.append(recovery_note)

                        if recovery_result.get("requires_replan", False):
                            replan_path = capture_screenshot()
                            if replan_path and has_vision:
                                planner_result = plan_action(
                                    screenshot_path=replan_path,
                                    query=question,
                                    history=_vision_observations,
                                    tool_schema={name: {} for name in TOOL_MAP},
                                )
                                if "error" not in planner_result:
                                    plan_note = f"[Vision Observation] Re-plan: {planner_result.get('action')}({json.dumps(planner_result.get('args', {}))}) — {planner_result.get('reasoning', '')}"
                                    conversation.append(plan_note)
                                    _vision_observations.append(plan_note)
                        else:
                            for act in recovery_result.get("actions", []):
                                act_note = f"[Vision Observation] Suggested next: {act.get('tool')}({json.dumps(act.get('args', {}))})"
                                conversation.append(act_note)
                                _vision_observations.append(act_note)
                        continue
                else:
                    LOGGER.info("Vision verification skipped (has_vision=%s, stable_path=%s)", has_vision, stable_path)
                    if result.success:
                        try:
                            auto_ss = _call_tool("screenshot", TOOL_MAP["screenshot"], {})
                            if auto_ss.success and auto_ss.details:
                                auto_wb = auto_ss.details.get("window_bounds")
                                if isinstance(auto_wb, dict):
                                    _last_window_bounds = auto_wb
                                auto_ocr = auto_ss.details.get("ocr_items")
                                if isinstance(auto_ocr, list) and auto_ocr:
                                    screen_content = "SCREEN CONTENT (after your action):\n"
                                    for item in auto_ocr[:50]:
                                        text = item.get("text", "")
                                        ix = item.get("x", 0)
                                        iy = item.get("y", 0)
                                        screen_content += f'  SOURCE: OCR (screen text) — "{text}" at ({ix}, {iy})\n'
                                    conversation.append(screen_content)
                                else:
                                    conversation.append("SCREEN CONTENT (after your action): No text detected on screen.")
                                steps_taken.append({"tool": "screenshot", "args": {}, "success": True, "message": "auto-screenshot after " + tool_name})
                        except Exception as auto_exc:
                            LOGGER.warning("Auto-screenshot exception: %s", auto_exc)

            # Rotate vision observations if too many
            if len(_vision_observations) > vision_config.MAX_HISTORY_OBSERVATIONS:
                _vision_observations = _vision_observations[-vision_config.MAX_HISTORY_OBSERVATIONS:]

        elif "answer" in response:
            final = response["answer"]

            LOGGER.info("LLM wants to answer: %s", final[:300])
            has_screenshot = any(s.get("tool") == "screenshot" for s in steps_taken)
            has_app_state = any(s.get("tool") == "get_app_state" for s in steps_taken)
            LOGGER.info("Verification check: has_screenshot=%s, has_app_state=%s, steps=%d",
                       has_screenshot, has_app_state, len(steps_taken))

            # Always force a screenshot before answering if none was taken yet
            if not has_screenshot and not has_app_state and iteration < max_calls - 1:
                LOGGER.warning("No screenshot taken yet — forcing verification screenshot")
                conversation.append(
                    get_prompt("premature_answer")
                )
                continue

            LOGGER.info("=== TASK COMPLETE ===")
            LOGGER.info("Final answer: %s", final[:500])
            LOGGER.info("Steps taken: %d", len(steps_taken))
            for i, s in enumerate(steps_taken):
                LOGGER.info("  Step %d: %s(%s) -> success=%s", i+1, s.get("tool"), s.get("args"), s.get("success"))
            _emit_status("complete", "Task complete")

            recipe_saved = False
            if registry and _is_successful_completion(final, steps_taken):
                rid = registry.save(question, steps_taken, final)
                recipe_saved = rid is not None
                LOGGER.info("Recipe saved: %s (id=%s)", recipe_saved, rid)
            else:
                LOGGER.info("Recipe NOT saved: completion=%s, registry=%s",
                           _is_successful_completion(final, steps_taken), registry is not None)

            LOGGER.info("=== AGENT LOOP END ===")
            return {"success": True, "answer": final, "steps": steps_taken, "recipe_saved": recipe_saved}

        else:
            conversation.append(f"ASSISTANT: {json.dumps(response)}")
            if any(k in response for k in ["summary", "message", "response"]):
                return {"success": True, "answer": response.get("summary") or response.get("message") or response.get("response", ""), "steps": steps_taken}

    return {"success": False, "error": "Task did not complete.", "steps": steps_taken}
