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


def _state_file() -> Path:
    # Persist toggle state in repo-root tmp/ (tools -> python -> common -> root).
    # Falls back to module dir when repo layout is unavailable.
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        if (repo_root / "common" / "python").is_dir():
            state_dir = repo_root / "tmp"
        else:
            state_dir = Path(__file__).resolve().parent
        state_dir.mkdir(parents=True, exist_ok=True)
        new_path = state_dir / "esp32_light_state.json"
        if not new_path.exists():
            # One-time migration from the previous common/tmp location.
            legacy = repo_root / "common" / "tmp" / "esp32_light_state.json"
            try:
                if legacy.exists():
                    new_path.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        return new_path
    except Exception:
        return Path(__file__).resolve().parent / "esp32_light_state.json"


def get_saved_state() -> dict:
    """Return last known light state. Defaults to off."""
    default = {"on": False, "r": 0, "g": 0, "b": 0, "color": "off", "brightness": 1.0}
    try:
        p = _state_file()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
            return {**default, **data}
    except Exception:
        pass
    return default


def save_state(on: bool, r: int = 0, g: int = 0, b: int = 0, color: str = "", brightness: float = 1.0) -> dict:
    """Persist last known light state (preserves last_host)."""
    prev = get_saved_state()
    state = {"on": bool(on), "r": int(r), "g": int(g), "b": int(b), "color": str(color), "brightness": float(brightness)}
    if prev.get("last_host"):
        state["last_host"] = prev["last_host"]
    try:
        _state_file().write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass
    return state


def note_good_host(host: str) -> None:
    """Remember the host that just answered so the next tap tries it first."""
    try:
        state = get_saved_state()
        if state.get("last_host") == host:
            return
        state["last_host"] = host
        _state_file().write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def _candidate_hosts(configured_ip: str) -> list[str]:
    """Fast-first host order: last-known-good, configured .env IP, mDNS name."""
    hosts: list[str] = []
    try:
        last = (get_saved_state().get("last_host") or "").strip()
        if last:
            hosts.append(last)
    except Exception:
        pass
    if configured_ip not in hosts:
        hosts.append(configured_ip)
    mdns = "blinky-esp32.local"
    if mdns not in hosts:
        hosts.append(mdns)
    return hosts


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


def send_to_esp32(r: int, g: int, b: int, ip: str = DEFAULT_ESP32_IP, timeout: float = 1.5) -> dict:
    """Send RGB values to ESP32 /rgb endpoint (firmware: BlinkyUniversalDaemon).

    Fast-first: tries the last-known-good host, then the configured IP, then
    mDNS. Short timeout because a healthy daemon answers in milliseconds;
    a wedged/offline one never answers, so fail fast and move on.
    """
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))

    hosts = _candidate_hosts(ip)

    last_err = None
    for host in hosts:
        # Universal Daemon serves /rgb (legacy /set kept as fallback).
        endpoints = [f"http://{host}/rgb?r={r}&g={g}&b={b}", f"http://{host}/set?r={r}&g={g}&b={b}"]
        for url in endpoints:
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    body = response.read().decode("utf-8").strip()
                    note_good_host(host)
                    return {
                        "success": True,
                        "status": "ok",
                        "ip": host,
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
        "error": f"Failed to connect to ESP32 at {ip} (tried {', '.join(hosts)}): {last_err}. Check serial monitor IP matches ESP32_HOST in .env.",
        "ip": ip,
    }


