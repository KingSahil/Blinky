from __future__ import annotations

from unittest.mock import MagicMock, Mock, call, patch

from computer_use.tools import ToolResult, VirtualMouse, mouse_tool


def _reset_vm():
    if VirtualMouse._instance is not None:
        VirtualMouse._instance.close()
    VirtualMouse._instance = None
    import computer_use.tools as _t
    _t._VM_SCREEN_W = 2560
    _t._VM_SCREEN_H = 1440


# ── VirtualMouse class ──────────────────────────────────────────────

def test_virtual_mouse_singleton() -> None:
    _reset_vm()
    vm1 = VirtualMouse.get_instance()
    vm2 = VirtualMouse.get_instance()
    assert vm1 is vm2
    _reset_vm()


def test_virtual_mouse_move_clamps_bounds() -> None:
    vm = VirtualMouse(screen_w=1920, screen_h=1080)
    with patch.object(vm, "_ui") as mock_ui:
        vm.move(-50, 2000)
        mock_ui.write.assert_any_call(vm.e.EV_ABS, vm.e.ABS_X, 0)
        mock_ui.write.assert_any_call(vm.e.EV_ABS, vm.e.ABS_Y, 1080)
        assert mock_ui.syn.called
    vm.close()


def test_virtual_mouse_move_sends_abs_events() -> None:
    vm = VirtualMouse(screen_w=2560, screen_h=1440)
    with patch.object(vm, "_ui") as mock_ui:
        vm.move(800, 600)
        expected_calls = [
            call(vm.e.EV_ABS, vm.e.ABS_X, 800),
            call(vm.e.EV_ABS, vm.e.ABS_Y, 600),
        ]
        mock_ui.write.assert_has_calls(expected_calls, any_order=False)
    vm.close()


def test_virtual_mouse_click_sends_key_events() -> None:
    vm = VirtualMouse(screen_w=2560, screen_h=1440)
    with patch.object(vm, "_ui") as mock_ui:
        vm.click(100, 200, "right")
        mock_ui.write.assert_any_call(vm.e.EV_KEY, vm.e.BTN_RIGHT, 1)
        mock_ui.write.assert_any_call(vm.e.EV_KEY, vm.e.BTN_RIGHT, 0)
        mock_ui.write.assert_any_call(vm.e.EV_ABS, vm.e.ABS_X, 100)
    vm.close()


def test_virtual_mouse_click_defaults_left() -> None:
    vm = VirtualMouse(screen_w=2560, screen_h=1440)
    with patch.object(vm, "_ui") as mock_ui:
        vm.click(100, 200)
        mock_ui.write.assert_any_call(vm.e.EV_KEY, vm.e.BTN_LEFT, 1)
    vm.close()


def test_virtual_mouse_scroll_sends_rel_wheel() -> None:
    vm = VirtualMouse(screen_w=1920, screen_h=1080)
    with patch.object(vm, "_ui") as mock_ui:
        vm.scroll(3)
        mock_ui.write.assert_any_call(vm.e.EV_REL, vm.e.REL_WHEEL, -1)
    vm.close()


def test_virtual_mouse_scroll_up_sends_positive() -> None:
    vm = VirtualMouse(screen_w=1920, screen_h=1080)
    with patch.object(vm, "_ui") as mock_ui:
        vm.scroll(-2)
        mock_ui.write.assert_any_call(vm.e.EV_REL, vm.e.REL_WHEEL, 1)
    vm.close()


def test_virtual_mouse_create_device_failure_handled() -> None:
    with patch("evdev.UInput", side_effect=Exception("no permission")):
        vm = VirtualMouse(screen_w=1920, screen_h=1080)
        assert vm._ui is None
        vm.move(100, 100)
        vm.click(100, 100)
        vm.scroll(1)


def test_virtual_mouse_close_closes_ui() -> None:
    _reset_vm()
    vm = VirtualMouse.get_instance()
    _ui = vm._ui
    vm.close()
    assert vm._ui is None


def test_virtual_mouse_close_handles_none_ui() -> None:
    _reset_vm()
    vm = VirtualMouse()
    vm._ui = None
    vm.close()


