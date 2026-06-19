import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser_agent import parse_browser_plan, plan_browser_action, run_browser_plan


class BrowserAgentPlanTests(unittest.TestCase):
    def test_parse_site_search_plan(self):
        plan = parse_browser_plan(json.dumps({
            "match": True,
            "action": "site_search",
            "site": "blinkit",
            "query": "gaming chair",
            "confidence": 92,
        }))

        self.assertEqual(plan, {
            "match": True,
            "action": "site_search",
            "site": "blinkit",
            "query": "gaming chair",
            "confidence": 92,
        })

    def test_rejects_unsafe_actions(self):
        plan = parse_browser_plan(json.dumps({
            "match": True,
            "action": "run_python",
            "site": "blinkit",
            "query": "gaming chair",
            "confidence": 99,
        }))

        self.assertEqual(plan["match"], False)
        self.assertIn("Unsupported browser action", plan["reasoning"])

    def test_plan_browser_action_uses_ai_for_unknown_sites(self):
        with patch(
            "browser_agent.ask_text_model",
            return_value=json.dumps({
                "match": True,
                "action": "site_search",
                "site": "blinkit",
                "query": "gaming chair",
                "confidence": 91,
            }),
        ) as mock_ask:
            plan = plan_browser_action("give me gaming chair from blinkit")

        self.assertEqual(plan["action"], "site_search")
        self.assertEqual(plan["site"], "blinkit")
        self.assertEqual(plan["query"], "gaming chair")
        mock_ask.assert_called_once()


class BrowserAgentRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_site_search_opens_search_engine_site_query(self):
        controller = AsyncMock()
        controller.open_url.return_value = {
            "url": "https://www.google.com/search?q=site%3Ablinkit+gaming+chair",
            "title": "gaming chair - Google Search",
        }

        result = await run_browser_plan({
            "match": True,
            "action": "site_search",
            "site": "blinkit",
            "query": "gaming chair",
            "confidence": 91,
        }, controller=controller)

        controller.open_url.assert_awaited_once_with(
            "https://www.google.com/search?q=site%3Ablinkit+gaming+chair"
        )
        self.assertEqual(result["response"], "Opened web search for gaming chair on blinkit.")
        self.assertEqual(result["url"], "https://www.google.com/search?q=site%3Ablinkit+gaming+chair")


if __name__ == "__main__":
    unittest.main()
