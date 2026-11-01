import asyncio
import json
from unittest.mock import Mock

import pytest

from computer_use import vercel_engine as v


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "ROOT", tmp_path)
    monkeypatch.setenv("BLINKY_DESKTOP_ENGINE", "agent-desktop")
    monkeypatch.setenv("BLINKY_BROWSER_ENGINE", "agent-browser")
    monkeypatch.delenv("BLINKY_BROWSER_CDP_URL", raising=False)


def test_attach_only():
    assert "--auto-connect" in v.browser_flags()
    assert v.browser_flags("http://127.0.0.1:9222")[-2:] == ["--cdp", "9222"]
    with pytest.raises(ValueError):
        v.browser_flags("https://example.org")


@pytest.mark.parametrize("query", ["click Save", "type hello into the search box", "scroll down", "agent-desktop status"])
def test_desktop_route(query):
    assert v.should_route(query)


@pytest.mark.parametrize("query", ["open https://example.com", "read the title on https://example.com", "write hello in cell A1", "play music on spotify", "what is a variable?"])
def test_preserves_specialized_routes(query):
    assert not v.should_route(query)


def test_refs_must_be_current():
    assert v.action_args("agent-desktop", {"action": "click", "ref": "@s123:e1"}, '"@s123:e1"') == ["click", "@s123:e1"]
    with pytest.raises(ValueError):
        v.action_args("agent-desktop", {"action": "click", "ref": "@old:e1"}, '"@new:e1"')
    with pytest.raises(ValueError):
        v.action_args("agent-browser", {"action": "click", "ref": "e1"}, '"e10"')


def test_no_generated_shell_or_script():
    for action in ({"action": "eval", "value": "alert(1)"}, {"action": "open", "url": "javascript:alert(1)"}):
        with pytest.raises(ValueError):
            v.action_args("agent-browser", action, "")


def test_fill_preserves_literal_text():
    assert v.action_args("agent-browser", {"action": "fill", "ref": "e1", "value": "literal $(bad)"}, '"e1"') == ["fill", "@e1", "literal $(bad)"]
    with pytest.raises(ValueError):
        v.action_args("agent-browser", {"action": "fill", "ref": "e1", "value": "--headed"}, '"e1"')


def test_uncertain_delivery_stops(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "executable", lambda engine: ["fake"])
    run = Mock(return_value=type("P", (), {"returncode": 1, "stdout": json.dumps({"ok": False, "error": {"code": "TIMEOUT", "disposition": {"retry": "unsafe"}}})})())
    monkeypatch.setattr(v.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="TIMEOUT"):
        v.invoke("agent-desktop", ["click", "@s1:e1"], tmp_path / "result.json")
    assert run.call_count == 1
    assert (tmp_path / "result.json").exists()


def test_loop_observes_after_action_and_saves_debug(monkeypatch):
    from ai import client
    replies = iter([{"action": "click", "ref": "e1"}, {"action": "done", "summary": "Saved", "evidence": "Saved status visible"}])
    monkeypatch.setattr(client, "ask_text_model", lambda *a, **kw: next(replies))
    calls = []
    def invoke(engine, args, artifact=None):
        calls.append(args)
        result = {"success": True, "data": {"snapshot": "button Save [ref=e1]"}}
        if artifact:
            artifact.write_text(json.dumps(result))
        return result
    monkeypatch.setattr(v, "invoke", invoke)
    result = v.run_task("Save", "agent-browser", max_steps=1)
    assert result["success"]
    assert result["steps"] == 1
    assert sum("snapshot" in c for c in calls) == 2
    debug = v.Path(result["debug_dir"])
    assert (debug / "000-snapshot.json").exists()
    assert (debug / "000-decision.json").exists()
    assert (debug / "000-result.json").exists()
    assert all("--auto-connect" in c for c in calls)


def test_step_limit_never_reports_success(monkeypatch):
    from ai import client
    monkeypatch.setattr(client, "ask_text_model", lambda *a, **kw: {"action": "click", "ref": "e1"})
    monkeypatch.setattr(v, "invoke", lambda *a, **kw: {"success": True, "data": {"snapshot": "[ref=e1]"}})
    result = v.run_task("Save", "agent-browser", max_steps=1)
    assert not result["success"]
    assert "Step limit" in result["result"]


def test_missing_browser_does_not_fallback(monkeypatch):
    def fail(*a, **kw):
        raise RuntimeError("No running Chrome")
    monkeypatch.setattr(v, "invoke", fail)
    result = v.run_task("read my tab", "agent-browser")
    assert not result["success"]
    assert "No running Chrome" in result["result"]


