from __future__ import annotations

import os
import subprocess

from utils.logging import get_logger

LOGGER = get_logger("blinky.app_inventory")


def _desktop_env() -> str | None:
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if de:
        return de
    return None


def _kde_apps() -> list[str]:
    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        result = subprocess.run(
            ["krunner", "--list"],
            capture_output=True, text=True, timeout=5,
            env=env,
        )
        if result.returncode != 0:
            return []
        apps: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("."):
                name = line.rsplit(".desktop", 1)[0] if ".desktop" in line else line
                if name:
                    apps.append(name)
        return apps
    except Exception as e:
        LOGGER.debug("KDE app discovery failed: %s", e)
        return []


def _gnome_apps() -> list[str]:
    try:
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        result = subprocess.run(
            ["gio", "app", "info", "--list"],
            capture_output=True, text=True, timeout=5,
            env=env,
        )
        if result.returncode != 0:
            return []
        apps: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and ".desktop" in line:
                name = line.rsplit(".desktop", 1)[0] if ".desktop" in line else line
                if name:
                    apps.append(name)
        return apps
    except Exception as e:
        LOGGER.debug("GNOME app discovery failed: %s", e)
        return []


def _mcp_running_apps() -> list[str]:
    try:
        from computer_use.linux_mcp import list_apps
        apps_data = list_apps()
        app_names: set[str] = set()
        for app in apps_data:
            if isinstance(app, dict):
                name = app.get("name") or app.get("app_id") or ""
                if name:
                    app_names.add(str(name).strip())
            elif isinstance(app, str):
                app_names.add(app.strip())
        return sorted(app_names)
    except Exception as e:
        LOGGER.debug("MCP running apps discovery failed: %s", e)
        return []


def get_app_inventory() -> list[str]:
    de = _desktop_env()

    apps: list[str] = []
    if de and "kde" in de:
        try:
            apps = _kde_apps()
        except Exception:
            apps = []
    elif de and "gnome" in de:
        try:
            apps = _gnome_apps()
        except Exception:
            apps = []

    try:
        mcp_apps = _mcp_running_apps()
    except Exception:
        mcp_apps = []
    all_apps_set: set[str] = set(apps) | set(mcp_apps)
    all_apps = sorted(all_apps_set)

    if len(all_apps) > 50:
        all_apps = all_apps[:50]

    if all_apps:
        LOGGER.info("App inventory: %d apps discovered", len(all_apps))
    else:
        LOGGER.debug("App inventory: empty (no DE or MCP apps found)")

    return all_apps
