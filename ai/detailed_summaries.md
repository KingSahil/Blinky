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
    │(Overlay.ts│ │(CommandBar│ │ (App.tsx) │
    └───────────┘ └───────────┘ └───────────┘
```

### 2.1 `frontend/src/Overlay.tsx` (Target pulse Canvas)
A transparent, fullscreen React view that maps raw text coordinates onto the active viewport and handles targets dismissal.

* **Coordinate Scaling Formula**:
  Computes scale variables mapping from the $1920 \times 1080$ saved image size:
  ```typescript
  const scaleX = window.innerWidth / screenshotWidth;
  const scaleY = window.innerHeight / screenshotHeight;
  ```
  Applies scaling transforms to create visible highlight nodes:
  ```typescript
  left: Math.round(match.x * scaleX),
  top: Math.round(match.y * scaleY),
  width: Math.max(8, Math.round(match.width * scaleX)),
  height: Math.max(8, Math.round(match.height * scaleY)),
  ```

* **Interactive Target Dismissal (`containsClick`)**:
  Determines if a low-level OS mouse-click coordinate $(x_{click}, y_{click})$ matches a visible overlay frame.
  * *Calculation*: Checks bounds with a `10px` clickable margin tolerance:
    ```typescript
    x >= frame.left - 10 && x <= frame.left + frame.width + 10 &&
    y >= frame.top - 10  && y <= frame.top + frame.height + 10
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
           ┌────────────────────────┐
           │     python/main.py     │
           │  (Worker Orchestrator) │
           └────────────────────────┘
                       │
     ┌───────┬─────────┴─────────┬───────┐
     ▼       ▼                   ▼       ▼
 ┌──────┐ ┌──────┐            ┌──────┐ ┌──────┐
 │screen│ │window│            │ex-   │ │uia.py│
 │.py   │ │.py   │            │tract │ │      │
 └──────┘ └──────┘            └──────┘ └──────┘
  Screen   Active              WinRT    Active
  dxcam    Window              OCR      UIA
     │       │                   │       │
     └───────┼─────────┬─────────┴───────┘
               ▼         ▼
           ┌──────┐   ┌──────┐
           │prompt│   │client│ ──► [Groq/Ollama]
           │.py   │   │.py   │
           └──────┘   └──────┘
             Prompt     Model
             Builder    Router
               │
               ▼
           ┌──────┐
           │match-│ ──► Coordinates Fuzzy Matcher
           │ing.py│
           └──────┘
```

### 3.1 `python/main.py` (Worker orchestrator)
The standard input/output interface for processing questions and screen coordinates.

* **`run(question: str) -> dict`**:
  Executes the primary pipeline:
  1. Grabs display frames via `capture_screen()`.
  2. Queries active window process metadata using `get_active_window()`.
  3. Extracts OCR text elements using WinRT/EasyOCR.
  4. Inspects UIA element nodes using `get_visible_ui_text()`.
  5. Dedupes overlapping text items using `merge_visible_items()`.
  6. Intercepts queries using local intents, or compiles the system prompt and calls the model router.
  7. Fuzzy matches returned steps back to screen rectangles via `attach_matches()`.
  8. Returns the final data payload.

* **`merge_visible_items(ocr_items: list, uia_items: list) -> list`**:
  Combines OCR text blocks and UI Automation tree items.
  * *Deduplication logic*: Divides coordinates by $8$ pixels to group items into bucket grids. If a text string overlaps inside a bucket grid, **the OCR entry is prioritized**, ensuring higher alignment precision for visual overlays.

### 3.2 `python/ocr/extract.py` (OCR Parser)
Extracts visible text and coordinates from captured screenshot images.

* **`extract_visible_text(image_path: Path) -> list[dict]`**:
  Attempts native Windows WinRT OCR engine first. If WinRT modules are unavailable or raise errors, falls back to local EasyOCR.
* **`_windows_ocr(image_path: Path) -> list[dict]`**:
  Loads WinRT's native OCR APIs (`winrt.windows.media.ocr.OcrEngine`) using async event loops. Translates lines and word bounding rects into standard coordinate structures.
* **`_easy_ocr(image_path: Path) -> list[dict]`**:
  Initializes an offline `easyocr.Reader(["en"])` instance. Runs text bounding-box detections on the screenshot image and converts PyTorch coordinates into normal formats.

### 3.3 `python/utils/matching.py` (Fuzzy Matcher)
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

### 3.4 `python/utils/uia.py` (UI Automation Tree Inspector)
Inspects structural desktop components that are difficult for OCR to extract (such as VS Code file explorers).

* **`get_visible_ui_text() -> list[dict]`**:
  Initializes a pywinauto UIA Desktop instance (`Desktop(backend="uia")`). Fetches the active window handle, scans descendant elements, and extracts coordinate boxes where width/height are $\ge 4\text{ px}$.

### 3.5 `python/ai/prompt.py` (Prompt Builder)
Formats screen context into a compact markdown instruction set for the model.

* **Slicky UI Filtering Heuristics**:
  To prevent the AI model from instructing users to click inside the Slicky app itself, `build_prompt()` filters out any OCR coordinates containing words from the `slicky_ignored_terms` set (e.g. "Slicky app", "groq", "ollama", "ask anything"). It also filters out OCR elements that match the user's input question.
* **Text Length Optimization**:
  To avoid exceeding LLM context limits, the prompt builder limits the OCR elements list to the first $180$ elements.

### 3.6 `python/ai/local_intents.py` (Deterministic router)
Intercepts common queries to provide immediate, reliable answers.

* **`answer_local_question(question: str, visible_items: list) -> dict | None`**:
  Checks if the normalized query contains the word "frontend". If found, it searches `visible_items` for files matching `frontend/src/app.tsx` or `app.tsx`. If found, it returns immediate, structured navigation steps, bypassing model inference completely.
