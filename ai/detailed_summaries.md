# Clicky — Granular Per-File API & Contract Specifications

This reference document provides developer-level documentation for all key source files in Slicky. It details classes, functions, argument types, return values, and implementation specifics.

---

## 1. Native Integration & System Logic

### 1.1 `src-tauri/src/lib.rs` (Tauri App Core)
Orchestrates Tauri commands, system tray lifecycle, and schedules asynchronous system tasks.

* **Commands Exposed to Frontend**:
  * `async fn run_tutor(app: AppHandle, request: TutorRequest) -> Result<Value, String>`
    * *Inputs*: `TutorRequest { question: String }`
    * *Outputs*: Resolves with the `TutorResult` JSON output from the Python worker.
    * *Side-effects*: Invokes `run_python_worker()`, emits `clicky://guidance` with result payload to `/overlay`, and shows the overlay window.
  * `fn show_overlay(app: AppHandle) -> Result<(), String>`
    * Sets overlay window cursor-passthrough style and makes the window visible.
  * `fn hide_overlay(app: AppHandle) -> Result<(), String>`
    * Hides the full-screen overlay window.
  * `fn show_command_bar(app: AppHandle) -> Result<(), String>`
    * Focuses and reveals the command bar popup.
  * `fn resize_command_window(app: AppHandle, height: f64) -> Result<(), String>`
    * Resizes the command bar height to dynamically match the webview's DOM height.
  * `async fn get_settings(app: AppHandle) -> Result<ClickySettings, String>`
    * Reads key-value pairs from `.env` to return configured providers and shortcuts.
  * `async fn save_settings(app: AppHandle, provider: String, shortcut: String) -> Result<(), String>`
    * Writes updated provider and shortcut entries back to `.env`.

* **Internal Helpers**:
  * `fn run_python_worker(app: &AppHandle, question: &str) -> Result<String, String>`
    * Spawns `python.exe` targeting `python/main.py`. Pipes prompt input as JSON into standard input, reads standard output synchronously, and checks standard error.
  * `fn start_global_click_listener(app: AppHandle)`
    * Spawns a background OS thread running a `loop` that uses the Windows `GetAsyncKeyState` API to capture mouse clicks. Emits `clicky://global-click` with cursor metrics.

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
    ( "/overlay" ) ( "/command" ) ( default / )
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

* **Box Size Cap** — `MAX_BOX = 50` px:
  UIA bounding rects for VS Code sidebar buttons are `63×64` px (correct icon area), but some elements report the entire panel. The cap ensures the highlight never exceeds 50×50 px and is centered on the element's geometric center:
  ```typescript
  const displayWidth  = Math.min(rawWidth,  MAX_BOX);
  const displayHeight = Math.min(rawHeight, MAX_BOX);
  const displayLeft   = rawLeft + Math.round((rawWidth  - displayWidth)  / 2);
  const displayTop    = rawTop  + Math.round((rawHeight - displayHeight) / 2);
  ```

* **Interactive Target Dismissal (`containsClick`)**:
  Determines if a low-level OS mouse-click coordinate $(x_{click}, y_{click})$ matches a visible overlay frame.
  * *Calculation*: Checks bounds with a `10px` clickable margin tolerance:
    ```typescript
    x >= frame.left - 10 && x <= frame.left + frame.width  + 10 &&
    y >= frame.top  - 10 && y <= frame.top  + frame.height + 10
    ```
  * *Side-effects*: If matched, adds the highlight's key to the `dismissedKeys` state to hide the pulsing ring.

### 2.2 `frontend/src/CommandBar.tsx` (Chat & Control UI)
The user interface for prompt input, status displays, settings configuration, and window layouts.

* **Dynamic Size Manager**:
  Spawns a `ResizeObserver` on mount that watches the main container's DOM height. When the input grows or settings open, it calls the `resizeCommandWindow` command to dynamically adjust Tauri's window height.