def test_browser_entry_uses_vercel_without_importing_browser_use(monkeypatch):
    from tools.browser_use_tool import run_browser_task
    run = Mock(return_value={"success": True})
    monkeypatch.setattr(v, "run_task", run)
    assert asyncio.run(run_browser_task("read my tab"))["success"]
    assert run.call_args.args[1] == "agent-browser"


def test_process_lock_rejects_second_task():
    with v.task_lock():
        with pytest.raises(RuntimeError, match="Another Blinky"):
            with v.task_lock():
                pass


def test_desktop_automation_does_not_become_browser_request():
    assert v.should_route("use agent-desktop to automate Notepad")


@pytest.mark.parametrize("task", ["open vscode and click extension button", "open VS Code then click Extensions", "please open Visual Studio Code and click the Extensions icon", "can you open vscode and then click Extensions"])
def test_compound_launch_and_click_routes_to_desktop(task):
    assert v.should_route(task)
    assert v.requested_app(task) == "code.exe"


def test_compound_classification_bypasses_laya():
    from main import classify_request
    result = classify_request("open vscode and click extension button", None, [])
    assert result["intent"] == "DESKTOP_REFS"
    assert result["needs_screen"] is False


def test_exact_ref_click_cannot_match_unrelated_text():
    data = {"tree": {"children": [
        {"role": "button", "name": "on", "ref_id": "@s:e1"},
        {"role": "tab", "name": "Extensions (Ctrl+Shift+X)", "ref_id": "@s:e2"},
    ]}}
    assert v.simple_ref_click("open vscode and click extension button", data, [])["ref"] == "@s:e2"
    assert v.simple_ref_click("click Extensions and install Python", data, []) is None
    assert v.simple_ref_click("click Delete", data, []) is None


def test_initial_target_is_named_app_not_focused_chat(monkeypatch):
    from ai import client
    monkeypatch.setattr(client, "ask_text_model", lambda *a, **kw: {"action": "done", "summary": "Extensions visible", "evidence": "Extensions selected"})
    calls = []
    def invoke(engine, args, artifact=None):
        calls.append(args)
        if "list-windows" in args:
            return {"ok": True, "data": [
                {"id": "w-chat", "app_name": "ChatGPT.exe", "is_focused": True, "visible": True, "accessible": True},
                {"id": "w-code", "app_name": "Code.exe", "visible": True, "accessible": True},
            ]}
        return {"ok": True, "data": {"window": {"id": "w-code"}, "tree": {"role": "window", "name": "Visual Studio Code"}}}
    monkeypatch.setattr(v, "invoke", invoke)
    result = v.run_task("open vscode and click Extensions", "agent-desktop", max_steps=2)
    assert result["success"]
    snapshots = [args for args in calls if "snapshot" in args]
    assert snapshots and all("w-code" in args for args in snapshots)
    assert all("w-chat" not in args for args in snapshots)


def test_ref_cursor_uses_screen_bounds():
    data = {"tree": {"children": [{"ref_id": "@s:e2", "bounds": {"x": 10, "y": 20, "width": 30, "height": 40}}]}}
    assert v.ref_bounds(data, "@s:e2") == {"x": 10, "y": 20, "width": 30, "height": 40}


def test_compact_snapshot_keeps_scroll_refs_and_omits_offscreen_controls():
    data = {"tree": {"role": "group", "ref_id": "@s:e1", "available_actions": ["Scroll"], "children": [
        {"role": "button", "ref_id": "@s:e2", "name": "Visible"},
        {"role": "button", "ref_id": "@s:e3", "name": "Hidden", "states": ["offscreen"]},
    ]}}
    result = v.planner_snapshot(data)
    assert "@s:e1" in result and "@s:e2" in result
    assert "@s:e3" not in result


def test_safe_stale_ref_replans_without_replaying_old_action(monkeypatch):
    from ai import client
    replies = iter([{"action": "click", "ref": "e1"}, {"action": "done", "summary": "Already saved", "evidence": "Saved status"}])
    monkeypatch.setattr(client, "ask_text_model", lambda *a, **kw: next(replies))
    mutations = []
    def invoke(engine, args, artifact=None):
        if "click" in args:
            mutations.append(args)
            raise v.CommandError(engine, {"error": {"code": "STALE_REF", "disposition": {"retry": "safe"}}})
        return {"success": True, "data": {"snapshot": "Save [ref=e1]"}}
    monkeypatch.setattr(v, "invoke", invoke)
    result = v.run_task("Save", "agent-browser", max_steps=2)
    assert result["success"]
    assert len(mutations) == 1
