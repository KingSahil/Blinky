# Blinky — Granular Per-File API & Contract Specifications

This reference document provides developer-level documentation for all key source files in Blinky. It details classes, functions, argument types, return values, and implementation specifics.

---

## 1. Native Integration & System Logic

### 1.1 `src-tauri/src/lib.rs` (Tauri App Core)
Orchestrates Tauri commands, system tray lifecycle, and schedules asynchronous system tasks.

* **Commands Exposed to Frontend**:
  * `async fn run_tutor(app: AppHandle, request: TutorRequest) -> Result<Value, String>`
    * *Inputs*: `TutorRequest { question: String, progress?: Value }`
    * *Outputs*: Resolves with the `TutorResult` JSON output from the Python worker.
    * *Side-effects*: Invokes `run_python_worker()`, emits `blinky://guidance` with result payload to `/overlay`, and shows the overlay window.
  * `fn show_overlay(app: AppHandle) -> Result<(), String>`
    * Sets overlay window cursor-passthrough style and makes the window visible.
  * `fn hide_overlay(app: AppHandle) -> Result<(), String>`
    * Hides the full-screen overlay window.
  * `fn show_command_bar(app: AppHandle) -> Result<(), String>`
    * Focuses and reveals the command bar popup.
  * `fn resize_command_window(app: AppHandle, height: f64) -> Result<(), String>`
    * Resizes the command bar height to dynamically match the webview's DOM height.
  * `async fn get_settings(app: AppHandle) -> Result<BlinkySettings, String>`
    * Reads key-value pairs from `.env` to return configured providers and shortcuts.
  * `async fn save_settings(app: AppHandle, provider: String, shortcut: String) -> Result<(), String>`
    * Writes updated provider and shortcut entries back to `.env`.

* **Internal Helpers**:
  * `fn run_python_worker(app: &AppHandle, question: &str, progress: Option<&Value>) -> Result<String, String>`
    * Spawns `python.exe` targeting `python/main.py`. Pipes question and optional workflow progress as JSON into standard input, reads standard output synchronously, and checks standard error.
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

* **Highlight Selection and Click Progress**:
  `Overlay.tsx` calls `getHighlightSteps()` so only the next matched Action Guide step receives a pulsing highlight. When the user clicks inside that frame, the overlay emits `blinky://target-clicked` with the generic step number, instruction, and target text. The command bar uses that payload as workflow progress for the next model call.

* **Box Size Cap**:
  UIA bounding rects for sidebar buttons can be wider than the visual icon. The overlay caps highlight dimensions and centers or left-aligns the rendered frame depending on whether the matched target looks like an icon or a row:
  ```typescript
  const displayWidth = Math.min(Math.max(MIN_BOX_SIZE, rawWidth), MAX_BOX_WIDTH);
  const displayHeight = Math.min(Math.max(MIN_BOX_SIZE, rawHeight), MAX_BOX_HEIGHT);
  ```

* **Interactive Target Dismissal (`containsClick`)**:
  Determines if a low-level OS mouse-click coordinate $(x_{click}, y_{click})$ matches a visible overlay frame.
  * *Calculation*: Checks bounds with a `10px` clickable margin tolerance:
    ```typescript
    x >= frame.left - 10 && x <= frame.left + frame.width  + 10 &&
    y >= frame.top  - 10 && y <= frame.top  + frame.height + 10
    ```
  * *Side-effects*: If matched, adds the highlight's key to the `dismissedKeys` state and emits completed step metadata to the command bar.

### 2.2 `frontend/src/CommandBar.tsx` (Chat & Control UI)
The user interface for prompt input, status displays, settings configuration, and window layouts.

* **Dynamic Size Manager**:
  Spawns a `ResizeObserver` on mount that watches the main container's DOM height. When the input grows or settings open, it calls the `resizeCommandWindow` command to dynamically adjust Tauri's window height.
* **Settings & Shortcut Synchronizer**:
  Uses React hooks to bind the `provider` state (Groq vs Ollama) and `shortcut` key (Enter vs Space). Saves these variables directly to `.env` using Tauri's backend file system bindings.
* **Workflow Progress Controller**:
  Stores the last query plus completed targets/instructions from highlighted clicks. A new typed or transcribed query resets progress and records whether automatic readback should continue. Highlight clicks complete click-only steps, but text-entry/search/input highlight clicks are treated as focus actions only; they do not mark the step complete or trigger a premature next step. Completed click steps hide the old overlay, schedule a short delayed rerun with progress, and wait for the fresh screen read before showing the next step or completion confirmation. The controller does not display the next step from stale data and does not assume the workflow is complete from the old plan.
