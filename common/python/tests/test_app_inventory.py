from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

LINUX_PYTHON = str(Path(__file__).resolve().parents[3] / "linux" / "python")
if LINUX_PYTHON not in os.environ.get("PYTHONPATH", ""):
    import sys
    if LINUX_PYTHON not in sys.path:
        sys.path.insert(0, LINUX_PYTHON)

from app_inventory import get_app_inventory


def test_app_inventory_kde_returns_apps() -> None:
    with (
        patch("app_inventory._desktop_env", return_value="kde"),
        patch("app_inventory._kde_apps", return_value=["firefox", "kate"]),
        patch("app_inventory._mcp_running_apps", return_value=["firefox"]),
    ):
        apps = get_app_inventory()
        assert "firefox" in apps
        assert "kate" in apps


def test_app_inventory_kde_exception_returns_mcp() -> None:
    with (
        patch("app_inventory._desktop_env", return_value="kde"),
        patch("app_inventory._kde_apps", return_value=[]),
        patch("app_inventory._mcp_running_apps", return_value=["terminal"]),
    ):
        apps = get_app_inventory()
        assert "terminal" in apps


def test_app_inventory_gnome_returns_apps() -> None:
    with (
        patch("app_inventory._desktop_env", return_value="gnome"),
        patch("app_inventory._gnome_apps", return_value=["nautilus", "gedit"]),
        patch("app_inventory._mcp_running_apps", return_value=[]),
    ):
        apps = get_app_inventory()
        assert "nautilus" in apps
        assert "gedit" in apps


def test_app_inventory_mcp_exception_returns_de() -> None:
    with (
        patch("app_inventory._desktop_env", return_value="kde"),
        patch("app_inventory._kde_apps", return_value=["firefox"]),
        patch("app_inventory._mcp_running_apps", side_effect=Exception("MCP down")),
    ):
        apps = get_app_inventory()
        assert apps == ["firefox"]


def test_app_inventory_no_de_returns_mcp() -> None:
    with (
        patch("app_inventory._desktop_env", return_value=None),
        patch("app_inventory._mcp_running_apps", return_value=["terminal"]),
    ):
        apps = get_app_inventory()
        assert apps == ["terminal"]


def test_app_inventory_truncates_at_50() -> None:
    with (
        patch("app_inventory._desktop_env", return_value="kde"),
        patch("app_inventory._kde_apps", return_value=[f"app{i}" for i in range(60)]),
        patch("app_inventory._mcp_running_apps", return_value=[]),
    ):
        apps = get_app_inventory()
        assert len(apps) <= 50
