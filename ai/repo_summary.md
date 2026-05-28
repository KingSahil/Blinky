# Clicky — Repository Summary

Quick summary:
- Purpose: Local, privacy-first AI desktop tutor for Windows that captures the screen, runs OCR, queries a local AI model, and highlights UI elements via an overlay.
- Tech stack: Tauri 2 (Rust) shell, React + TypeScript frontend, Python 3.11 worker for capture/OCR/AI integration, local AI providers (Ollama, optional Groq), Windows OCR / EasyOCR fallback, `dxcam` for capture, `pywinauto` for window/UI fallback.

Architecture & flow:
1. Frontend (Tauri + React) exposes a small command popup and overlay UI. Global hotkeys trigger a capture.
2. When the user asks a question, the frontend calls the Tauri backend which invokes the Python worker.
3. Python worker captures the screen (`capture.screen`), runs OCR (`ocr.extract`) and UI text collection (`utils.uia`).
4. The AI pipeline (`python/ai`) either answers from local intents or calls the configured provider (`ollama` or `groq`) via `ai.client`.
5. AI returns a short JSON-friendly set of `summary` + `steps`. Steps are matched to visible items (`utils.matching`) and returned to the frontend.
6. Overlay: the Tauri overlay window highlights matched targets on the screen.

Key entry points:
- Frontend UI: `frontend/src/App.tsx` — main React UI and submit flow.
- Tauri frontend <-> Rust: `src-tauri/src/main.rs` (Tauri app shell). (See `src-tauri/` for Rust integration and global shortcut wiring.)
- Python worker entry: `python/main.py` — accepts JSON on stdin, runs `run(question)` and prints JSON result.
- AI client: `python/ai/client.py` — routes to Ollama or Groq clients.

Where AI logic lives:
- `python/ai/` — model clients and prompt helpers (e.g., `ollama_client.py`, `groq_client.py`, `prompt.py`, `local_intents.py`).

How to run (dev):
1. Install Node 20+, Rust, Python 3.11+, Ollama (if using default provider).
2. Pull model: `ollama pull gemma4:e4b`.
3. Install deps and python setup:
   - `npm install`
   - `npm run setup:python`
   - `npm run dev`

Notable files & folders (quick):
- `frontend/` — React UI, overlay renderer, Tauri client helpers.
- `python/` — capture, OCR, AI integration, matching utilities.
- `src-tauri/` — Tauri Rust shell, `Cargo.toml`, native bindings.
- `shared/` — JSON schemas and example payloads.
- `scripts/` — helper PowerShell scripts: `setup-python.ps1`, `check-ollama.ps1`.

Notes for AI consumption:
- The Python worker (`python/main.py`) expects a `question` in stdin JSON and returns a JSON result with `summary`, `steps`, `ocr` and `screenshot` metadata.
- The project emphasizes local-only models and privacy; environment variables control provider and endpoints (`CLICKY_AI_PROVIDER`, `CLICKY_OLLAMA_URL`, etc.).

Where to look next for contributions:
- Add more UI adapters in `utils/uia.py` for other apps.
- Improve OCR heuristics in `ocr/extract.py`.
- Expand `ai/local_intents.py` for canned answers.

Generated on: 2026-05-28
