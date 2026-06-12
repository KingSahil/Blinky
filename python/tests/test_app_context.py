from app_context import get_app_context


def test_vscode_context_includes_help_location() -> None:
    context = get_app_context({"title": "Jarvis - Visual Studio Code", "process": "Code.exe"})

    assert "Help is in the top menu bar after Terminal" in context
    assert "Ctrl+Shift+X" in context


def test_windows_apps_context_is_always_available() -> None:
    context = get_app_context({"title": "Unknown", "process": "unknown.exe"})

    assert "Desktop apps can be opened" in context
