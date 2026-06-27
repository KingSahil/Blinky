import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from computer_use.agent import try_run_agent_action
from computer_use.tools import ToolResult, play_spotify_track_tool

def test_agent_routes_play_spotify_in_spotify():
    with patch("computer_use.tools.play_spotify_track_tool") as mock_play:
        mock_play.return_value = MagicMock()
        result = try_run_agent_action("play blinding lights in spotify")
        
    assert result is mock_play.return_value
    mock_play.assert_called_once_with("blinding lights")

def test_agent_routes_play_spotify_on_spotify():
    with patch("computer_use.tools.play_spotify_track_tool") as mock_play:
        mock_play.return_value = MagicMock()
        result = try_run_agent_action("play blinding lights on spotify")
        
    assert result is mock_play.return_value
    mock_play.assert_called_once_with("blinding lights")

def test_agent_routes_play_spotify_prefix():
    with patch("computer_use.tools.play_spotify_track_tool") as mock_play:
        mock_play.return_value = MagicMock()
        result = try_run_agent_action("play spotify blinding lights")
        
    assert result is mock_play.return_value
    mock_play.assert_called_once_with("blinding lights")

@pytest.mark.asyncio
@patch("computer_use.tools.os.name", "posix")
@patch("computer_use.tools.platform.system", return_value="Linux")
@patch("computer_use.tools.open_spotify_uri_linux")
@patch("wil.searxng_client.SearXNGClient.search_category", new_callable=AsyncMock)
async def test_play_spotify_linux_uses_desktop_uri_handler(mock_search_category, mock_open_linux, mock_platform):
    mock_search_category.return_value = [
        {"url": "https://open.spotify.com/track/6qYkmqFsXbj8CQjAdbYz07", "title": "Blinding Lights"}
    ]
    mock_open_linux.return_value = ToolResult(
        True,
        "open_spotify_uri",
        "Opened Spotify URI.",
        {"method": "xdg-open", "track_uri": "spotify:track:6qYkmqFsXbj8CQjAdbYz07"},
    )

    result = play_spotify_track_tool("blinding lights")
        
    assert result.success is True
    assert result.details["track_uri"] == "spotify:track:6qYkmqFsXbj8CQjAdbYz07"
    assert result.details["method"] == "xdg-open"
    mock_open_linux.assert_called_once_with("spotify:track:6qYkmqFsXbj8CQjAdbYz07")

@pytest.mark.asyncio
@patch("computer_use.tools.os.name", "nt")
@patch("computer_use.tools.os.startfile", create=True)
@patch("wil.searxng_client.SearXNGClient.search_category", new_callable=AsyncMock)
async def test_play_spotify_via_searxng_success(mock_search_category, mock_startfile):
    # Mock SearXNG returning a valid spotify track URL
    mock_search_category.return_value = [
        {"url": "https://open.spotify.com/track/6qYkmqFsXbj8CQjAdbYz07", "title": "Blinding Lights"}
    ]
    
    result = play_spotify_track_tool("blinding lights")
    
    assert result.success is True
    assert result.details["track_uri"] == "spotify:track:6qYkmqFsXbj8CQjAdbYz07"
    mock_startfile.assert_called_once_with("spotify:track:6qYkmqFsXbj8CQjAdbYz07")
    mock_search_category.assert_called_once()

@pytest.mark.asyncio
@patch("computer_use.tools.os.name", "nt")
@patch("computer_use.tools.os.startfile", create=True)
@patch("wil.searxng_client.SearXNGClient.search_category", new_callable=AsyncMock)
@patch("wil.http_fetcher.fetch_html", new_callable=AsyncMock)
async def test_play_spotify_via_ddg_fallback(mock_fetch_html, mock_search_category, mock_startfile):
    # 1. SearXNG fails (raises exception or returns empty)
    mock_search_category.side_effect = Exception("SearXNG down")
    
    # 2. DuckDuckGo returns HTML containing track ID
    mock_fetch_html.return_value = """
    <html>
        <body>
            <a href="https://open.spotify.com/track/6qYkmqFsXbj8CQjAdbYz07">Blinding Lights</a>
        </body>
    </html>
    """
    
    result = play_spotify_track_tool("blinding lights")
    
    assert result.success is True
    assert result.details["track_uri"] == "spotify:track:6qYkmqFsXbj8CQjAdbYz07"
    mock_startfile.assert_called_once_with("spotify:track:6qYkmqFsXbj8CQjAdbYz07")
    mock_fetch_html.assert_called_once()

@pytest.mark.asyncio
@patch("computer_use.tools.os.name", "nt")
@patch("wil.searxng_client.SearXNGClient.search_category", new_callable=AsyncMock)
@patch("wil.http_fetcher.fetch_html", new_callable=AsyncMock)
async def test_play_spotify_not_found(mock_fetch_html, mock_search_category):
    # Both search attempts fail to return any track URL
    mock_search_category.return_value = []
    mock_fetch_html.return_value = "<html>No results</html>"
    
    result = play_spotify_track_tool("some unknown track 12345")
    
    assert result.success is False
    assert "Could not find track" in result.message

def test_clean_song_query():
    from computer_use.tools import clean_song_query
    assert clean_song_query("any latest subh song") == "subh"
    assert clean_song_query("play cheques") == "play cheques"
    assert clean_song_query("the blinding lights") == "blinding lights"
    assert clean_song_query("latest new song by shubh") == "shubh"

def test_agent_routes_complex_query():
    with patch("computer_use.tools.play_spotify_track_tool") as mock_play:
        mock_play.return_value = MagicMock()
        result = try_run_agent_action("play any latest subh song in spotify")
        
    assert result is mock_play.return_value
    mock_play.assert_called_once_with("any latest subh song")

def test_agent_routes_voice_command():
    with patch("computer_use.tools.play_spotify_track_tool") as mock_play:
        mock_play.return_value = MagicMock()
        
        # Test punctuation stripping
        result = try_run_agent_action("play blinding lights in spotify.")
        assert result is mock_play.return_value
        
        result_q = try_run_agent_action("play blinding lights on spotify?")
        assert result_q is mock_play.return_value
        
        result_ex = try_run_agent_action("play blinding lights in spotify!  ")
        assert result_ex is mock_play.return_value

def test_agent_routes_stop_spotify():
    with patch("computer_use.agent.shortcut_tool") as mock_shortcut:
        mock_shortcut.return_value = MagicMock()
        
        result_stop = try_run_agent_action("stop spotify")
        assert result_stop is mock_shortcut.return_value
        mock_shortcut.assert_called_with("media_play_pause")
        
        result_pause = try_run_agent_action("pause music")
        assert result_pause is mock_shortcut.return_value
        
        result_resume = try_run_agent_action("resume playback")
        assert result_resume is mock_shortcut.return_value
