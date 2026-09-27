import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from computer_use.step_planner import (
    generate_procedural_plan,
    check_builtin_template,
    search_searxng_for_procedure,
)


def test_builtin_template_dark_mode_windows():
    plan = check_builtin_template("change my theme to dark mode", os_type="Windows")
    assert plan is not None
    assert "Personalization" in plan["markdown_guide"]
    assert len(plan["steps"]) >= 3
    assert plan["steps"][0]["target"] == "Personalization"
    assert plan["source"] == "builtin_template"
    assert plan["app_to_open"] == "ms-settings:colors"


def test_builtin_template_light_mode_windows():
    plan = check_builtin_template("enable light theme", os_type="Windows")
    assert plan is not None
    assert "Personalization" in plan["markdown_guide"]
    assert any("Light" in s["target"] or "Light" in s["instruction"] for s in plan["steps"])


def test_builtin_template_dark_mode_linux():
    plan = check_builtin_template("switch to dark mode", os_type="Linux")
    assert plan is not None
    assert "Appearance" in plan["markdown_guide"]
    assert plan["steps"][0]["target"] == "Appearance"


def test_builtin_template_edge_browser():
    active_app = {"title": "Settings - Microsoft Edge", "process": "msedge.exe"}
    plan = check_builtin_template("switch to dark mode", os_type="Windows", active_app=active_app)
    assert plan is not None
    assert "Microsoft Edge" in plan["markdown_guide"]
    assert plan["steps"][0]["target"] == "Appearance"
    assert plan["steps"][1]["target"] == "Dark"


def test_builtin_template_vscode():
    active_app = {"title": "Blinky - Visual Studio Code", "process": "Code.exe"}
    plan = check_builtin_template("enable light theme", os_type="Windows", active_app=active_app)
    assert plan is not None
    assert "VSCode" in plan["markdown_guide"]
    assert plan["steps"][0]["target"] == "Color Theme"
    assert plan["steps"][1]["target"] == "Light"


@pytest.mark.asyncio
async def test_search_searxng_for_procedure_success():
    mock_results = [
        {"title": "How to enable dark mode in VSCode", "content": "Press Ctrl+, and search for Color Theme. Select Dark."},
    ]
    with patch("wil.searxng_client.SearXNGClient.search_category", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_results
        result = await search_searxng_for_procedure("enable dark mode in vscode", app_title="Visual Studio Code")
        assert "How to enable dark mode in VSCode" in result
        assert "Press Ctrl+," in result


def test_generate_procedural_plan_searxng_llm():
    mock_llm_response = {
        "task": "install python extension in vscode",
        "markdown_guide": "# Install Python Extension\n1. Click Extensions\n2. Type Python\n3. Click Install",
        "summary": "Step-by-step guide to install Python in VSCode",
        "steps": [
            {"step": 1, "target": "Extensions", "action": "click", "instruction": "Click Extensions icon in sidebar"},
            {"step": 2, "target": "Search Extensions in Marketplace", "action": "type", "text_to_type": "Python", "instruction": "Type Python in the search bar"},
            {"step": 3, "target": "Install", "action": "click", "instruction": "Click Install button for Python"},
        ],
    }

    with patch("computer_use.step_planner._run_async_in_thread", return_value="Snippet about installing Python extension"), \
         patch("computer_use.step_planner.ask_text_model", return_value=mock_llm_response):
        plan = generate_procedural_plan(
            "install python extension in vscode",
            active_app={"title": "Visual Studio Code", "process": "Code.exe"},
        )
        assert plan["task"] == "install python extension in vscode"
        assert len(plan["steps"]) == 3
        assert plan["steps"][0]["target"] == "Extensions"
        assert plan["steps"][1]["action"] == "type"
        assert plan["source"] == "searxng_text_llm"


def test_generate_procedural_plan_fallback_on_error():
    with patch("computer_use.step_planner._run_async_in_thread", side_effect=Exception("SearXNG offline")), \
         patch("computer_use.step_planner.ask_text_model", side_effect=Exception("LLM offline")):
        plan = generate_procedural_plan(
            "custom complex workflow",
            active_app={"title": "Unknown App", "process": "custom.exe"},
        )
        assert plan["task"] == "custom complex workflow"
        assert len(plan["steps"]) == 1
        assert plan["source"] == "fallback"
