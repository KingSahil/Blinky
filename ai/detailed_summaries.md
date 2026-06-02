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

* **Coordinate Scaling**:
  ```typescript
  const screenshotWidth  = result?.screenshot?.width  || window.innerWidth;
  const screenshotHeight = result?.screenshot?.height || window.innerHeight;
  const scaleX = window.innerWidth  / screenshotWidth;
  const scaleY = window.innerHeight / screenshotHeight;
  ```
  By the time UIA coordinates reach the Overlay they have already been normalised to screenshot space in `main.py`. The scale factors bring them back to browser pixel space.

* **Input Control Full-Width Bypass**:
  When a matched element has `control_type` of `Edit`, `TextBox`, or `ComboBox`, the overlay bypasses the standard width cap and renders the highlight at the element's full width:
  ```typescript
  if (isInput) {
    displayWidth = rawWidth;   // keep full input field width
    displayLeft = rawLeft;     // no centering shift
  }
  ```

* **Box Size Cap** (non-input elements):
  ```typescript
  const MAX_BOX_WIDTH = isIcon ? 100 : 140;
  const MAX_BOX_HEIGHT = isIcon ? 40 : 44;
  const MIN_BOX_SIZE = 36;
  const displayWidth = Math.min(Math.max(MIN_BOX_SIZE, rawWidth), MAX_BOX_WIDTH);
  ```

* **Interactive Target Dismissal (`containsClick`)**:
  Determines if a low-level OS mouse-click coordinate matches a visible overlay frame with a `10px` clickable margin tolerance.

### 2.2 `frontend/src/App.tsx` (Tutor Container)
The user interface for prompt input, status displays, settings configuration, and window resize handling.

* **Dynamic Size Manager**: Spawns a `ResizeObserver` on mount that watches the main container's DOM height. Calls `resizeCommandWindow` to dynamically adjust Tauri's window height.
* **Drag Resize**: Supports left/right edge drag-resizing via pointer events, calling `resizeAndMoveCommandWindow` for smooth repositioning.
* **Settings Panel**: Uses React hooks to bind `provider` (Groq/Ollama), `shortcut` (Enter/Space), and API keys (Groq, Sarvam). Saves directly to `.env` via Tauri backend bindings.
* **No Background Polling**: The tutor only runs when the user submits a query. There is no polling loop.

---

## 3. Python Processing Engine

```text
           ┌────────────────────────────────────────────────┐
           │                python/main.py                  │
           │  1. Resolve target PID (before OCR)            │
           │  2. capture_screen()  →  Screenshot(w,h,sw,sh) │
           │  3. Print __BLINKY_CAPTURED__ marker           │
           │  4. Preflight classify (chat vs screen,        │
           │     continuation detection)                    │
           │  5. get_active_window(target_pid)              │
           │  6. extract_visible_text() [OCR]               │
           │  7. get_visible_ui_text(target_pid)            │
           │  8. Normalise UIA coords: screen→screenshot    │
           │  9. merge_visible_items(ocr, uia)              │
           │ 10. Filter Blinky UI items                     │
           │ 11. ask_model(prompt, screenshot) (LLM)        │
           │ 12. Post-process: attach → skip → fill → [:1]  │
           └────────────────────────────────────────────────┘
```

### 3.1 `python/main.py` (Worker Orchestrator)
The standard input/output interface for processing questions and screen coordinates.

* **`run(question: str, previous_question: str | None = None, progress: dict | None = None) -> dict`**:
  Executes the primary pipeline:
  1. Resolves target window PID before any screen operations.
  2. Captures screen via `capture_screen()` and prints `__BLINKY_CAPTURED__` marker.
  3. Runs preflight classifier with continuation detection (`is_continuation`).
  4. If `is_continuation=True`, uses `previous_question` as the effective question and passes the current question as `latest_update`.
  5. If `needs_screen=False`, calls `answer_without_screen()` and returns chat summary.
  6. Queries active window, OCR, and UIA.
  7. Normalises UIA coordinates to screenshot space.
  8. Merges and deduplicates visible items.
  9. Compiles prompt and queries LLM (single-step mode, 350 output tokens).
  10. **Post-processing pipeline**:
      * `attach_matches()` — fuzzy match targets to visible elements.
      * `skip_completed_navigation_steps()` — skip redundant panel-opening steps.
      * `_fill_empty_search_targets()` — auto-attach visible search inputs.
      * `steps[:1]` — ensure at most 1 step is returned.

