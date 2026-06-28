from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

# Mock gradio_client in sys.modules before any imports that might need it
mock_gradio_client_module = MagicMock()
sys.modules["gradio_client"] = mock_gradio_client_module

import pytest

from ocr import get_ocr_provider
from ocr.omniparser import OmniParserProvider


def test_get_ocr_provider_omniparser(monkeypatch):
    """Test that get_ocr_provider resolves to OmniParserProvider when configured."""
    monkeypatch.setenv("BLINKY_SCREENSHOT_MODE", "omniparser")
    # Reset cached provider
    import ocr
    ocr._provider = None

    provider = get_ocr_provider()
    assert isinstance(provider, OmniParserProvider)


def test_omniparser_api_extraction(monkeypatch):
    """Test standard API response parsing and mapping."""
    monkeypatch.setenv("BLINKY_SCREENSHOT_MODE", "omniparser")
    monkeypatch.setenv("BLINKY_OMNIPARSER_API_URL", "https://mock.omniparser.api/predict")

    provider = OmniParserProvider()
    assert provider.api_url == "https://mock.omniparser.api/predict"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"text": "Login Button", "x": 120, "y": 250, "width": 80, "height": 40, "type": "button", "confidence": 0.98},
        {"text": "Search Input", "x": 200, "y": 150, "width": 300, "height": 30, "type": "input", "confidence": 0.95},
        {"text": "", "x": 50, "y": 50, "width": 20, "height": 20, "type": "icon", "confidence": 0.90}
    ]

    with patch("requests.post", return_value=mock_response) as mock_post, \
         patch("builtins.open", mock_open(read_data=b"fake_image_data")):
        elements = provider.extract_text(Path("dummy_screenshot.png"))
        
        # Verify post parameters
        assert mock_post.called
        assert len(elements) == 3

        # Verify element 0 (Button)
        assert elements[0]["text"] == "Login Button"
        assert elements[0]["x"] == 120
        assert elements[0]["y"] == 250
        assert elements[0]["width"] == 80
        assert elements[0]["height"] == 40
        assert elements[0]["control_type"] == "button"
        assert elements[0]["clickable"] is True
        assert elements[0]["source"] == "omniparser"

        # Verify element 1 (Input)
        assert elements[1]["text"] == "Search Input"
        assert elements[1]["control_type"] == "input"
        assert elements[1]["clickable"] is True

        # Verify element 2 (Icon)
        assert elements[2]["text"] == ""
        assert elements[2]["control_type"] == "icon"
        assert elements[2]["clickable"] is True


def test_omniparser_api_failure_fallback(monkeypatch):
    """Test API failure maps to fallback behavior."""
    monkeypatch.setenv("BLINKY_SCREENSHOT_MODE", "omniparser")
    monkeypatch.setenv("BLINKY_OMNIPARSER_API_URL", "https://mock.omniparser.api/predict")

    provider = OmniParserProvider()
    
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("requests.post", return_value=mock_response), \
         patch("builtins.open", mock_open(read_data=b"fake_image_data")):
        elements = provider.extract_text(Path("dummy_screenshot.png"))
        # Should gracefully return empty list on API failure
        assert elements == []


def test_omniparser_hf_space_extraction(monkeypatch):
    """Test parsing logic specifically for the Hugging Face Space Gradio client output."""
    monkeypatch.setenv("BLINKY_SCREENSHOT_MODE", "omniparser")
    # Set to a space-like ID
    monkeypatch.setenv("BLINKY_OMNIPARSER_API_URL", "microsoft/OmniParser-v2")

    provider = OmniParserProvider()
    
    mock_client = MagicMock()
    # Mock return values for predict
    mock_client.predict.return_value = (
        "labeled_image.png",
        '[{"box_2d": [100, 200, 200, 300], "label": "icon: settings"}, {"box_2d": [300, 400, 400, 500], "label": "text: Click Me"}]'
    )

    mock_image = MagicMock()
    mock_image.size = (1000, 1000)

    # Re-mock gradio_client.Client since we mocked the module
    with patch("gradio_client.Client", return_value=mock_client) as mock_client_cls, \
         patch("PIL.Image.open", return_value=mock_image), \
         patch("builtins.open", mock_open(read_data=b"fake")):
        
        elements = provider.extract_text(Path("dummy.png"))
        
        assert mock_client_cls.called
        assert len(elements) == 2
        
        # Verify first element (Icon: Settings)
        assert elements[0]["text"] == "settings"
        assert elements[0]["control_type"] == "icon"
        assert elements[0]["x"] == 200
        assert elements[0]["y"] == 100
        assert elements[0]["width"] == 100
        assert elements[0]["height"] == 100
        assert elements[0]["clickable"] is True

        # Verify second element (Text: Click Me)
        assert elements[1]["text"] == "Click Me"
        assert elements[1]["control_type"] == "text"
        assert elements[1]["clickable"] is False


def test_omniparser_local_extraction(monkeypatch):
    """Test local inference extraction and overlaying default OCR text items."""
    monkeypatch.setenv("BLINKY_SCREENSHOT_MODE", "omniparser")
    # Empty URL triggers local processing mode
    monkeypatch.setenv("BLINKY_OMNIPARSER_API_URL", "")

    provider = OmniParserProvider()
    assert provider.api_url == ""

    # Mock YOLO model boxes
    mock_box = MagicMock()
    mock_xyxy = MagicMock()
    mock_xyxy.tolist.return_value = [10.0, 20.0, 110.0, 70.0]
    mock_box.xyxy = [mock_xyxy]
    mock_box.conf = [0.85]

    mock_result = MagicMock()
    mock_result.boxes = [mock_box]

    mock_yolo = MagicMock()
    mock_yolo.return_value = [mock_result]

    # Mock default OCR provider outputs that overlap spatially with the YOLO box
    mock_ocr_provider = MagicMock()
    mock_ocr_provider.extract_text.return_value = [
        {"text": "Submit", "x": 50, "y": 40, "width": 40, "height": 10, "control_type": "text"}
    ]

    with patch("ultralytics.YOLO", return_value=mock_yolo) as mock_yolo_cls, \
         patch("ocr.get_ocr_provider", return_value=mock_ocr_provider), \
         patch("pathlib.Path.exists", return_value=True):
        
        elements = provider.extract_text(Path("dummy.png"))
        
        assert mock_yolo_cls.called
        assert len(elements) == 1
        
        assert elements[0]["x"] == 10
        assert elements[0]["y"] == 20
        assert elements[0]["width"] == 100
        assert elements[0]["height"] == 50
        assert elements[0]["confidence"] == 0.85
        assert elements[0]["control_type"] == "Button"
        # Verify text was overlaid from OCR mapping
        assert elements[0]["text"] == "Submit"
