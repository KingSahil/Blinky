from __future__ import annotations

import os
from pathlib import Path
from pathlib import Path
from unittest.mock import MagicMock, patch

LINUX_PYTHON = str(Path(__file__).resolve().parents[2] / "linux" / "python")
if LINUX_PYTHON not in os.environ.get("PYTHONPATH", ""):
    import sys
    if LINUX_PYTHON not in sys.path:
        sys.path.insert(0, LINUX_PYTHON)

from computer_use.tools import ToolResult, screenshot_tool


def test_screenshot_tool_not_linux() -> None:
    with patch("computer_use.tools.IS_LINUX", False):
        result = screenshot_tool()
        assert result.success is False
        assert "supported on Linux only" in result.message


def test_screenshot_tool_legacy_mode_returns_ocr_items_key() -> None:
    with (
        patch("computer_use.tools.IS_LINUX", True),
        patch("computer_use.tools.os.environ.get", return_value="legacy"),
        patch("computer_use.linux_mcp.screenshot", return_value={}),
    ):
        result = screenshot_tool()
        assert result.success is True
        assert "ocr_items" in result.details
        assert result.details["ocr_items"] == []


def test_screenshot_tool_ocr_mode_x11_fallback() -> None:
    with (
        patch("computer_use.tools.IS_LINUX", True),
        patch("computer_use.tools.os.environ.get", return_value="ocr"),
        patch("computer_use.tools._detect_desktop_session", return_value="x11"),
        patch("computer_use.tools._WAYLAND_VISION_AVAILABLE", False),
        patch("computer_use.linux_mcp.screenshot", return_value={}),
    ):
        result = screenshot_tool()
        assert result.success is True
        assert isinstance(result.details.get("ocr_items"), list)
        assert result.details.get("window_bounds") is None


def test_screenshot_tool_has_vision_field() -> None:
    with (
        patch("computer_use.tools.IS_LINUX", True),
        patch("computer_use.tools.os.environ.get", return_value="legacy"),
        patch("computer_use.linux_mcp.screenshot", return_value={}),
    ):
        result = screenshot_tool()
        assert "has_vision" in result.details
        assert isinstance(result.details["has_vision"], bool)


def test_screenshot_tool_returns_toolresult_type() -> None:
    with (
        patch("computer_use.tools.IS_LINUX", True),
        patch("computer_use.tools.os.environ.get", return_value="legacy"),
        patch("computer_use.linux_mcp.screenshot", return_value={}),
    ):
        result = screenshot_tool()
        assert isinstance(result, ToolResult)


def test_screenshot_tool_uses_grim_direct_fallback_when_wayland_vision_unavailable(tmp_path) -> None:
    import computer_use.tools as _t
    _t._GRIM_AVAILABLE = None

    fake_png = tmp_path / "grim_test_999.png"

    with (
        patch("computer_use.tools.IS_LINUX", True),
        patch("computer_use.tools.os.environ.get", return_value="ocr"),
        patch("computer_use.tools._detect_desktop_session", return_value="wayland"),
        patch("computer_use.tools._WAYLAND_VISION_AVAILABLE", False),
        patch("computer_use.tools._check_grim_available", return_value=True),
        patch("computer_use.tools._screenshot_temp_dir", return_value=Path(tmp_path)),
        patch("computer_use.tools._cleanup_old_screenshots"),
        patch("computer_use.tools.subprocess.run") as mock_run,
        patch("PIL.Image.open") as mock_img_open,
    ):
        mock_img = MagicMock()
        mock_img.size = (2560, 1440)
        mock_img_open.return_value.__enter__.return_value = mock_img

        def fake_grim_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and len(cmd) > 1 and cmd[0] == "grim":
                p = Path(cmd[1])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"png_data")
            return MagicMock(returncode=0, stdout=b"")

        mock_run.side_effect = fake_grim_run

        result = screenshot_tool()

    assert result.success is True
    assert "ocr_items" in result.details
    assert isinstance(result.details.get("window_bounds"), dict)
    assert result.details["window_bounds"]["width"] == 2560
    assert result.details["window_bounds"]["height"] == 1440
