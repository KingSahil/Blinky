#!/usr/bin/env python3
"""Tests for Browser-Use autonomous agent tool in Blinky."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tools.browser_use_tool import (
    get_browser_use_llm,
    resolve_browser_use_request,
    run_browser_task,
)
from main import classify_request, run_browser_use_tool


@patch.dict("os.environ", {"BLINKY_BROWSER_ENGINE": "browser_use", "BLINKY_DESKTOP_ENGINE": "legacy"})
class BrowserUseToolTests(unittest.TestCase):
    def setUp(self):
        discovery = patch("tools.browser_use_tool.get_existing_browser_endpoint", return_value=None)
        discovery.start()
        self.addCleanup(discovery.stop)

    def test_resolve_browser_use_request_phrasings(self):
        valid_queries = [
            "go to https://example.com and find the heading",
            "navigate to https://github.com/KingSahil/Blinky and extract contributors",
            "open website https://news.ycombinator.com and check top story",
            "use browser agent to search for laptops on amazon.com",
            "click on login button on https://example.com",
            "extract the data from https://weather.com",
            "run browser-use to find cheap flights on kayak.com",
            "go to https://instagram.com/blinky_ai and tell me the first comment of latest video",
            "tell me the first comment of latest video on https://instagram.com/blinky_ai",
        ]
        for q in valid_queries:
            res = resolve_browser_use_request(q)
            self.assertIsNotNone(res, f"Failed to match valid query: {q}")
            self.assertEqual(res["action"], "browser_use")
            self.assertEqual(res["task"], q)

    def test_rejects_unrelated_queries(self):
        invalid_queries = [
            "write hello in cell a1",
            "turn on red light",
            "play despacito on spotify",
            "what is the meaning of life?",
        ]
        for q in invalid_queries:
            res = resolve_browser_use_request(q)
            self.assertIsNone(res, f"Should not match unrelated query: {q}")

    @patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_gemini_key"})
    def test_get_browser_use_llm_gemini(self):
        primary, fallback = get_browser_use_llm()
        self.assertIsNotNone(primary)
        self.assertIsNotNone(fallback)

    @patch("browser_use.Agent")
    @patch("browser_use.Browser")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_gemini_key"})
    def test_run_browser_task_success(self, mock_browser_cls, mock_agent_cls):
        import asyncio

        mock_history = MagicMock()
        mock_history.final_result.return_value = "Found heading 'Example Domain'"
        mock_history.action_names.return_value = ["navigate", "done"]
        mock_history.errors.return_value = []

        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_history)
        mock_agent_cls.return_value = mock_agent_instance

        res = asyncio.run(run_browser_task("Go to https://example.com and get heading", headless=True))
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "browser_use")
        self.assertEqual(res["result"], "Found heading 'Example Domain'")
        self.assertEqual(res["steps"], 2)
        mock_browser_cls.assert_called_with(channel="msedge", headless=True)

    @patch("browser_use.Agent")
    @patch("browser_use.Browser")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_gemini_key"})
    def test_run_browser_task_with_cdp_url(self, mock_browser_cls, mock_agent_cls):
        import asyncio

        mock_history = MagicMock()
        mock_history.final_result.return_value = "Connected to existing tab"
        mock_history.action_names.return_value = ["click", "done"]
        mock_history.errors.return_value = []

        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_history)
        mock_agent_cls.return_value = mock_agent_instance

        res = asyncio.run(run_browser_task("Complete form in existing browser", cdp_url="http://localhost:9222"))
        self.assertTrue(res["success"])
        mock_browser_cls.assert_called_with(
            cdp_url="http://localhost:9222",
            is_local=True,
            use_cloud=False,
            enable_default_extensions=False,
            auto_download_pdfs=False,
        )

    def test_classify_request_routes_to_browser_use(self):
        res = classify_request("go to https://example.com and extract heading", None, [])
        self.assertEqual(res["intent"], "BROWSER_USE")
        self.assertEqual(res["extracted_params"]["action"], "browser_use")

    def test_classify_request_routes_instagram_url_to_browser_use(self):
        res = classify_request("go to https://instagram.com/blinky_ai and tell me the first comment of latest video", None, [])
        self.assertEqual(res["intent"], "BROWSER_USE")
        self.assertNotEqual(res["intent"], "VIDEO_EDIT")

    @patch("tools.browser_use_tool.run_browser_task")
    def test_run_browser_use_tool_returns_clean_blinky_result(self, mock_run_task):
        mock_run_task.return_value = {
            "success": True,
            "action": "browser_use",
            "result": "Completed web automation.",
        }
        res = run_browser_use_tool(
            {"task": "Go to website and click submit"},
            started=0.0,
            warnings=[],
        )
        self.assertEqual(res["summary"], "Completed web automation.")
        self.assertEqual(res["active_app"]["title"], "Connected browser")
        self.assertEqual(res["active_app"]["process"], "")


if __name__ == "__main__":
    unittest.main()
