from __future__ import annotations

import unittest

from utils.window import is_ignored_overlay_window
from main import filter_ignored_overlay_items


class WindowSelectionTests(unittest.TestCase):
    def test_ignores_snipping_recording_toolbar(self) -> None:
        self.assertTrue(is_ignored_overlay_window("snippingtool.exe", "Recording toolbar"))

    def test_does_not_ignore_normal_app_window(self) -> None:
        self.assertFalse(is_ignored_overlay_window("code.exe", "Jarvis - Visual Studio Code"))

    def test_filters_ocr_inside_ignored_overlay_rect(self) -> None:
        class Screenshot:
            width = 500
            height = 250
            screen_width = 1000
            screen_height = 500

        items = [
            {"text": "Stop recording", "x": 210, "y": 30, "width": 80, "height": 20},
            {"text": "Real app", "x": 10, "y": 160, "width": 80, "height": 20},
        ]

        from unittest.mock import patch
        with patch("main.get_ignored_overlay_rects", return_value=[{"x": 400, "y": 40, "width": 200, "height": 80}]):
            filtered = filter_ignored_overlay_items(items, Screenshot())

        self.assertEqual([item["text"] for item in filtered], ["Real app"])


if __name__ == "__main__":
    unittest.main()