* **`skip_completed_navigation_steps(steps: list[dict]) -> list[dict]`**:
  If step 1 is a navigation action (containing "click"/"open" + "tab"/"sidebar"/"menu"/"panel"/"button") AND step 2 has a visible match on screen, removes step 1 and renumbers from 1.

* **`_fill_empty_search_targets(steps: list[dict], visible_items: list[dict]) -> list[dict]`**:
  For steps with a type/search/filter instruction but empty `target_text` and no match, scans visible items for the first element that is either:
  * An input control (`Edit`, `TextBox`, `ComboBox`) with a search keyword in its text (highest priority), OR
  * Any element with a search/filter/find keyword.
  Auto-attaches the found item as both `target_text` and `match`.

* **`classify_request(question, previous_question, warnings) -> dict | None`**:
  Calls text-only model with `build_preflight_prompt()`. Returns `{needs_screen, is_continuation}`.

* **`answer_without_screen(question: str) -> dict`**:
  Calls text-only model with `build_chat_prompt()` for non-screen requests.

* **`merge_visible_items(ocr_items: list, uia_items: list) -> list`**:
  Combines OCR and UIA items with calibration:
  * **UIA-OCR Calibration**: If a UIA element matches an OCR element on the same row, overrides UIA bounds with precise OCR coordinates. Input controls are NOT calibrated (they keep their full-width bounds).
  * **Input Box Expansion**: OCR items falling inside a UIA input control's bounding box are expanded to the full input dimensions and inherit its `control_type`.
  * **Deduplication**: Divides coordinates by $8$ pixels for bucket-based dedup.

### 3.2 `python/capture/screen.py` (Screen Capture)
* **`Screenshot` dataclass**:
  ```python
  @dataclass
  class Screenshot:
      path: Path
      width: int        # post-thumbnail width  (e.g. 1728)
      height: int       # post-thumbnail height (e.g. 1080)
      screen_width: int   # physical screen width  (e.g. 2560)
      screen_height: int  # physical screen height (e.g. 1600)
  ```

* **`capture_screen() -> Screenshot`**:
  Uses `dxcam` for GPU-accelerated capture, falling back to PIL `ImageGrab`. Scales to fit within 1920×1080 (Lanczos) while preserving aspect ratio.

### 3.3 `python/utils/window.py` (Window Resolver)
* **`get_target_window_element(window=None, target_pid: int | None = None)`**:
  Resolves the target application window, excluding Blinky itself and Windows system shells.
  * If `target_pid` is provided, scans Z-order for the first visible window with matching PID.
  * Exclusions: process names containing `blinky`/`tauri`, window titles containing `blinky`, system shells.

* **`get_active_window(window=None, target_pid: int | None = None) -> dict`**:
  Thin wrapper returning `{ title, process, supported }` for the resolved window.

### 3.4 `python/utils/uia.py` (UI Automation Tree Inspector)
* **`get_visible_ui_text(window=None, target_pid: int | None = None) -> list[dict]`**:
  * Resolves the target window via `get_target_window_element(target_pid=target_pid)`. Always obtains a **fresh COM element** when `target_pid` is supplied.
  * Traverses `active.descendants()`, filtering to `ALLOWED_CONTROL_TYPES`.
  * Skips elements with `width < 4` or `height < 4`, or with off-screen coordinates.
  * Returns items with `source: "uia"` and `confidence: 0.98`.
  * **Does NOT apply any manual coordinate offset**.

### 3.5 `python/ocr/extract.py` (OCR Parser)
* **`extract_visible_text(image_path: Path) -> list[dict]`**:
  Attempts native Windows WinRT OCR engine first. Falls back to local EasyOCR.

### 3.6 `python/utils/matching.py` (Fuzzy Matcher)
Maps LLM target text recommendations back to concrete physical text boxes on screen.

