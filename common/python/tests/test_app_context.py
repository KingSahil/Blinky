import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from app_context import get_app_context
import app_context.registry as registry

def test_vscode_context_includes_help_location() -> None:
    context = get_app_context({"title": "Jarvis - Visual Studio Code", "process": "Code.exe"})

    assert "Help is in the top menu bar after Terminal" in context
    assert "Ctrl+Shift+X" in context

def test_windows_apps_context_is_always_available() -> None:
    # Use a mock/temp directory for context files to avoid writing to codebase disk
    with patch("app_context.registry.APP_CONTEXT_DIR") as mock_dir:
        mock_dir.exists.return_value = True
        mock_dir.__truediv__.return_value = mock_dir
        mock_dir.read_text.return_value = "Desktop apps can be opened"
        
        # Mock generate_context_file to not write files
        with patch("app_context.registry.generate_context_file", return_value=True):
            context = get_app_context({"title": "Unknown", "process": "unknown.exe"})

    assert "Desktop apps can be opened" in context

@patch("wil.searxng_client.SearXNGClient.search_category", new_callable=AsyncMock)
@patch("ai.client.ask_text_model")
def test_dynamic_context_generation_success(mock_ask_model, mock_search, tmp_path):
    # Setup tmp path for app context files
    with patch("app_context.registry.APP_CONTEXT_DIR", tmp_path):
        mock_search.return_value = [
            {"title": "ChatGPT Keyboard Shortcuts", "content": "Press Alt+Space to open companion, Ctrl+comma for settings."}
        ]
        mock_ask_model.return_value = {
            "context": "# ChatGPT App\n\n- Settings: Ctrl+,\n- Help: Click Profile -> Help"
        }
        
        # Get context for unregistered app
        context = get_app_context({"title": "ChatGPT Desktop", "process": "chatgpt.exe"})
        
        # Verify custom content is in context
        assert "ChatGPT App" in context
        assert "Settings: Ctrl+," in context
        
        # Verify it created the file on disk
        created_file = tmp_path / "chatgpt.md"
        assert created_file.exists()
        assert "Settings: Ctrl+," in created_file.read_text()

@patch("wil.searxng_client.SearXNGClient.search_category", new_callable=AsyncMock)
@patch("ai.client.ask_text_model")
def test_dynamic_context_generation_fallback(mock_ask_model, mock_search, tmp_path):
    # Setup tmp path for app context files
    with patch("app_context.registry.APP_CONTEXT_DIR", tmp_path):
        # Force LLM model call to raise exception
        mock_search.side_effect = Exception("SearXNG down")
        mock_ask_model.side_effect = Exception("LLM down")
        
        # Get context for unregistered app
        context = get_app_context({"title": "CustomApp Title", "process": "customapp.exe"})
        
        # Verify boilerplate fallback context
        assert "This is a Windows application: customapp.exe" in context
        assert "F1 for Help" in context
        
        # Verify it created the fallback file on disk
        created_file = tmp_path / "customapp.md"
        assert created_file.exists()
        assert "customapp.exe" in created_file.read_text()
