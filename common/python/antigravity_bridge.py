#!/usr/bin/env python3
"""
Antigravity IDE to Blinky Bridge Script.

Invoked by Antigravity IDE Lifecycle Hooks (PostToolUse, Stop, PreInvocation).
Streams real-time progress and completed assistant output to Blinky Mobile.
NEVER emits or requests approval dialogs.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BLINKY_HOOK_URL = "http://127.0.0.1:9002/hook"
QUEUE_FILE = Path(__file__).resolve().parent.parent.parent / ".agents" / "prompt_queue.json"
DEBUG_LOG = Path(__file__).resolve().parent / "bridge_debug.log"


def log_debug(msg: str):
    """Append debug logs for hook activity."""
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def post_to_blinky(payload: dict, timeout: float = 0.5) -> dict | None:
    """Send hook payload to Blinky desktop server on loopback port 9002 (fast, non-blocking)."""
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
        return "Waiting for user input..."
    elif tool_name.startswith("browser_"):
        return f"Browser: {tool_name}"
    else:
        return f"Executing {tool_name}"


def handle_pre_tool_use(data: dict) -> dict:
    """Handle PreToolUse event: NEVER ask for approval, always allow immediately."""
    tool_call = data.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    tool_args = tool_call.get("args", {})
    conv_id = data.get("conversationId", "")

    detail = format_tool_detail(tool_name, tool_args)

    # Stream real-time progress to Blinky mobile chatbar
    post_to_blinky({
        "event": "Progress",
        "tool": tool_name,
        "detail": detail,
        "conversationId": conv_id,
    }, timeout=0.3)

    # UNCONDITIONALLY ALLOW. Do NOT ask, do NOT prompt, do NOT pop up dialogs.
    return {
        "decision": "allow",
        "reason": "Auto-allowed by Blinky bridge",
    }


def handle_post_tool_use(data: dict) -> dict:
    """Handle PostToolUse event: stream step finish to Blinky mobile."""
    err = data.get("error", "")
    conv_id = data.get("conversationId", "")
    post_to_blinky({
        "event": "Progress",
        "tool": "step_done",
        "detail": f"Step error: {err[:50]}" if err else "Step completed",
        "conversationId": conv_id,
    }, timeout=0.3)
    return {}


def extract_final_output(data: dict) -> str:
    """Read the assistant's final response content from transcript.jsonl."""
    transcript_path = data.get("transcriptPath")
    
    if not transcript_path or not os.path.exists(transcript_path):
        conv_id = data.get("conversationId")
        candidates = []
        if conv_id:
            for app_dir in ["antigravity-ide", "antigravity", "antigravity-cli"]:
                p = Path.home() / ".gemini" / app_dir / "brain" / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
                if p.exists():
                    candidates.append(p)
        
        if not candidates:
            brain_roots = [
                Path.home() / ".gemini" / "antigravity-ide" / "brain",
                Path.home() / ".gemini" / "antigravity" / "brain",
            ]
            for root in brain_roots:
                if root.exists():
                    for t in root.glob("*/.system_generated/logs/transcript.jsonl"):
                        candidates.append(t)
            candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

        if candidates:
            transcript_path = str(candidates[0])

    if transcript_path and os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            for line in reversed(lines):
                step = json.loads(line)
                if step.get("type") == "PLANNER_RESPONSE":
                    content = (step.get("content") or "").strip()
                    if content:
                        return content
        except Exception as exc:
            log_debug(f"extract_final_output read error: {exc}")
    return ""


def handle_stop(data: dict) -> dict:
    """Handle Stop event: notify mobile of session completion with full output."""
    output_text = extract_final_output(data)
    log_debug(f"Stop event: extracted output length={len(output_text)}")
    payload = {
        "event": "Stop",
        "terminationReason": data.get("terminationReason", "model_stop"),
        "error": data.get("error", ""),
        "fullyIdle": data.get("fullyIdle", True),
        "conversationId": data.get("conversationId", ""),
        "output": output_text,
        "timestamp": int(time.time()),
    }
    post_to_blinky(payload, timeout=3.0)
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
                    log_debug(f"PreInvocation injecting prompt: {next_prompt}")
                    return {
                        "injectSteps": [
                            {
                                "userMessage": f"[Mobile Remote]: {next_prompt}"
                            }
                        ]
                    }
    except Exception as exc:
        log_debug(f"PreInvocation error: {exc}")
    return {}


def main():
    try:
        stdin_content = sys.stdin.read().strip()
        data = json.loads(stdin_content) if stdin_content else {}
    except Exception as exc:
        log_debug(f"Failed to parse stdin: {exc}")
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
