#!/usr/bin/env python3
"""
ESP32 RGB Light Controller Tool for Blinky and Antigravity.
Controls RGB LED strip/diode connected to ESP32 over local Wi-Fi.
ESP32 IP: 192.168.1.4 (configurable via ESP32_LIGHT_IP env var).
"""

import sys
import os
import json
import urllib.request
import urllib.error
from pathlib import Path

def _get_default_ip():
    if "ESP32_HOST" in os.environ:
        return os.environ["ESP32_HOST"]
    if "ESP32_LIGHT_IP" in os.environ:
        return os.environ["ESP32_LIGHT_IP"]
    env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ESP32_HOST=") or line.startswith("ESP32_LIGHT_IP="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    return "192.168.1.4"

DEFAULT_ESP32_IP = _get_default_ip()


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


def send_to_esp32(r: int, g: int, b: int, ip: str = DEFAULT_ESP32_IP, timeout: float = 3.0) -> dict:
    """Send RGB values to ESP32 /set endpoint."""
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))

    # Try /rgb first (Universal Daemon), fallback to /set (Legacy Sketch)
    endpoints = [f"http://{ip}/rgb?r={r}&g={g}&b={b}", f"http://{ip}/set?r={r}&g={g}&b={b}"]
    last_err = None
    for url in endpoints:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8").strip()
                return {
                    "success": True,
                    "status": "ok",
                    "ip": ip,
                    "r": r,
                    "g": g,
                    "b": b,
                    "esp32_response": body,
                    "message": f"Light set to RGB({r}, {g}, {b})",
                }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            last_err = e
        except Exception as e:
            last_err = e
            break

    return {
        "success": False,
        "error": f"Failed to connect to ESP32 at {ip}: {last_err}",
        "ip": ip,
    }


def check_status(ip: str = DEFAULT_ESP32_IP, timeout: float = 2.0) -> dict:

    """Check if ESP32 web server is reachable."""
    url = f"http://{ip}/"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8").strip()
            return {
                "success": True,
                "online": True,
                "ip": ip,
                "esp32_response": body,
            }
    except Exception as e:
        return {
            "success": False,
            "online": False,
            "ip": ip,
            "error": str(e),
        }


def resolve_color(color_name: str, r=None, g=None, b=None, brightness: float = 1.0):
    """Resolve color input to RGB values with optional brightness (0.0 to 1.0)."""
    color_clean = str(color_name or "").strip().lower().replace(" ", "_")

    if r is not None and g is not None and b is not None:
        target_r, target_g, target_b = int(r), int(g), int(b)
    elif color_clean in COLOR_MAP:
        target_r, target_g, target_b = COLOR_MAP[color_clean]
    elif "off" in color_clean:
        target_r, target_g, target_b = 0, 0, 0
    else:
        # Default fallback
        target_r, target_g, target_b = 255, 255, 255

    # Apply brightness if provided
    brightness = max(0.0, min(1.0, float(brightness)))
    final_r = int(target_r * brightness)
    final_g = int(target_g * brightness)
    final_b = int(target_b * brightness)

    return final_r, final_g, final_b


def handle_request(params: dict) -> dict:
    action = params.get("action", "set_color")
    ip = params.get("ip", DEFAULT_ESP32_IP)

    if action == "status":
        return check_status(ip=ip)

    if action in ("turn_off", "off"):
        return send_to_esp32(0, 0, 0, ip=ip)

    color = params.get("color", "")
    r = params.get("r")
    g = params.get("g")
    b = params.get("b")
    brightness = params.get("brightness", 1.0)

    # Convert brightness from percentage (e.g. 50 or 0.5)
    if isinstance(brightness, (int, float)) and brightness > 1.0:
        brightness = brightness / 100.0

    final_r, final_g, final_b = resolve_color(color, r, g, b, brightness)
    res = send_to_esp32(final_r, final_g, final_b, ip=ip)
    res["color_requested"] = color or f"RGB({final_r},{final_g},{final_b})"
    return res


def resolve_light_request(question: str) -> dict | None:
    """Fast-path resolution for light commands."""
    import re
    q = question.strip().lower()
    q_clean = re.sub(r"[?!.,;:']", "", q)

    # Check for off commands first
    if (
        re.search(r"\b(turn|switch|shut)\s+(off|down)\b.*\b(light|led)s?\b", q_clean)
        or re.search(r"\b(light|led)s?\b.*\b(turn|switch|shut)?\s*off\b", q_clean)
        or q_clean in ("lights off", "light off", "turn off light", "turn off lights")
    ):
        return {"action": "turn_off"}

    is_light_mention = bool(re.search(r"\b(light|led)s?\b", q_clean))
    found_color = None
    for color_name in sorted(COLOR_MAP.keys(), key=lambda x: -len(x)):
        if color_name in ("off", "black"):
            continue
        c_pat = color_name.replace("_", " ")
        if re.search(r"\b" + re.escape(c_pat) + r"\b", q_clean):
            found_color = color_name
            break

    if is_light_mention:
        brightness = 1.0
        pct_match = re.search(r"(\d{1,3})\s*%", q_clean)
        if pct_match:
            brightness = float(pct_match.group(1)) / 100.0

        if (
            re.search(r"\b(turn|switch)\s+on\b", q_clean)
            or re.search(r"\b(set|change|make|dim|brighten)\b", q_clean)
            or found_color
            or q_clean in ("lights on", "light on", "turn on light", "turn on lights")
        ):
            return {
                "action": "set_color",
                "color": found_color or "white",
                "brightness": brightness,
            }

    if found_color and ("light" in q_clean or "led" in q_clean):
        return {
            "action": "set_color",
            "color": found_color,
            "brightness": 1.0,
        }

    return None


def main():

    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Usage: python esp32_light_tool.py '<json_input>' or python esp32_light_tool.py <color>"
        }))
        sys.exit(1)

    arg = sys.argv[1].strip()
    if arg.startswith("{"):
        try:
            params = json.loads(arg)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON input: {e}"}))
            sys.exit(1)
    else:
        # Simple color or command passed directly
        params = {"color": arg}

    result = handle_request(params)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