* **Task Display and TTS**:
  Uses `getDisplaySteps()` to clean model output, `getCurrentGuideSteps()` to choose the one current pending step, `mergeGuideHistory()` to keep completed Action Guide rows visible while appending the next freshly-read step, `getHighlightSteps()` to highlight only the current matched target, `shouldCompleteStepOnHighlightClick()` to avoid completing typed/search steps on focus, `getWorkflowContinuationReadback()` to keep typed workflows silent, and `shouldShowSummaryBubble()` to hide task summaries unless a verified completion summary should be shown. Automatic voice readback speaks the current guide step for voice-started workflows and the summary for informational or completion replies.

---

## 3. Python Processing Engine

```text
           ┌────────────────────────────────────────────────┐
           │                python/main.py                  │
           │  1. Resolve target PID (before OCR)            │
           │  2. capture_screen()  →  Screenshot(w,h,sw,sh) │
           │  3. get_active_window(target_pid)              │
           │  4. extract_visible_text() [OCR, ~15 s]        │
           │  5. get_visible_ui_text(target_pid)            │
           │  6. Normalise UIA coords: screen→screenshot    │
           │  7. merge_visible_items(ocr, uia)              │
           │  8. classify chat vs screen guidance           │
           │  9. ask_model(prompt, screenshot) (LLM)        │
           │ 10. attach_matches(steps, items)               │
           └────────────────────────────────────────────────┘
```

### 3.1 `python/main.py` (Worker Orchestrator)
The standard input/output interface for processing questions and screen coordinates.

* **`run(question: str, progress: dict | None = None) -> dict`**:
  Executes the primary pipeline:
  1. Runs a text-only preflight classifier. If `needs_screen=false`, calls `answer_without_screen()` and returns a normal chat summary with no capture.
  2. Calls `get_target_window_element()` and extracts its **PID** (`target_pid`) before any slow screen operations.
  3. Grabs display frames via `capture_screen()` which returns a `Screenshot` with both post-thumbnail (`width`/`height`) and physical screen (`screen_width`/`screen_height`) dimensions.
  4. Queries active window metadata using `get_active_window(target_pid=target_pid)`.
  5. Extracts OCR text elements using WinRT/EasyOCR (`extract_visible_text()`).
  6. Calls `get_visible_ui_text(target_pid=target_pid)` — UIA re-resolves a **fresh COM element** by PID, avoiding the staleness window.
  7. **Normalises UIA coordinates** from physical screen space to screenshot space: `x *= screenshot.width / screenshot.screen_width`.
  8. Dedupes overlapping items and calibrates wide UIA coordinates with precise OCR coordinates using `merge_visible_items()`.
  9. Compiles the screen prompt with active app, visible items, and optional completed workflow progress, then routes to `ask_model()`.
  10. Fuzzy matches returned steps back to screen rectangles via `attach_matches()`.
  11. Returns the final data payload.

* **`classify_request(question: str, warnings: list[str]) -> dict | None`**:
  Calls the text-only model with `build_preflight_prompt()` to decide whether the request needs screen capture. If the classifier fails, Blinky falls back to screen mode and records a warning.

* **`answer_without_screen(question: str) -> dict`**:
  Calls the text-only model with `build_chat_prompt()` for greetings, identity questions, general conversation, and non-screen informational requests. This path must not capture the screen.

* **`merge_visible_items(ocr_items: list, uia_items: list) -> list`**:
  Combines OCR text blocks and UI Automation tree items with pixel-perfect calibration:
  * *OCR Calibration*: Scans UIA tree elements. If a UIA element matches a precise WinRT OCR element on the same visual row (close Y-coordinate), it overwrites the UIA element's full-width bounds (`x=63, width=900`) with the precise OCR coordinates!
  * *Order*: UIA items are calibrated and listed first, followed by standalone OCR items as fallback.
  * *Deduplication*: Divides coordinates by $8$ pixels to group items into bucket grids and removes duplicates.

### 3.2 `python/capture/screen.py` (Screen Capture)
Captures the primary display and records dimensions needed for coordinate normalisation.

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
  `screen_width` and `screen_height` are recorded from the captured image **before** `image.thumbnail()` is called.

* **`capture_screen() -> Screenshot`**:
  Uses `dxcam` for GPU-accelerated capture, falling back to PIL `ImageGrab`. Scales to fit within 1920×1080 (Lanczos) while preserving aspect ratio.

### 3.3 `python/utils/window.py` (Window Resolver)
Resolves the target application window, excluding Blinky itself and Windows system shells.

* **`get_target_window_element(window=None, target_pid: int | None = None)`**:
  * If `window` is provided, returns it immediately (bypass scan).
  * If `target_pid` is provided, scans the Z-order and returns the **first visible window whose `process_id()` matches `target_pid`** — acquiring a fresh COM element.
  * Otherwise, returns the first non-excluded visible window.
  * Exclusions: process names containing `blinky`/`tauri`, window titles containing `blinky`, system shells (`searchhost.exe`, etc.), `Taskbar`, `Program Manager`.

