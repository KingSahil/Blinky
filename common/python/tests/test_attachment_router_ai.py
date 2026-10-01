import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from attachment_router_ai import choose_action

IMAGE = [{"name": "screen.png", "type": "image", "mimeType": "image/png"}]


class AttachmentRouterTests(unittest.TestCase):
    def test_blank_prompt_transfers_without_calling_ai(self):
        with patch("attachment_router_ai.ask_text_model") as model:
            self.assertEqual(choose_action("  ", IMAGE), "transfer")
            model.assert_not_called()

    def test_natural_request_is_decided_by_ai(self):
        with patch("attachment_router_ai.ask_text_model", return_value={"action": "transfer"}) as model:
            self.assertEqual(choose_action("These belong wherever I keep my receipts", IMAGE), "transfer")
            self.assertIn("These belong wherever I keep my receipts", model.call_args.args[0])

    def test_image_question_uses_model_action(self):
        with patch("attachment_router_ai.ask_text_model", return_value={"action": "analyze-image"}):
            self.assertEqual(choose_action("Summarize this and save the answer", IMAGE), "analyze-image")

    def test_invalid_model_action_is_not_a_transfer(self):
        for response in ({"action": "delete"}, {}, None):
            with patch("attachment_router_ai.ask_text_model", return_value=response):
                with self.assertRaises(ValueError):
                    choose_action("send this to PC", IMAGE)

    def test_model_failure_propagates_without_transfer(self):
        with patch("attachment_router_ai.ask_text_model", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                choose_action("summarize", IMAGE)

    def test_vision_tool_rejects_unsupported_attachments(self):
        with patch("attachment_router_ai.ask_text_model", return_value={"action": "analyze-image"}):
            self.assertEqual(choose_action("summarize", [{"name": "report.pdf"}]), "unsupported")


if __name__ == "__main__":
    unittest.main()
