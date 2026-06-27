import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_router import (
    audit_code,
    build_generator_prompt,
    execute_script,
    handle_request,
    is_playwright_health_check_request,
    repair_generated_playwright_code,
    resolve_ai_open_url_request,
    resolve_open_url_request,
    resolve_web_search_request,
    resolve_youtube_search_request,
)


class AgentRouterOpenUrlTests(unittest.TestCase):
    def test_resolves_known_site(self):
        self.assertEqual(
            resolve_open_url_request("open youtube"),
            ("YouTube", "https://www.youtube.com"),
        )

    def test_resolves_whatsapp(self):
        self.assertEqual(
            resolve_open_url_request("open whatsapp"),
            ("WhatsApp", "https://web.whatsapp.com"),
        )

    def test_resolves_domain(self):
        self.assertEqual(
            resolve_open_url_request("go to example.com"),
            ("example.com", "https://example.com"),
        )

    def test_ignores_non_open_request(self):
        self.assertIsNone(resolve_open_url_request("what is youtube"))

    def test_resolves_web_search(self):
        self.assertEqual(
            resolve_web_search_request("search never gonna give u up"),
            ("never gonna give u up", "https://www.google.com/search?q=never+gonna+give+u+up"),
        )

    def test_resolves_youtube_search(self):
        self.assertEqual(
            resolve_youtube_search_request("open mythpat on youtube"),
            ("mythpat", "https://www.youtube.com/results?search_query=mythpat"),
        )

    def test_resolves_youtube_search_with_in_youtube(self):
        self.assertEqual(
            resolve_youtube_search_request("play latest mythpat video in youtube"),
            ("latest mythpat video", "https://www.youtube.com/results?search_query=latest+mythpat+video"),
        )

    def test_resolves_youtube_search_when_youtube_is_before_video(self):
        self.assertEqual(
            resolve_youtube_search_request("play latest mrbeast youtube video"),
            ("latest mrbeast video", "https://www.youtube.com/results?search_query=latest+mrbeast+video"),
        )

    def test_ai_resolves_open_site_intent(self):
        with patch(
            "agent_router.ask_text_model",
            return_value='{"match": true, "label": "WhatsApp", "url": "https://web.whatsapp.com", "confidence": 95, "reasoning": "official web app"}',
        ):
            self.assertEqual(
                resolve_ai_open_url_request("open whatsapp"),
                ("WhatsApp", "https://web.whatsapp.com"),
            )

    def test_ai_open_rejects_low_confidence(self):
        with patch(
            "agent_router.ask_text_model",
            return_value='{"match": true, "label": "Unknown", "url": "https://example.com", "confidence": 45, "reasoning": "not sure"}',
        ):
            self.assertIsNone(resolve_ai_open_url_request("open something vague"))

    def test_detects_playwright_health_check_request(self):
        self.assertTrue(is_playwright_health_check_request("test playwright"))
        self.assertTrue(is_playwright_health_check_request("does playwright work?"))
        self.assertFalse(is_playwright_health_check_request("search playwright docs"))

    def test_generator_prompt_requires_bounded_playwright_waits(self):
        prompt = build_generator_prompt("find an example")

        self.assertIn("page.set_default_timeout", prompt)
        self.assertIn("Do not await set_default_timeout", prompt)
        self.assertIn("Do not pass timeout", prompt)
        self.assertIn("domcontentloaded", prompt)
        self.assertIn("Return JSON", prompt)

    def test_repairs_common_generated_playwright_api_mistakes(self):
        code = """
async def main():
    await page.set_default_timeout(8000)
    results = await page.query_selector_all("h3", timeout=8000)
    title = await result.text_content(timeout=8000)
    link = await result.evaluate("(element) => element.closest('a').href", timeout=8000)
"""

        repaired = repair_generated_playwright_code(code)

        self.assertIn("page.set_default_timeout(8000)", repaired)
        self.assertNotIn("await page.set_default_timeout", repaired)
        self.assertIn('query_selector_all("h3")', repaired)
        self.assertIn("text_content()", repaired)
        self.assertIn('evaluate("(element) => element.closest(\'a\').href")', repaired)
        self.assertNotIn("timeout=8000", repaired)

    def test_audit_rejects_generated_playwright_without_bounded_waits(self):
        code = """
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_selector("h1")
"""

        ok, reason = audit_code(code)

        self.assertFalse(ok)
        self.assertIn("bounded timeout", reason)


class AgentRouterOpenUrlRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_script_timeout_reports_requested_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "slow.py"
            script.write_text(
                "import time\n"
                "time.sleep(2)\n"
                "print('{\"ok\": true}')\n",
                encoding="utf-8",
            )

            success, status, details = await execute_script(script, {}, timeout=0.1)

        self.assertFalse(success)
        self.assertEqual(status, "TIMEOUT")
        self.assertIn("0.1 seconds", details)

    async def test_playwright_health_check_bypasses_llm_routing(self):
        with (
            patch("agent_router.run_playwright_health_check", return_value=(True, "Playwright is working.")) as mock_health,
            patch("agent_router.ask_text_model", side_effect=AssertionError("LLM should not be called")),
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"test playwright"}')

        mock_health.assert_called_once()
        mock_send.assert_any_call("abc", "success", data={"response": "Playwright is working."})

    async def test_open_request_bypasses_llm_routing(self):
        with (
            patch("agent_router.webbrowser.open", return_value=True) as mock_open,
            patch("agent_router.ask_text_model", side_effect=AssertionError("LLM should not be called")),
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"open youtube"}')

        mock_open.assert_called_once_with("https://www.youtube.com")
        mock_send.assert_any_call("abc", "success", data={"response": "Opened YouTube."})

    async def test_whatsapp_open_request_uses_ai_url_resolver(self):
        with (
            patch("agent_router.webbrowser.open", return_value=True) as mock_open,
            patch("agent_router.ask_text_model", side_effect=AssertionError("LLM should not be called")),
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"open whatsapp"}')

        mock_open.assert_called_once_with("https://web.whatsapp.com")
        mock_send.assert_any_call("abc", "success", data={"response": "Opened WhatsApp."})

    async def test_search_request_bypasses_llm_routing(self):
        with (
            patch("agent_router.webbrowser.open", return_value=True) as mock_open,
            patch("agent_router.ask_text_model", side_effect=AssertionError("LLM should not be called")),
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"search never gonna give u up"}')

        mock_open.assert_called_once_with("https://www.google.com/search?q=never+gonna+give+u+up")
        mock_send.assert_any_call("abc", "success", data={"response": "Searched for never gonna give u up."})

    async def test_youtube_search_request_bypasses_llm_routing(self):
        with (
            patch("agent_router.webbrowser.open", return_value=True) as mock_open,
            patch("agent_router.ask_text_model", side_effect=AssertionError("LLM should not be called")),
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"open mythpat on youtube"}')

        mock_open.assert_called_once_with("https://www.youtube.com/results?search_query=mythpat")
        mock_send.assert_any_call("abc", "success", data={"response": "Searched YouTube for mythpat."})

    async def test_youtube_search_in_youtube_request_bypasses_llm_routing(self):
        from unittest.mock import AsyncMock
        with (
            patch("agent_router.webbrowser.open", return_value=True) as mock_open,
            patch("agent_router.ask_text_model", side_effect=AssertionError("LLM should not be called")),
            patch("computer_use.tools.resolve_youtube_video_url", new_callable=AsyncMock) as mock_resolve,
            patch("agent_router.send_response") as mock_send,
        ):
            mock_resolve.return_value = "https://www.youtube.com/watch?v=mocked_id"
            await handle_request('{"requestId":"abc","query":"play latest mythpat video in youtube"}')

        mock_open.assert_called_once_with("https://www.youtube.com/watch?v=mocked_id")
        mock_send.assert_any_call("abc", "success", data={"response": "Playing latest video on YouTube."})

    async def test_youtube_video_phrase_bypasses_tool_router(self):
        from unittest.mock import AsyncMock
        with (
            patch("agent_router.webbrowser.open", return_value=True) as mock_open,
            patch("agent_router.ask_text_model", side_effect=AssertionError("LLM should not be called")),
            patch("agent_router.load_registry_async", side_effect=AssertionError("Tool router should not be called")),
            patch("computer_use.tools.resolve_youtube_video_url", new_callable=AsyncMock) as mock_resolve,
            patch("agent_router.send_response") as mock_send,
        ):
            mock_resolve.return_value = "https://www.youtube.com/watch?v=mocked_id2"
            await handle_request('{"requestId":"abc","query":"play latest mrbeast youtube video"}')

        mock_open.assert_called_once_with("https://www.youtube.com/watch?v=mocked_id2")
        mock_send.assert_any_call("abc", "success", data={"response": "Playing latest video on YouTube."})

    async def test_unknown_site_search_uses_ai_browser_plan_before_tool_generation(self):
        plan = {
            "match": True,
            "action": "site_search",
            "site": "blinkit",
            "query": "gaming chair",
            "confidence": 91,
        }
        browser_result = {
            "response": "Opened web search for gaming chair on blinkit.",
            "url": "https://www.google.com/search?q=site%3Ablinkit+gaming+chair",
            "title": "gaming chair - Google Search",
        }
        with (
            patch("agent_router.plan_browser_action", return_value=plan) as mock_plan,
            patch("agent_router.run_browser_plan", return_value=browser_result) as mock_run,
            patch("agent_router.load_registry_async", side_effect=AssertionError("Tool router should not be called")),
            patch("agent_router.execute_script", side_effect=AssertionError("Generated scripts should not run")),
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"give me gaming chair from blinkit"}')

        mock_plan.assert_called_once_with("give me gaming chair from blinkit")
        mock_run.assert_awaited_once_with(plan)
        mock_send.assert_any_call("abc", "success", data=browser_result)

    async def test_local_spotify_playback_via_agent_router(self):
        preflight_payload = {
            "intent": "MEDIA_PLAYBACK",
            "needs_screen": False,
            "is_continuation": False,
            "extracted_params": {
                "song_name": "blinding lights",
                "platform": "spotify"
            }
        }
        from computer_use.tools import ToolResult
        mock_result = ToolResult(True, "play_spotify", "Playing 'blinding lights' in Spotify.", {})
        with (
            patch("main.classify_request", return_value=preflight_payload) as mock_classify,
            patch("computer_use.tools.play_spotify_track_tool", return_value=mock_result) as mock_play,
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"play blinding lights on spotify"}')

        mock_classify.assert_called_once()
        mock_play.assert_called_once_with("blinding lights")
        mock_send.assert_any_call("abc", "success", data={"response": "Playing 'blinding lights' in Spotify."})

    async def test_local_app_open_via_agent_router(self):
        preflight_payload = {
            "intent": "OPEN_APP",
            "needs_screen": False,
            "is_continuation": False,
            "extracted_params": {
                "app_name": "spotify"
            }
        }
        from computer_use.tools import ToolResult
        mock_result = ToolResult(True, "open_app", "Opened spotify.", {})
        with (
            patch("main.classify_request", return_value=preflight_payload) as mock_classify,
            patch("computer_use.tools.open_app_tool", return_value=mock_result) as mock_open,
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"open spotify"}')

        mock_classify.assert_called_once()
        mock_open.assert_called_once_with("spotify")
        mock_send.assert_any_call("abc", "success", data={"response": "Opened spotify."})


if __name__ == "__main__":
    unittest.main()
