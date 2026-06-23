#!/usr/bin/env python3
"""End-to-end test: run computer use loop with MiMo model."""

import os
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parent / "common" / "python"
sys.path.insert(0, str(PYTHON_ROOT))

os.environ["BLINKY_AI_PROVIDER"] = "mimo"
os.environ["BLINKY_SCREENSHOT_MODE"] = "ocr"
os.environ["MIMO_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")

from computer_use.loop import run_computer_use_loop

if __name__ == "__main__":
    question = "Open firefox and search 'youtube.com'"
    print(f"Query: {question}")
    print("Running... (this may take a while)\n")

    result = run_computer_use_loop(question, max_calls=10)

    print(f"\nSuccess: {result.get('success')}")
    print(f"Answer: {result.get('answer', 'N/A')}")
    print(f"Error: {result.get('error', 'None')}")
    print(f"Steps: {len(result.get('steps', []))}")
    for i, step in enumerate(result.get("steps", [])):
        print(f"  Step {i+1}: {step.get('message','')[:120]} | success={step.get('success')}")
