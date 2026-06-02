# Blinky — System Architecture & Technical Specifications

Blinky is a local, privacy-first AI-powered desktop tutor for Windows. It captures the screen, extracts text through OCR and Windows UI Automation, resolves guidance via LLMs (Ollama / Groq), and projects a visual click overlay directly on the user's screen — **one step at a time**.

This specification serves as the primary system-design reference for both human engineers and AI coding agents.

---

## 1. High-Level System Flow

The system uses a multi-process architecture consisting of:
1. **The Tauri Native Host (Rust)**: Manages OS-level tasks (hotkeys, window settings, capture exclusion, global mouse monitoring, process spawning).
2. **The Frontend App (React/TS/Vite)**: Drives two independent webviews—the **Command Bar** (`/command`) and the **Overlay canvas** (`/overlay`).
3. **The Offline Worker (Python 3.11)**: Orchestrates screen capturing, OCR, UI tree inspection, AI inference, and step post-processing.

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
                                        ▼ (Post-processing)
                          ┌─────────────────────────┐
                          │ F. Step Post-Processor   │
                          │  attach_matches()        │
                          │  skip_navigation_steps() │
                          │  fill_search_targets()   │
                          │  slice to [:1]           │
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
                                         ▼ (Draw Pulse)
                                   User Desktop
```

---

## 2. Request Lifecycle Sequence

The sequence diagram below traces the end-to-end flow of a single tutor request, showing how coordinates are preserved across process boundaries.

```text
  ┌──────────────────────────────────────────────────┐
  │ 1. USER: Enters prompt in Command Bar            │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 2. Command Bar: Sends run_tutor IPC call         │
  │    with optional workflow progress and           │
  │    previous_question for continuations           │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 3. Tauri Host: Sets WDA_EXCLUDEFROMCAPTURE on    │
  │    command + overlay windows (flicker-free)      │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 4. Tauri Host: Spawns Python Worker              │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 5. Python Worker: Resolves target window PID     │
  │    BEFORE any screen capture                     │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 6. Python Worker: Captures screen via dxcam,     │
  │    prints __BLINKY_CAPTURED__ marker to stdout   │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 7. Tauri Host: Reads __BLINKY_CAPTURED__,        │
  │    restores WDA_NONE on both windows             │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 8. Python Worker: Runs preflight classifier      │
  │    (chat vs screen, continuation detection)      │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 9. Python Worker: Runs WinRT/EasyOCR + UIA       │
  │    (re-resolves fresh COM element by PID)        │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 10. Python Worker: Scales UIA coords from screen │
  │     space → screenshot space, merges with OCR    │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 11. Python Worker: Queries Ollama / Groq         │
  │     (single-step mode, max 350 output tokens)    │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 12. Python Worker: Post-processing pipeline      │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 13. Tauri Host: Receives result & emits          │
  │     guidance payload overlay event               │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 14. Overlay: Scales bounds & renders the single  │
  │     matched Action Guide highlight               │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │ 15. Tauri Host: Mouse hook catches highlighted   │
  │     clicks, records progress, and reruns with    │
  │     fresh screen state for next step             │
  └──────────────────────────────────────────────────┘
