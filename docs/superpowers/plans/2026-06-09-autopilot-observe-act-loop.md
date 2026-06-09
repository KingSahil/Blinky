# Autopilot Observe Act Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded autopilot loop that reads the screen, acts on one high-confidence step, verifies by reading again, and retries up to five times.

**Architecture:** Keep the existing screen guidance model as the planner. Add a frontend orchestration helper that calls `runTutor`, clicks the center of a matched target when the step is safe, waits briefly, then calls `runTutor` again. Add a Tauri command for OS-level clicks on Windows.

**Tech Stack:** React/TypeScript, Bun tests, Tauri Rust command, Windows `SendInput`, existing Python screen guidance.

---

### Task 1: Autopilot Loop Helper

**Files:**
- Create: `frontend/src/lib/autopilot.ts`
- Create: `frontend/tests/autopilot.test.ts`

- [ ] Add tests for max 5 attempts, stop on repeated unchanged target, and only clicking safe matched click steps.
- [ ] Implement `runAutopilotLoop` with injected `observe`, `act`, and `wait` callbacks.
- [ ] Run `bun test frontend/tests/autopilot.test.ts`.

### Task 2: Click Command

**Files:**
- Modify: `src-tauri/src/lib.rs`
- Modify: `frontend/src/lib/tauri.ts`

- [ ] Add a Tauri command `click_screen_point(x, y)` that sends a left click on Windows.
- [ ] Add frontend wrapper `clickScreenPoint`.
- [ ] Run `bun run build`.

### Task 3: Command Bar Integration

**Files:**
- Modify: `frontend/src/CommandBar.tsx`
- Test: `frontend/tests/autopilot.test.ts`

- [ ] In globe/web mode, run the browser/screen setup first, then let the autopilot loop click safe next steps up to five times.
- [ ] Keep existing manual Action Guide behavior when autopilot cannot safely act.
- [ ] Run frontend tests and build.
