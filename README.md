<img width="4320" height="1440" alt="hh26 main poster 2 with sponsors 3x1 (4320 x 1440 px) (2)" src="https://github.com/user-attachments/assets/c698b2cd-da84-4cb0-9276-125c6a7244aa" />

<div align="center">

# 🧠 Blinky — AI Desktop Tutor & Agent

> An offline-first, privacy-respecting AI desktop tutor that reads your screen and guides you visually or runs autopilot computer automation.

<br>

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

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)
![License](https://img.shields.io/badge/license-MIT-purple)

</div>

---

An AI-powered Windows desktop tutor that teaches users software directly on their screen using local AI. In web mode it can also open/search in your default Edge browser and run a bounded safe-click autopilot loop after reading the screen. In **Agent Mode** it can launch apps, play Spotify tracks, and press keyboard shortcuts entirely autonomously.

---

## 📌 Problem & Domain

Learning complex software (like VS Code, Blender, or system configurations) typically involves a lot of context switching between tutorials, videos, static documentation, and the application itself. This creates "tutorial hell" and slows down software onboarding.

Blinky brings the learning experience directly into the active application. By capturing the screen, running local OCR + Windows UIA, and leveraging local or cloud LLMs, Blinky guides users step-by-step with real-time visual highlights directly on their screen.

**Themes Selected (at least one):**
- [x] Human Experience & Productivity  
- [x] Learning & Knowledge Systems  
- [x] Developer Tools & Software Infrastructure  

---

## 🎯 Objective

Blinky serves students, developers, and general users learning to navigate desktop software.

- **Target Users**: Software learners, junior developers, and remote users looking for hands-on, contextual guide steps.
- **Pain Point**: Context-switching, static text manuals, video pacing issues, and lack of visual mapping.
- **Value Provided**: Real-time visual overlay highlighting on the actual screen, offline-first voice read-aloud via Sarvam AI, and hands-free desktop autopilot execution.

---

## 🧠 Team & Approach

### Team Name:  
`Tech Nerds`

### Team Members:  
- **Sparsh Khanna** (GitHub: [KhannaSparsh0001](https://github.com/KhannaSparsh0001) / Role: Voice & UI-UX Architect)
- **Sahil** (GitHub: [KingSahil](https://github.com/KingSahil) / Role: Backend & Tauri Developer)
- **FeV-06** (GitHub: [FeV-06](https://github.com/FeV-06) / Role: Mobile and Linux Developer)
- **meharwanfr** (GitHub: [meharwanfr](https://github.com/meharwanfr) / Role: Linux Developer)

### Your Approach:
- **Why we chose this problem**: Traditional training methods fail because they are separated from the workspace. We wanted a tool that feels like a teacher looking over your shoulder.
- **Key challenges addressed**:
  - **Flicker-Free Screenshots**: Using Windows display affinity flags to exclude Blinky's overlay and command windows from screenshots without closing them.
  - **OCR Coordinates Mapping**: Matching local WinRT OCR box dimensions to physical monitor DPI scales for pixel-perfect overlays and clicking.
  - **Dynamic App Context**: Auto-generating keyboard shortcuts and menus documentation on first app run.
  - **Voice Synchronization**: Creating word-by-word active highlighting synchronized with the Sarvam TTS audio timeline.
- **Pivots & Iterations**: Shifted from pure on-screen highlighting to full autonomous Agent Mode, allowing users to choose between manual guidance and automatic autopilot execution. We also revamped the command bar to place actions at the bottom right like modern assistants (ChatGPT/Copilot).

---

## 🛠️ Tech Stack

### Core Technologies Used:

| Component                            | Technology                                         |
| ------------------------------------ | -------------------------------------------------- |
| **Desktop Framework**                | Tauri 2 (Rust desktop shell)                       |
| **Frontend**                         | React 19 + TypeScript                              |
| **Package Manager / Runtime**        | Bun 1.3.14                                         |
| **Backend Runtime**                  | Python 3.11+                                       |
| **AI Runtime**                       | Ollama (Local)                                     |
| **AI Model**                         | `gemma4:e4b`                                       |
| **Cloud AI (optional)**              | Groq — `meta-llama/llama-4-scout-17b-16e-instruct` |
| **OCR**                              | Windows OCR API (WinRT), Falls back to pytesseract  |
| **Screen Capture**                   | `dxcam` (DirectX-based high-frame capture)         |
| **Window Detection**                 | `pywinauto`                                        |
| **Browser Automation**               | Playwright + Microsoft Edge                        |
| **Local Web Search**                 | SearXNG + Docker Compose                           |
| **Overlay System**                   | Transparent Tauri Window                           |
| **Voice Input**                      | Sarvam AI `saaras:v3` (STT)                        |
| **Voice Output**                     | Sarvam AI `bulbul:v3` (TTS)                        |
| **Agent Actions**                    | `computer_use/` — app launch, Spotify, shortcuts   |

### Additional Technologies Used (Optional):
- [x] AI / ML  
- [ ] Web3 / Blockchain  
- [ ] Cyber Security  
- [x] Cloud  

---

## 🏆 Sponsored Track (Optional)

Select if your project participates in any track:

- [x] **Expo Track** – Built using Expo  
- [ ] **Neo4j Track** – Uses AuraDB as primary database  
- [ ] **Base44 Track** – Prototype/Final Product built using Base44
- [x] **Sarvam Track** - TTS & STT

Provide a short note on how you used the partner technology:

> Under `common/mobile/`, we built an **Expo-powered mobile companion app**. It connects directly to the desktop Tauri WebSocket server (port 9001), allowing users to send voice commands and monitor autopilot workflows directly from their phone.

---

## ✨ Key Features

### 🤖 Full Agent Mode (Computer Use)
Blinky now ships a dedicated **Agent Mode** (activate with the 🤖 button) that can perform direct computer-use actions without requiring you to click anything:
- **Open any app** — uses app protocol URIs, known executable paths, Windows Start Apps (`Get-StartApps`), and finally Windows Search as a fallback chain.
- **Play Spotify tracks** — searches SearXNG (and falls back to DuckDuckGo HTML) to resolve a `spotify:track:ID` URI and opens it directly in the Spotify desktop app.
- **Press keyboard shortcuts** — parses natural-language shortcut descriptions (`Ctrl+S`, `Alt+H`, `Win+D`) and executes them via `pywinauto`.
- **Open help menus** — detects the active app process (e.g., VS Code) and sends the correct shortcut automatically.
- **Type text into fields** — autopilot can extract quoted text from instructions and type it into focused controls.
- **Scroll screens** — autopilot detects scroll instructions and calls `scroll_at_point` through Rust `SendInput`.
- The bounded autopilot loop (max 5 attempts) now handles `type`, `search`, `submit`, and `scroll` actions in addition to safe clicks.

### 🎨 Modern Chatbar UI (ChatGPT/Copilot Layout)
- Features actions grouped at the bottom, with Mic, Read-Aloud, and Send aligned on the bottom right.
- Manually trigger TTS readbacks or cancel active synthesis with a single click.

### 🗣️ Sarvam AI Voice Integration & Dynamic Word Highlighting
- Indian-context speech-to-text dictation and text-to-speech readbacks.
- **Real-time Word Highlighting**: Fades out unspoken text, highlighting the active word dynamically as the voice readback plays in sync with the audio duration timeline.

### 🧠 Intent Classification (Preflight Router)
Before any screenshot is taken, Blinky runs a fast **preflight classifier** that routes requests into one of five intents:
- `DESKTOP_AUTOMATION` — needs screen capture + OCR + AI overlay
- `OPEN_APP` — directly launches the named app
- `MEDIA_PLAYBACK` — plays a named song on Spotify
- `SYSTEM_SHORTCUT` — presses a keyboard shortcut
- `INFORMATIONAL_CHAT` — answers without any screen capture
- Safety overrides prevent `OPEN_APP` from being triggered by in-app feature names or multi-word queries.

### 🗂️ Dynamic App Context Generation
For any app Blinky hasn't seen before, `app_context/registry.py` now **auto-generates a navigation guide** on first encounter:
1. Queries SearXNG for `"<AppName> Windows keyboard shortcuts menus navigation"`
2. Asks the LLM to produce a structured markdown guide from those search results
3. Saves the guide to `python/app_context/<process_name>.md` for future runs
4. Falls back to a minimal boilerplate if both SearXNG and LLM fail.

### 🏷️ Screen Element `@ref` System & UI Map Cache
- Every visible UI element is tagged with a stable `@ref` (e.g., `@e14`) for precise target identification.
- Caches the merged OCR+UIA map with a 2-second TTL using spatial IOU + name-similarity scoring to reuse refs across observations for fast autopilot runs.

### 🛡️ Dynamic Capture Exclusion (Flicker-Free Mode)
- Excludes Blinky's overlay window from screenshots programmatically using `SetWindowDisplayAffinity` (`WDA_EXCLUDEFROMCAPTURE`).
- Blinky remains fully visible to you, but the screenshot sent to the AI model is completely clean.

---

## 📽 ... Demo & Deliverables

- **Demo Video Link (Mandatory):** _[Paste YouTube/Loom Link]_  
- **Deployment Link (Recommended):** _[Paste Tauri Build Releases Link]_  
- **Pitch Deck / PPT (Optional):** _[Paste Canva/Google Slides Link]_  

---

## ✅ Tasks & Bonus Checklist

- [ ] All team members completed the mandatory social task  
- [ ] Bonus Task 1 – Badge sharing  
- [ ] Bonus Task 2 – Blog/article  

---

## 🧪 How to Run the Project

### Prerequisites
Install the following software:
- Bun 1.3+
- Rust Stable
- Python 3.11+
- Ollama
- Docker & Docker Compose (optional, for local search)
- Tesseract OCR (on Linux, for text extraction)
- GStreamer Good Plugins (on Linux, for audio support)

---

### 1️⃣ Pull the AI Model (Optional - if using local inference)
```bash
ollama pull gemma4:e4b
```

---

### 2️⃣ Install Dependencies
#### Windows
```powershell
bun install
bun run setup:python
bun run check:ollama
```

#### Linux
```bash
bun install
bun run linux:setup:python
```
> [!NOTE]
> On Arch Linux, you should also install the GStreamer good plugins for audio support:
> ```bash
> sudo pacman -S gst-plugins-good
> ```

---

### 3️⃣ Setup OCR (Tesseract) on Linux
If you do not have root access or want to bypass installing system language data:
1. Create a local folder and download the English model:
   ```bash
   mkdir -p common/tessdata
   curl -L -o common/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata
   ```
2. Add the variable to your `.env` file:
   ```env
   TESSDATA_PREFIX=/absolute/path/to/Blinky/common/tessdata/
   ```

---

### 4️⃣ Start Blinky
```bash
bun run dev
```

### Optional: Start Local Web Search
For web intelligence backed by SearXNG, run from the root directory:
```bash
docker compose -f common/docker-compose.yml up -d
```
SearXNG will be exposed at `http://localhost:8888`.

### ⌨️ Open Blinky
- **Main Hotkey**: `CTRL + SHIFT + SPACE`
- **Fallback Hotkey**: `CTRL + SHIFT + ENTER`

---

## 🧠 Example Workflows

### 1. Screen Tutor: User Opens VS Code
**User asks**:
```text
How do I install Python extension?
```
**Blinky detects**:
```text
Active app: Visual Studio Code
Visible UI (as @refs):
  @e1 Extensions tab (sidebar)
  @e7 Search Extensions in Marketplace (Edit)
```
**AI response**:
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
**Overlay highlights**:
✅ Search Extensions in Marketplace (full-width input box)

---

### 2. Agent Mode: Play Spotify
**User says (with 🤖 active)**:
```text
Play lo-fi beats on Spotify
```
**Blinky workflow**:
1. Resolves the preflight intent → `MEDIA_PLAYBACK`
2. Calls `play_spotify_track_tool("lo-fi beats")`
3. Searches SearXNG for `site:open.spotify.com/track lo-fi beats`
4. Extracts `spotify:track:XXXXXXXX` URI
5. Calls `os.startfile("spotify:track:XXXXXXXX")` to open it in Spotify desktop
6. Returns: _"Playing 'lo-fi beats' in Spotify."_

---

### 3. Agent Mode: Open an App
**User says (with 🤖 active)**:
```text
Open WhatsApp
```
**Blinky workflow**:
1. Preflight → `OPEN_APP`, app_name = "whatsapp"
2. Tries `whatsapp:` protocol URI via `os.startfile`
3. Falls back to known executable path, then `Get-StartApps`, then Windows Search
4. Returns: _"Opened WhatsApp."_

---

## 🎮 Supported MVP Apps
- VS Code
- Chrome / Edge
- WhatsApp Desktop
- ChatGPT Desktop
- Windows Settings
- Spotify
- Paint
- File Explorer
- _Dynamic app context generation_ auto-creates guides for other encountered apps.

---

## 📂 Project Structure

```text
common/
├── src-tauri/
│   ├── Rust desktop shell
│   ├── Overlay window
│   ├── Global hotkeys
│   ├── WebSocket server (port 9001)
│   └── Native SendInput clicking + scrolling
│
├── frontend/src/
│   ├── CommandBar.tsx       Primary command UI (voice, agent, autopilot)
│   ├── Overlay.tsx          Transparent highlight layer
│   ├── lib/autopilot.ts     Bounded observe-act loop (click/type/scroll)
│   ├── lib/guidance.ts      Step state helpers
│   ├── lib/tauri.ts         Typed Tauri command wrappers
│   ├── lib/tts.ts           Sarvam TTS/STT helpers
│   └── lib/webGuidance.ts   Browser intelligence bridge
│
├── python/
│   ├── main.py              Screen tutor orchestrator + intent router
│   ├── agent_router.py      Remote browser-agent sidecar
│   ├── browser_agent.py     Safe JSON browser planner
│   ├── browser_controller.py Playwright Edge controller
│   ├── ai/
│   │   ├── prompt.py        Preflight + screen + chat prompt builders
│   │   ├── client.py        Provider router (Ollama / Groq)
│   │   ├── ollama_client.py Local Ollama client
│   │   └── groq_client.py   Groq vision + text client
│   ├── app_context/
│   │   ├── registry.py      Dynamic app context generator (SearXNG + LLM)
│   │   ├── vscode.md        VS Code navigation guide
│   │   ├── browser.md       Chrome/Edge navigation guide
│   │   ├── whatsapp.root.md WhatsApp shortcuts guide
│   │   ├── chatgpt.md       ChatGPT desktop guide
│   │   ├── systemsettings.md Windows Settings guide
│   │   └── ...              Auto-generated guides for other apps
│   ├── capture/screen.py    Screenshot capture + Screenshot dataclass
│   ├── computer_use/
│   │   ├── agent.py         Intent regex router
│   │   └── tools.py         open_app, shortcut, play_spotify tools
│   ├── ocr/extract.py       OCR provider registry (WinRT / tesseract)
│   ├── tools/
│   │   ├── registry.json    Registered browser/data tool schemas
│   │   ├── find_crypto_price.py
│   │   ├── lookup_wikipedia_entity.py
│   │   ├── lookup_youtube_stats.py
│   │   └── search_product_info.py
│   ├── utils/
│   │   ├── matching.py      Fuzzy target matcher
│   │   ├── ui_map_cache.py  Stable @ref UI element cache
│   │   ├── screen_elements.py @ref assignment
│   │   ├── sufficiency_checker.py LLM tool output auditor
│   │   ├── generalizer.py   Background tool generalization
│   │   ├── uia.py           Windows UIA extraction
│   │   └── window.py        Active window + overlay exclusion
│   └── wil/
│       ├── pipeline.py      Web Intelligence Layer orchestrator
│       ├── searxng_client.py SearXNG JSON client
│       ├── acquirer.py       Source page fetcher
│       ├── http_fetcher.py   HTTP fetch helper
│       ├── browser_engine.py Playwright fallback fetcher
│       ├── processor.py      Source text cleaner
│       └── reasoner.py       LLM answer synthesizer
│
├── mobile/
│   ├── App.tsx              Expo remote controller UI
│   └── usePCWebSocket.ts    WebSocket hook (ws://host:9001)
│
├── shared/
│   └── clicky-result.schema.json   Result JSON schema
│
└── searxng/                 SearXNG configuration files

windows/                     Windows configuration & setup scripts
└── scripts/
    ├── setup-python.ps1
    └── check-ollama.ps1

linux/                       Linux configuration & setup scripts
└── scripts/
    ├── setup-python.sh
    ├── check-ollama.sh
    └── groq-check.sh
```

---

## 🧬 Future Scope
- 📈 **More Integrations**: Control tools for major developer software suites (Docker, Kubernetes dashboards, cloud consoles).
- 🛡️ **Enhanced Sandbox Protection**: Sandboxed execution mode for typing/clicking safely.
- 🌐 **Deep Localization**: Supporting regional languages using Sarvam API for multi-lingual tutors.
- 🕶️ **Multi-Monitor Layouts**: Autopilot click mapping extended to multiple monitor coordinate frames.

---

## 🔒 Privacy & Production Notes
- **Local Processing**: No cloud screenshots (unless Groq is active), fully local Ollama inference, and local SearXNG search.
- **Tauri Integration**: Intentionally avoids FastAPI or local web servers. Tauri launches the Python sidecar directly and communicates using JSON over stdout/stdin for maximum performance and reliability in hackathons.

---

## 📎 Resources / Credits
- **APIs**: Sarvam AI API for speech features, Groq Vision API.
- **Libraries**: Tauri, React, ReactMarkdown, dxcam, WinRT OCR APIs, pywinauto, Playwright.
- **Acknowledgements**: Inspired by modern assistive agents and built for hackathon learners worldwide.

---

## 🏁 Final Words
Blinky has been a thrilling journey of integrating Rust (Tauri), React, and Python sidecars into a single, cohesive desktop assistant. Solving overlay flickering and mapping OCR coordinates to physical DPI frames was a major engineering obstacle, but seeing the visual guide draw directly on top of target apps made every hour of development worth it!
