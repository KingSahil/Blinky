# Blinky — System Architecture & Technical Specifications

Blinky is a local, privacy-first AI-powered desktop tutor for Windows. It captures the screen, extracts text through OCR and Windows UI Automation, resolves guidance via LLMs (Ollama / Groq), and projects a visual click overlay directly on the user's screen.

This specification serves as the primary system-design reference for both human engineers and AI coding agents.

---

## 1. High-Level System Flow

The system uses a multi-process architecture consisting of:
1. **The Tauri Native Host (Rust)**: Manages OS-level tasks (hotkeys, window settings, global mouse monitoring, process spawning).
2. **The Frontend App (React/TS/Vite)**: Drives two independent webviews—the **Command Bar** (`/command`) and the **Overlay canvas** (`/overlay`).
3. **The Offline Worker (Python 3.11)**: Orchestrates screen capturing, OCR, UI tree inspection, and AI inference.

```text
           ┌────────────────────────┐
           │        A. User         │
           └────────────────────────┘
                        │
                        ▼ (Hotkey)
           ┌────────────────────────┐
           │  B. Tauri App Shell    │
           │         (Rust)         │
           └────────────────────────┘
            │                      │
            ▼ (Reveal popup)       ▼ (Spawn process)
 ┌────────────────────┐  ┌────────────────────┐
 │  C. Command Bar    │  │  D. Python Worker  │
 │      (React)       │  │     (main.py)      │
 └────────────────────┘  └────────────────────┘
            │                      │
            ▼ (runTutor IPC)       │ (Reads Context)
            └──────────────────────┼─────────────┐
                                   ▼             ▼
                         ┌───────────┐ ┌───────────┐
                         │EasyOCR/   │ │pywinauto  │
                         │WinRT OCR  │ │ UIA Tree  │
                         └───────────┘ └───────────┘
                                   │             │
                                   ▼             ▼
                         ┌─────────────────────────┐
                         │   E. LLM Model Router   │
                         │     (Ollama / Groq)     │
                         └─────────────────────────┘
                                       │
                                       ▼ (Attach steps)
                         ┌─────────────────────────┐
                         │ F. Targets Fuzzy Match  │
                         │    (SequenceMatcher)    │
                         └─────────────────────────┘
                                       │
                                       ▼ (JSON Stdout)
                          ┌────────────────────────┐
                          │  B. Tauri App Shell    │
                          └────────────────────────┘
                                        │
                                        ▼ (blinky://guidance)
                          ┌────────────────────────┐
                          │  G. Overlay Canvas     │
                          │        (React)         │
                          └────────────────────────┘
                                        │
                                        ▼ (Draw Rings)
                                  User Desktop
```

---

## 2. Request Lifecycle Sequence

The sequence diagram below traces the end-to-end flow of a single tutor request, showing how coordinates are preserved across process borders.

```text
  ┌──────────────────────────────────────────────────┐
  │ 1. USER: Enters prompt in Command Bar            │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 2. Command Bar: Sends run_tutor IPC call         │
  │    with optional workflow progress               │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 3. Tauri Host: Spawns Python Worker              │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 4. Python Worker: Classifies chat vs screen task │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 5. Python Worker: For screen tasks, resolves     │
  │    target window PID before OCR                  │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 6. Python Worker: Captures screen via dxcam      │
  │    Records physical screen resolution for UIA    │
  │    coordinate normalisation                      │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 7. Python Worker: Runs WinRT/EasyOCR             │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 8. Python Worker: Re-resolves target window by   │
  │    PID -> fresh COM element -> UIA tree scan     │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 9. Python Worker: Scales UIA coords from screen  │
  │    space -> screenshot space, merges with OCR    │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 10. Python Worker: Queries Ollama / Groq         │
  │     with visible UI and completed step context   │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 11. Python Worker: Fuzzy-matches returned targets│
  │     to text bounding coordinates                 │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 12. Tauri Host: Receives result & emits          │
  │     guidance payload overlay event               │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 13. Overlay: Scales bounds & renders only the    │
  │     next matched Action Guide highlight          │
  └──────────────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────────────┐
  │ 14. Tauri Host: Mouse hook catches highlighted   │
  │     clicks, records progress, and reruns only    │
  │     when more guide steps remain                 │
  └──────────────────────────────────────────────────┘
```

