#!/usr/bin/env python3
"""
Generates config.h for ESP32 firmware by reading credentials from .env.
Ensures Wi-Fi credentials are NEVER hardcoded in .ino files.
"""

import os
import sys
import subprocess
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
CONFIG_H_PATH = ROOT_DIR / "esp32_firmware" / "BlinkyUniversalDaemon" / "config.h"


def load_env_vars() -> dict:
    env_vars = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars


def get_wifi_credentials() -> tuple[str, str]:
    env = load_env_vars()
    ssid = env.get("ESP32_WIFI_SSID") or os.environ.get("ESP32_WIFI_SSID")
    password = env.get("ESP32_WIFI_PASSWORD") or os.environ.get("ESP32_WIFI_PASSWORD")

    # If missing in .env, attempt to detect from local Windows Wi-Fi profile
    if not ssid and sys.platform == "win32":
        try:
            out = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], text=True)
            m = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.MULTILINE)
            if m:
                detected_ssid = m.group(1).strip()
                # If connected to 5G, check for 2.4G equivalent
                if detected_ssid.endswith("_5G"):
                    base_ssid = detected_ssid[:-3]
                    ssid = base_ssid
                else:
                    ssid = detected_ssid

                # Query password
                p_out = subprocess.check_output(["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"], text=True)
                km = re.search(r"Key Content\s*:\s*(.+)$", p_out)
                if km:
                    password = km.group(1).strip()
        except Exception:
            pass

    return ssid or "YOUR_WIFI_SSID", password or "YOUR_WIFI_PASSWORD"


def generate_config_header():
    ssid, password = get_wifi_credentials()

    CONFIG_H_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = f"""// AUTO-GENERATED FROM .env - DO NOT EDIT MANUALLY OR COMMIT TO GIT
#ifndef BLINKY_CONFIG_H
#define BLINKY_CONFIG_H

#define WIFI_SSID "{ssid}"
#define WIFI_PASSWORD "{password}"

#endif // BLINKY_CONFIG_H
"""

    with open(CONFIG_H_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Generated {CONFIG_H_PATH.relative_to(ROOT_DIR)} with SSID: {ssid}")


if __name__ == "__main__":
    generate_config_header()
