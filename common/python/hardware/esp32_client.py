#!/usr/bin/env python3
"""
Blinky ESP32 Universal Client.
Communicates with the Zero-Flash BlinkyUniversalDaemon running on the ESP32.
"""

import os
import json
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# Load .env if present
def _get_default_host():
    if "ESP32_HOST" in os.environ:
        return os.environ["ESP32_HOST"]
    env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ESP32_HOST="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    return "192.168.1.4"

DEFAULT_ESP32_HOST = _get_default_host()


class ESP32Client:

    def __init__(self, host: str = DEFAULT_ESP32_HOST):
        self.host = host

    def _get(self, endpoint: str, params: dict | None = None, timeout: float = 3.0) -> dict:
        query_string = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"http://{self.host}{endpoint}{query_string}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8").strip()
                try:
                    return json.loads(data)
                except Exception:
                    return {"status": "ok", "raw": data}
        except urllib.error.URLError as e:
            return {"status": "error", "error": f"Failed to connect to ESP32 at {self.host}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def check_status(self) -> dict:
        return self._get("/status")

    def set_rgb(self, r: int, g: int, b: int, rp: int = 25, gp: int = 26, bp: int = 27) -> dict:
        return self._get("/rgb", {"r": r, "g": g, "b": b, "rp": rp, "gp": gp, "bp": bp})

    def digital_write(self, pin: int, val: int) -> dict:
        return self._get("/digital", {"pin": pin, "val": 1 if val else 0})

    def digital_read(self, pin: int) -> dict:
        return self._get("/digital", {"pin": pin})

    def set_pwm(self, pin: int, val: int) -> dict:
        return self._get("/pwm", {"pin": pin, "val": max(0, min(255, val))})

    def set_servo(self, pin: int, angle: int) -> dict:
        return self._get("/servo", {"pin": pin, "angle": max(0, min(180, angle))})

    def play_tone(self, pin: int, freq: int = 1000, duration: int = 300) -> dict:
        return self._get("/tone", {"pin": pin, "freq": freq, "duration": duration})

    def analog_read(self, pin: int) -> dict:
        return self._get("/analog", {"pin": pin})
