import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_router import (
    handle_request,
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


class AgentRouterOpenUrlRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_request_bypasses_llm_routing(self):
        with (
            patch("agent_router.webbrowser.open", return_value=True) as mock_open,
            patch("agent_router.ask_text_model", side_effect=AssertionError("LLM should not be called")),
            patch("agent_router.send_response") as mock_send,
        ):
            await handle_request('{"requestId":"abc","query":"open youtube"}')

        mock_open.assert_called_once_with("https://www.youtube.com")
        mock_send.assert_any_call("abc", "success", data={"response": "Opened YouTube."})

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


if __name__ == "__main__":
    unittest.main()
