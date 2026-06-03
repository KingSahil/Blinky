from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai.groq_client import _validate_response as validate_groq_response
from ai.ollama_client import _validate_response as validate_ollama_response
from ai.prompt import build_chat_prompt, build_preflight_prompt, build_prompt
from main import extract_locator_target, run
from utils.matching import attach_matches
from utils.matching import find_best_match


class GuidanceFlowTests(unittest.TestCase):
    def test_clients_preserve_empty_steps(self) -> None:
        payload = {"summary": "No visible action is needed.", "steps": []}

        self.assertEqual(validate_groq_response(payload)["steps"], [])
        self.assertEqual(validate_ollama_response(payload)["steps"], [])

    def test_empty_target_text_does_not_match_from_instruction(self) -> None:
        steps = [
            {
                "step": 1,
                "instruction": "Open the relevant panel or menu and ask again.",
                "target_text": "",
            }
        ]
        items = [
            {
                "text": "Settings",
                "x": 10,
                "y": 10,
                "width": 20,
                "height": 20,
                "confidence": 0.9,
            }
        ]

        self.assertIsNone(attach_matches(steps, items)[0]["match"])

    def test_preflight_prompt_asks_model_to_avoid_screen_for_general_chat(self) -> None:
        prompt = build_preflight_prompt("what is the weather today?")

        self.assertIn("needs_screen", prompt)
        self.assertIn("normal conversation", prompt)
        self.assertNotIn("summary", prompt)

    def test_chat_prompt_tells_model_to_answer_instead_of_explaining_classification(self) -> None:
        prompt = build_chat_prompt("hi how are you?")
        prompt_lower = prompt.lower()

        self.assertIn("answer as blinky", prompt_lower)
        self.assertIn("greet", prompt_lower)
        self.assertIn("do not explain", prompt_lower)

    def test_general_chat_uses_chat_answer_not_classifier_reasoning(self) -> None:
        responses = iter(
            [
                {
                    "needs_screen": False,
                    "summary": "The student is greeting and inquiring about my status, which is a normal conversation.",
                },
                {"summary": "Hey! I'm doing well and ready to help.", "steps": []},
            ]
        )

        with (
            patch("main.ask_text_model", side_effect=lambda _prompt: next(responses)),
            patch("main.capture_screen", side_effect=AssertionError("screen should not be captured")),
        ):
            result = run("hi how are you?")

        self.assertEqual(result["summary"], "Hey! I'm doing well and ready to help.")
        self.assertEqual(result["steps"], [])

    def test_screen_prompt_uses_active_app_workflow_without_app_switching(self) -> None:
        prompt = build_prompt(
            question="how to install code runner extension",
            active_app={"title": "Jarvis - Visual Studio Code", "process": "Code.exe", "supported": True},
            ocr_items=[
                {
                    "text": "Extensions",
                    "x": 16,
                    "y": 170,
                    "width": 24,
                    "height": 24,
                    "confidence": 0.9,
                }
            ],
        )
        prompt_lower = prompt.lower()

        self.assertIn("stay in the active app", prompt_lower)
        self.assertIn("do not switch to another app", prompt_lower)
        self.assertIn("return a short workflow plan", prompt_lower)
        self.assertIn("do not repeat completed actions", prompt_lower)
        self.assertNotIn("strictly return a maximum of 1 step", prompt_lower)

    def test_screen_prompt_includes_completed_workflow_progress(self) -> None:
        prompt = build_prompt(
            question="how to install an extension",
            active_app={"title": "Editor", "process": "editor.exe", "supported": True},
            ocr_items=[
                {
                    "text": "Install",
                    "x": 300,
                    "y": 180,
                    "width": 80,
                    "height": 28,
                    "confidence": 0.95,
                }
            ],
            progress={
                "completed_targets": ["Extensions"],
                "completed_instructions": ["Open the Extensions panel."],
            },
        )
        prompt_lower = prompt.lower()

        self.assertIn("completed workflow context", prompt_lower)
        self.assertIn("completed_targets", prompt)
        self.assertIn("do not repeat or highlight completed targets", prompt_lower)
        self.assertIn("start with the next not-yet-completed step", prompt_lower)

    def test_screen_prompt_prefers_visible_search_when_requested_item_is_missing(self) -> None:
        prompt = build_prompt(
            question="install the requested extension",
            active_app={"title": "Editor Extensions", "process": "editor.exe", "supported": True},
            ocr_items=[
                {
                    "text": "Search Extensions in Marketplace",
                    "x": 40,
                    "y": 80,
                    "width": 300,
                    "height": 30,
                    "confidence": 0.95,
                    "control_type": "Edit",
                },
                {
                    "text": "Install",
                    "x": 300,
                    "y": 180,
                    "width": 80,
                    "height": 28,
                    "confidence": 0.95,
                    "control_type": "Button",
                },
            ],
            progress={"completed_targets": ["Extensions"]},
        )
        prompt_lower = prompt.lower()

        self.assertIn("if the requested item is not visible", prompt_lower)
        self.assertIn("visible search", prompt_lower)
        self.assertIn("do not choose an unrelated visible install", prompt_lower)

    def test_matching_prefers_interactive_sidebar_control_over_incidental_text(self) -> None:
        items = [
            {
                "text": "Extensions",
                "x": 88,
                "y": 610,
                "width": 120,
                "height": 24,
                "confidence": 0.95,
                "source": "ocr",
            },
            {
                "text": "Extensions",
                "x": 18,
                "y": 170,
                "width": 26,
                "height": 26,
                "confidence": 0.8,
                "source": "uia",
                "control_type": "Button",
            },
        ]

        match = find_best_match("Extensions", items, "Click the Extensions icon on the left sidebar.")

        self.assertIsNotNone(match)
        self.assertEqual(match["source"], "uia")
        self.assertEqual(match["control_type"], "Button")

    def test_matching_ignores_generic_ui_words_in_target_text(self) -> None:
        items = [
            {
                "text": "Extensions",
                "x": 18,
                "y": 170,
                "width": 26,
                "height": 26,
                "confidence": 0.8,
                "source": "uia",
                "control_type": "Button",
            },
        ]

        match = find_best_match("Extensions icon", items, "Click the Extensions icon on the left sidebar.")

        self.assertIsNotNone(match)
        self.assertEqual(match["text"], "Extensions")

    def test_matching_prefers_instruction_target_when_ai_target_text_disagrees(self) -> None:
        items = [
            {
                "text": "Explorer (Ctrl+Shift+E)",
                "x": 0,
                "y": 52,
                "width": 72,
                "height": 73,
                "confidence": 0.9,
                "source": "uia",
                "control_type": "Button",
            },
            {
                "text": "Extensions (Ctrl+Shift+X) - 2 require restart",
                "x": 0,
                "y": 196,
                "width": 72,
                "height": 73,
                "confidence": 0.9,
                "source": "uia",
                "control_type": "Button",
            },
        ]

        match = find_best_match(
            "Explorer (Ctrl+Shift+E)",
            items,
            "Click the Extensions icon on the left sidebar.",
        )

        self.assertIsNotNone(match)
        self.assertIn("Extensions", match["text"])

    def test_locator_settings_does_not_match_customize_layout(self) -> None:
        items = [
            {
                "text": "Customize Layout...",
                "x": 1482,
                "y": 6,
                "width": 38,
                "height": 30,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
            },
            {
                "text": "Settings",
                "x": 1615,
                "y": 384,
                "width": 38,
                "height": 38,
                "confidence": 0.98,
                "source": "blinky",
                "control_type": "Button",
            },
        ]

        match = find_best_match("settings", items, "Locate the settings control.")

        self.assertIsNotNone(match)
        self.assertEqual(match["text"], "Settings")

    def test_matching_prefers_search_input_over_header_for_type_instruction(self) -> None:
        items = [
            {
                "text": "EXTENSIONS",
                "x": 80,
                "y": 56,
                "width": 120,
                "height": 24,
                "confidence": 0.95,
                "source": "uia",
                "control_type": "Text",
            },
            {
                "text": "Search Extensions in Marketplace",
                "x": 82,
                "y": 90,
                "width": 320,
                "height": 30,
                "confidence": 0.9,
                "source": "uia",
                "control_type": "Edit",
            },
        ]

        match = find_best_match(
            "Extensions Marketplace search bar",
            items,
            "Type 'Code Runner' in the Extensions Marketplace search bar.",
        )

        self.assertIsNotNone(match)
        self.assertEqual(match["control_type"], "Edit")
        self.assertEqual(match["text"], "Search Extensions in Marketplace")

    def test_screen_prompt_requires_fresh_confirmation_after_completed_actions(self) -> None:
        prompt = build_prompt(
            question="install the requested extension",
            active_app={"title": "Editor Extensions", "process": "editor.exe", "supported": True},
            ocr_items=[
                {
                    "text": "Installed",
                    "x": 300,
                    "y": 180,
                    "width": 80,
                    "height": 28,
                    "confidence": 0.95,
                    "control_type": "Button",
                }
            ],
            progress={
                "completed_targets": ["Install"],
                "completed_instructions": ["Click the Install button for the requested extension."],
            },
        )
        prompt_lower = prompt.lower()

        self.assertIn("confirm completion from the current visible ui", prompt_lower)
        self.assertIn("do not assume completion just because a previous step was clicked", prompt_lower)
        self.assertIn('"steps": []', prompt)

    def test_preflight_prompt_with_previous_question_classifies_continuation(self) -> None:
        prompt = build_preflight_prompt("what to do", "install the code runner extension")
        prompt_lower = prompt.lower()

        self.assertIn("previous active goal/task", prompt_lower)
        self.assertIn("is_continuation", prompt_lower)
        self.assertIn("install the code runner extension", prompt_lower)

    def test_run_with_continuation_forces_screen_and_passes_latest_update(self) -> None:
        preflight_response = {
            "needs_screen": False,
            "is_continuation": True,
        }
        ai_response = {
            "summary": "Here is the next step to install.",
            "steps": [],
        }

        with (
            patch("main.ask_text_model", return_value=preflight_response),
            patch("main.capture_screen") as mock_capture,
            patch("main.get_active_window", return_value={"title": "VS Code"}),
            patch("main.extract_visible_text", return_value=[]),
            patch("main.get_visible_ui_text", return_value=[]),
            patch("main.ask_model", return_value=ai_response),
        ):
            # Even though preflight needs_screen is False, is_continuation=True should force needs_screen=True!
            result = run("what to do", "install the code runner extension")

        self.assertEqual(result["summary"], "Here is the next step to install.")
        self.assertTrue(result["is_continuation"])
        mock_capture.assert_called_once()

    def test_locator_target_extraction_removes_generic_words(self) -> None:
        self.assertEqual(extract_locator_target("where is the extension button?"), "extension")
        self.assertEqual(extract_locator_target("show me where the frontend folder is"), "frontend")
        self.assertIsNone(extract_locator_target("how to install code runner extension"))

    def test_locator_question_uses_local_uia_match_without_ocr_or_ai(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        items = [
            {
                "text": "Extensions (Ctrl+Shift+X)",
                "x": 0,
                "y": 196,
                "width": 72,
                "height": 73,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
            }
        ]

        with (
            patch("main.capture_screen", return_value=screenshot),
            patch("utils.window.get_target_window_element", return_value=None),
            patch("main.get_active_window", return_value={"title": "VS Code", "process": "code.exe"}),
            patch("main.get_visible_ui_text", return_value=items),
            patch("main.extract_visible_text", side_effect=AssertionError("OCR should be skipped")),
            patch("main.ask_text_model", side_effect=AssertionError("preflight AI should be skipped")),
            patch("main.ask_model", side_effect=AssertionError("guidance AI should be skipped")),
        ):
            result = run("where is the extension button?")

        self.assertEqual(result["provider"], "local")
        self.assertEqual(result["steps"][0]["match"]["text"], "Extensions (Ctrl+Shift+X)")
        self.assertEqual(result["ocr"]["count"], 1)

    def test_locator_question_ignores_blinky_controls_unless_requested(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        items = [
            {
                "text": "Customize Layout...",
                "x": 1482,
                "y": 6,
                "width": 38,
                "height": 30,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
            },
            {
                "text": "Settings",
                "x": 1615,
                "y": 384,
                "width": 38,
                "height": 38,
                "confidence": 0.98,
                "source": "blinky",
                "control_type": "Button",
            },
        ]

        with (
            patch("main.capture_screen", return_value=screenshot),
            patch("utils.window.get_target_window_element", return_value=None),
            patch("main.get_active_window", return_value={"title": "VS Code", "process": "code.exe"}),
            patch("main.get_visible_ui_text", return_value=items),
            patch("main.extract_visible_text", return_value=[]),
            patch("main.ask_text_model", return_value={"needs_screen": True, "is_continuation": False}),
            patch("main.ask_model", return_value={"summary": "No settings button is visible.", "steps": []}),
        ):
            result = run("where is settings?")

        self.assertNotEqual(result["provider"], "local")
        self.assertEqual(result["steps"], [])


if __name__ == "__main__":
    unittest.main()