---

## 3. Core Component Reference

### 3.1 Native Host Shell (`src-tauri/`)
* **`src-tauri/src/lib.rs`**: Main entryway. Registers Tauri commands, builds system tray context, and sets up window controls. It registers global shortcut hooks (`Ctrl + Shift + Enter` or `Ctrl + Shift + Space`) and spawns a background OS thread for mouse click monitoring.
* **`tauri.conf.json`**: Window configuration. Configures the frameless command bar, transparency keys, and sets the overlay window to native full-screen.

### 3.2 Frontend GUI (`frontend/src/`)
* **Vite Multi-route Entry (`main.tsx`)**: Inspects `window.location.pathname` to branch rendering into three routes dynamically:
  * `/command` $\rightarrow$ `CommandBar.tsx` (command popup).
  * `/overlay` $\rightarrow$ `Overlay.tsx` (full-screen transparent highlight map).
  * `/` $\rightarrow$ `App.tsx` (tutor window container).
* **Command Bar Controller (`CommandBar.tsx`)**: Manages textarea size dynamically via `ResizeObserver`, calls `resizeCommandWindow` Tauri command to prevent layout clipping, and drives the settings pane. It also tracks workflow progress from highlighted clicks, keeps completed Action Guide history visible, treats text-entry/search highlight clicks as focus-only actions, appends one freshly-read current step at a time, hides task summaries while actionable steps remain, shows verified completion summaries, and speaks the current guide step only when the workflow started with voice readback.
* **Overlay Canvas (`Overlay.tsx`)**: Scales coordinates from screenshot space to overlay CSS pixels. It renders only the filtered current Action Guide step, emits completed step metadata on highlighted clicks, and caps displayed highlight boxes so oversized UIA bounding rects do not produce giant rectangles on screen.

### 3.3 Python Engine (`python/`)
* **`main.py`**: Orchestrates the full pipeline. It first runs a text-only preflight classifier so casual chat does not capture the screen. For screen-bound tasks it resolves the target window PID before OCR starts, passes the PID to UIA so a fresh COM element is always used, normalises UIA coordinates from physical screen space to screenshot space before merging with OCR items, and passes completed workflow progress into the prompt.
* **`capture/screen.py`**: Captures the primary display via `dxcam` (falling back to PIL `ImageGrab`). Records both the pre-scaling physical screen resolution (`screen_width`, `screen_height`) and the post-thumbnail screenshot dimensions (`width`, `height`). These are used downstream to compute the UIA→screenshot scale factors.
* **`ocr/extract.py`**: OCR hub. Tries Windows WinRT OCR first (instant, lightweight C++ API), falling back to PyTorch-powered local `EasyOCR` if native WinRT bindings are missing.
* **`utils/matching.py`**: Fuzzy matching utility. Scores targets using difflib string similarities alongside coordinate weight metrics.
* **`utils/uia.py`**: Queries the Windows active window's UI Automation tree via `pywinauto`. Accepts an optional `target_pid` so it always scans the app that was in focus at query time, not the app in focus when UIA runs (which may differ after the OCR wait).
* **`utils/window.py`**: Z-order window scanner. Returns the first non-Blinky visible window. Accepts `target_pid` to restrict the scan to a specific process, enabling PID-based window locking across the OCR phase.

---

## 4. Protocols & API Contracts

### 4.1 Stdin CLI Request Format
The Tauri host communicates with the Python worker by piping a JSON payload into the worker's standard input:

