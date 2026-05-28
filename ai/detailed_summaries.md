# Clicky — Detailed Per-File Summaries

This document provides concise, AI-friendly summaries for key files listed in `ai/files_index.json`.

- [frontend/src/App.tsx](frontend/src/App.tsx): Main React UI and command popup
  - Purpose: User-facing chat UI and command popup that triggers screen captures and displays results.
  - Key functions/components:
    - `App()` — React root component managing messages, overlay toggle, and `submitAsk()` flow.
    - `submitAsk()` — Sends question to backend via `runTutor()` (Tauri invoke) and appends results.
    - `StatusGrid`, `Steps`, `Preview` — small UI helpers for status and rendering matched steps.
  - Inputs/Outputs: Calls `runTutor(question)` and expects a `TutorResult` object containing `summary`, `steps`, `ocr`, `screenshot`, `provider`, and `warnings`.
  - Notes: Hotkey listener listens to `clicky://open-command` and uses `runTutor` from `frontend/src/lib/tauri.ts`.

- [frontend/src/lib/tauri.ts](frontend/src/lib/tauri.ts): Tauri JS helpers
  - Purpose: Thin client wrapper over Tauri `invoke` calls used by the React UI.
  - Exports: `runTutor(question)`, `showOverlay()`, `hideOverlay()`, `showCommandBar()`.
  - Contract: `runTutor` invokes the Rust command `run_tutor` and returns a `TutorResult`.

- [python/main.py](python/main.py): Python worker entrypoint
  - Purpose: CLI-style worker that accepts a JSON payload on stdin (expects `question`) and returns JSON result on stdout.
  - Key flow (`run(question)`):
    1. `capture_screen()` — captures screenshot and returns `Screenshot(path,width,height)`.
    2. `get_active_window()` — returns active window metadata.
    3. `extract_visible_text(screenshot.path)` — OCR items.
    4. `get_visible_ui_text()` — optional UIA items.
    5. `merge_visible_items()` — dedupe and order items (OCR preferred).
    6. `answer_local_question()` — fast deterministic intents.
    7. If no local answer: `build_prompt()` then `ask_model()` via `python/ai/client.py`.
    8. `attach_matches()` — map AI step `target_text` to OCR/UI items.
  - Output: JSON with `summary`, `steps` (with `match` field), `active_app`, `ocr` metadata, `screenshot` info, `provider`, `elapsed_ms`, and `warnings`.
  - Error handling: Exceptions are logged and returned as `error`/`warnings` JSON.

- [python/ai/client.py](python/ai/client.py): AI routing
  - Purpose: Routes prompt requests to the selected provider determined by env `CLICKY_AI_PROVIDER`.
  - Providers: `ollama` (default) via `python/ai/ollama_client.py`, or `groq` via `python/ai/groq_client.py`.
  - API: `ask_model(prompt, screenshot_path)` returns a dict containing `summary` and `steps`.
  - `get_provider_label()` returns a human-friendly provider name.

- [python/ai/prompt.py](python/ai/prompt.py): Prompt builder
  - Purpose: Turns the question, active app metadata, and visible OCR items into a compact textual prompt for the model.
  - Rules enforced in prompt:
    - Only reference visible UI elements.
    - Never invent UI not present in OCR items.
    - Output must be valid JSON with `summary` and `steps` (max 6 steps).
  - Practical note: Compact the first ~180 OCR items to avoid overly large prompts.

- [python/ai/local_intents.py](python/ai/local_intents.py): Deterministic answers
  - Purpose: Provide immediate deterministic responses for common demo questions (e.g., "where is frontend?") to avoid noisy model inference.
  - Behavior: Checks visible items and returns a small JSON `summary` + `steps` when a match is found.

- [python/ocr/extract.py](python/ocr/extract.py): OCR pipeline
  - Purpose: Extract visible text boxes from a screenshot using Windows OCR (WinRT) first, falling back to `easyocr`.
  - Functions:
    - `extract_visible_text(image_path)` — tries `_windows_ocr()` then `_easy_ocr()`.
    - `_windows_ocr()` — uses WinRT OCR engine via `winrt` packages (async wrapper run via `asyncio.run`).
    - `_easy_ocr()` — uses `easyocr.Reader(...).readtext()` and converts results into `{'text','x','y','width','height','confidence','source'}` boxes.
  - Fallback: If OCR fails entirely, returns a single placeholder item so the pipeline still returns predictable JSON.

- [python/capture/screen.py](python/capture/screen.py): Capture helper
  - Purpose: Capture primary display using `dxcam` when available, else fall back to PIL `ImageGrab`.
  - Returns: `Screenshot(path, width, height)` and saves captures under `tmp/captures`.

- [python/utils/matching.py](python/utils/matching.py): Match AI targets to OCR boxes
  - Purpose: Given AI `steps` (with `target_text`), find the best matching OCR/UI item to allow overlay highlight placement.
  - Logic: Normalizes text, uses `SequenceMatcher` ratio for fuzzy matches, boosts exact/substring matches, factors in OCR `confidence`, and prefers items from OCR (`source == 'ocr'`).
  - Thresholds: Discards matches below a weighted threshold (~0.52).

- [src-tauri/Cargo.toml](src-tauri/Cargo.toml): Tauri / Rust native deps
  - Purpose: Rust crate config for Tauri integration, plugin deps (global shortcut, shell), and Windows native features.
  - Note: Check `src-tauri/src/main.rs` for Tauri command handlers such as `run_tutor`, overlay management, and global shortcut registration.

- [package.json](package.json): Scripts and dependencies
  - Notable scripts: `dev` (runs `tauri dev`), `build` (typecheck + `vite build`), `setup:python` (PowerShell to set up Python venv), `check:ollama`.
  - Frontend deps: React, Vite, TypeScript; Tauri CLI in devDependencies.

- [README.md](README.md): Project overview and setup
  - Usage: lists prerequisites, model pull, setup commands, provider env var overrides, hotkeys, and architecture diagram.

## How to use these summaries programmatically
- The Python worker expects `question` via stdin JSON; you can call `python/python/main.py` manually by piping JSON:

```powershell
echo '{"question": "How do I open frontend?"}' | python python/main.py
```

- To run the app in dev mode (Tauri + frontend):

```powershell
npm install
npm run setup:python
npm run dev
```

## Next steps I can take (pick any):
- Produce per-file, function-level markdown files under `ai/` (one file per source file).
- Bundle file contents into `ai/context_bundle.jsonl` for embedding.
- Add short unit-test stubs for `utils/matching.py` and `python/ocr/extract.py`.

Generated: 2026-05-28
