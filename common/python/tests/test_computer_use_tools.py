from unittest.mock import Mock, patch

from computer_use.agent import cleanup_app_name, try_run_agent_action
from computer_use.tools import ToolResult, find_start_app, normalize_app_name, normalize_shortcut, open_app_tool, open_app_via_windows_search, open_web_destination_tool


def test_cleanup_app_name_removes_trailing_app_word() -> None:
    assert cleanup_app_name("Spotify app") == "Spotify"


def test_agent_routes_open_app_request() -> None:
    with patch("computer_use.agent.open_app_tool") as open_app:
        open_app.return_value = Mock()
        result = try_run_agent_action("open Spotify")

    assert result is open_app.return_value
    open_app.assert_called_once_with("Spotify")


def test_agent_routes_web_destination_to_browser_tool() -> None:
    with (
        patch("computer_use.agent.open_app_tool", side_effect=AssertionError("web destination should not open as a desktop app")),
        patch("computer_use.agent.open_web_destination_tool") as open_web,
    ):
        open_web.return_value = Mock()
        result = try_run_agent_action("open YouTube")

    assert result is open_web.return_value
    open_web.assert_called_once_with("YouTube")


def test_open_web_destination_uses_known_url() -> None:
    with patch("computer_use.tools.webbrowser.open", return_value=True) as open_url:
        result = open_web_destination_tool("YouTube")

    assert result.success is True
    assert result.tool == "open_web_destination"
    assert result.details["url"] == "https://www.youtube.com/"
    open_url.assert_called_once_with("https://www.youtube.com/")


def test_agent_routes_help_menu_to_shortcut_when_context_matches() -> None:
    observation = {
        "active_app": {"process": "Code.exe"},
        "app_context": "Help is in the top menu bar after Terminal. Shortcut: Alt+H.",
    }
    with patch("computer_use.agent.shortcut_tool") as shortcut:
        shortcut.return_value = Mock()
        result = try_run_agent_action("open Help", observation)

    assert result is shortcut.return_value
    shortcut.assert_called_once_with("alt+h")


def test_find_start_app_parses_powershell_json() -> None:
    completed = Mock(returncode=0, stdout='{"Name":"Spotify","AppID":"SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"}')
    with patch("computer_use.tools.subprocess.run", return_value=completed):
        result = find_start_app("spotify")

    assert result == {"Name": "Spotify", "AppID": "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"}


def test_open_app_uses_start_apps_appid_on_windows() -> None:
    with (
        patch("computer_use.tools.os.name", "nt"),
        patch("computer_use.tools.find_start_app", return_value={"Name": "Notion", "AppID": "Notion.App!Notion"}),
        patch("computer_use.tools.subprocess.Popen") as popen,
        patch("computer_use.tools.time.sleep"),
    ):
        result = open_app_tool("Notion")

    assert result.success is True
    assert result.tool == "open_app"
    popen.assert_called_once_with(["explorer.exe", "shell:AppsFolder\\Notion.App!Notion"])


def test_open_app_uses_protocol_before_start_apps() -> None:
    with (
        patch("computer_use.tools.os.name", "nt"),
        patch("computer_use.tools.os.startfile") as startfile,
        patch("computer_use.tools.find_start_app", side_effect=AssertionError("StartApps should not run first")),
        patch("computer_use.tools.time.sleep"),
    ):
        result = open_app_tool("Edge")

    assert result.success is True
    assert result.details["method"] == "app_protocol"
    startfile.assert_called_once_with("microsoft-edge:")


def test_open_app_uses_windows_search_as_last_fallback() -> None:
    with (
        patch("computer_use.tools.os.name", "nt"),
        patch("computer_use.tools.os.startfile", side_effect=OSError("protocol unavailable")),
        patch("computer_use.tools.find_start_app", return_value=None),
        patch("computer_use.tools.open_app_via_windows_search") as search,
    ):
        search.return_value = ToolResult(True, "open_app", "Searched Windows and opened WhatsApp.", {"method": "windows_search_enter"})
        result = open_app_tool("WhatsApp installed")

    assert result.success is True
    search.assert_called_once_with("whatsapp")


def test_normalize_app_name_removes_filler_words() -> None:
    assert normalize_app_name("WhatsApp installed app please") == "whatsapp"
    assert normalize_app_name("Microsoft Edge browser") == "microsoft edge"


def test_windows_search_fallback_clicks_visible_result() -> None:
    match = {"text": "WhatsApp", "x": 100, "y": 200, "width": 160, "height": 40}
    with (
        patch("computer_use.tools.os.name", "nt"),
        patch("pywinauto.keyboard.send_keys") as send_keys,
        patch("computer_use.tools.find_windows_search_result", return_value=match),
        patch("computer_use.tools.click_item_center") as click_item,
        patch("computer_use.tools.time.sleep"),
    ):
        result = open_app_via_windows_search("whatsapp")

    assert result.success is True
    assert result.details["method"] == "windows_search_screen_match"
    click_item.assert_called_once_with(match)
    assert send_keys.call_count == 2


def test_normalize_shortcut_translates_alt_h() -> None:
    assert normalize_shortcut("alt+h") == "%h"


def test_agent_ignores_in_app_open_requests() -> None:
    assert try_run_agent_action("open new tab") is None
    assert try_run_agent_action("open settings") is None
    assert try_run_agent_action("open status on whatsapp") is None