```json
{
  "question": "How do I expand the frontend directory?",
  "progress": {
    "completed_targets": ["Explorer"],
    "completed_instructions": ["Open the Explorer panel."]
  }
}
```

`progress` is optional. The frontend supplies it only while continuing an Action Guide after a highlighted click.

### 4.2 Stdout JSON Result Schema
The Python worker must output a single, valid JSON object to standard output on completion:

```json
{
  "summary": "Detailed textual explanation of what to do next.",
  "steps": [
    {
      "step": 1,
      "instruction": "Click on the 'frontend' folder in your workspace explorer.",
      "target_text": "frontend",
      "match": {
        "text": "frontend",
        "x": 240,
        "y": 482,
        "width": 110,
        "height": 24,
        "confidence": 0.92,
        "source": "ocr"
      }
    }
  ],
  "active_app": {
    "title": "Jarvis - Antigravity IDE",
    "process": "antigravity ide.exe",
    "supported": true
  },
  "ocr": {
    "count": 42,
    "items": [
      {
        "text": "frontend",
        "x": 240,
        "y": 482,
        "width": 110,
        "height": 24,
        "confidence": 0.92,
        "source": "ocr"
      }
    ]
  },
  "screenshot": {
    "path": "tmp\\captures\\screen-17170123456.jpg",
    "width": 1728,
    "height": 1080
  },
  "elapsed_ms": 740,
  "provider": "Ollama",
  "warnings": []
}
```

> **Note**: `screenshot.width` and `screenshot.height` reflect the post-thumbnail dimensions, not the physical screen resolution. The Overlay uses these to compute `scaleX`/`scaleY`.

If an unhandled exception occurs inside the worker, it prints a standard error payload and exits with code 1:

```json
{
  "error": "Detailed description of error context",
  "steps": [],
  "warnings": ["Detailed description of error context"]
}
```

### 4.3 Tauri Inter-Process Events

#### `blinky://guidance`
* **Source**: Tauri Command `run_tutor`
* **Destination**: `/overlay` webview
* **Payload**: The exact JSON stdout structure from the Python worker.
* **Action**: Signals the overlay webview to display highlight rings.

#### `blinky://open-command`
* **Source**: Tauri Global Hotkey handler
* **Destination**: `/command` webview
* **Payload**: `()`
* **Action**: Commands the popup bar to focus the textarea.

#### `blinky://global-click`
* **Source**: Rust background mouse thread
* **Destination**: `/overlay` webview
* **Payload**:
  ```json
  {
    "x": 1240,
    "y": 512,
    "overlay_x": 0,
    "overlay_y": 0,
    "scale_factor": 1.25
  }
  ```
* **Action**: Used by the overlay to verify if the user clicked on a highlight.

#### `blinky://target-clicked`
* **Source**: `/overlay` webview
* **Destination**: `/command` webview
* **Payload**:
  ```json
  {
    "key": "1-Extensions-18-170",
    "step": 1,
    "target_text": "Extensions",
    "instruction": "Open the Extensions panel."
  }
  ```
* **Action**: Records completed workflow progress and hides the old overlay for click-only steps. For text-entry/search/input steps, the highlighted click only focuses the target and does not mark the step complete or rerun the model; the next step should appear only after a later fresh screen state proves the required typed/search action has happened. Click-only completions rerun `run_tutor` with the progress payload after a short UI-settle delay, then wait for the fresh screen read before displaying/highlighting the next step or showing a verified completion summary. The controller never treats the last clicked step in an old plan as proof that the workflow is complete.

### 4.4 Chat, Guidance, and Voice Readback Contract

* Casual chat requests use `build_preflight_prompt()` followed by `build_chat_prompt()` and return a direct summary with `steps: []`.
* Screen-bound workflow requests use `build_prompt()` with visible OCR/UIA items and optional `progress`.
* Actionable workflows keep completed guide rows visible, append one freshly-read current step, and suppress the summary bubble while actionable steps remain, so hidden summary text is not treated as the user-facing task instruction.
* `target_text` must contain an exact visible control only when that control should be highlighted now. Later invisible steps can remain in the model payload with `target_text: ""`, but the overlay receives only the current pending step.
* Voice readback for workflows speaks the current guide step only when the workflow began from voice input. Typed workflows remain silent during highlight-click continuations. Informational, casual, or verified completion answers speak the summary only when readback was requested.