* **Settings & Shortcut Synchronizer**:
  Uses React hooks to bind the `provider` state (Groq vs Ollama) and `shortcut` key (Enter vs Space). Saves these variables directly to `.env` using Tauri's backend file system bindings.

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
           │     → fresh COM element for locked PID         │
           │  6. Normalise UIA coords: screen→screenshot    │
           │  7. merge_visible_items(ocr, uia)              │
           │  8. ask_model(prompt, screenshot)              │
           │  9. attach_matches(steps, items)               │
           └────────────────────────────────────────────────┘
```

### 3.1 `python/main.py` (Worker Orchestrator)
The standard input/output interface for processing questions and screen coordinates.

* **`run(question: str) -> dict`**:
  Executes the primary pipeline:
  1. Calls `get_target_window_element()` and extracts its **PID** (`target_pid`) before any slow operations.
  2. Grabs display frames via `capture_screen()` which returns a `Screenshot` with both post-thumbnail (`width`/`height`) and physical screen (`screen_width`/`screen_height`) dimensions.
  3. Queries active window metadata using `get_active_window(target_pid=target_pid)`.
  4. Extracts OCR text elements using WinRT/EasyOCR (`extract_visible_text()`).
  5. Calls `get_visible_ui_text(target_pid=target_pid)` — UIA re-resolves a **fresh COM element** by PID, avoiding the 15-second staleness window.
  6. **Normalises UIA coordinates** from physical screen space to screenshot space: `x *= screenshot.width / screenshot.screen_width`.
  7. Dedupes overlapping items using `merge_visible_items()`.
  8. Compiles the prompt and routes to the model via `ask_model()`.
  9. Fuzzy matches returned steps back to screen rectangles via `attach_matches()`.
  10. Returns the final data payload.

* **`merge_visible_items(ocr_items: list, uia_items: list) -> list`**:
  Combines OCR text blocks and UI Automation tree items.
  * *Order*: UIA items are listed first (richer labels for icon-only UI controls).
  * *Deduplication logic*: Divides coordinates by $8$ pixels to group items into bucket grids. First-seen entry (UIA) wins on duplicate text+bucket.

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
Resolves the target application window, excluding Slicky itself and Windows system shells.

* **`get_target_window_element(window=None, target_pid: int | None = None)`**:
  * If `window` is provided, returns it immediately (bypass scan).
  * If `target_pid` is provided, scans the Z-order and returns the **first visible window whose `process_id()` matches `target_pid`** — acquiring a fresh COM element.
  * Otherwise, returns the first non-excluded visible window.
  * Exclusions: process names containing `clicky`/`tauri`, window titles containing `slicky`, system shells (`searchhost.exe`, etc.), `Taskbar`, `Program Manager`.

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

* **`find_best_match(target: str, ocr_items: list[dict]) -> dict | None`**:
  Normalizes search strings and scores elements using fuzzy string ratios:
  * Exact matches get `1.0`.
  * Substring overlaps get `0.86`.
  * Other pairs are evaluated using `difflib.SequenceMatcher.ratio()`. Ratio values below `0.65` are skipped.
  * *Score Weighting Formula*:
    $$\text{Score} = (\text{Fuzzy Ratio} \times 0.94) + (\text{OCR Confidence} \times 0.06) + \text{Bonus}$$
    Where $\text{Bonus} = 0.02$ if the element was parsed via OCR.
  * *Threshold*: If the best score is $< 0.52$, it returns `None`.

### 3.7 `python/ai/prompt.py` (Prompt Builder)
Formats screen context into a compact markdown instruction set for the model.

* **Slicky UI Filtering Heuristics**:
  To prevent the AI model from instructing users to click inside the Slicky app itself, `build_prompt()` filters out any OCR coordinates containing words from the `slicky_ignored_terms` set (e.g. "Slicky app", "groq", "ollama", "ask anything"). It also filters out OCR elements that match the user's input question.
* **Text Length Optimization**:
  To avoid exceeding LLM context limits, the prompt builder limits the OCR elements list to the first $180$ elements.
