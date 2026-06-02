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

The sequence diagram below traces the end-to-end flow of a single tutor request, showing how coordinates are preserved across process borders.

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
  │ 12. Python Worker: Post-processing pipeline:     │
  │     a. attach_matches() — fuzzy match targets    │
  │     b. skip_navigation_steps() — skip redundant  │
  │     c. fill_search_targets() — auto-attach       │
  │        visible search inputs to empty targets    │
  │     d. slice to steps[:1] — one step only        │
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
  │     matched Action Guide highlight (full-width   │
  │     for input controls, capped for other items)  │
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
* **`src-tauri/src/lib.rs`**: Main entryway. Registers Tauri commands, builds system tray context, and sets up window controls. It registers global shortcut hooks (`Ctrl + Shift + Enter` or `Ctrl + Shift + Space`) and spawns a background OS thread for mouse click monitoring.
* **Flicker-Free Capture Exclusion**: Before spawning the Python worker, Rust sets `WDA_EXCLUDEFROMCAPTURE` (display affinity `0x00000011`) on both the command bar and overlay windows. This hides them from DXGI/DWM captures while keeping them fully visible and interactive. When the Python worker prints `__BLINKY_CAPTURED__`, Rust immediately restores `WDA_NONE` (`0x00000000`).
* **`tauri.conf.json`**: Window configuration. Configures the frameless command bar, transparency keys, and sets the overlay window to native full-screen.

### 3.2 Frontend GUI (`frontend/src/`)
* **Vite Multi-route Entry (`main.tsx`)**: Inspects `window.location.pathname` to branch rendering into three routes dynamically:
  * `/command` → `CommandBar.tsx` (command popup).
  * `/overlay` → `Overlay.tsx` (full-screen transparent highlight map).
  * `/` → `App.tsx` (tutor window container).
* **Command Bar Controller (`CommandBar.tsx`)**: Manages textarea size dynamically via `ResizeObserver`, calls `resizeCommandWindow` Tauri command to prevent layout clipping, and drives the settings pane. **No background polling** — the tutor only runs when the user submits a query or clicks a highlighted target.
* **Overlay Canvas (`Overlay.tsx`)**: Scales coordinates from screenshot space to overlay CSS pixels. Renders only the single current Action Guide step. For input controls (Edit, TextBox, ComboBox), bypasses width capping and renders a full-width highlight frame around the entire input field. Emits completed step metadata on highlighted clicks.

### 3.3 Python Engine (`python/`)
* **`main.py`**: Orchestrates the full pipeline. Key features:
  * **Preflight classifier** with continuation detection (`is_continuation`).
  * **PID-based window locking** before OCR.
  * **Capture marker** (`__BLINKY_CAPTURED__`) for flicker-free window restoration.
  * **UIA coordinate normalisation** from physical screen space to screenshot space.
  * **Blinky UI filtering** — filters OCR items matching Blinky's own UI elements.
  * **Post-processing pipeline**: `attach_matches()` → `skip_completed_navigation_steps()` → `_fill_empty_search_targets()` → `steps[:1]`.
* **`ai/prompt.py`**: Formats screen context into compact string representation. Key rules:
  * **Single-step enforcement**: Exactly 1 step per response.
  * **Search-bar awareness**: If a search/filter input is already visible, skip the panel-opening step entirely.
  * **Visible search target_text**: Must use the exact search placeholder text (e.g. `"Search Extensions in Marketplace"`) as `target_text`.
* **`ai/client.py`**: Routes requests to `ollama_client.py` or `groq_client.py` based on `BLINKY_AI_PROVIDER`.
* **`ai/ollama_client.py`**: Local Ollama inference with `num_predict: 350`, retry logic, and 120s timeout.
* **`ai/groq_client.py`**: Cloud Groq Vision inference with `max_tokens: 350` and configurable timeout.
* **`capture/screen.py`**: Captures via `dxcam` (falling back to PIL `ImageGrab`). Records both physical screen resolution and post-thumbnail dimensions.
* **`ocr/extract.py`**: OCR hub. Tries Windows WinRT OCR first, falling back to PyTorch-powered local `EasyOCR`.
* **`utils/matching.py`**: Fuzzy matching with exact match bonus, interactive control bonuses, sidebar context bonuses, and input control preference for search/type instructions.
* **`utils/uia.py`**: Queries UIA tree via `pywinauto`. Accepts `target_pid` for fresh COM element resolution. Returns screen-absolute coordinates.
* **`utils/window.py`**: Z-order window scanner with `target_pid` support and Blinky exclusion.

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

> **Note**: `steps` always contains **at most 1 step** (enforced by the backend). `screenshot.width`/`height` reflect post-thumbnail dimensions, not the physical screen resolution.

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