---

## 5. Architectural Trade-offs & Calculations

### 5.1 Resolution Normalization and Scale Mapping

#### Screenshot Scaling
Screens can be captured at any physical resolution (e.g. 2560×1600, 4K). To maintain reliable OCR speed and lower model prompt sizes, `capture/screen.py` downsamples screenshots using Lanczos resizing to fit within:
$$\text{Max Resolution} = 1920 \times 1080 \text{ px (preserving aspect ratio)}$$

The actual output dimensions depend on the screen's aspect ratio. For example, a 2560×1600 (16:10) screen produces a 1728×1080 screenshot.

`capture_screen()` returns a `Screenshot` object with both:
* `width` / `height` — the post-thumbnail screenshot dimensions.
* `screen_width` / `screen_height` — the original capture dimensions (physical screen).

#### UIA Coordinate Normalisation
Windows UI Automation returns element bounding rectangles in **physical screen-absolute pixels** — the same coordinate space as `screen_width × screen_height`. OCR items, however, are already in **screenshot space** (`width × height`).

To put both sources in the same space before the overlay applies its scale transform, `main.py` normalises UIA coordinates:

$$s_x = \frac{\text{screenshot.width}}{\text{screenshot.screen\_width}}, \quad s_y = \frac{\text{screenshot.height}}{\text{screenshot.screen\_height}}$$

$$x_{\text{ss}} = \lfloor x_{\text{uia}} \times s_x \rceil, \quad y_{\text{ss}} = \lfloor y_{\text{uia}} \times s_y \rceil$$

For a 2560×1600 screen producing a 1728×1080 screenshot: $s_x = s_y = 0.675$.

#### Overlay Display Scaling
When `/overlay` renders, it maps screenshot-space coordinates to browser viewport pixels:

$$\text{scale}_x = \frac{\text{window.innerWidth}}{\text{screenshot.width}}, \quad \text{scale}_y = \frac{\text{window.innerHeight}}{\text{screenshot.height}}$$

$$\text{frame.left} = \text{round}(x_{\text{ss}} \times \text{scale}_x), \quad \text{frame.top} = \text{round}(y_{\text{ss}} \times \text{scale}_y)$$

The two scale factors cancel correctly:
$$x_{\text{screen}} = x_{\text{uia}} \times s_x \times \text{scale}_x = x_{\text{uia}} \times \frac{\text{screenshot.width}}{\text{screen\_width}} \times \frac{\text{window.innerWidth}}{\text{screenshot.width}} = x_{\text{uia}} \times \frac{\text{window.innerWidth}}{\text{screen\_width}}$$

On a standard display (window fills screen): $\text{window.innerWidth} = \text{screen\_width}$, so the element appears at its exact pixel position.

#### Highlight Box Size Cap
UIA bounding rects sometimes encompass a whole row or panel rather than the visual control. The overlay uses dynamic caps so small icon targets stay icon-sized and wider row targets remain readable without covering the full panel:

```typescript
const MAX_BOX_WIDTH = isIcon ? 100 : 140;
const MAX_BOX_HEIGHT = isIcon ? 40 : 44;
const MIN_BOX_SIZE = 36;
const displayWidth = Math.min(Math.max(MIN_BOX_SIZE, rawWidth), MAX_BOX_WIDTH);
const displayHeight = Math.min(Math.max(MIN_BOX_SIZE, rawHeight), MAX_BOX_HEIGHT);
```

### 5.2 Window Locking & COM Staleness