* **`get_active_window(window=None, target_pid: int | None = None) -> dict`**:
  Thin wrapper returning `{ title, process, supported }` for the resolved window.

### 3.4 `python/utils/uia.py` (UI Automation Tree Inspector)
Inspects structural desktop components that are difficult for OCR to extract (VS Code sidebar icons, menus, file trees).

* **`get_visible_ui_text(window=None, target_pid: int | None = None) -> list[dict]`**:
  * Resolves the target window via `get_target_window_element(target_pid=target_pid)`. When `target_pid` is supplied, a **fresh COM element** is always obtained — critical because pywinauto `UIAWrapper` COM pointers go stale within ~15 seconds while OCR runs.
  * Traverses `active.descendants()`, filtering to `ALLOWED_CONTROL_TYPES` (Button, TabItem, MenuItem, etc.) for speed.
  * Skips elements with `width < 4` or `height < 4`, or with off-screen coordinates (`x < -1000` or `y < -1000`).
  * Returns items with `source: "uia"` and `confidence: 0.98`.
  * **Does NOT apply any manual coordinate offset**. UIA returns screen-absolute positions by design; coordinate normalisation to screenshot space is handled in `main.py`.

### 3.5 `python/ocr/extract.py` (OCR Parser)
Extracts visible text and coordinates from captured screenshot images.

* **`extract_visible_text(image_path: Path) -> list[dict]`**:
  Attempts native Windows WinRT OCR engine first. If WinRT modules are unavailable or raise errors, falls back to local EasyOCR.
* **`_windows_ocr(image_path: Path) -> list[dict]`**:
  Loads WinRT's native OCR APIs (`winrt.windows.media.ocr.OcrEngine`) using async event loops. Translates lines and word bounding rects into standard coordinate structures.
* **`_easy_ocr(image_path: Path) -> list[dict]`**:
  Initializes an offline `easyocr.Reader(["en"])` instance. Runs text bounding-box detections on the screenshot image and converts PyTorch coordinates into normal formats.

### 3.6 `python/utils/matching.py` (Fuzzy Matcher)
Maps LLM target text recommendations back to concrete physical text boxes on screen.

* **`find_best_match(target: str, ocr_items: list[dict], instruction: str = "") -> dict | None`**:
  Normalizes search strings and scores elements using fuzzy string ratios:
  * Exact matches get `1.0`.
  * Substring overlaps get `0.86`.
  * Other pairs are evaluated using `difflib.SequenceMatcher.ratio()`. Ratio values below `0.65` are skipped.
  * *Score Weighting Formula*:
    $$\text{Score} = (\text{Fuzzy Ratio} \times 0.94) + (\text{OCR Confidence} \times 0.06) + \text{Bonus}$$
    Where $\text{Bonus} = 0.02$ if the element was parsed via OCR.
  * *Threshold*: If the best score is $< 0.52$, it returns `None`.
  * *Control preference*: When the instruction asks for an icon, sidebar item, tab, menu, or button, UIA controls receive a bonus and incidental OCR text receives a penalty. Generic words such as "icon" or "button" are stripped from target candidates so `"Extensions icon"` can match a visible `"Extensions"` control.

### 3.7 `python/ai/prompt.py` (Prompt Builder)
Formats screen context into a compact markdown instruction set for the model.

* **Preflight and Chat Prompts**:
  `build_preflight_prompt()` classifies whether a request needs screen capture. `build_chat_prompt()` produces direct casual/informational replies and explicitly prevents classifier reasoning such as "the student is..." from leaking into the UI.

* **Blinky UI Filtering Heuristics**:
  To prevent the AI model from instructing users to click inside the Blinky app itself, `build_prompt()` filters out any OCR coordinates containing words from the `blinky_ignored_terms` set (e.g. "Blinky app", "groq", "ollama", "ask anything"). It also filters out OCR elements that match the user's input question.
* **Text Length Optimization**:
  To avoid exceeding LLM context limits, the prompt builder limits the OCR elements list to the first $180$ elements.
* **Workflow Progress Context**:
  `build_prompt(question, active_app, ocr_items, progress=None)` includes `completed_targets` and `completed_instructions`. The model is told not to repeat or highlight completed targets, to start at the next not-yet-completed step based on the current visible UI, and to confirm completion from the current visible UI before ending a workflow.
* **Search Before Unrelated Actions**:
  If the requested item is not visible but a relevant search/filter/find/marketplace input is visible, the prompt tells the model to target that input next. It must not choose an unrelated visible action button for a different item.
* **Action Guide Contract**:
  Workflow model payloads may include multiple steps, including future plain instructions with `target_text: ""`, but only currently visible controls that should be highlighted now should use exact `target_text`. The frontend filters completed steps for the overlay, retains completed guide history in the command bar, and appends one current pending step at a time only after a fresh worker result. Informational requests and verified completion replies should return a detailed summary and `steps: []`.