### 4.4 Chat, Guidance, and Voice Readback Contract

* Casual chat requests use `build_preflight_prompt()` followed by `build_chat_prompt()` and return a direct summary with `steps: []`.
* The preflight classifier also detects **continuations** (`is_continuation`) — follow-ups like "what next?" or "done" that refer to the previous active goal rather than starting a new task.
* Screen-bound workflow requests use `build_prompt()` with visible OCR/UIA items and optional `progress` context.
* The AI generates exactly **1 step** per request. The backend enforces this with both prompt rules and programmatic `steps[:1]` slicing.
* `target_text` must contain the **exact visible text** of the control to highlight. For search inputs, this is the placeholder text (e.g. `"Search Extensions in Marketplace"`). The backend fallback `_fill_empty_search_targets()` auto-attaches visible search inputs when the AI leaves `target_text` empty.
* Voice readback speaks the current guide step only when the workflow began from voice input. Typed workflows remain silent during highlight-click continuations.

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

#### Highlight Box Sizing
The overlay uses dynamic size caps and input-specific bypasses:

```typescript
// Standard elements: capped sizes
const MAX_BOX_WIDTH = isIcon ? 100 : 140;
const MAX_BOX_HEIGHT = isIcon ? 40 : 44;
const MIN_BOX_SIZE = 36;

// Input controls (Edit, TextBox, ComboBox): full-width bypass
if (isInput) {
  displayWidth = rawWidth;   // no cap
  displayLeft = rawLeft;     // no centering shift
}
```

### 5.2 Window Locking & COM Staleness

OCR takes approximately 15 seconds. If `get_target_window_element()` is called after OCR, it may return a different app. Additionally, caching a pywinauto `UIAWrapper` COM object across the OCR wait causes it to become stale.

**Solution**: Extract the target window's **PID** before OCR starts. Both `get_active_window()` and `get_visible_ui_text()` accept `target_pid`. When UIA runs (after OCR), it re-scans the Z-order filtered to that PID, acquiring a **fresh COM element** for the correct app.

### 5.3 Merge and Deduplication Matrix
To coordinate UIA items and OCR text boxes, `main.py` runs a grid deduplication helper:
1. Inputs are rounded into coarse buckets by dividing coordinates by $8$ pixels.
2. UIA items are placed first (higher priority). If a UIA item matches an OCR item on the same row, the UIA bounds are overridden with the precise OCR bounds.
3. **Input control calibration**: OCR items that fall inside a UIA input control's bounding box are expanded to the full input control dimensions and inherit its `control_type`.
4. If two elements have identical text in the same bucket, the first entry (UIA) wins.

### 5.4 Step-to-Target Matching Heuristics
The LLM returns target labels in plain text. The matcher (`python/utils/matching.py`) finds the best screen element using a weighted scoring formula:

1. **Exact Match**: If normalized target equals normalized text, `score = 1.0`.
2. **Substring Match**: If target is a substring of the text (or vice versa), `score = 0.86`.
3. **Fuzzy Match**: Calls `difflib.SequenceMatcher.ratio()`. If ratio is $< 0.65$, it is ignored.
4. **Weighted Score Formula**:
   $$\text{Score} = (\text{Similarity} \times 0.94) + (\text{OCR Confidence} \times 0.06) + \sum \text{Bonuses}$$
   
   Bonuses include:
   * **OCR source**: $+0.02$
   * **Size**: Up to $+0.05$ based on element area
   * **Sidebar context**: $+0.20$ if instruction mentions "sidebar"/"left" and element is in sidebar region
   * **Interactive control**: $+0.24$ for UIA buttons/tabs/menus when instruction asks for an interactive element
   * **Input control preference**: $+0.30$ when instruction is a type/search action and element is an input control
   * **Exact match bonus**: $+0.30$ for case-insensitive exact string match
   * **Blinky source penalty**: $-0.40$ for elements from Blinky's own UI

   Minimum acceptance threshold: **`Score >= 0.52`**.

### 5.5 Step Post-Processing Pipeline

After the AI model returns its response, the backend applies a four-stage pipeline:

1. **`attach_matches(steps, visible_items)`**: Fuzzy-matches each step's `target_text` to the best visible element.
2. **`skip_completed_navigation_steps(steps)`**: If step 1 is a navigation action (click tab/sidebar/menu) AND step 2's target is already visible on screen, skips step 1.
3. **`_fill_empty_search_targets(steps, visible_items)`**: If a step has a search/type instruction but empty `target_text`, auto-finds the first visible search/filter/find input and attaches it.
4. **`steps[:1]`**: Programmatically slices to at most 1 step for the frontend.

### 5.6 Flicker-Free Capture Exclusion

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
