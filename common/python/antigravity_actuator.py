#!/usr/bin/env python3
"""
Antigravity IDE Actuator.

Receives prompts from Blinky Mobile and injects them directly into the
desktop Antigravity IDE chat or queues them for active sessions.
"""

import argparse
import ctypes
import json
import os
import sys
import time
from pathlib import Path

QUEUE_FILE = Path(__file__).resolve().parent.parent.parent / ".agents" / "prompt_queue.json"


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
    """Attempt to focus Antigravity IDE window and paste prompt."""
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
    parser = argparse.ArgumentParser(description="Antigravity IDE Prompt Actuator")
    parser.add_argument("--prompt", required=True, help="Prompt text to dispatch")
    args = parser.parse_args()

    prompt = args.prompt.strip()
    if not prompt:
        print("[Actuator] Empty prompt, ignoring.", file=sys.stderr)
        return

    # Attempt window activation & typing into active chat
    success = activate_and_type(prompt)
    if not success:
        # Fallback to queuing prompt for PreInvocation hook if window was not automated
        queue_prompt(prompt)


if __name__ == "__main__":
    main()