def check_status(ip: str = DEFAULT_ESP32_IP, timeout: float = 2.0) -> dict:

    """Check if ESP32 web server is reachable (tries mDNS fallback too)."""
    hosts = [ip] if ip == "blinky-esp32.local" else [ip, "blinky-esp32.local"]
    last_err: Exception | None = None
    for host in hosts:
        url = f"http://{host}/"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8").strip()
                return {
                    "success": True,
                    "online": True,
                    "ip": host,
                    "esp32_response": body,
                }
        except Exception as e:
            last_err = e
            continue
    return {
        "success": False,
        "online": False,
        "ip": ip,
        "error": str(last_err),
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
        res = send_to_esp32(0, 0, 0, ip=ip)
        if res.get("success"):
            save_state(on=False, r=0, g=0, b=0, color="off")
            res["message"] = "Light turned off."
        return res

    if action in ("turn_on", "on"):
        saved = get_saved_state()
        r, g, b = saved.get("r", 0), saved.get("g", 0), saved.get("b", 0)
        color = saved.get("color", "")
        if (r, g, b) == (0, 0, 0):
            r, g, b, color = 255, 255, 255, color or "white"
        res = send_to_esp32(r, g, b, ip=ip)
        if res.get("success"):
            save_state(on=True, r=r, g=g, b=b, color=color or "white")
            res["message"] = f"Light turned on ({color or f'RGB({r},{g},{b})'})."
        return res

    if action == "toggle":
        saved = get_saved_state()
        if saved.get("on"):
            res = send_to_esp32(0, 0, 0, ip=ip)
            if res.get("success"):
                save_state(on=False, r=0, g=0, b=0, color="off")
                res["message"] = "Light turned off."
            return res
        # Turn on: restore last color or default to warm white
        r, g, b = saved.get("r", 0), saved.get("g", 0), saved.get("b", 0)
        color = saved.get("color", "")
        if (r, g, b) == (0, 0, 0):
            r, g, b, color = 255, 255, 255, "white"
        res = send_to_esp32(r, g, b, ip=ip)
        if res.get("success"):
            save_state(on=True, r=r, g=g, b=b, color=color)
            res["message"] = f"Light turned on ({color})."
        return res

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
    if res.get("success"):
        is_on = not (final_r == 0 and final_g == 0 and final_b == 0)
        save_state(on=is_on, r=final_r, g=final_g, b=final_b, color=color or f"RGB({final_r},{final_g},{final_b})", brightness=brightness)
    res["color_requested"] = color or f"RGB({final_r},{final_g},{final_b})"
    return res


def resolve_light_request(question: str) -> dict | None:
    """Fast-path resolution for light commands."""
    import re
    q = question.strip().lower()
    q_clean = re.sub(r"[?!.,;:']", "", q)

    # Never hijack media playback ("play ... lights ..." song titles).
    if re.search(r"\bplay\b", q_clean) and re.search(r"\b(spotify|youtube|song|music|track|artist|album|playlist)\b", q_clean):
        return None

    # Check for off commands first
    if (
        re.search(r"\b(turn|switch|shut)\s+(off|down)\b.*\b(light|led)s?\b", q_clean)
        or re.search(r"\b(light|led)s?\b.*\b(turn|switch|shut)?\s*off\b", q_clean)
        or q_clean in ("lights off", "light off", "turn off light", "turn off lights")
    ):
        return {"action": "turn_off"}

    # Toggle / turn-on bare commands (quick-action buttons send these)
    if re.search(r"\btoggle\b.*\b(light|led)s?\b", q_clean) or re.search(r"\b(light|led)s?\b.*\btoggle\b", q_clean):
        return {"action": "toggle"}
    if q_clean in ("toggle lights", "toggle light", "toggle_lights", "lights", "toggle"):
        return {"action": "toggle"}

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
        res = handle_request({"action": "status"})
        print(json.dumps(res, indent=2))
        return

    arg = sys.argv[1].strip()
    if arg.startswith("{"):
        try:
            params = json.loads(arg)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON input: {e}"}))
            sys.exit(1)
    else:
        # Bare CLI word from the Rust quick-action sidecar or manual use.
        # Map control words to actions (NOT colors) so `toggle` actually toggles.
        arg_lower = arg.lower()
        if arg_lower in COLOR_MAP:
            params = {"action": "set_color", "color": arg_lower}
        elif arg_lower in {"on", "off", "toggle", "status"}:
            params = {"action": arg_lower}
        elif arg_lower in {"turn_on", "turn_off"}:
            params = {"action": arg_lower}
        else:
            resolved = resolve_light_request(arg)
            params = resolved if resolved else {"color": arg}

    result = handle_request(params)
    print(json.dumps(result, indent=2))


resolve_esp32_light_request = resolve_light_request


if __name__ == "__main__":
    main()
