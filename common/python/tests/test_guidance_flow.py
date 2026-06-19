from __future__ import annotations

from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from ai.groq_client import _validate_response as validate_groq_response
from ai.ollama_client import _validate_response as validate_ollama_response
from ai.prompt import build_chat_prompt, build_preflight_prompt, build_prompt
from computer_use.tools import ToolResult
from main import (
    assign_screen_element_refs,
    extract_locator_target,
    merge_visible_items,
    resolve_locator_fast_path,
    run,
    should_force_screen_context,
)
from utils.matching import attach_matches
from utils.matching import find_best_match, find_best_match_with_score
from utils.ui_map_cache import UiMapCache, window_signature
from utils.uia import _element_text, _readable_metadata_text, _uia_item


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

    def test_chat_prompt_includes_recent_conversation_history(self) -> None:
        prompt = build_chat_prompt(
            "what did I ask before?",
            [{"role": "student", "content": "I asked about Java loops."}],
        )

        self.assertIn("Recent conversation", prompt)
        self.assertIn("Java loops", prompt)

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

    def test_screen_context_heuristic_keeps_general_chat_off_screen(self) -> None:
        self.assertFalse(should_force_screen_context("how are you?"))
        self.assertFalse(should_force_screen_context("what can you do?"))

    def test_screen_context_heuristic_forces_screen_for_app_guidance(self) -> None:
        self.assertTrue(should_force_screen_context("where is settings?"))
        self.assertTrue(should_force_screen_context("how to install code runner extension"))
        self.assertTrue(should_force_screen_context("what next?", "install code runner extension"))

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
        self.assertIn("return only the immediate next step", prompt_lower)
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

    def test_screen_prompt_gives_unlabeled_icon_controls_matchable_labels(self) -> None:
        prompt = build_prompt(
            question="where is the voice input button?",
            active_app={"title": "Chat", "process": "chat.exe", "supported": True},
            ocr_items=[
                {
                    "text": "",
                    "x": 1200,
                    "y": 980,
                    "width": 44,
                    "height": 44,
                    "source": "uia",
                    "control_type": "Button",
                }
            ],
        )

        self.assertIn('role=Button name="Visible Button 1" box=(1200,980,44,44)', prompt)
        self.assertIn('target_ref', prompt)
        self.assertIn("For unlabeled icon-only controls", prompt)

    def test_screen_prompt_keeps_interactive_controls_after_many_text_items(self) -> None:
        text_items = [
            {
                "text": f"Lesson text {index}",
                "x": 100,
                "y": index * 20,
                "width": 200,
                "height": 18,
                "source": "ocr",
                "control_type": "Text",
            }
            for index in range(60)
        ]
        prompt = build_prompt(
            question="where is the voice input button?",
            active_app={"title": "Chat", "process": "chat.exe", "supported": True},
            ocr_items=[
                *text_items,
                {
                    "text": "",
                    "x": 1200,
                    "y": 980,
                    "width": 44,
                    "height": 44,
                    "source": "uia",
                    "control_type": "Button",
                },
            ],
        )

        self.assertIn('role=Button name="Visible Button 1" box=(1200,980,44,44)', prompt)

    def test_assign_screen_element_refs_adds_stable_refs_and_flags(self) -> None:
        items = assign_screen_element_refs(
            [
                {
                    "text": "Search Extensions in Marketplace",
                    "x": 40,
                    "y": 80,
                    "width": 300,
                    "height": 30,
                    "source": "uia",
                    "control_type": "Edit",
                    "automation_id": "search-box",
                },
                {
                    "text": "",
                    "x": 16,
                    "y": 170,
                    "width": 24,
                    "height": 24,
                    "source": "uia",
                    "control_type": "Button",
                },
            ]
        )

        self.assertEqual(items[0]["ref"], "@e1")
        self.assertEqual(items[0]["automation_id"], "search-box")
        self.assertTrue(items[0]["input"])
        self.assertTrue(items[0]["clickable"])
        self.assertEqual(items[1]["ref"], "@e2")
        self.assertEqual(items[1]["ai_label"], "Visible Button 1")
        self.assertTrue(items[1]["clickable"])

    def test_merge_visible_items_deduplicates_overlapping_ocr_and_uia(self) -> None:
        merged = merge_visible_items(
            ocr_items=[
                {
                    "text": "Install",
                    "x": 302,
                    "y": 181,
                    "width": 42,
                    "height": 17,
                    "source": "ocr",
                    "control_type": "Text",
                }
            ],
            uia_items=[
                {
                    "text": "Install",
                    "x": 300,
                    "y": 180,
                    "width": 80,
                    "height": 28,
                    "source": "uia",
                    "control_type": "Button",
                }
            ],
        )

        install_items = [item for item in merged if item.get("text") == "Install"]
        self.assertEqual(len(install_items), 1)
        self.assertEqual(install_items[0]["control_type"], "Button")

    def test_attach_matches_resolves_target_ref_before_fuzzy_text(self) -> None:
        items = assign_screen_element_refs(
            [
                {
                    "text": "Install",
                    "x": 20,
                    "y": 20,
                    "width": 40,
                    "height": 20,
                    "source": "ocr",
                    "control_type": "Text",
                },
                {
                    "text": "Extensions",
                    "x": 16,
                    "y": 170,
                    "width": 24,
                    "height": 24,
                    "source": "uia",
                    "control_type": "Button",
                },
            ]
        )
        steps = [
            {
                "step": 1,
                "instruction": "Click the Extensions button.",
                "target_ref": "@e2",
                "target_text": "Install",
            }
        ]

        matched_step = attach_matches(steps, items)[0]

        self.assertEqual(matched_step["match"]["ref"], "@e2")
        self.assertEqual(matched_step["match"]["text"], "Extensions")
        self.assertEqual(matched_step["match"]["match_method"], "ref")

    def test_attach_matches_falls_back_to_target_text_when_ref_is_stale(self) -> None:
        items = assign_screen_element_refs(
            [
                {
                    "text": "Extensions",
                    "x": 16,
                    "y": 170,
                    "width": 24,
                    "height": 24,
                    "source": "uia",
                    "control_type": "Button",
                }
            ]
        )
        steps = [
            {
                "step": 1,
                "instruction": "Click the Extensions button.",
                "target_ref": "@e99",
                "target_text": "Extensions",
            }
        ]

        matched_step = attach_matches(steps, items)[0]

        self.assertEqual(matched_step["match"]["ref"], "@e1")
        self.assertEqual(matched_step["match"]["match_method"], "text")

    def test_attach_matches_can_target_synthetic_unlabeled_control_label(self) -> None:
        steps = [
            {
                "step": 1,
                "instruction": "Click the visible voice input button.",
                "target_text": "Visible Button 1",
            }
        ]
        items = [
            {
                "text": "",
                "ai_label": "Visible Button 1",
                "x": 1200,
                "y": 980,
                "width": 44,
                "height": 44,
                "source": "uia",
                "control_type": "Button",
            }
        ]

        matched_step = attach_matches(steps, items)[0]

        self.assertIsNotNone(matched_step["match"])
        self.assertEqual(matched_step["match"]["ai_label"], "Visible Button 1")

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

    def test_matching_can_use_generic_accessibility_id_text(self) -> None:
        items = [
            {
                "text": "new chat button",
                "x": 18,
                "y": 90,
                "width": 32,
                "height": 32,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
                "automation_id": "new-chat-button",
            }
        ]

        match = find_best_match("new chat", items, "Locate the new chat control.")

        self.assertIsNotNone(match)
        self.assertEqual(match["automation_id"], "new-chat-button")

    def test_uia_metadata_ids_are_readable_for_matching(self) -> None:
        self.assertEqual(_readable_metadata_text("new-chat-button"), "new chat button")
        self.assertEqual(_readable_metadata_text("newChatButton"), "new Chat Button")

    def test_uia_does_not_use_metadata_for_unlabeled_containers(self) -> None:
        class ElementInfo:
            name = ""
            help_text = ""
            automation_id = "chatgpt-logo"

        class Element:
            element_info = ElementInfo()

            def window_text(self) -> str:
                return ""

        self.assertEqual(_element_text(Element(), "Pane"), "")

    def test_uia_items_do_not_claim_fake_confidence(self) -> None:
        item = _uia_item(
            text="Share",
            x=10,
            y=20,
            width=30,
            height=40,
            source="uia",
            control_type="Button",
            automation_id="share-button",
        )

        self.assertNotIn("confidence", item)
        self.assertEqual(item["source"], "uia")

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

    def test_screen_prompt_includes_app_context(self) -> None:
        prompt = build_prompt(
            question="how do I open Help?",
            active_app={"title": "VS Code", "process": "Code.exe", "supported": True},
            ocr_items=[],
            app_context="Help is in the top menu bar after Terminal. Shortcut: Alt+H.",
        )

        self.assertIn("Active app knowledge", prompt)
        self.assertIn("Help is in the top menu bar after Terminal", prompt)

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

    def test_normal_mode_does_not_execute_agent_tools(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1280,
            height=720,
            screen_width=1280,
            screen_height=720,
        )
        ai_response = {"summary": "Use Agent mode to open desktop apps.", "steps": []}

        with (
            patch("main.capture_screen", return_value=screenshot),
            patch("utils.window.get_target_window_element", return_value=None),
            patch("main.resolve_locator_fast_path", return_value=None),
            patch("main.get_active_window", return_value={"title": "VS Code", "process": "Code.exe", "supported": True}),
            patch("main.extract_visible_text", return_value=[]),
            patch("main.get_visible_ui_text", return_value=[]),
            patch("main.ask_model", return_value=ai_response),
            patch("main.try_run_agent_action", side_effect=AssertionError("agent tool should not run")),
        ):
            result = run("open Spotify", agent_mode=False)

        self.assertEqual(result["summary"], "Use Agent mode to open desktop apps.")
        self.assertNotIn("agent_action", result)

    def test_agent_mode_can_execute_open_app_tool_before_screen_capture(self) -> None:
        action = ToolResult(True, "open_app", "Opened Spotify.", {"app_name": "Spotify"})
        with (
            patch("main.try_run_agent_action", return_value=action),
            patch("main.capture_screen", side_effect=AssertionError("app launch should not require screen capture")),
            patch("main.get_active_window", return_value={"title": "Spotify", "process": "Spotify.exe", "supported": False}),
        ):
            result = run("open Spotify", agent_mode=True)

        self.assertEqual(result["summary"], "Opened Spotify.")
        self.assertEqual(result["agent_action"]["tool"], "open_app")

    def test_run_reuses_fresh_ui_map_cache_without_ocr_or_uia(self) -> None:
        screenshot = SimpleNamespace(
            path="cached-screen.png",
            width=1280,
            height=720,
            screen_width=1280,
            screen_height=720,
        )
        active_app = {"title": "Jarvis - Visual Studio Code", "process": "Code.exe", "supported": True}
        ai_response = {
            "summary": "Click Extensions.",
            "steps": [
                {
                    "step": 1,
                    "instruction": "Click Extensions.",
                    "target_ref": "@e1",
                    "target_text": "Extensions",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = UiMapCache(tmpdir, ttl_seconds=60)
            signature = window_signature(active_app, screenshot, target_pid=None)
            cache.save(
                signature,
                [
                    {
                        "ref": "@e1",
                        "text": "Extensions",
                        "x": 16,
                        "y": 170,
                        "width": 24,
                        "height": 24,
                        "confidence": 1,
                        "control_type": "Button",
                        "source": "uia",
                    }
                ],
            )

            with (
                patch("main.UI_MAP_CACHE", cache),
                patch("main.classify_request", return_value={"needs_screen": True}),
                patch("utils.window.get_target_window_element", return_value=None),
                patch("main.capture_screen", return_value=screenshot),
                patch("main.resolve_locator_fast_path", return_value=None),
                patch("main.get_active_window", return_value=active_app),
                patch("main.extract_visible_text", side_effect=AssertionError("OCR should be skipped")),
                patch("main.get_visible_ui_text", side_effect=AssertionError("UIA should be skipped")),
                patch("main.ask_model", return_value=ai_response),
            ):
                result = run("click extensions")

        self.assertEqual(result["steps"][0]["match"]["ref"], "@e1")
        self.assertEqual(result["ocr"]["items"][0]["text"], "Extensions")

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
            patch("main.ask_text_model", side_effect=AssertionError("preflight AI should be skipped")),
            patch("main.ask_model", return_value={"summary": "No app settings are visible.", "steps": []}),
        ):
            result = run("where is settings?")

        self.assertNotEqual(result["provider"], "local")
        self.assertEqual(result["steps"], [])

    def test_locator_question_uses_ocr_without_ai_when_uia_misses(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        ocr_items = [
            {
                "text": "Search or start new chat",
                "x": 80,
                "y": 120,
                "width": 240,
                "height": 28,
                "confidence": 0.95,
                "source": "ocr",
            }
        ]

        with (
            patch("main.capture_screen", return_value=screenshot),
            patch("utils.window.get_target_window_element", return_value=None),
            patch("main.get_active_window", return_value={"title": "WhatsApp", "process": "WhatsApp.exe"}),
            patch("main.get_visible_ui_text", return_value=[]),
            patch("main.extract_visible_text", return_value=ocr_items),
            patch("main.ask_text_model", side_effect=AssertionError("preflight AI should be skipped")),
            patch("main.ask_model", side_effect=AssertionError("guidance AI should be skipped")),
        ):
            result = run("where is search?")

        self.assertEqual(result["provider"], "local")
        self.assertEqual(result["steps"][0]["match"]["text"], "Search or start new chat")

    def test_matcher_returns_confidence_diagnostics(self) -> None:
        items = [
            {
                "text": "Underline",
                "x": 120,
                "y": 80,
                "width": 30,
                "height": 30,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
            }
        ]

        result = find_best_match_with_score("underline", items, "Locate the underline control.")

        self.assertIsNotNone(result)
        self.assertEqual(result["item"]["text"], "Underline")
        self.assertGreaterEqual(result["score"], 1.0)
        self.assertEqual(result["text_similarity"], 1.0)
        self.assertTrue(result["is_exact_text"])
        self.assertEqual(result["source"], "uia")
        self.assertEqual(result["control_type"], "button")
        self.assertEqual(result["candidate_count"], 1)

    def test_locator_keeps_exact_visible_text_local(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        items = [
            {
                "text": "lol",
                "x": 500,
                "y": 500,
                "width": 30,
                "height": 20,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Text",
            }
        ]

        with (
            patch("main.get_active_window", return_value={"title": "OneNote", "process": "onenote.exe"}),
            patch("main.get_visible_ui_text", return_value=items),
            patch("main.extract_visible_text", side_effect=AssertionError("OCR should be skipped")),
        ):
            result = resolve_locator_fast_path("where is lol?", screenshot, None, [], 0.0)

        self.assertIsNotNone(result)
        self.assertEqual(result["provider"], "local")
        self.assertEqual(result["steps"][0]["match"]["text"], "lol")

    def test_locator_defers_weak_control_match_to_ai(self) -> None:
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
                "confidence": 0.7,
                "source": "uia",
                "control_type": "Button",
            }
        ]

        with (
            patch("main.get_active_window", return_value={"title": "VS Code", "process": "code.exe"}),
            patch("main.get_visible_ui_text", return_value=items),
            patch("main.extract_visible_text", return_value=[]),
        ):
            result = resolve_locator_fast_path("where is settings button?", screenshot, None, [], 0.0)

        self.assertIsNone(result)

    def test_locator_defers_ambiguous_control_match_to_ai(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        items = [
            {
                "text": "Search",
                "x": 10,
                "y": 100,
                "width": 40,
                "height": 40,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
            },
            {
                "text": "Search",
                "x": 500,
                "y": 500,
                "width": 180,
                "height": 30,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Edit",
            },
        ]

        with (
            patch("main.get_active_window", return_value={"title": "App", "process": "app.exe"}),
            patch("main.get_visible_ui_text", return_value=items),
            patch("main.extract_visible_text", return_value=[]),
        ):
            result = resolve_locator_fast_path("where is search button?", screenshot, None, [], 0.0)

        self.assertIsNone(result)

    def test_locator_accepts_duplicate_exact_control_matches(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        items = [
            {
                "text": "New chat",
                "x": 20,
                "y": 90,
                "width": 44,
                "height": 44,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
            },
            {
                "text": "New chat",
                "x": 22,
                "y": 92,
                "width": 40,
                "height": 40,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
            },
        ]

        with (
            patch("main.get_active_window", return_value={"title": "ChatGPT", "process": "chatgpt.exe"}),
            patch("main.get_visible_ui_text", return_value=items),
            patch("main.extract_visible_text", side_effect=AssertionError("OCR should be skipped")),
        ):
            result = resolve_locator_fast_path("where is the new chat button?", screenshot, None, [], 0.0)

        self.assertIsNotNone(result)
        self.assertEqual(result["provider"], "local")
        self.assertEqual(result["steps"][0]["match"]["text"], "New chat")

    def test_locator_ai_fallback_skips_preflight(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        weak_items = [
            {
                "text": "Customize Layout...",
                "x": 1482,
                "y": 6,
                "width": 38,
                "height": 30,
                "confidence": 0.7,
                "source": "uia",
                "control_type": "Button",
            }
        ]
        ai_response = {
            "summary": "AI found it.",
            "steps": [{"step": 1, "instruction": "Click the Settings button.", "target_text": "Settings"}],
        }

        with (
            patch("main.capture_screen", return_value=screenshot),
            patch("utils.window.get_target_window_element", return_value=None),
            patch("main.get_active_window", return_value={"title": "App", "process": "app.exe"}),
            patch("main.get_visible_ui_text", return_value=weak_items),
            patch("main.extract_visible_text", return_value=[]),
            patch("main.ask_text_model", side_effect=AssertionError("preflight AI should be skipped")),
            patch("main.ask_model", return_value=ai_response),
        ):
            result = run("where is settings button?")

        self.assertEqual(result["summary"], "AI found it.")
        self.assertFalse(any("Preflight classification failed" in warning for warning in result["warnings"]))

    def test_locator_does_not_accept_single_letter_partial_for_long_search_bar_query(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        items = [
            {
                "text": "S",
                "x": 20,
                "y": 100,
                "width": 20,
                "height": 20,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Text",
            }
        ]

        with (
            patch("main.get_active_window", return_value={"title": "ChatGPT", "process": "chatgpt.exe"}),
            patch("main.get_visible_ui_text", return_value=items),
            patch("main.extract_visible_text", return_value=[]),
        ):
            result = resolve_locator_fast_path(
                "where is search bar for chatgpt to search and give it input?",
                screenshot,
                None,
                [],
                0.0,
            )

        self.assertIsNone(result)

    def test_locator_defers_icon_only_control_without_moving_mouse(self) -> None:
        screenshot = SimpleNamespace(
            path="screenshots/test.jpg",
            width=1728,
            height=1080,
            screen_width=2560,
            screen_height=1600,
        )
        icon_items = [
            {
                "text": "",
                "x": 1200,
                "y": 980,
                "width": 44,
                "height": 44,
                "confidence": 0.98,
                "source": "uia",
                "control_type": "Button",
            }
        ]

        with (
            patch("main.get_active_window", return_value={"title": "ChatGPT", "process": "chatgpt.exe"}),
            patch("main.get_visible_ui_text", return_value=icon_items),
            patch("main.extract_visible_text", return_value=[]),
            patch("main.ask_model", side_effect=AssertionError("direct fast path helper should not call AI")),
        ):
            result = resolve_locator_fast_path("where is dictate?", screenshot, None, [], 0.0)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
