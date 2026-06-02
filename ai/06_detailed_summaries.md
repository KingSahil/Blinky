# Blinky — Granular Per-File API & Contract Specifications

This reference document provides developer-level documentation for all key source files in Blinky. It details classes, functions, argument types, return values, and implementation specifics.

---

## 1. Native Integration & System Logic

### 1.1 `src-tauri/src/lib.rs` (Tauri App Core)
Orchestrates Tauri commands, system tray lifecycle, flicker-free capture exclusion, and asynchronous system tasks.

* **Commands Exposed to Frontend**:
  * `async fn run_tutor(app: AppHandle, request: TutorRequest) -> Result<Value, String>`
    * *Inputs*: `TutorRequest { question: String, previous_question?: String, progress?: Value }`
    * *Outputs*: Resolves with the `TutorResult` JSON output from the Python worker.
    * *Side-effects*: Sets `WDA_EXCLUDEFROMCAPTURE` on command + overlay windows, invokes `run_python_worker()`, restores `WDA_NONE` after `__BLINKY_CAPTURED__` marker, emits `blinky://guidance` with result payload to `/overlay`, and shows the overlay window.
  * `fn show_overlay(app: AppHandle) -> Result<(), String>`
    * Sets overlay window cursor-passthrough style and makes the window visible.
  * `fn hide_overlay(app: AppHandle) -> Result<(), String>`
    * Hides the full-screen overlay window.
  * `fn show_command_bar(app: AppHandle) -> Result<(), String>`
    * Focuses and reveals the command bar popup.
  * `fn resize_command_window(app: AppHandle, height: f64) -> Result<(), String>`
    * Resizes the command bar height to dynamically match the webview's DOM height.
  * `fn resize_and_move_command_window(app: AppHandle, x: f64, y: f64, width: f64, height: f64) -> Result<(), String>`
    * Resizes and repositions the command bar (used for drag-resize).
  * `async fn get_settings(app: AppHandle) -> Result<BlinkySettings, String>`
    * Reads key-value pairs from `.env` to return configured providers, shortcuts, and API keys.
  * `async fn save_settings(app: AppHandle, provider: String, shortcut: String, sarvam_api_key: String, groq_api_key: String) -> Result<(), String>`
    * Writes updated settings entries back to `.env`.

* **Internal Helpers**:
  * `fn run_python_worker(app: &AppHandle, question: &str, previous_question: Option<&str>, progress: Option<&Value>, command: Option<WebviewWindow>, overlay: Option<WebviewWindow>) -> Result<String, String>`
    * Spawns `python.exe` targeting `python/main.py`. Pipes question, previous_question, and optional progress as JSON into standard input. Reads stdout line-by-line, watching for the `__BLINKY_CAPTURED__` marker to restore capture visibility. Returns the final JSON output line.
  * `fn set_window_capture_exclusion(window: &WebviewWindow, exclude: bool)`
    * Calls `SetWindowDisplayAffinity` to toggle `WDA_EXCLUDEFROMCAPTURE` / `WDA_NONE`.
  * `fn start_global_click_listener(app: AppHandle)`
    * Spawns a background OS thread running a `loop` that uses the Windows `GetAsyncKeyState` API to capture mouse clicks. Emits `blinky://global-click` with cursor metrics.

---

## 2. Frontend Interface & Coordinate Mapping

```text
          ┌────────────────────────┐
          │  Vite Entry (main.tsx) │
          └────────────────────────┘
                       │
                       ▼
          [ window.location.pathname ]
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ("/overlay") ("/command") (/ default)
         │             │             │
         ▼             ▼             ▼
    ┌───────────┐ ┌───────────┐ ┌───────────┐
    │  Overlay  │ │CommandBar │ │    App    │
    │(Overlay.tsx)│(CommandBar│ │ (App.tsx) │
    └───────────┘ └───────────┘ └───────────┘
```

