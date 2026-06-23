from __future__ import annotations

from unittest.mock import Mock, patch

from computer_use.loop import _get_screen_dims


def test_get_screen_dims_from_mcp_window_bounds() -> None:
    with patch("computer_use.linux_mcp.get_focused_window_bounds", return_value={"x": 0, "y": 0, "width": 2560, "height": 1440}):
        w, h = _get_screen_dims()
    assert w == 2560
    assert h == 1440


def test_get_screen_dims_from_xrandr() -> None:
    xrandr_output = """Screen 0: minimum 320 x 200, current 2560 x 1440, maximum 16384 x 16384
HDMI-1 connected primary 2560x1440+0+0 (normal left inverted right x axis y axis) 527mm x 296mm"""

    with (
        patch("computer_use.linux_mcp.get_focused_window_bounds", return_value=None),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = xrandr_output
        w, h = _get_screen_dims()
    assert w == 2560
    assert h == 1440


def test_get_screen_dims_xrandr_multi_monitor_picks_first_connected() -> None:
    xrandr_output = """Screen 0: minimum 320 x 200, current 3840 x 2160, maximum 16384 x 16384
DP-1 connected 1920x1080+0+0 (normal left inverted right x axis y axis) 527mm x 296mm
HDMI-1 disconnected (normal left inverted right x axis y axis)"""

    with (
        patch("computer_use.linux_mcp.get_focused_window_bounds", return_value=None),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = xrandr_output
        w, h = _get_screen_dims()
    assert w == 1920
    assert h == 1080


def test_get_screen_dims_fallback_on_xrandr_failure() -> None:
    with (
        patch("computer_use.linux_mcp.get_focused_window_bounds", return_value=None),
        patch("subprocess.run", side_effect=FileNotFoundError("no xrandr")),
        patch("computer_use.tools.capture_screenshot", return_value=None),
    ):
        w, h = _get_screen_dims()
    assert w == 1920
    assert h == 1080


def test_get_screen_dims_from_screenshot_fallback() -> None:
    with (
        patch("computer_use.linux_mcp.get_focused_window_bounds", return_value=None),
        patch("subprocess.run", side_effect=FileNotFoundError("no xrandr")),
        patch("computer_use.tools.capture_screenshot", return_value="/tmp/fake.png"),
        patch("PIL.Image.open") as mock_img_open,
    ):
        mock_img = Mock()
        mock_img.size = (2560, 1440)
        mock_img_open.return_value.__enter__.return_value = mock_img
        w, h = _get_screen_dims()
    assert w == 2560
    assert h == 1440
