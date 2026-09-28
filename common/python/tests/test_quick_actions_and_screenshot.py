import sys
from pathlib import Path

_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import time
import pytest
from main import classify_request, run, run_screenshot_tool, run_esp32_light_tool
from tools.esp32_light_tool import resolve_esp32_light_request


def test_screenshot_classification():
    queries = [
        "capture screenshot",
        "take a screenshot",
        "Take a screenshot of the desktop",
        "capture current pc screen",
        "take screenshot",
        "pc screenshot",
        "screenshot",
    ]
    for q in queries:
        res = classify_request(q, None, [])
        assert res["intent"] == "SCREENSHOT", f"Expected SCREENSHOT for '{q}', got {res['intent']}"
        assert res["needs_screen"] is False, f"needs_screen must be False for '{q}'"


def test_esp32_light_classification():
    queries = [
        "toggle smart lights",
        "turn on red light",
        "turn off light",
        "lights off",
        "switch on the lights",
        "make light blue",
        "dim lights to 50",
    ]
    for q in queries:
        res = classify_request(q, None, [])
        assert res["intent"] == "ESP32_LIGHT", f"Expected ESP32_LIGHT for '{q}', got {res['intent']}"
        assert res["needs_screen"] is False, f"needs_screen must be False for '{q}'"


def test_media_queries_not_hijacked_by_lights():
    media_queries = [
        "play blinding lights in spotify",
        "play blinding lights on spotify",
        "play spotify blinding lights",
        "play street lights by kanye west",
        "play green light by lorde on youtube",
    ]
    for q in media_queries:
        match = resolve_esp32_light_request(q)
        assert match is None, f"Query '{q}' should NOT match esp32 light tool"


def test_screenshot_tool_execution_fast_and_zero_ocr():
    warnings = []
    start = time.perf_counter()
    res = run_screenshot_tool(start, warnings)
    elapsed = (time.perf_counter() - start) * 1000

    assert res["summary"] == "Captured screenshot of current PC screen."
    assert res["steps"] == []
    assert res["ocr"]["count"] == 0
    assert len(res["ocr"]["items"]) == 0
    assert bool(res.get("screenshot_b64")), "screenshot_b64 must be present and non-empty"
    assert len(res["screenshot_b64"]) > 1000
    assert res["is_continuation"] is False


def test_esp32_light_tool_execution_zero_ocr():
    warnings = []
    start = time.perf_counter()
    res = run_esp32_light_tool({"action": "toggle"}, start, warnings)
    assert res["steps"] == []
    assert res["ocr"]["count"] == 0
    assert len(res["ocr"]["items"]) == 0
    assert res["is_continuation"] is False


def test_esp32_light_toggle_on_and_off():
    from tools.esp32_light_tool import handle_request, get_saved_state, save_state

    # Ensure baseline state off
    save_state(on=False, r=0, g=0, b=0)
    
    # First toggle: should turn on
    res1 = handle_request({"action": "toggle"})
    assert res1.get("r", 0) > 0 or res1.get("g", 0) > 0 or res1.get("b", 0)
    assert "on" in res1["message"].lower()
    assert get_saved_state()["on"] is True

    # Second toggle (pressing again): must turn off!
    res2 = handle_request({"action": "toggle"})
    assert res2.get("r", 0) == 0 and res2.get("g", 0) == 0 and res2.get("b", 0) == 0
    assert "off" in res2["message"].lower()
    assert get_saved_state()["on"] is False


def test_attached_image_gemini_vision_fast_path():
    import io
    import base64
    from PIL import Image

    img = Image.new("RGB", (100, 100), color="purple")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    res = run("what color is this?", attached_image=b64)
    assert res["steps"] == []
    assert res["screenshot_b64"] == b64
    assert res["computer_use"] is True
    assert "purple" in res["summary"].lower() or "violet" in res["summary"].lower()