```

---

## 3. Core Component Reference

### 3.1 Native Host Shell (`src-tauri/`)
* **[lib.rs](file:///c:/projects/Jarvis/src-tauri/src/lib.rs)**: Main entryway. Registers Tauri commands, builds system tray context, and sets up window controls. It registers global shortcut hooks (`Ctrl + Shift + Enter` or `Ctrl + Shift + Space`) and spawns a background OS thread for mouse click monitoring.
* **Flicker-Free Capture Exclusion**: Before spawning the Python worker, Rust sets `WDA_EXCLUDEFROMCAPTURE` (display affinity `0x00000011`) on both the command bar and overlay windows. This hides them from DXGI/DWM captures while keeping them fully visible and interactive. When the Python worker prints `__BLINKY_CAPTURED__`, Rust immediately restores `WDA_NONE` (`0x00000000`).
* **[tauri.conf.json](file:///c:/projects/Jarvis/src-tauri/tauri.conf.json)**: Window configuration. Configures the frameless command bar, transparency keys, and sets the overlay window to native full-screen.

### 3.2 Frontend GUI (`frontend/src/`)
* **[main.tsx](file:///c:/projects/Jarvis/frontend/src/main.tsx)**: Vite Multi-route Entry. Inspects `window.location.pathname` to branch rendering into three routes dynamically:
  * `/command` → `CommandBar.tsx` (command popup).
  * `/overlay` → `Overlay.tsx` (full-screen transparent highlight map).
  * `/` → `App.tsx` (tutor window container).
* **[CommandBar.tsx](file:///c:/projects/Jarvis/frontend/src/CommandBar.tsx)**: Manages textarea size dynamically via `ResizeObserver`, calls `resizeCommandWindow` Tauri command to prevent layout clipping, and drives the settings pane. **No background polling** — the tutor only runs when the user submits a query or clicks a highlighted target.
* **[Overlay.tsx](file:///c:/projects/Jarvis/frontend/src/Overlay.tsx)**: Scales coordinates from screenshot space to overlay CSS pixels. Renders only the single current Action Guide step. For input controls (Edit, TextBox, ComboBox), bypasses width capping and renders a full-width highlight frame around the entire input field. Emits completed step metadata on highlighted clicks. See the [Coordinate Scaling Guide](file:///c:/projects/Jarvis/ai/02_coordinate_scaling.md) for full details.

### 3.3 Python Engine (`python/`)
* **[main.py](file:///c:/projects/Jarvis/python/main.py)**: Orchestrates the full pipeline. Key features:
  * Preflight classifier with continuation detection (`is_continuation`).
  * PID-based window locking before OCR.
  * Capture marker (`__BLINKY_CAPTURED__`) for flicker-free window restoration.
  * UIA coordinate normalisation from physical screen space to screenshot space.
  * Blinky UI filtering — filters OCR items matching Blinky's own UI elements.
  * Post-processing pipeline.
* **[prompt.py](file:///c:/projects/Jarvis/python/ai/prompt.py)**: Formats screen context into compact string representation. Key rules:
  * Single-step enforcement: Exactly 1 step per response.
  * Search-bar awareness: If a search/filter input is already visible, skip the panel-opening step entirely.
  * Visible search target_text: Must use the exact search placeholder text (e.g. `"Search Extensions in Marketplace"`) as `target_text`.
* **[client.py](file:///c:/projects/Jarvis/python/ai/client.py)**: Routes requests to `ollama_client.py` or `groq_client.py` based on `BLINKY_AI_PROVIDER`. See the [AI Inference Guide](file:///c:/projects/Jarvis/ai/04_ai_inference.md) for detailed descriptions.
* **[screen.py](file:///c:/projects/Jarvis/python/capture/screen.py)**: Captures via `dxcam` (falling back to PIL `ImageGrab`). Records both physical screen resolution and post-thumbnail dimensions.
* **[extract.py](file:///c:/projects/Jarvis/python/ocr/extract.py)**: OCR hub. Tries Windows WinRT OCR first, falling back to PyTorch-powered local `EasyOCR`.
* **[matching.py](file:///c:/projects/Jarvis/python/utils/matching.py)**: Fuzzy matching with exact match bonus, interactive control bonuses, sidebar context bonuses, and input control preference for search/type instructions. See the [Target Matching Heuristics Guide](file:///c:/projects/Jarvis/ai/03_matching_heuristics.md) for matching details.
* **[uia.py](file:///c:/projects/Jarvis/python/utils/uia.py)**: Queries UIA tree via `pywinauto`. Accepts `target_pid` for fresh COM element resolution. Returns screen-absolute coordinates.
* **[window.py](file:///c:/projects/Jarvis/python/utils/window.py)**: Z-order window scanner with `target_pid` support and Blinky exclusion.

---

## 4. Protocols & API Contracts

### 4.1 Stdin CLI Request Format
The Tauri host communicates with the Python worker by piping a JSON payload into the worker's standard input:

```json
{
  "question": "How do I install the code runner extension?",
  "previous_question": "tell me the steps to download code runner extension",
  "progress": {
    "completed_targets": ["Extensions"],
    "completed_instructions": ["Open the Extensions panel."]
  }
}
```

* `progress` is optional. The frontend supplies it only while continuing an Action Guide after a highlighted click.
* `previous_question` is optional. Supplied when there is an active goal/task in progress for continuation detection.

### 4.2 Stdout JSON Result Schema
The Python worker must output a single, valid JSON object to standard output on completion:

```json
{
  "summary": "In Jarvis - Antigravity IDE, type 'Code Runner' into the search bar.",
  "steps": [
    {
      "step": 1,
      "instruction": "Type 'Code Runner' into the search bar.",
      "target_text": "Search Extensions in Marketplace",
      "match": {
        "text": "Search Extensions in Marketplace",
        "x": 82,
        "y": 90,
        "width": 320,
        "height": 30,
        "confidence": 0.9,
        "source": "uia",
        "control_type": "Edit"
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
    "items": [...]
  },
  "screenshot": {
    "path": "tmp\\captures\\screen-17170123456.jpg",
    "width": 1728,
    "height": 1080
  },
  "elapsed_ms": 740,
  "provider": "Ollama",
  "warnings": [],
  "is_continuation": false
}
```

If an unhandled exception occurs, the worker prints an error payload and exits with code 1:

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
* **Action**: Signals the overlay webview to display the highlight ring.

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
* **Action**: Records completed workflow progress. Click-only completions rerun `run_tutor` with the progress payload after a short delay, then wait for the fresh screen read before displaying the next step. Text-entry/search highlight clicks are treated as focus actions only.

---

## 5. Architectural Implementation Details

Detailed specifications for coordinate calculations, target resolution, and AI prompting can be found in the dedicated guides below:
* **[Coordinate Scaling & Normalization Guide](file:///c:/projects/Jarvis/ai/02_coordinate_scaling.md)**: Physical screen downsampling, UIA bounds normalization, CSS display scaling, and highlight capping rules.
* **[Target Matching Heuristics Guide](file:///c:/projects/Jarvis/ai/03_matching_heuristics.md)**: Weighted fuzzy matching score calculations, interactive bonuses, grid deduplication matrix, and post-processing steps pipeline.
* **[AI Inference Guide](file:///c:/projects/Jarvis/ai/04_ai_inference.md)**: Preflight classifier, conversation logic, compact prompting, and Ollama/Groq provider details.
* **[Sarvam AI Voice Integration Guide](file:///c:/projects/Jarvis/ai/05_sarvam.md)**: Text-to-speech payload schemas, speech-to-text multipart transcript processing, voice-first constraint logic, settings hooks, and voice readback state.

### 5.1 Window Locking & COM Staleness
OCR operations can take several seconds. If `get_target_window_element()` is called after OCR, it may return a different app. Additionally, caching a pywinauto `UIAWrapper` COM object across the OCR wait causes it to become stale.

**Solution**: Extract the target window's **PID** before OCR starts. Both `get_active_window()` and `get_visible_ui_text()` accept `target_pid`. When UIA runs (after OCR), it re-scans the Z-order filtered to that PID, acquiring a **fresh COM element** for the correct app.

### 5.2 Flicker-Free Capture Exclusion
Instead of hiding/showing windows during capture (which causes flicker), Rust uses the Windows Display Affinity API:

```text
Before capture  →  SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE = 0x00000011)
Python prints __BLINKY_CAPTURED__  →  SetWindowDisplayAffinity(hwnd, WDA_NONE = 0x00000000)
```

This keeps the windows visible to the user while invisible to DXGI/DWM screen capture, with restoration happening within ~100ms of capture completion.

---

## 6. Environment & Settings Variables

Configure system variables inside a `.env` file in the project root:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `BLINKY_AI_PROVIDER` | `ollama` | Intelligence source. Set to `ollama` (local) or `groq` (cloud). |
| `BLINKY_OLLAMA_URL` | `http://localhost:11434/api/generate` | Custom URL endpoint for local Ollama instances. |
| `BLINKY_OLLAMA_MODEL` | `gemma4:e4b` | Ollama model name to pull and execute. |
| `BLINKY_GROQ_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq model for vision and text inference. |
| `GROQ_API_KEY` | *(None)* | API secret key needed if using Groq cloud options. |
| `BLINKY_GROQ_TIMEOUT` | `90` | Timeout in seconds for Groq API requests. |
| `BLINKY_SHORTCUT` | `Enter` | The primary popup hotkey. Evaluates to `Ctrl + Shift + Enter`. |
| `SARVAM_API_KEY` | *(None)* | API key for Sarvam AI voice services. |

---

## 7. AI Agent Development Guidelines

When modifying this repository, AI agents must adhere to the following architectural rules:

1. **Maintain Stdin/Stdout Purity**: The Python worker must only output valid JSON to `stdout`. The only exception is the `__BLINKY_CAPTURED__` marker line, which must be printed immediately after screen capture and flushed. Pipe all other telemetry to `stderr` or use the custom logger (`LOGGER`).
2. **Handle Optional WinRT Imports Gracefully**: Windows OCR packages (`winrt`) are not guaranteed on all dev environments. Keep imports scoped inside functional try-except blocks, falling back to EasyOCR.
3. **Keep Bounding Box Coordinate Integrity**: UIA coordinates are in physical screen space. Always normalise them to screenshot space (multiply by `screenshot.width / screenshot.screen_width`) before passing to the overlay pipeline. Do not apply any additional manual offsets.
4. **Never Bypass the Overlay Passthrough Policy**: The overlay window must remain click-through (`set_ignore_cursor_events`).
5. **Lock the Target Window by PID, Not by COM Element**: Always extract `process_id()` before long operations and pass `target_pid` to UIA/window helpers so they re-resolve a fresh element.
6. **Do Not Add Manual Y-Offsets for Electron Apps**: VS Code / Antigravity IDE UIA elements return correct screen-absolute positions.
7. **Preserve Single-Step Mode**: The prompt must enforce exactly 1 step. The backend must slice `steps[:1]`. Do not revert to multi-step generation — it causes significant local Ollama latency (3+ seconds of unnecessary token generation).
8. **Maintain the Post-Processing Pipeline Order**: The four-stage pipeline (`attach_matches` → `skip_navigation` → `fill_search_targets` → `slice`) must run in this exact order. Adding new stages should be inserted before the final slice.
9. **Respect Token Limits**: Keep `num_predict` (Ollama) and `max_tokens` (Groq) at `350` for the main prompt. The preflight/chat prompts use `300`.
10. **Filter Blinky's Own UI**: OCR items matching Blinky's UI elements (defined in `blinky_ignored_terms`) must be filtered before being sent to the AI model.

---

## 8. Troubleshooting & Operational Diagnostics

Common gotchas and error conditions encountered during Windows native development:

### 8.1 Windows WinRT OCR Package Fails to Import
* **Symptom**: Python output logs print `Windows OCR unavailable: No module named 'winrt'`.
* **Root Cause**: WinRT C++ packaging requires native Windows compilers and appropriate SDK interfaces.
* **Workaround**: EasyOCR fallback triggers automatically. For native speed:
  ```powershell
  pip install winrt-Windows.Media.Ocr
  ```

### 8.2 Overlay Highlight Renders on the Wrong Element
* **Symptom**: The pulsing highlight ring appears on a different sidebar icon than expected.
* **Root Causes**:
  1. **COM Staleness**: UIA was called after OCR on a cached `UIAWrapper` object.
  2. **Wrong Window**: OCR took 15s during which the user focused a different app.
  3. **Missing UIA→Screenshot scale**: UIA returns physical screen pixels; if not multiplied by `screenshot.width / screen_width`, coordinates overshoot on non-1080p screens.
* **Diagnosis**: Check `tmp/logs/blinky.log` for:
  * `UIA: active process = '...'` — confirm it matches the intended app.
  * `UIA: N sidebar-region elements` — N should be 8–12 for VS Code; if N < 5, COM is stale.
  * `Scaling UIA coords from screen (AxB) → screenshot (CxD)` — confirms the normalisation ran.

### 8.3 Search Bar Highlight Missing
* **Symptom**: The green pulsing highlight doesn't appear on the search bar even though the Extensions panel is open.
* **Root Cause**: The AI model returned `target_text: ""` for the search instruction instead of the visible placeholder text.
* **Diagnosis**: Check `blinky.log` for `AI Result:` — verify the `target_text` value. Check for `Search Target Fallback:` log entry — this indicates the auto-fallback successfully attached the search input.
* **Fix Built-In**: The `_fill_empty_search_targets()` post-processor automatically scans visible items for search/filter/find input controls and attaches them when `target_text` is empty. If this is still failing, check that the UIA/OCR items list contains the search placeholder text.

### 8.4 Local Ollama Inference Has Extreme Latency
* **Symptom**: Blinky status is stuck at `Reading the screen...` for more than 10 seconds.
* **Root Cause**: Ollama executes models on standard CPU cores if no compatible Nvidia CUDA or AMD ROCm graphics engines are detected.
* **Workaround**: Verify Ollama is downloaded and pulled via `ollama list`. Set `BLINKY_AI_PROVIDER=groq` for cloud inference. Token output is capped at 350 to minimise generation time.

### 8.5 dxcam Screen Capture Errors
* **Symptom**: Telemetry prints `dxcam capture failed, using ImageGrab: ...` or crash loop.
* **Root Cause**: dxcam targets Windows Desktop Duplication APIs (DirectX). This can fail on dual hybrid GPU laptops.
* **Workaround**: Blinky catches these automatically and switches to GDI-based PIL `ImageGrab`.

### 8.6 Navigation Step Not Skipped
* **Symptom**: Blinky tells the user to "Click the Extensions tab" even though the Extensions panel is already open with the search bar visible.
* **Root Cause**: The AI generated only 1 step (the navigation step), so `skip_completed_navigation_steps()` couldn't compare against a second step.
* **Diagnosis**: The prompt rules should prevent this, but local models may not follow them reliably. The post-processing pipeline handles this by auto-attaching search targets.