### 2.1 `frontend/src/Overlay.tsx` (Target Pulse Canvas)
A transparent, fullscreen React view that maps raw text coordinates onto the active viewport and handles target dismissal.
* **Scaling and Capping**: Translates coordinate rects from downsampled screenshot coordinates back to active CSS layout pixels. For input elements, the standard sizing restrictions are bypassed.
* See the [Coordinate Scaling & Resolution Normalization Guide](file:///c:/projects/Jarvis/ai/02_coordinate_scaling.md) for formulas and implementation logic.

### 2.2 `frontend/src/App.tsx` (Tutor Container)
The user interface for prompt input, status displays, settings configuration, and window resize handling.
* **Dynamic Size Manager**: Spawns a `ResizeObserver` on mount that watches the main container's DOM height. Calls `resizeCommandWindow` to dynamically adjust Tauri's window height.
* **Drag Resize**: Supports left/right edge drag-resizing via pointer events, calling `resizeAndMoveCommandWindow` for smooth repositioning.
* **Settings Panel**: Uses React hooks to bind `provider` (Groq/Ollama), `shortcut` (Enter/Space), and API keys (Groq, Sarvam). Saves directly to `.env` via Tauri backend bindings.

### 2.3 `frontend/src/lib/tts.ts` (Sarvam voice serialization)
Helper methods for assembling payloads and audio URL mapping.
* See the [Sarvam AI Voice Integration Guide](file:///c:/projects/Jarvis/ai/05_sarvam.md) for full payload structures, properties, and error message parsing.

---

## 3. Python Processing Engine

### 3.1 `python/main.py` (Worker Orchestrator)
The standard input/output interface for processing questions and screen coordinates.
* **`run(question: str, previous_question: str | None = None, progress: dict | None = None) -> dict`**: Executes the primary pipeline.
* **`skip_completed_navigation_steps(steps: list[dict]) -> list[dict]`**: If step 1 is a navigation action and step 2 has a visible match on screen, removes step 1.
* **`_fill_empty_search_targets(steps: list[dict], visible_items: list[dict]) -> list[dict]`**: Fallback that scans visible items for the first search/filter box if target_text is empty.
* **`classify_request(question, previous_question, warnings) -> dict | None`**: Calls text-only model to check if screen capture is needed.
* **`answer_without_screen(question: str) -> dict`**: General conversation responder.
* **`merge_visible_items(ocr_items: list, uia_items: list) -> list`**: Deduplicates and aligns elements. See the [Target Matching Heuristics Guide](file:///c:/projects/Jarvis/ai/03_matching_heuristics.md) for merge details.

### 3.2 `python/capture/screen.py` (Screen Capture)
* **`Screenshot` dataclass**: Captures pixel metrics for scaling calculations. See [Coordinate Scaling Guide](file:///c:/projects/Jarvis/ai/02_coordinate_scaling.md) for metrics description.
* **`capture_screen() -> Screenshot`**: Captures via `dxcam` (falling back to PIL `ImageGrab`) and downsamples to fit $1920 \times 1080$.

### 3.3 `python/utils/window.py` (Window Resolver)
* **`get_target_window_element(window=None, target_pid: int | None = None)`**: Resolves target application window, excluding Blinky itself.
* **`get_active_window(window=None, target_pid: int | None = None) -> dict`**: Thin wrapper returning `{ title, process, supported }` for the resolved window.

### 3.4 `python/utils/uia.py` (UI Automation Tree Inspector)
* **`get_visible_ui_text(window=None, target_pid: int | None = None) -> list[dict]`**: Traverses `active.descendants()` to extract active controls of `ALLOWED_CONTROL_TYPES`. Requires `target_pid` to acquire a fresh COM window instance.

### 3.5 `python/ocr/extract.py` (OCR Parser)
* **`extract_visible_text(image_path: Path) -> list[dict]`**: Runs Windows WinRT OCR engine with EasyOCR fallback.

### 3.6 `python/utils/matching.py` (Fuzzy Matcher)
* **`find_best_match(target: str, ocr_items: list[dict], instruction: str = "") -> dict | None`**: Fuzzy-matches step `target_text` to visible screen controls. Uses weighted scoring matrix. See [Target Matching Heuristics Guide](file:///c:/projects/Jarvis/ai/03_matching_heuristics.md) for formulas and bonuses.

### 3.7 `python/ai/prompt.py` (Prompt Builder)
* **`build_preflight_prompt(question, previous_question=None) -> str`**: Compiles preflight classifier prompt.
* **`build_chat_prompt(question) -> str`**: Compiles conversational chat prompt.
* **`build_prompt(question, active_app, ocr_items, progress=None, latest_update=None) -> str`**: Compiles main visual-context prompt. See [AI Inference Guide](file:///c:/projects/Jarvis/ai/04_ai_inference.md) for formatting rules.

### 3.8 `python/ai/client.py` (Model Router)
* **`ask_model(prompt, screenshot_path) -> dict`**: Routes requests to selected LLM vision provider.
* **`ask_text_model(prompt) -> dict`**: Routes requests to selected LLM text-only provider.

### 3.9 `python/ai/ollama_client.py` (Local Ollama)
* **`ask_ollama(prompt) -> dict`**: Local vision execution.
* **`ask_ollama_text(prompt) -> dict`**: Local preflight/chat text execution.

### 3.10 `python/ai/groq_client.py` (Cloud Groq Vision)
* **`ask_groq_vision(prompt, screenshot_path) -> dict`**: Cloud Groq vision execution.
* **`ask_groq_text(prompt) -> dict`**: Cloud Groq preflight/chat text execution.