* **`find_best_match(target: str, ocr_items: list[dict], instruction: str = "") -> dict | None`**:
  * Normalizes search strings and generates target candidates by stripping generic UI words (`"icon"`, `"button"`, `"tab"`, etc.).
  * If `target` is empty but `instruction` is present, extracts candidates from quoted terms and capitalized words.
  * Special semantic handlers for close buttons and settings/layout buttons.
  * Score weighting formula:
    $$\text{Score} = (\text{Similarity} \times 0.94) + (\text{Confidence} \times 0.06) + \text{Bonuses}$$
    
    Bonuses breakdown:
    * `source_bonus`: $+0.02$ for OCR source
    * `size_bonus`: Up to $+0.05$ based on element area ($\frac{w \times h}{10000}$)
    * `context_bonus`: $+0.20$ for sidebar, $+0.10$ for top/bottom/right position, $+0.18$ for input control when instruction wants text input
    * `interactive_bonus`: $+0.24$ for UIA buttons/tabs when instruction asks for interactive controls, $+0.30$ for input controls when instruction is search/type, $-0.18$ for non-input controls during search/type
    * `exact_match_bonus`: $+0.30$ for case-insensitive exact match
    * `source_penalty`: $-0.40$ for Blinky's own UI elements
    
  * Minimum acceptance: **`Score >= 0.52`**.

* **`_wants_text_input(instruction_lower: str) -> bool`**:
  Returns `True` if instruction contains: `type`, `enter`, `search`, `filter`, `find`, `input`, `text field`, `search bar`, `marketplace search`.

* **`_is_input_control(text_norm, control_type, automation_id) -> bool`**:
  Returns `True` if `control_type` is `edit`/`textbox`/`combobox` OR if text/automation_id contains `search`/`filter`/`find`.

### 3.7 `python/ai/prompt.py` (Prompt Builder)

* **`build_preflight_prompt(question, previous_question=None) -> str`**:
  Classifies whether a request needs screen capture (`needs_screen`) and whether it's a continuation of the previous goal (`is_continuation`). Includes concrete examples for continuation detection.

* **`build_chat_prompt(question) -> str`**:
  Produces direct casual/informational replies. Prevents classifier reasoning from leaking into the UI.

* **`build_prompt(question, active_app, ocr_items, progress=None, latest_update=None) -> str`**:
  Main prompt for screen-bound tasks. Key characteristics:
  * **Compact item format**: Items are serialized as `"text" (x,y,width,height,control_type)` strings, capped at 45 items.
  * **Blinky UI filtering**: Items matching `blinky_ignored_terms` are filtered out before prompt construction.
  * **Single-step enforcement**: CRITICAL rule restricts output to exactly 1 step.
  * **Search-bar awareness**: If a visible item contains "Search"/"Filter"/"Find" placeholder text, the model must skip panel-opening steps and directly target the search input.
  * **Explicit target_text requirement**: For search inputs, `target_text` MUST be set to the exact visible placeholder text (e.g. `"Search Extensions in Marketplace"`).
  * **Progress context**: Includes `completed_targets` and `completed_instructions` to avoid repeating completed actions.

### 3.8 `python/ai/client.py` (Model Router)
Routes requests to `ollama_client.py` or `groq_client.py` based on `BLINKY_AI_PROVIDER` environment variable.

* **`ask_model(prompt, screenshot_path) -> dict`**: Vision/main prompt routing.
* **`ask_text_model(prompt) -> dict`**: Text-only prompt routing (preflight, chat).
* **`get_provider_label() -> str`**: Returns the provider name for display.

### 3.9 `python/ai/ollama_client.py` (Local Ollama)
* **`ask_ollama(prompt) -> dict`**: Main inference with `num_predict: 350`, `temperature: 0.1`, retry logic (2 attempts), 120s timeout.
* **`ask_ollama_text(prompt) -> dict`**: Text-only inference with `num_predict: 300`.
* Response validation normalises steps to max 6, extracts summary, and ensures clean JSON.

### 3.10 `python/ai/groq_client.py` (Cloud Groq Vision)
* **`ask_groq_vision(prompt, screenshot_path) -> dict`**: Vision inference with `max_tokens: 350`, configurable timeout via `BLINKY_GROQ_TIMEOUT`.
* **`ask_groq_text(prompt) -> dict`**: Text-only inference with `max_tokens: 300`.
* Handles decommissioned models gracefully by falling back to `DEFAULT_GROQ_MODEL`.
* Screenshots are sent as base64 data URLs.
