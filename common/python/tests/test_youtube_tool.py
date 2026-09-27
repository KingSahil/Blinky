import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from computer_use.agent import try_run_agent_action
from computer_use.tools import play_youtube_video_tool, extract_channel_from_query

def test_agent_routes_play_youtube_in_youtube():
    with patch("computer_use.tools.play_youtube_video_tool") as mock_play:
        mock_play.return_value = MagicMock()
        result = try_run_agent_action("play latest video of mythpat in youtube")
        
    assert result is mock_play.return_value
    mock_play.assert_called_once_with("latest video of mythpat")

def test_agent_routes_play_youtube_on_youtube():
    with patch("computer_use.tools.play_youtube_video_tool") as mock_play:
        mock_play.return_value = MagicMock()
        result = try_run_agent_action("play mythpat's latest video on youtube")
        
    assert result is mock_play.return_value
    mock_play.assert_called_once_with("mythpat's latest video")

def test_agent_routes_play_youtube_prefix():
    with patch("computer_use.tools.play_youtube_video_tool") as mock_play:
        mock_play.return_value = MagicMock()
        result = try_run_agent_action("play youtube funny cats")
        
    assert result is mock_play.return_value
    mock_play.assert_called_once_with("funny cats")

def test_extract_channel_from_query():
    assert extract_channel_from_query("play latest video of mythpat on youtube") == "mythpat"
    assert extract_channel_from_query("play mythpat's latest video") == "mythpat"
    assert extract_channel_from_query("play latest mythpat video on youtube") == "mythpat"
    assert extract_channel_from_query("mythpat latest video") == "mythpat"
    assert extract_channel_from_query("play coding tutorial on youtube") is None

@pytest.mark.asyncio
@patch("computer_use.tools.webbrowser.open")
@patch("computer_use.tools.resolve_youtube_video_url", new_callable=AsyncMock)
async def test_play_youtube_success(mock_resolve, mock_open):
    mock_resolve.return_value = "https://www.youtube.com/watch?v=_XxLyzgoRlU"
    
    result = play_youtube_video_tool("latest video of mythpat")
    
    assert result.success is True
    assert result.details["video_url"] == "https://www.youtube.com/watch?v=_XxLyzgoRlU"
    mock_open.assert_called_once_with("https://www.youtube.com/watch?v=_XxLyzgoRlU")

@pytest.mark.asyncio
@patch("computer_use.tools.webbrowser.open")
@patch("computer_use.tools.resolve_youtube_video_url", new_callable=AsyncMock)
async def test_play_youtube_fallback_on_fail(mock_resolve, mock_open):
    mock_resolve.return_value = None
    
    result = play_youtube_video_tool("funny cats")
    
    assert result.success is True
    assert "fallback_url" in result.details
    mock_open.assert_called_once()
    assert "search_query=funny%20cats" in mock_open.call_args[0][0]
