#!/usr/bin/env python3
"""
Antigravity IDE to Blinky Bridge Script.

Invoked by Antigravity IDE Lifecycle Hooks (PreToolUse, PostToolUse, Stop, PreInvocation).
Receives event context on stdin and communicates with the Blinky Desktop server
(port 9002 HTTP loopback) to deliver notifications and real-time progress to Blinky Mobile.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BLINKY_HOOK_URL = "http://127.0.0.1:9002/hook"
QUEUE_FILE = Path(__file__).resolve().parent.parent.parent / ".agents" / "prompt_queue.json"


def post_to_blinky(payload: dict, timeout: float = 35.0) -> dict | None:
    """Send hook payload to Blinky desktop server on loopback port 9002."""
    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            BLINKY_HOOK_URL,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                return json.loads(body) if body.strip() else {}
    except Exception:
        pass
    return None


def is_auto_proceed_enabled() -> bool:
    """Check if Antigravity is configured to auto-proceed / eager execution."""
    try:
        config_path = Path.home() / ".gemini" / "config" / "config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            policy = config.get("userSettings", {}).get("autoExecutionPolicy", "")
            if policy in ("CASCADE_COMMANDS_AUTO_EXECUTION_EAGER", "always-proceed", "CASCADE_COMMANDS_AUTO_EXECUTION_ALLOW"):
                return True
    except Exception:
        pass
    return False


def format_tool_detail(tool_name: str, args: dict) -> str:
    """Produce clean human-readable progress text for mobile chatbar."""
    if tool_name == "run_command":
        cmd = args.get("CommandLine", "")
        return f"Running: {cmd[:60]}..." if len(cmd) > 60 else f"Running: {cmd}"
    elif tool_name in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
        target = args.get("TargetFile", "")
        basename = os.path.basename(target) if target else "file"
        return f"Editing {basename}"
    elif tool_name == "view_file":
        target = args.get("AbsolutePath", "")
        basename = os.path.basename(target) if target else "file"
        return f"Reading {basename}"
    elif tool_name == "grep_search":
        q = args.get("Query", "")
        return f"Searching code for '{q}'"
    elif tool_name == "ask_question":
        return "Waiting for your input..."
    elif tool_name.startswith("browser_"):
        return f"Browser: {tool_name}"
    else:
        return f"Executing {tool_name}"


def handle_pre_tool_use(data: dict) -> dict:
    """Handle PreToolUse event: stream progress and conditionally request approval."""
    tool_call = data.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    tool_args = tool_call.get("args", {})
    conv_id = data.get("conversationId", "")
    action_id = f"act-{uuid.uuid4().hex[:8]}"

    detail = format_tool_detail(tool_name, tool_args)

    # 1. Always stream real-time progress to Blinky mobile
    post_to_blinky({
        "event": "Progress",
        "tool": tool_name,
        "detail": detail,
        "conversationId": conv_id,
    }, timeout=3.0)

    # 2. Check if this action requires user approval on PC
    # In 'always-proceed' / eager mode, tools run automatically without asking on PC.
    # 'ask_question' is an interactive modal that ALWAYS requires user input.
    auto_proceed = is_auto_proceed_enabled()
    requires_approval = (tool_name == "ask_question") or (not auto_proceed)

    if not requires_approval:
        # Auto-proceed without bothering mobile with approval modal
        return {
            "decision": "allow",
            "reason": "Auto-proceed active in Antigravity",
        }

    # 3. Requires approval: prompt mobile
    payload = {
        "event": "PreToolUse",
        "actionId": action_id,
        "toolCall": tool_call,
        "conversationId": conv_id,
        "stepIdx": data.get("stepIdx", 0),
        "timestamp": int(time.time()),
    }

    result = post_to_blinky(payload, timeout=35.0)
    if result and "decision" in result:
        return {
            "decision": result["decision"],
            "reason": result.get("reason", "Decision received from Blinky mobile"),
        }

    # Fallback to desktop IDE prompt if mobile timed out
    return {
        "decision": "ask",
        "reason": "Blinky mobile review timed out or desktop bridge offline.",
    }


def handle_post_tool_use(data: dict) -> dict:
    """Handle PostToolUse event: stream tool finish."""
    err = data.get("error", "")
    post_to_blinky({
        "event": "Progress",
        "tool": "step_done",
        "detail": f"Step error: {err[:50]}" if err else "Step completed",
        "conversationId": data.get("conversationId", ""),
    }, timeout=3.0)
    return {}


def extract_final_output(data: dict) -> str:
    """Read the agent's final response content from transcript.jsonl."""
    transcript_path = data.get("transcriptPath")
    if not transcript_path or not os.path.exists(transcript_path):
        conv_id = data.get("conversationId")
        if conv_id:
            candidates = list(Path.home().glob(f".gemini/antigravity-ide/brain/{conv_id}/**/transcript.jsonl"))
            if candidates and candidates[0].exists():
                transcript_path = str(candidates[0])

    if transcript_path and os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            for line in reversed(lines):
                step = json.loads(line)
                if step.get("type") == "PLANNER_RESPONSE" and step.get("content"):
                    return step.get("content")
        except Exception:
            pass
    return ""


def handle_stop(data: dict) -> dict:
    """Handle Stop event: notify mobile of session completion with full output."""
    output_text = extract_final_output(data)
    payload = {
        "event": "Stop",
        "terminationReason": data.get("terminationReason", "model_stop"),
        "error": data.get("error", ""),
        "fullyIdle": data.get("fullyIdle", True),
        "conversationId": data.get("conversationId", ""),
        "output": output_text,
        "timestamp": int(time.time()),
    }
    post_to_blinky(payload, timeout=5.0)
    return {}


def handle_pre_invocation(data: dict) -> dict:
    """Handle PreInvocation event: inject any queued mobile prompts."""
    try:
        if QUEUE_FILE.exists():
            content = QUEUE_FILE.read_text(encoding="utf-8").strip()
            if content:
                queue_data = json.loads(content)
                prompts = queue_data.get("prompts", [])
                if prompts:
                    next_prompt = prompts.pop(0)
                    QUEUE_FILE.write_text(json.dumps({"prompts": prompts}, indent=2), encoding="utf-8")
                    return {
                        "injectSteps": [
                            {
                                "userMessage": f"[Mobile Remote]: {next_prompt}"
                            }
                        ]
                    }
    except Exception:
        pass
    return {}


def main():
    try:
        stdin_content = sys.stdin.read().strip()
        data = json.loads(stdin_content) if stdin_content else {}
    except Exception:
        data = {}

    if "toolCall" in data:
        response = handle_pre_tool_use(data)
    elif "stepIdx" in data:
        response = handle_post_tool_use(data)
    elif "terminationReason" in data:
        response = handle_stop(data)
    elif "invocationNum" in data:
        response = handle_pre_invocation(data)
    else:
        response = {}

    sys.stdout.write(json.dumps(response))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
