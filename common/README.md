# 🧠 Blinky — AI Desktop Tutor for Students

<div align="center">

### _Ask. Learn. Click. Done._

<br>

<p align="center">

<img src="https://img.shields.io/badge/Tauri-2.x-orange?style=for-the-badge">
<img src="https://img.shields.io/badge/React-TypeScript-61dafb?style=for-the-badge">
<img src="https://img.shields.io/badge/Bun-1.3.14-f9f1e1?style=for-the-badge">
<img src="https://img.shields.io/badge/Python-3.11-yellow?style=for-the-badge">
<img src="https://img.shields.io/badge/Playwright-Edge-green?style=for-the-badge">

</p>

<p align="center">

<img src="https://img.shields.io/badge/Ollama-gemma4:e4b-green?style=for-the-badge">
<img src="https://img.shields.io/badge/Groq-Llama4Scout-purple?style=for-the-badge">
<img src="https://img.shields.io/badge/OCR-Windows%20OCR-blue?style=for-the-badge">

</p>

<p align="center">

<img src="https://img.shields.io/badge/EasyOCR-Fallback-red?style=for-the-badge">
<img src="https://img.shields.io/badge/dxcam-Screen%20Capture-black?style=for-the-badge">
<img src="https://img.shields.io/badge/pywinauto-Window%20Detection-darkgreen?style=for-the-badge">

</p>