OCR takes approximately 15 seconds. If `get_target_window_element()` is called after OCR, it may return a different app (whichever the user focused during OCR). Additionally, caching a pywinauto `UIAWrapper` COM object across the OCR wait causes it to become stale—`descendants()` returns near-empty results.

**Solution**: Extract the target window's **PID** before OCR starts. Both `get_active_window()` and `get_visible_ui_text()` accept `target_pid`. When UIA runs (after OCR), it re-scans the Z-order filtered to that PID, acquiring a **fresh COM element** for the correct app.

```
before OCR  →  target_pid = window.process_id()   (PID is stable for process lifetime)
after OCR   →  fresh_element = find_window(pid=target_pid)   (new COM handle, not stale)
```

### 5.3 Merge and Deduplication Matrix
To coordinate UIA items and OCR text boxes, `main.py` runs a grid deduplication helper:
1. Inputs are rounded into coarse buckets by dividing coordinates by $8$ pixels.
2. UIA items are placed first in the merged list (higher priority — icon labels are richer in UIA than OCR).
3. If two elements have identical text in the same bucket, the first entry (UIA) wins.

### 5.4 Step-to-Target Matching Heuristics
The LLM returns target labels in plain text. The matcher (`python/utils/matching.py`) finds the best screen element using a fuzzy scoring formula:

1. **Exact Match**: If normalized target equals normalized text, `score = 1.0`.
2. **Substring Match**: If target is a substring of the text (or vice versa), `score = 0.86`.
3. **Fuzzy Match**: Calls `difflib.SequenceMatcher.ratio()`. If ratio is $< 0.65$, it is ignored.
4. **Confidence & Source Bonuses**:
   $$\text{Weighted Score} = (\text{Similarity Score} \times 0.94) + (\text{OCR Confidence} \times 0.06) + \text{Bonus}_{source}$$
   * $\text{Bonus}_{source} = 0.02$ if the source is `ocr`.
   * Minimum acceptance threshold: **`Weighted Score >= 0.52`**.

---

## 6. Environment & Settings Variables

Configure system variables inside a `.env` file in the project root:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `BLINKY_AI_PROVIDER` | `ollama` | Intelligence source. Set to `ollama` (local) or `groq` (cloud). |
| `BLINKY_OLLAMA_URL` | `http://localhost:11434/api/generate` | Custom URL endpoint for local Ollama instances. |
| `BLINKY_OLLAMA_MODEL` | `gemma4:e4b` | Ollama model name to pull and execute. |
| `BLINKY_GROQ_MODEL` | `llama-3.1-70b-versatile` | Groq model. Vision models are chosen dynamically. |
| `BLINKY_GROQ_API_KEY` | *(None)* | API secret key needed if using Groq cloud options. |
| `BLINKY_SHORTCUT` | `Enter` | The primary popup hotkey. Evaluates to `Ctrl + Shift + Enter`. |

---

## 7. AI Agent Development Guidelines

When modifying this repository, AI agents must adhere to the following architectural rules:

1. **Maintain Stdin/Stdout Purity**: The Python worker must only output valid JSON to `stdout`. Do not write log outputs, warnings, or debug messages to `stdout`. Pipe all telemetry and error traces to `stderr` or use the custom logger (`LOGGER`).
2. **Handle Optional WinRT Imports Gracefully**: Windows OCR packages (`winrt`) are not guaranteed on all dev environments. Never make `winrt` a hard top-level dependency in `ocr/extract.py`. Keep imports scoped inside functional try-except blocks, falling back to EasyOCR.
3. **Keep Bounding Box Coordinate Integrity**: UIA coordinates are in physical screen space. Always normalise them to screenshot space (multiply by `screenshot.width / screenshot.screen_width`) before passing to the overlay pipeline. Do not apply any additional manual offsets — pywinauto returns screen-absolute coordinates by design.
4. **Never Bypass the Overlay Passthrough Policy**: The overlay window must remain click-through (`set_ignore_cursor_events`). Never change this setting in Tauri window creation, as it will block standard OS interactions.
5. **Lock the Target Window by PID, Not by COM Element**: Pywinauto `UIAWrapper` COM objects go stale after ~15 s (VS Code redraws its accessibility tree during OCR). Always extract `process_id()` before long operations and pass `target_pid` to UIA/window helpers so they re-resolve a fresh element.
6. **Do Not Add Manual Y-Offsets for Electron Apps**: VS Code / Antigravity IDE UIA elements return correct screen-absolute positions. The historical "Electron chrome offset" workaround is incorrect and must not be re-applied.