def test_virtual_mouse_get_instance_creates_singleton() -> None:
    _reset_vm()
    vm = VirtualMouse.get_instance()
    assert isinstance(vm, VirtualMouse)
    assert VirtualMouse._instance is vm
    _reset_vm()


# ── _get_screen_dimensions ──────────────────────────────────────────

@patch("computer_use.linux_mcp.get_focused_window_bounds")
def test_get_screen_dimensions_from_mcp(mock_bounds: Mock) -> None:
    mock_bounds.return_value = {"x": 0, "y": 0, "width": 2560, "height": 1440}
    from computer_use.tools import _get_screen_dimensions
    w, h = _get_screen_dimensions()
    assert w == 2560
    assert h == 1440


@patch("computer_use.tools.subprocess.run", side_effect=FileNotFoundError)
@patch("computer_use.linux_mcp.get_focused_window_bounds", return_value=None)
def test_get_screen_dimensions_fallback_1920x1080(_mock_bounds: Mock, _mock_subprocess: Mock) -> None:
    from computer_use.tools import _get_screen_dimensions
    w, h = _get_screen_dimensions()
    assert w == 1920
    assert h == 1080


# ── mouse_tool ──────────────────────────────────────────────────────

@patch("computer_use.tools.VirtualMouse.get_instance")
def test_mouse_tool_move_calls_virtual_mouse(mock_get_vm: Mock) -> None:
    mock_vm = MagicMock()
    mock_get_vm.return_value = mock_vm
    result = mouse_tool(action="move", x=500, y=300)
    assert result.success is True
    mock_vm.move.assert_called_once_with(500, 300)


@patch("computer_use.tools.VirtualMouse.get_instance")
def test_mouse_tool_scroll_calls_virtual_mouse(mock_get_vm: Mock) -> None:
    mock_vm = MagicMock()
    mock_get_vm.return_value = mock_vm
    result = mouse_tool(action="scroll", scroll_amount=5)
    assert result.success is True
    mock_vm.scroll.assert_called_once_with(5)


@patch("computer_use.tools._virtual_mouse_click")
def test_mouse_tool_click_calls_virtual_mouse_click(mock_click: Mock) -> None:
    result = mouse_tool(action="click", x=100, y=200, button="right")
    assert result.success is True
    mock_click.assert_called_once_with(100, 200, "right")


def test_mouse_tool_unknown_action() -> None:
    result = mouse_tool(action="fly", x=0, y=0)
    assert result.success is False
    assert "Unknown" in result.message


def test_mouse_tool_not_linux() -> None:
    with patch("computer_use.tools.IS_LINUX", False):
        result = mouse_tool(action="move", x=100, y=100)
        assert result.success is False
        assert "Linux only" in result.message


# ── VirtualMouse recreation on screen size change ───────────────────

@patch("computer_use.tools._get_screen_dimensions")
@patch("computer_use.tools._show_click_crosshair")
@patch("computer_use.tools.capture_screenshot")
@patch("computer_use.tools.VirtualMouse.get_instance")
def test_click_recreates_vm_on_screen_size_change(
    mock_get_vm: Mock,
    mock_cap: Mock,
    mock_crosshair: Mock,
    mock_dims: Mock,
) -> None:
    _reset_vm()
    old_vm = VirtualMouse(screen_w=1920, screen_h=1080)
    VirtualMouse._instance = old_vm
    old_vm._ui = MagicMock()

    mock_dims.return_value = (3840, 2160)
    mock_new_vm = MagicMock()
    mock_new_vm.click.return_value = True
    mock_get_vm.return_value = mock_new_vm

    from computer_use.tools import _virtual_mouse_click
    _virtual_mouse_click(100, 100)

    assert old_vm._ui is None


@patch("computer_use.tools._get_screen_dimensions", return_value=(2560, 1440))
@patch("computer_use.tools._show_click_crosshair")
@patch("computer_use.tools.capture_screenshot")
def test_click_does_not_recreate_on_same_size(
    mock_cap: Mock,
    mock_crosshair: Mock,
    _mock_dims: Mock,
) -> None:
    _reset_vm()
    vm = VirtualMouse(screen_w=1920, screen_h=1080)
    VirtualMouse._instance = vm
    vm._ui = MagicMock()

    from computer_use.tools import _virtual_mouse_click
    _virtual_mouse_click(100, 100)

    assert vm._ui is not None