<br>

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![License](https://img.shields.io/badge/license-MIT-purple)

</div>

---

An AI-powered Windows desktop tutor that teaches users software directly on their screen using local AI. In web mode it can also open/search in your default Edge browser and run a bounded safe-click autopilot loop after reading the screen. In **Agent Mode** it can launch apps, play Spotify tracks, and press keyboard shortcuts entirely autonomously.

# ⚡ Quick Start

please refer to [linux_quick_start.md](./linux_quick_start.md) if you are using a **linux based machine**.

## 1️⃣ Install Prerequisites

Install the following software:

- Bun 1.3+
- Rust Stable
- Python 3.11+
- Ollama

---

## 2️⃣ Pull the AI Model

```powershell
ollama pull gemma4:e4b
```

---

## 3️⃣ Install Dependencies

```powershell
bun install
bun run setup:python
bun run check:ollama
```

---

## 4️⃣ Start Blinky

```powershell
bun run dev
```

## Optional: Start Local Web Search

For globe/web intelligence backed by SearXNG:

```powershell
docker compose up -d searxng
```

SearXNG is exposed at `http://localhost:8888` and returns JSON search results for the Python Web Intelligence Layer and Spotify URI resolution.

## ⌨️ Open Blinky

### Main Hotkey

```text
CTRL + SHIFT + SPACE
```

### Fallback Hotkey

```text
CTRL + SHIFT + ENTER
```

---

Ask something like:

```text
How do I install Python extension?
```

Blinky will:

- Capture the current screen
- Run OCR + Windows UIA
- Detect the active application
- Generate AI instructions with screen-element `@refs`
- Highlight matching UI elements
- In globe/web mode, optionally click safe matched targets for up to 5 observe-act attempts

In **Agent Mode** (🤖), Blinky can autonomously open apps, play music on Spotify, press shortcuts, scroll, and type — all with no clicks from you.

## Provider Configuration

By default Blinky uses Ollama. To switch to Groq with image understanding, set these environment variables before running:

```powershell
$env:BLINKY_AI_PROVIDER="groq"
$env:GROQ_API_KEY="your-groq-api-key"
```

Optional overrides:

```powershell
$env:BLINKY_GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"
$env:BLINKY_GROQ_URL="https://api.groq.com/openai/v1/chat/completions"
```

For Ollama overrides:

```powershell
$env:BLINKY_AI_PROVIDER="ollama"
$env:BLINKY_OLLAMA_MODEL="gemma4:e4b"
$env:BLINKY_OLLAMA_URL="http://localhost:11434/api/generate"
```

</div>

---

# 🚀 What is Blinky?

Blinky is a **hackathon-ready AI desktop tutor** that helps students learn software in real time.

Instead of:

- Watching long YouTube tutorials
- Reading confusing documentation
- Switching tabs repeatedly

Users can simply ask:

```text
"How do I install Python extension?"
"How do I crop an image?"
"How do I export this?"
"Open Spotify and play Lo-Fi beats"
"Open VS Code"
```

Blinky will:

1. Classify the request (screen action, agent action, or chat)
2. If screen-based: Capture the current screen, read UI text, detect the active app, generate AI instructions, highlight the exact button/menu to click
3. If agent-based: Directly launch apps, play music, press shortcuts, or type text
4. If informational: Answer directly without a screenshot

---

# ✨ Features

## 🌟 Recent Enhancements

### 🤖 Full Agent Mode (Computer Use)

Blinky now ships a dedicated **Agent Mode** (activate with the 🤖 button) that can perform direct computer-use actions without requiring you to click anything:

- **Open any app** — uses app protocol URIs, known executable paths, Windows Start Apps (`Get-StartApps`), and finally Windows Search as a fallback chain.
- **Play Spotify tracks** — searches SearXNG (and falls back to DuckDuckGo HTML) to resolve a `spotify:track:ID` URI and opens it directly in the Spotify desktop app.
- **Press keyboard shortcuts** — parses natural-language shortcut descriptions (`Ctrl+S`, `Alt+H`, `Win+D`) and executes them via `pywinauto`.
- **Open help menus** — detects the active app process (e.g., VS Code) and sends the correct shortcut automatically.
- **Type text into fields** — autopilot can extract quoted text from instructions and type it into focused controls.
- **Scroll screens** — autopilot detects scroll instructions and calls `scroll_at_point` through Rust `SendInput`.
- The bounded autopilot loop (max 5 attempts) now handles `type`, `search`, `submit`, and `scroll` actions in addition to safe clicks.

### 🧠 Intent Classification (Preflight Router)

Before any screenshot is taken, Blinky runs a fast **preflight classifier** that routes requests into one of five intents:

- `DESKTOP_AUTOMATION` — needs screen capture + OCR + AI overlay
- `OPEN_APP` — directly launches the named app
- `MEDIA_PLAYBACK` — plays a named song on Spotify
- `SYSTEM_SHORTCUT` — presses a keyboard shortcut
- `INFORMATIONAL_CHAT` — answers without any screen capture

Safety overrides prevent `OPEN_APP` from being triggered by in-app feature names (e.g., "tabs", "settings", "downloads") or multi-word queries.

### 🗂️ Dynamic App Context Generation

For any app Blinky hasn't seen before, `app_context/registry.py` now **auto-generates a navigation guide** on first encounter:

1. Queries SearXNG for `"<AppName> Windows keyboard shortcuts menus navigation"`
2. Asks the LLM to produce a structured markdown guide from those search results
3. Saves the guide to `python/app_context/<process_name>.md` for future runs
4. Falls back to a minimal boilerplate if both SearXNG and LLM fail

Built-in context files cover: VS Code, Chrome/Edge, File Explorer, WhatsApp, ChatGPT, Windows Settings, and Spotify.

### 🏷️ Screen Element `@ref` System

Every visible UI element is now tagged with a stable `@ref` (e.g., `@e14`). The AI prompt uses these refs for precise target identification:

- The model returns `target_ref: "@e14"` alongside `target_text`
- Matching can use the ref directly for O(1) lookup, bypassing fuzzy text search
- Refs are preserved across subsequent observations using an IOU + name-similarity cache (`utils/ui_map_cache.py`)

### 🗃️ UI Map Cache with Stable Refs

`utils/ui_map_cache.py` caches the merged OCR+UIA map for the current window with a 2-second TTL:

- Cache key is a signature of `(process, title, pid, screenshot dimensions)`
- On cache hit, visible items are returned immediately without re-running OCR or UIA
- On cache miss, fresh items are built and refs from the previous snapshot are **re-used** for unchanged elements using `automation_id` exact match and IOU/name-similarity scoring
- This makes autopilot continuation fast and stable — the same element keeps the same `@ref` across observations

### 🧭 Bounded Autopilot Loop (Extended)

Blinky can now run a small observe-act-observe loop from the command bar's Agent Mode button.

- **Safe actions**: click, open, select, choose, go to, type, enter, search, submit, scroll
- **Blocked actions**: install, enable, delete, remove, buy, purchase, pay, sign in, login
- **Scroll support**: `scroll_at_point` through Rust `SendInput` (up or down, configurable amount)
- **Type support**: Extracts quoted text from instructions and types it via `typeText` Tauri command
- **Enter support**: `shouldPressEnterAfterTyping` detects "press enter", "submit", or "search" and fires Enter after typing
- Stops after 5 attempts, when the task is complete, when the same target repeats, or when the next action is unsafe

### 🌐 Edge Browser Intelligence

The Python router now has a safer browser-planning path before generated tools.

- Common open/search/site-search requests are planned as JSON actions.
- Playwright launches visible Microsoft Edge (`msedge`) instead of a hidden throwaway browser when possible.
- Generated Playwright code is still available as a fallback, but common API mistakes are repaired before safety auditing and verification.

### 🛡️ Dynamic Capture Exclusion (Flicker-Free Mode)

Blinky now uses the native Windows API (`SetWindowDisplayAffinity` / `WDA_EXCLUDEFROMCAPTURE`) to exclude its own command and overlay windows from screen captures programmatically.

- **The Blinky UI remains fully visible and active to you.**
- **The screenshots captured for the AI model are completely clean**, hiding the Blinky UI from its own vision without needing to minimize or hide the app.
- **Manual user screenshots (e.g., `Ctrl + Win + S` / `Win + Shift + S`) still capture Blinky correctly** because capture exclusion is dynamically restored immediately after the AI's screenshot is captured (under 100ms).

### 🎯 Full-Width Search & Input Highlighting

Highlight boxes for search bars and text inputs are no longer constrained or shrunk to specific OCR words.

- Blinky automatically detects when OCR text lies within a native text-input control (using UIA boundaries).
- It scales and extends the highlight overlay to cover the **entire width of the input field**, providing a clean, clear visual guide.

### 📋 Robust Action Guides & Fallbacks

Action-oriented tasks (such as searching, downloading, or configuring settings) will **always generate a step-by-step Action Guide**, even when the target view, panel, or extension marketplace is currently closed.

- Instead of defaulting to a plain text summary, Blinky guides you to open the appropriate panel or sidebar view first, followed by the search and interaction steps.
- Non-visible targets are listed as text guidance with `target_text: ""` to keep guidance clear without drawing empty highlights.

### ⚡ Local Inference Performance Optimizations

Local Ollama (Gemma) execution speed has been optimized to **5-7 seconds** (down from 15+ seconds) through:

- **Duplicate Capture Elimination:** Removed redundant screenshot and OCR execution loops in the Python worker.
- **Prompt Compression:** Compressed OCR layout tokens by converting items to a compact `@ref role=X name="Y" box=(x,y,w,h)` format, reducing prompt tokens by ~1800.
- **UI Map Caching:** 2-second TTL cache avoids re-running OCR/UIA on consecutive observations.
- **Timeout Tuning:** Extended connection timeouts to 120 seconds to prevent local model load-time failures.

### 🔬 Tool Sufficiency Auditing

The browser agent router now runs a two-stage sufficiency check on all tool results:

1. **Heuristic pass** — immediately rejects empty strings, empty JSON, or outputs containing "no results", "not found", "error", "404".
2. **LLM audit** — sends tool output to the AI with a lenient prompt: if the result contains concrete data (names, prices, links), it is marked sufficient.

### 🛠️ Command Window Resizable

The command bar window can now be **dragged wider or narrower** using resize handles on the left and right edges. Width is clamped to a minimum of 560px.

### ⏹️ Run Cancellation

A **Stop button** (square icon) appears in the send button position while Blinky is thinking. Clicking it immediately cancels the current run and clears the overlay.

## 🖥️ Real-Time Screen Capture

Captures the active screen instantly when the user asks a question.

## 🔍 OCR-Based UI Understanding

Extracts visible text, buttons, menus, and labels from applications.

- Windows OCR API (primary)
- EasyOCR fallback

## 🧠 Local AI Reasoning

Runs fully offline using:

- Ollama
- `gemma4:e4b`

## 🎯 Smart Overlay Highlighting

Highlights buttons and menus directly on the user's screen using stable `@ref`-tracked elements.

## 🖱️ Safe Autopilot Clicking

When Agent Mode or globe/web mode is active, Blinky can convert matched screenshot coordinates back to physical screen coordinates and call the native Windows click command. The AI still sees the optimized screenshot; the click lands in the real desktop coordinate space.

## ⚡ Global Hotkey Workflow

Open Blinky instantly using:

```text
CTRL + SHIFT + SPACE
```

## 🔒 Privacy Friendly

- Fully local processing
- No cloud screenshots
- No tracking
- No mandatory external APIs

---

# 🎯 Why It Matters

Students waste hours learning basic software workflows.

Blinky transforms software learning into an **interactive real-time experience**.

### Benefits

✅ Learn directly inside apps  
✅ No long tutorials  
✅ No cloud dependency  
✅ Beginner-friendly guidance  
✅ Privacy-first local AI  
✅ Fast workflow assistance  
✅ Autonomous agent actions (open apps, play music, press shortcuts)

---

# 🏗️ Architecture

```text
┌─────────────────────┐
│ User Question       │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Global Hotkey       │
└──────────┬──────────┘
           ↓
┌──────────────────────────────┐
│ Preflight Intent Classifier  │
│ OPEN_APP / MEDIA_PLAYBACK /  │
│ SYSTEM_SHORTCUT /            │
│ DESKTOP_AUTOMATION /         │
│ INFORMATIONAL_CHAT           │
└──────────┬───────────────────┘
           ↓
┌─────────────────────┐        ┌─────────────────────┐
│ Agent Mode          │        │ Screen Capture       │
│ open_app_tool       │        │ dxcam                │
│ play_spotify_tool   │        └──────────┬──────────┘
│ shortcut_tool       │                   ↓
└─────────────────────┘        ┌─────────────────────┐
                                │ OCR Extraction      │
                                │ Windows OCR         │
                                │ + UIA Controls      │
                                └──────────┬──────────┘
                                           ↓
                                ┌─────────────────────┐
                                │ UI Map Cache        │
                                │ Stable @ref system  │
                                └──────────┬──────────┘
                                           ↓
                                ┌─────────────────────┐
                                │ Dynamic App Context │
                                │ + AI Step Gen       │
                                └──────────┬──────────┘
                                           ↓
                                ┌─────────────────────┐
                                │ JSON Instructions   │
                                │ with @ref targets   │
                                └──────────┬──────────┘
                                           ↓
                                ┌─────────────────────┐
                                │ Overlay Highlight   │
                                │ Guidance            │
                                └─────────────────────┘

Agent Mode autopilot adds:

┌─────────────────────┐
│ Observe (runTutor)  │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Safety Gate Check   │
│ click/type/scroll   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Act (click/type/    │
│ scroll/shortcut)    │
│ Max 5 Attempts      │
└─────────────────────┘

Globe/web mode adds:

┌─────────────────────┐
│ Browser Planner     │
│ Playwright + Edge   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Screen Tutor        │
│ Observe Next Step   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Native Safe Click   │
│ Max 5 Attempts      │
└─────────────────────┘
```

---

# 🛠️ Tech Stack

| Component                            | Technology                                         |
| ------------------------------------ | -------------------------------------------------- |
| Desktop Framework                    | Tauri 2                                            |
| Frontend                             | React 19 + TypeScript                              |
| JavaScript Runtime / Package Manager | Bun 1.3.14                                         |
| Backend Runtime                      | Python 3.11+                                       |
| AI Runtime                           | Ollama                                             |
| AI Model                             | `gemma4:e4b`                                       |
| Cloud AI (optional)                  | Groq — `meta-llama/llama-4-scout-17b-16e-instruct` |
| OCR                                  | Windows OCR API (WinRT)                            |
| OCR Fallback                         | pytesseract                                        |
| Screen Capture                       | `dxcam`                                            |
| Window Detection                     | `pywinauto`                                        |
| Browser Automation                   | Playwright + Microsoft Edge                        |
| Local Web Search                     | SearXNG + Docker Compose                           |
| Overlay System                       | Transparent Tauri Window                           |
| Voice Input                          | Sarvam AI `saaras:v3` (STT)                        |
| Voice Output                         | Sarvam AI `bulbul:v3` (TTS)                        |
| Agent Actions                        | `computer_use/` — app launch, Spotify, shortcuts   |

---

# 📂 Project Structure

```text
src-tauri/
├── Rust desktop shell
├── Overlay window
├── Global hotkeys
├── WebSocket server (port 9001)
└── Native SendInput clicking + scrolling

frontend/src/
├── CommandBar.tsx       Primary command UI (voice, agent, autopilot)
├── Overlay.tsx          Transparent highlight layer
├── lib/autopilot.ts     Bounded observe-act loop (click/type/scroll)
├── lib/guidance.ts      Step state helpers
├── lib/tauri.ts         Typed Tauri command wrappers
├── lib/tts.ts           Sarvam TTS/STT helpers
└── lib/webGuidance.ts   Browser intelligence bridge

python/
├── main.py              Screen tutor orchestrator + intent router
├── agent_router.py      Remote browser-agent sidecar
├── browser_agent.py     Safe JSON browser planner
├── browser_controller.py Playwright Edge controller
├── ai/
│   ├── prompt.py        Preflight + screen + chat prompt builders
│   ├── client.py        Provider router (Ollama / Groq)
│   ├── ollama_client.py Local Ollama client
│   └── groq_client.py   Groq vision + text client
├── app_context/
│   ├── registry.py      Dynamic app context generator (SearXNG + LLM)
│   ├── vscode.md        VS Code navigation guide
│   ├── browser.md       Chrome/Edge navigation guide
│   ├── whatsapp.root.md WhatsApp shortcuts guide
│   ├── chatgpt.md       ChatGPT desktop guide
│   ├── systemsettings.md Windows Settings guide
│   └── ...              Auto-generated guides for other apps
├── capture/screen.py    Screenshot capture + Screenshot dataclass
├── computer_use/
│   ├── agent.py         Intent regex router
│   └── tools.py         open_app, shortcut, play_spotify tools
├── ocr/extract.py       OCR provider registry (WinRT / tesseract)
├── tools/
│   ├── registry.json    Registered browser/data tool schemas
│   ├── find_crypto_price.py
│   ├── lookup_wikipedia_entity.py
│   ├── lookup_youtube_stats.py
│   └── search_product_info.py
├── utils/
│   ├── matching.py      Fuzzy target matcher
│   ├── ui_map_cache.py  Stable @ref UI element cache
│   ├── screen_elements.py @ref assignment
│   ├── sufficiency_checker.py LLM tool output auditor
│   ├── generalizer.py   Background tool generalization
│   ├── uia.py           Windows UIA extraction
│   └── window.py        Active window + overlay exclusion
└── wil/
    ├── pipeline.py      Web Intelligence Layer orchestrator
    ├── searxng_client.py SearXNG JSON client
    ├── acquirer.py       Source page fetcher
    ├── http_fetcher.py   HTTP fetch helper
    ├── browser_engine.py Playwright fallback fetcher
    ├── processor.py      Source text cleaner
    └── reasoner.py       LLM answer synthesizer

mobile/
├── App.tsx              Expo remote controller UI
└── usePCWebSocket.ts    WebSocket hook (ws://host:9001)

shared/
└── clicky-result.schema.json   Result JSON schema

scripts/
├── setup-python.ps1
└── check-ollama.ps1
```

---

# ⚡ Installation

## 1️⃣ Install Requirements

### Required Software

- Bun 1.3+
- Rust Stable
- Python 3.11+
- Ollama

---

## 2️⃣ Pull the Local AI Model

```powershell
ollama pull gemma4:e4b
```

---

## 3️⃣ Install Dependencies

```powershell
bun install
bun run setup:python
bun run check:ollama
```

---

## 4️⃣ Start Development Server

```powershell
bun run dev
```

---

# ⌨️ Usage

Press:

```text
CTRL + SHIFT + SPACE
```

Then ask:

```text
How do I install Python extension?
```

Or activate **Agent Mode** (🤖 button) and say:

```text
Open Spotify
Play lo-fi beats on Spotify
Open VS Code
Press Ctrl+S
```

Blinky will:

1. Classify the request intent (agent action vs. screen action)
2. In screen mode: Capture screen, extract UI text, detect active app, generate AI instructions with `@ref` targets, highlight matching buttons/menus
3. In agent mode: Directly execute the action (launch app, play music, press shortcut)
4. In autopilot: Observe → act (click/type/scroll) → observe again, up to 5 times

---

# 🧠 Example Workflows

## Screen Tutor: User Opens VS Code

### User asks:

```text
How do I install Python extension?
```

### Blinky detects:

```text
Active app: Visual Studio Code
Visible UI (as @refs):
  @e1 Extensions tab (sidebar)
  @e7 Search Extensions in Marketplace (Edit)
```

### AI response:

```json
{
  "summary": "In Visual Studio Code, search for the Python extension.",
  "steps": [
    {
      "step": 1,
      "instruction": "Type Python in the extensions search field.",
      "target_ref": "@e7",
      "target_text": "Search Extensions in Marketplace"
    }
  ]
}
```

### Overlay highlights:

✅ Search Extensions in Marketplace (full-width input box)

---

## Agent Mode: Play Spotify

### User says (with 🤖 active):

```text
Play lo-fi beats on Spotify
```

### Blinky:

1. Resolves the preflight intent → `MEDIA_PLAYBACK`
2. Calls `play_spotify_track_tool("lo-fi beats")`
3. Searches SearXNG for `site:open.spotify.com/track lo-fi beats`
4. Extracts `spotify:track:XXXXXXXX` URI
5. Calls `os.startfile("spotify:track:XXXXXXXX")` to open it in Spotify desktop
6. Returns: _"Playing 'lo-fi beats' in Spotify."_

---

## Agent Mode: Open an App

### User says (with 🤖 active):

```text
Open WhatsApp
```

### Blinky:

1. Preflight → `OPEN_APP`, app_name = "whatsapp"
2. Tries `whatsapp:` protocol URI via `os.startfile`
3. Falls back to known executable path, then `Get-StartApps`, then Windows Search
4. Returns: _"Opened WhatsApp."_

---

# 🎮 Supported MVP Apps

Optimized for:

- VS Code
- Chrome / Edge
- WhatsApp Desktop
- ChatGPT Desktop
- Windows Settings
- Spotify
- Paint
- File Explorer

Other applications work via **dynamic app context generation** — Blinky auto-creates a navigation guide using SearXNG + LLM on first encounter.

---

# 🔮 Future Improvements

### Planned Features

- Interactive step tracking
- Voice assistant mode (always-on listening)
- Multi-monitor support
- Cursor tracking
- AI workflow memory across sessions
- Richer autopilot verification (visual diff)
- Safe typed-input handoff for forms

---

# 🔒 Privacy

Blinky is designed to be **privacy-first**.

### Local Processing

- No cloud screenshots (unless Groq provider is enabled)
- No remote AI dependency by default (Ollama)
- No external tracking
- SearXNG local web search — no Google/Bing telemetry

Everything stays on the user's device by default.

---

# 🧪 Production Notes

This MVP intentionally avoids:

- FastAPI
- Local web servers
- Microservices

Tauri launches Python worker scripts directly and communicates using JSON over stdout.

### Why?

This makes the app:

- Simpler
- Faster
- Easier to debug
- More reliable for hackathons

---

# 📸 Demo Assets

Recommended hackathon assets:

- Main UI screenshot
- Overlay demo GIF
- Hotkey popup GIF
- VS Code walkthrough demo
- Agent Mode Spotify demo
- Before/after comparison

---

# 🏆 Hackathon Pitch

> **"Blinky is an AI desktop tutor that teaches students software directly on their screen using local AI — and can autonomously open apps, play music, and execute keyboard shortcuts on demand."**

---

# 🤝 Contributing

Contributions, ideas, and feedback are welcome.

Feel free to:

- Open issues
- Suggest features
- Improve OCR
- Optimize overlays
- Add app-specific context guides to `python/app_context/`
- Add new agent tools to `python/tools/`

---

# 📜 License

MIT License

---

# ⭐ Support

If you like this project:

- Star the repository
- Share it with friends
- Contribute improvements

---

<div align="center">

## 🚀 Built for students, hackers, and curious learners.

</div>