---

## 8. Troubleshooting & Operational Diagnostics

Common gotchas and error conditions encountered during Windows native development:

### 8.1 Windows WinRT OCR Package Fails to Import
* **Symptom**: Python output logs print `Windows OCR unavailable: No module named 'winrt'`.
* **Root Cause**: WinRT C++ packaging requires native Windows compilers and appropriate SDK interfaces. This occurs if running within virtualized sandboxes (like Docker or WSL) or using custom Python distributions (like MSYS/Cygwin).
* **Workaround**: EasyOCR fallback triggers automatically. If native speed is required on host, ensure native Windows Python is in use and execute:
  ```powershell
  pip install winrt-Windows.Media.Ocr
  ```

### 8.2 Overlay Highlight Renders on the Wrong Element
* **Symptom**: The pulsing highlight ring appears on a different sidebar icon than expected.
* **Root Causes**:
  1. **COM Staleness**: UIA was called after OCR on a cached `UIAWrapper` object. The `descendants()` call returns very few items (e.g. 4 instead of 115).
  2. **Wrong Window**: OCR took 15 s during which the user focused a different app; UIA then scanned that app's tree.
  3. **Missing UIA→Screenshot scale**: UIA returns physical screen pixels; if not multiplied by `screenshot.width / screen_width`, coordinates overshoot on non-1080p screens.
* **Diagnosis**: Check `tmp/logs/blinky.log` for:
  * `UIA: active process = '...'` — confirm it matches the intended app.
  * `UIA: N sidebar-region elements` — N should be 8–12 for VS Code; if N < 5, COM is stale.
  * `Scaling UIA coords from screen (AxB) → screenshot (CxD)` — confirms the normalisation ran.
* **Workaround**: All three issues are addressed by the PID-locking + fresh-element pattern. Do not revert to caching the COM element.

### 8.3 Offsets or Drifting in Overlay Highlight Rings (DPI Scaling)
* **Symptom**: Highlights render consistently offset from visual elements across all elements.
* **Root Cause**: Windows display scaling (e.g. `125%` or `150%`) can affect DPI. Verify scale factor is captured correctly via `blinky://global-click` coordinate logs.
* **Workaround**: Tauri's `overlay.scale_factor()` queries native display properties. The UIA→screenshot normalisation handles aspect-ratio mismatch automatically.

### 8.4 Local Ollama Inference Has Extreme Latency
* **Symptom**: Blinky status is stuck at `Reading the screen...` for more than 10 seconds.
* **Root Cause**: Ollama executes models on standard CPU cores if no compatible Nvidia CUDA or AMD ROCm graphics engines are detected.
* **Workaround**: Verify Ollama is downloaded and pulled via `ollama list`. If running on CPU-only machines, set `BLINKY_AI_PROVIDER=groq` inside your `.env` to delegate reasoning to Groq cloud APIs instantly.

### 8.5 dxcam Screen Capture Errors
* **Symptom**: Telemetry prints `dxcam capture failed, using ImageGrab: ...` or crash loop.
* **Root Cause**: dxcam targets Windows Desktop Duplication APIs (DirectX). This can fail if running on dual hybrid GPU laptops (Nvidia Optimus) where display layers are managed dynamically, or when active screen captures/sharing blocks native device handles.
* **Workaround**: Blinky catches these captures automatically and switches to standard GDI-based PIL `ImageGrab` loop, ensuring no interruption.
