# Slicky — System Architecture & Technical Specifications

Slicky is a local, privacy-first AI-powered desktop tutor for Windows. It captures the screen, extracts text through OCR and Windows UI Automation, resolves guidance via local heuristics or LLMs (Ollama / Groq), and projects a visual click overlay directly on the user's screen.

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
                         │ WinRT OCR │ │pywinauto  │
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
                        ▼ (clicky://guidance)
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
  ┌──────────────────────────────────────────┐
  │ 1. USER: Enters prompt in Command Bar    │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 2. Command Bar: Sends run_tutor IPC call │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 3. Tauri Host: Spawns Python Worker      │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 4. Python Worker: Captures screen and    │
  │    inspects active window UIA elements   │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 5. Python Worker: Runs WinRT OCR & merges│
  │    UI Automation controls                │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 6. Python Worker: Queries Ollama / Groq  │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 7. Python Worker: Fuzzy-matches returned │
  │    targets to text bounding coordinates  │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 8. Tauri Host: Receives result & emits   │
  │    guidance payload overlay event        │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 9. Overlay: Scales bounds & renders ring │
  │    pulsers on screen targets             │
  └──────────────────────────────────────────┘
                        │
                        ▼
  ┌──────────────────────────────────────────┐
  │ 10. Tauri Host: Mouse hook catches user  │
  │     clicks & dismisses matched overlay   │
  └──────────────────────────────────────────┘
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
* **Command Bar Controller (`CommandBar.tsx`)**: Manages textarea size dynamically via `ResizeObserver`, calls `resizeCommandWindow` Tauri command to prevent layout clipping, and drives the settings pane.
* **Overlay Canvas (`Overlay.tsx`)**: Calculates scale factor ratios mapping from the saved 1920x1080 screenshot space to active user display coordinates, placing highlights on exact pixel targets.

### 3.3 Python Engine (`python/`)
* **`main.py`**: Merges OCR and UIA coordinates via proximity grids, runs the local-intent routing, executes prompt templates, and runs fuzzy targets alignment.
* **`ocr/extract.py`**: OCR hub. Tries Windows WinRT OCR first (instant, lightweight C++ API), falling back to PyTorch-powered local `EasyOCR` if native WinRT bindings are missing.
* **`utils/matching.py`**: Fuzzy matching utility. Scores targets using difflib string similarities alongside coordinate weight metrics.
* **`utils/uia.py`**: Queries the Windows active window's UI Automation tree via `pywinauto`. Captures coordinate bounding boxes of IDE menus, tabs, and folder structures.

---

## 4. Protocols & API Contracts

### 4.1 Stdin CLI Request Format
The Tauri host communicates with the Python worker by piping a JSON payload into the worker's standard input:

```json
{
  "question": "How do I expand the frontend directory?"
}
```

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
    "title": "Jarvis - Visual Studio Code",
    "process": "code.exe",
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
    "width": 1920,
    "height": 1080
  },
  "elapsed_ms": 740,
  "provider": "Ollama",
  "warnings": []
}
```

If an unhandled exception occurs inside the worker, it prints a standard error payload and exits with code 1:

```json
{
  "error": "Detailed description of error context",
  "steps": [],
  "warnings": ["Detailed description of error context"]
}
```

### 4.3 Tauri Inter-Process Events

#### `clicky://guidance`
* **Source**: Tauri Command `run_tutor`
* **Destination**: `/overlay` webview
* **Payload**: The exact JSON stdout structure from the Python worker.
* **Action**: Signals the overlay webview to display highlight rings.

#### `clicky://open-command`
* **Source**: Tauri Global Hotkey handler
* **Destination**: `/command` webview
* **Payload**: `()`
* **Action**: Commands the popup bar to focus the textarea.

#### `clicky://global-click`
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

---

## 5. Architectural Trade-offs & Calculations

### 5.1 Resolution Normalization and Scale Mapping
Screens can be captured at any resolution (e.g. 3840x2160, 4K). To maintain reliable OCR speed and lower model prompt sizes, the capture helper (`capture/screen.py`) downsamples screenshots using Lanczos resizing:
$$\text{Target Resolution} = 1920 \times 1080 \text{ px}$$

All returned OCR pixel coordinate bounding boxes $(x_{ocr}, y_{ocr})$ are relative to this $1920 \times 1080$ frame. When `/overlay` renders, it handles high-DPI displays by mapping these coordinates back to the active browser window layout:

$$\text{scale}_x = \frac{\text{window.innerWidth}}{1920}$$
$$\text{scale}_y = \frac{\text{window.innerHeight}}{1080}$$

$$\text{frame.left} = \text{round}(x_{ocr} \times \text{scale}_x)$$
$$\text{frame.top} = \text{round}(y_{ocr} \times \text{scale}_y)$$

### 5.2 Merge and Deduplication Matrix
To coordinate UIA items and OCR text boxes, `main.py` runs a grid deduplication helper:
1. Inputs are rounded into coarse buckets by dividing coordinates by $8$ pixels.
2. If two elements have identical text values in the same bucket, the **OCR bounding box is prioritized**. OCR elements are captured from raw screenshot pixels, making them align more closely with visual overlay placement than UIA handles.

### 5.3 Step-to-Target Matching Heuristics
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
| `CLICKY_AI_PROVIDER` | `ollama` | Intelligence source. Set to `ollama` (local) or `groq` (cloud). |
| `CLICKY_OLLAMA_URL` | `http://localhost:11434/api/generate` | Custom URL endpoint for local Ollama instances. |
| `CLICKY_OLLAMA_MODEL` | `gemma4:e4b` | Ollama model name to pull and execute. |
| `CLICKY_GROQ_MODEL` | `llama-3.1-70b-versatile` | Groq model. Vision models are chosen dynamically. |
| `CLICKY_GROQ_API_KEY` | *(None)* | API secret key needed if using Groq cloud options. |
| `CLICKY_SHORTCUT` | `Enter` | The primary popup hotkey. Evaluates to `Ctrl + Shift + Enter`. |

---

## 7. AI Agent Development Guidelines

When modifying this repository, AI agents must adhere to the following architectural rules:

1. **Maintain Stdin/Stdout Purity**: The Python worker must only output valid JSON to `stdout`. Do not write log outputs, warnings, or debug messages to `stdout`. Pipe all telemetry and error traces to `stderr` or use the custom logger (`LOGGER`).
2. **Handle Optional WinRT Imports Gracefully**: Windows OCR packages (`winrt`) are not guaranteed on all dev environments. Never make `winrt` a hard top-level dependency in `ocr/extract.py`. Keep imports scoped inside functional try-except blocks, falling back to EasyOCR.
3. **Keep Bounding Box Coordinate Integrity**: Always check that coordinates remain relative to the scaled $1920 \times 1080$ screenshot frame so highlights don't shift.
4. **Never Bypass the Overlay Passthrough Policy**: The overlay window must remain click-through (`set_ignore_cursor_events`). Never change this setting in Tauri window creation, as it will block standard OS interactions.

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

### 8.2 Offsets or Drifting in Overlay Highlight Rings
* **Symptom**: The red pulsing highlight rings render offset from actual visual elements (e.g. 50px higher or shifted left).
* **Root Cause**: Occurs when Windows standard display scaling (e.g. `125%` or `150%` text size adjustments) is enabled, or multi-monitor resolutions scaling gets mismatched.
* **Workaround**: Tauri's `overlay.scale_factor()` queries native display properties to adjust DPI layers. Verify scale factor is captured correctly via `clicky://global-click` coordinates logs.

### 8.3 Local Ollama Inference Has Extreme Latency
* **Symptom**: Slicky status is stuck at `Reading the screen...` for more than 10 seconds.
* **Root Cause**: Ollama executes models on standard CPU cores if no compatible Nvidia CUDA or AMD ROCm graphics engines are detected.
* **Workaround**: Verify Ollama is downloaded and pulled via `ollama list`. If running on CPU-only machines, set `CLICKY_AI_PROVIDER=groq` inside your `.env` to delegate reasoning to Groq cloud APIs instantly.

### 8.4 dxcam Screen Capture Errors
* **Symptom**: Telemetry prints `dxcam capture failed, using ImageGrab: ...` or crash loop.
* **Root Cause**: dxcam targets Windows Desktop Duplication APIs (DirectX). This can fail if running on dual hybrid GPU laptops (Nvidia Optimus) where display layers are managed dynamically, or when active screen captures/sharing blocks native device handles.
* **Workaround**: Slicky catches these captures automatically and switches to standard GDI-based PIL `ImageGrab` loop, ensuring no interruption.

