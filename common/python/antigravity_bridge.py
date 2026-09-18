#!/usr/bin/env python3
"""
Antigravity IDE to Blinky Bridge Script.

Invoked by Antigravity IDE Lifecycle Hooks (PreToolUse, Stop, PreInvocation).
Receives event context on stdin and communicates with the Blinky Desktop server
(port 9002 HTTP loopback) to deliver notifications to Blinky Mobile.
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
    except Exception as exc:
        # Blinky desktop server might not be running or timed out
        pass
    return None


def handle_pre_tool_use(data: dict) -> dict:
    """Handle PreToolUse event: request approval from mobile."""
    tool_call = data.get("toolCall", {})
    action_id = f"act-{uuid.uuid4().hex[:8]}"

    payload = {
        "event": "PreToolUse",
        "actionId": action_id,
        "toolCall": tool_call,
        "conversationId": data.get("conversationId", ""),
        "stepIdx": data.get("stepIdx", 0),
        "timestamp": int(time.time()),
    }

    result = post_to_blinky(payload, timeout=35.0)
    if result and "decision" in result:
        return {
            "decision": result["decision"],
            "reason": result.get("reason", "Decision received from Blinky mobile"),
        }

    # Default fallback: ask user on desktop IDE if mobile did not respond or bridge is offline
    return {
        "decision": "ask",
        "reason": "Blinky mobile review timed out or desktop bridge offline.",
    }


def handle_stop(data: dict) -> dict:
    """Handle Stop event: notify mobile of session completion."""
    payload = {
        "event": "Stop",
        "terminationReason": data.get("terminationReason", "model_stop"),
        "error": data.get("error", ""),
        "fullyIdle": data.get("fullyIdle", True),
        "conversationId": data.get("conversationId", ""),
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

    # Identify hook event type based on payload keys
    if "toolCall" in data:
        response = handle_pre_tool_use(data)
    elif "terminationReason" in data:
        response = handle_stop(data)
    elif "invocationNum" in data:
        response = handle_pre_invocation(data)
    else:
        # Unknown event type, return clean empty dict
        response = {}

    sys.stdout.write(json.dumps(response))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
