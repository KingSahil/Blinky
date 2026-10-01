import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai.gemini_client import _get_gemini_client
from main import run


class AttachedImageSafetyTests(unittest.TestCase):
    def test_gemini_client_allows_twenty_seconds_for_network_request(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch("google.genai.Client") as client:
            _get_gemini_client()
        options = client.call_args.kwargs["http_options"]
        self.assertGreaterEqual(options.timeout / 1000, 20)

    def test_failed_image_analysis_returns_no_desktop_actions(self):
        with patch("ai.gemini_client.ask_gemini_vision", side_effect=RuntimeError("offline")), \
             patch("main.capture_screen", side_effect=AssertionError("Captured desktop")), \
             patch("main.get_active_window", side_effect=AssertionError("Scanned desktop")):
            result = run("summarise this screenshot", attached_image="dGVzdA==")
        self.assertEqual(result["steps"], [])
        self.assertEqual(result["ocr"]["count"], 0)
        self.assertIn("offline", result["summary"])

    def test_unexpected_image_failure_cannot_fall_back_to_desktop_control(self):
        with patch("main.run_attached_image_vision", side_effect=RuntimeError("unexpected failure")), \
             patch("main.capture_screen", side_effect=AssertionError("Captured desktop")), \
             patch("main.get_active_window", side_effect=AssertionError("Scanned desktop")):
            with self.assertRaisesRegex(RuntimeError, "Image analysis failed"):
                run("summarise this screenshot", attached_image="dGVzdA==")


if __name__ == "__main__":
    unittest.main()
