#!/usr/bin/env python3
"""
Antigravity IDE Actuator & Real-time Transcript Watcher.

Receives prompts from Blinky Mobile, injects them directly into the
desktop Antigravity IDE chat without disrupting the window or closing the chatbar,
and monitors transcript.jsonl to stream live progress and the final assistant response
back to Blinky Mobile.
"""

import argparse
import ctypes
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BLINKY_HOOK_URL = "http://127.0.0.1:9003/hook"
QUEUE_FILE = Path(__file__).resolve().parent.parent.parent / ".agents" / "prompt_queue.json"


def post_to_blinky(payload: dict, timeout: float = 2.0) -> dict | None:
    """Send hook payload to Blinky desktop server on loopback port 9003."""
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


def find_active_transcript() -> Path | None:
    """Find the most recently updated transcript.jsonl across all Antigravity brain directories."""
    roots = [
        Path.home() / ".gemini" / "antigravity-ide" / "brain",
        Path.home() / ".gemini" / "antigravity" / "brain",
    ]
    candidates = []
    for r in roots:
        if r.exists():
            for f in r.glob("*/.system_generated/logs/transcript.jsonl"):
                try:
                    candidates.append((f.stat().st_mtime, f))
                except Exception:
                    pass
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def format_tool_detail(tool_name: str, args: dict) -> str:
    """Produce clean human-readable progress text for mobile chatbar."""
    if tool_name == "run_command":
        cmd = args.get("CommandLine", "")
        return f"Running: {cmd[:50]}..." if len(cmd) > 50 else f"Running: {cmd}"
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


def watch_transcript_for_completion(transcript_path: Path, start_line_count: int, max_wait: float = 180.0):
    """Monitor transcript.jsonl for progress and the final assistant response."""
    start_time = time.time()
    seen_lines = start_line_count

    # Notify mobile that prompt was submitted
    post_to_blinky({
        "event": "Progress",
        "tool": "antigravity",
        "detail": "Antigravity received prompt, thinking...",
    })

    while time.time() - start_time < max_wait:
        time.sleep(0.4)
        if not transcript_path.exists():
            continue

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                all_lines = [l.strip() for l in f if l.strip()]
        except Exception:
            continue

        if len(all_lines) > seen_lines:
            new_lines = all_lines[seen_lines:]
            seen_lines = len(all_lines)

            for raw in new_lines:
                try:
                    step = json.loads(raw)
                except Exception:
                    continue

                step_type = step.get("type", "")

                # Check for tool execution progress
                if step_type == "PLANNER_RESPONSE":
                    tool_calls = step.get("tool_calls", [])
                    if tool_calls:
                        for tc in tool_calls:
                            name = tc.get("name", "")
                            args = tc.get("args", {})
                            detail = format_tool_detail(name, args)
                            post_to_blinky({
                                "event": "Progress",
                                "tool": name,
                                "detail": detail,
                            })

                    # Check for final completed response text
                    content = (step.get("content") or "").strip()
                    if content and not tool_calls:
                        # Completed! Emit Stop with output to Blinky mobile
                        print(f"[Actuator] Found final response (length={len(content)}), notifying Blinky.")
                        post_to_blinky({
                            "event": "Stop",
                            "output": content,
                            "terminationReason": "model_stop",
                        }, timeout=5.0)
                        return

        # If transcript stopped changing and the last step was a PLANNER_RESPONSE with content
        if time.time() - start_time > 3.0 and all_lines:
            try:
                last_step = json.loads(all_lines[-1])
                if last_step.get("type") == "PLANNER_RESPONSE":
                    content = (last_step.get("content") or "").strip()
                    tool_calls = last_step.get("tool_calls", [])
                    if content and not tool_calls:
                        print(f"[Actuator] Session idle with final response (length={len(content)}).")
                        post_to_blinky({
                            "event": "Stop",
                            "output": content,
                            "terminationReason": "model_stop",
                        }, timeout=5.0)
                        return
            except Exception:
                pass


def queue_prompt(prompt: str) -> None:
    """Queue prompt for in-flight Antigravity PreInvocation injection."""
    try:
        QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        prompts = []
        if QUEUE_FILE.exists():
            try:
                data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
                prompts = data.get("prompts", [])
            except Exception:
                prompts = []
        prompts.append(prompt)
        QUEUE_FILE.write_text(json.dumps({"prompts": prompts}, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[Actuator] Failed to queue prompt: {exc}", file=sys.stderr)


def activate_and_type(prompt: str) -> bool:
    """Attempt to focus Antigravity IDE window and paste prompt without un-maximizing."""
    if os.name != "nt":
        return False

    try:
        import psutil
        import win32clipboard
        import win32con
        import win32gui
        from pywinauto.keyboard import send_keys

        user32 = ctypes.windll.user32

        # 1. Locate Antigravity IDE processes
        target_pids = set()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = p.info["name"].lower()
                if "antigravity" in name:
                    target_pids.add(p.info["pid"])
            except Exception:
                continue

        if not target_pids:
            print("[Actuator] No running Antigravity IDE process found.", file=sys.stderr)
            return False

        # 2. Find matching top-level visible window
        found_hwnd = None

        def enum_cb(hwnd, _):
            nonlocal found_hwnd
            if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                pid_val = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
                if pid_val.value in target_pids:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        found_hwnd = hwnd
                        return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        if not found_hwnd:
            print("[Actuator] Antigravity IDE window not found or minimized.", file=sys.stderr)
            return False

        # 3. Bring window to foreground without resizing, un-maximizing, or moving
        if user32.IsIconic(found_hwnd):
            user32.ShowWindow(found_hwnd, win32con.SW_SHOW)
        user32.SetForegroundWindow(found_hwnd)
        time.sleep(0.15)

        # 4. Copy prompt to clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(prompt, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()

        # 5. Paste prompt and send Enter (do NOT press Ctrl+L, which closes an already open chatbar)
        send_keys("^v")
        time.sleep(0.1)
        send_keys("{ENTER}")
        print(f"[Actuator] Successfully sent prompt to Antigravity IDE: {prompt[:40]}...")
        return True

    except Exception as exc:
        print(f"[Actuator] Error automating window: {exc}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Antigravity IDE Prompt Actuator & Watcher")
    parser.add_argument("--prompt", required=True, help="Prompt text to dispatch")
    args = parser.parse_args()

    prompt = args.prompt.strip()
    if not prompt:
        print("[Actuator] Empty prompt, ignoring.", file=sys.stderr)
        return

    # Snapshot active transcript before sending prompt
    active_t = find_active_transcript()
    initial_count = 0
    if active_t and active_t.exists():
        try:
            with open(active_t, "r", encoding="utf-8") as f:
                initial_count = len([l for l in f if l.strip()])
        except Exception:
            pass

    # Attempt window activation & typing into active chat
    success = activate_and_type(prompt)
    if not success:
        queue_prompt(prompt)
        return

    # Watch transcript to stream progress and deliver the final response to mobile
    if active_t:
        watch_transcript_for_completion(active_t, initial_count)


if __name__ == "__main__":
    main()
