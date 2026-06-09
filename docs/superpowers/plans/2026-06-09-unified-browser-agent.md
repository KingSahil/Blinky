# Unified Browser Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generated browser scripts with an AI-planned, safe-action browser path that can handle unknown sites without hardcoding each site.

**Architecture:** Keep deterministic fast paths for obvious commands, then use a JSON-only browser action planner before legacy tool routing. The planner may return only safe actions, and the executor runs those actions through the persistent Edge `BrowserController`.

**Tech Stack:** Python `unittest`, existing `ask_text_model`, Playwright via `browser_controller.py`, Tauri agent sidecar.

---

### Task 1: Safe Browser Planner

**Files:**
- Create: `python/browser_agent.py`
- Test: `python/tests/test_browser_agent.py`

- [ ] Write tests for parsing AI JSON into a safe `site_search` action.
- [ ] Run `python -m unittest python.tests.test_browser_agent` and verify missing module failure.
- [ ] Implement `plan_browser_action()` and `parse_browser_plan()` with strict action allow-listing.
- [ ] Run `python -m unittest python.tests.test_browser_agent` and verify pass.

### Task 2: Router Integration

**Files:**
- Modify: `python/agent_router.py`
- Test: `python/tests/test_agent_router_open_url.py`

- [ ] Write a failing test proving `give me gaming chair from blinkit` uses `run_browser_plan()` and does not call registry/generator execution.
- [ ] Run `python -m unittest python.tests.test_agent_router_open_url` and verify failure.
- [ ] Insert the browser planner before registry routing and generated-code fallback.
- [ ] Run `python -m unittest python.tests.test_agent_router_open_url` and verify pass.

### Task 3: Verification

**Files:**
- Verify: `python/tests/test_browser_agent.py`
- Verify: `python/tests/test_agent_router_open_url.py`

- [ ] Run `python -m unittest python.tests.test_browser_agent python.tests.test_agent_router_open_url`.
- [ ] Confirm no generated script path is used for generic site searches.
