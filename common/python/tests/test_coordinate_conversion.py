from __future__ import annotations

from unittest.mock import patch

from computer_use.tools import (
    _is_relative_coordinate,
    _to_int,
    translate_relative_to_absolute,
)


def test_to_int_int() -> None:
    assert _to_int(42) == 42


def test_to_int_string() -> None:
    assert _to_int("150") == 150


def test_to_int_float() -> None:
    assert _to_int(150.7) == 151


def test_to_int_none() -> None:
    assert _to_int(None) == 0


def test_basic_conversion() -> None:
    window_bounds = {"x": 100, "y": 50, "width": 800, "height": 600}
    ocr = {"x": 0, "y": 0, "width": 50, "height": 20, "text": "Hello", "source": "ocr"}
    result = translate_relative_to_absolute(ocr, window_bounds, 1.0)
    assert result["absolute_bounds"]["x"] == 100
    assert result["absolute_bounds"]["y"] == 50


def test_offset_conversion() -> None:
    window_bounds = {"x": 100, "y": 50, "width": 800, "height": 600}
    ocr = {"x": 150, "y": 200, "width": 50, "height": 20, "text": "Button", "source": "ocr"}
    result = translate_relative_to_absolute(ocr, window_bounds, 1.0)
    assert result["absolute_bounds"]["x"] == 250
    assert result["absolute_bounds"]["y"] == 250


def test_scale_factor() -> None:
    window_bounds = {"x": 100, "y": 50, "width": 800, "height": 600}
    ocr = {"x": 100, "y": 100, "width": 50, "height": 20, "source": "ocr"}
    result = translate_relative_to_absolute(ocr, window_bounds, 2.0)
    assert result["absolute_bounds"]["x"] == 400
    assert result["absolute_bounds"]["y"] == 300


def test_no_window_bounds() -> None:
    ocr = {"x": 100, "y": 100, "width": 50, "height": 20, "source": "ocr"}
    result = translate_relative_to_absolute(ocr, None, 1.0)
    assert "absolute_bounds" not in result


def test_negative_clamping() -> None:
    window_bounds = {"x": 0, "y": 0, "width": 800, "height": 600}
    ocr = {"x": -10, "y": -20, "width": 50, "height": 20, "source": "ocr"}
    result = translate_relative_to_absolute(ocr, window_bounds, 1.0)
    assert result["absolute_bounds"]["x"] == 0
    assert result["absolute_bounds"]["y"] == 0


def test_source_tagging_ocr() -> None:
    ocr_coords = {"x": 10, "y": 20, "source": "ocr"}
    assert _is_relative_coordinate(ocr_coords) is True


def test_source_tagging_mcp() -> None:
    mcp_coords = {"x": 10, "y": 20, "source": "mcp", "absolute_bounds": {"x": 100, "y": 200, "width": 50, "height": 30}}
    assert _is_relative_coordinate(mcp_coords) is False


def test_absolute_bounds_prevents_double_conversion() -> None:
    coords = {"x": 10, "y": 20, "absolute_bounds": {"x": 100, "y": 200, "width": 50, "height": 30}}
    assert _is_relative_coordinate(coords) is False


def test_call_tool_with_fractional_mouse_coords() -> None:
    from unittest.mock import MagicMock, patch

    from computer_use.loop import _call_tool

    mock_fn = MagicMock()
    mock_fn.return_value = MagicMock(success=True)

    args = {"action": "click", "x": 0.5, "y": 0.25, "button": "left"}

    with patch("computer_use.loop._get_screen_dims", return_value=(2560, 1440)):
        _call_tool("mouse", mock_fn, args)

    call_kwargs = mock_fn.call_args[1]
    assert call_kwargs["x"] == 1280
    assert call_kwargs["y"] == 360


def test_call_tool_with_absolute_mouse_coords_passthrough() -> None:
    from unittest.mock import MagicMock, patch

    from computer_use.loop import _call_tool

    mock_fn = MagicMock()
    mock_fn.return_value = MagicMock(success=True)

    args = {"action": "click", "x": 800, "y": 600, "button": "left"}

    with patch("computer_use.loop._get_screen_dims") as mock_dims:
        _call_tool("mouse", mock_fn, args)

    call_kwargs = mock_fn.call_args[1]
    assert call_kwargs["x"] == 800
    assert call_kwargs["y"] == 600
    mock_dims.assert_not_called()


def test_call_tool_mouse_without_coords_passthrough() -> None:
    from unittest.mock import MagicMock, patch

    from computer_use.loop import _call_tool

    mock_fn = MagicMock()
    mock_fn.return_value = MagicMock(success=True)

    args = {"action": "scroll", "scroll_amount": 3}
    _call_tool("mouse", mock_fn, args)

    call_kwargs = mock_fn.call_args[1]
    assert call_kwargs["x"] is None
    assert call_kwargs["y"] is None
