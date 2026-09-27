import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai.custom_client import _extract_content, _parse_json, _post_with_fallback


class TestCustomClient(unittest.TestCase):
    def test_parse_json_strips_think_tags(self):
        raw = "<think>Here is the plan...</think>{\"intent\": \"TEST\", \"score\": 100}"
        parsed = _parse_json(raw)
        self.assertEqual(parsed, {"intent": "TEST", "score": 100})

    def test_parse_json_strips_markdown_code_blocks(self):
        raw = "```json\n{\"status\": \"ok\", \"count\": 5}\n```"
        parsed = _parse_json(raw)
        self.assertEqual(parsed, {"status": "ok", "count": 5})

    def test_extract_content_falls_back_to_reasoning(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": "{\"salvaged\": true}",
                    }
                }
            ]
        }
        content = _extract_content(payload)
        self.assertEqual(content, "{\"salvaged\": true}")

    def test_post_with_fallback_attempts_candidates(self):
        with patch("ai.custom_client._post") as mock_post:
            mock_post.side_effect = [
                RuntimeError("Invalid parameter: thinking"),
                {"choices": [{"message": {"content": "{\"ok\": true}"}}]},
            ]
            res = _post_with_fallback(
                {"model": "minimax-test"},
                "http://fake.api",
                "dummy_key",
                "minimax-test",
            )
            self.assertIn("choices", res)
            self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
