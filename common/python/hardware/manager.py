#!/usr/bin/env python3
"""
Blinky Universal Hardware Manager.
Provides Zero-Flash dynamic hardware execution and natural language device mapping.
"""

import os
import sys
import json
import re
from pathlib import Path

_HARDWARE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = _HARDWARE_DIR / "device_registry.json"

if str(_HARDWARE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_HARDWARE_DIR.parent))

from hardware.esp32_client import ESP32Client

COLOR_MAP = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "purple": (180, 0, 255),
    "pink": (255, 20, 147),
    "orange": (255, 100, 0),
    "white": (255, 255, 255),
    "warm_white": (255, 180, 100),
    "off": (0, 0, 0),
    "black": (0, 0, 0),
}


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_registry(registry: dict):
    try:
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
    except Exception:
        pass


def resolve_hardware_command(question: str) -> dict | None:
    """Fast natural language parser for any registered hardware device."""
    q = question.strip().lower()
    q_clean = re.sub(r"[?!.,;:']", "", q)
    registry = load_registry()

    # 1. Check if user is trying to configure a new device
    # e.g., "I connected a servo on pin 18 named door lock" or "add buzzer on pin 19"
    cfg_match = re.search(r"\b(?:connect(?:ed)?|add(?:ed)?)\s+(?:a|an)?\s*(?P<type>servo|relay|rgb|light|buzzer|motor|sensor)\s+(?:on|to)\s+pin\s+(?P<pin>\d+)(?:\s+(?:named|called)\s+(?P<name>[a-zA-Z0-9_ -]+))?", q_clean)
    if cfg_match:
        dev_type = cfg_match.group("type")
        pin = int(cfg_match.group("pin"))
        name = (cfg_match.group("name") or dev_type).strip().replace(" ", "_")
        return {
            "action": "configure_device",
            "name": name,
            "type": dev_type,
            "pin": pin,
        }

    # 2. Check for Servo actions (door, gate, arm, lock, open, close)
    for dev_id, dev in registry.items():
        if dev.get("type") == "servo":
            triggers = dev.get("triggers", [dev_id])
            if any(t in q_clean for t in triggers):
                # Check for explicit angle (e.g., "set door to 45 degrees")
                angle_match = re.search(r"(\d{1,3})\s*(?:deg|degree|degrees)?", q_clean)
                angle = None
                if "open" in q_clean or "unlock" in q_clean:
                    angle = dev.get("positions", {}).get("open", 90)
                elif "close" in q_clean or "lock" in q_clean:
                    angle = dev.get("positions", {}).get("close", 0)
                elif angle_match and not ("turn on" in q_clean):
                    candidate = int(angle_match.group(1))
                    if 0 <= candidate <= 180:
                        angle = candidate

                if angle is not None:
                    return {
                        "action": "servo",
                        "device": dev_id,
                        "pin": dev.get("pin", 18),
                        "angle": angle,
                        "description": f"Moving {dev_id} to {angle} degrees",
                    }

    # 3. Check for Tone/Buzzer actions (beep, buzz, alarm, siren)
    for dev_id, dev in registry.items():
        if dev.get("type") == "tone":
            triggers = dev.get("triggers", [dev_id])
            if any(t in q_clean for t in triggers):
                return {
                    "action": "tone",
                    "device": dev_id,
                    "pin": dev.get("pin", 19),
                    "freq": 1200,
                    "duration": 400,
                    "description": f"Sounding alert on {dev_id}",
                }

    # 4. Check for Digital Write (relay, switch, fan, plug)
    for dev_id, dev in registry.items():
        if dev.get("type") in ("relay", "switch", "digital"):
            triggers = dev.get("triggers", [dev_id])
            if any(t in q_clean for t in triggers):
                val = 0 if any(w in q_clean for w in ["off", "stop", "disable"]) else 1
                return {
                    "action": "digital_write",
                    "device": dev_id,
                    "pin": dev.get("pin"),
                    "val": val,
                    "description": f"Setting {dev_id} to {'ON' if val else 'OFF'}",
                }

    # 5. Check for RGB Light actions
    for dev_id, dev in registry.items():
        if dev.get("type") == "rgb":
            triggers = dev.get("triggers", [dev_id, "light", "lights"])
            if any(t in q_clean for t in triggers):
                # Is it turn off?
                if any(w in q_clean for w in ["off", "shut", "kill"]):
                    return {
                        "action": "rgb",
                        "device": dev_id,
                        "r": 0, "g": 0, "b": 0,
                        "description": "Turning off light",
                    }
                # Color search
                found_color = None
                for c_name in sorted(COLOR_MAP.keys(), key=lambda x: -len(x)):
                    if c_name in ("off", "black"):
                        continue
                    if re.search(r"\b" + re.escape(c_name.replace("_", " ")) + r"\b", q_clean):
                        found_color = c_name
                        break
                r, g, b = COLOR_MAP.get(found_color or "white", (255, 255, 255))
                return {
                    "action": "rgb",
                    "device": dev_id,
                    "r": r, "g": g, "b": b,
                    "description": f"Setting {dev_id} to {found_color or 'white'}",
                }

    return None


def execute_hardware_command(params: dict) -> dict:
    """Executes the command against the ESP32 Universal Micro-Daemon."""
    client = ESP32Client()
    action = params.get("action")

    if action == "configure_device":
        registry = load_registry()
        dev_id = params["name"]
        registry[dev_id] = {
            "name": dev_id,
            "type": params["type"],
            "pin": params["pin"],
            "triggers": [dev_id.replace("_", " "), params["type"]],
        }
        save_registry(registry)
        return {
            "success": True,
            "message": f"Successfully registered {params['type']} '{dev_id}' on GPIO {params['pin']}. You can now control it with voice!",
        }

    if action == "servo":
        pin = params.get("pin", 18)
        angle = params.get("angle", 90)
        res = client.set_servo(pin, angle)
        return {
            "success": res.get("status") == "ok",
            "message": f"Servo on pin {pin} moved to {angle}°",
            "details": res,
        }

    if action == "tone":
        pin = params.get("pin", 19)
        freq = params.get("freq", 1200)
        duration = params.get("duration", 400)
        res = client.play_tone(pin, freq, duration)
        return {
            "success": res.get("status") == "ok",
            "message": f"Buzzer on pin {pin} sounded ({freq}Hz for {duration}ms)",
            "details": res,
        }

    if action == "digital_write":
        pin = params.get("pin")
        val = params.get("val", 1)
        res = client.digital_write(pin, val)
        return {
            "success": res.get("status") == "ok",
            "message": f"Pin {pin} switched to {'HIGH' if val else 'LOW'}",
            "details": res,
        }

    if action == "rgb":
        r = params.get("r", 255)
        g = params.get("g", 255)
        b = params.get("b", 255)
        res = client.set_rgb(r, g, b)
        return {
            "success": res.get("status") == "ok",
            "message": f"Light set to RGB({r}, {g}, {b})",
            "details": res,
        }

    return {"success": False, "message": f"Unknown hardware action: {action}"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python manager.py '<natural_language_or_json>'"}))
        sys.exit(1)

    query = sys.argv[1].strip()
    if query.startswith("{"):
        params = json.loads(query)
    else:
        params = resolve_hardware_command(query)
        if not params:
            print(json.dumps({"error": f"Could not match '{query}' to any registered hardware device."}))
            sys.exit(1)

    result = execute_hardware_command(params)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
