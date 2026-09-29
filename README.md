<div align="center">

# 🧠 Blinky — AI Desktop Tutor, Autonomous Agent & Workstation Companion

> An offline-first, privacy-respecting AI desktop tutor and remote workstation companion that reads your screen, guides you visually, runs background headless computer automation via Hermes `cua-driver`, bridges to mobile over encrypted WebSocket, and synchronizes with physical IoT hardware.

<br>

### _Ask. Learn. Automate. Control from Anywhere._

<br>

<p align="center">
<img src="https://img.shields.io/badge/Hackathon-AssemblyAI%20Voice%20Agent-blueviolet?style=for-the-badge">
<img src="https://img.shields.io/badge/Tauri-2.x-orange?style=for-the-badge">
<img src="https://img.shields.io/badge/React-19-61dafb?style=for-the-badge">
<img src="https://img.shields.io/badge/Bun-1.3.14-f9f1e1?style=for-the-badge">
<img src="https://img.shields.io/badge/Python-3.11-yellow?style=for-the-badge">
</p>

<p align="center">
<img src="https://img.shields.io/badge/Playwright-Edge-green?style=for-the-badge">
<img src="https://img.shields.io/badge/Ollama-gemma4:e4b-green?style=for-the-badge">
<img src="https://img.shields.io/badge/Groq-Llama4Scout-purple?style=for-the-badge">
<img src="https://img.shields.io/badge/OCR-Windows%20OCR-blue?style=for-the-badge">
</p>

<br>

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20Android-blue)
![License](https://img.shields.io/badge/license-MIT-purple)

</div>

---

## 🎙️ AssemblyAI - Voice Agent Hackathon Submission

This project is submitted to the **AssemblyAI - Voice Agent Hackathon**, a month-long online challenge (Sep 1–30, 2026) run by lablab.ai together with AssemblyAI. 

**Hackathon Highlights:**
- 🌎 **Online Hackathon:** Fully online challenge connecting innovators globally.
- 💻 **Challenge:** Building the fastest path to a working voice agent using AssemblyAI infrastructure.
- 🏆 **Prize Pool:** $10,000 ($5k cash + $5k in AAI credits).

Blinky leverages modern voice AI patterns to create an immersive, screen-aware voice agent that acts as a tutor directly on your desktop.

---

## 📌 Problem & Domain

Learning complex software (like VS Code, Blender, CAD, or system configurations) typically involves constant context switching between tutorials, video timestamps, static manuals, and the application workspace. This induces "tutorial hell" and stalls productivity.

Blinky brings the learning experience directly into the active application. By capturing the screen, running local OCR + Windows UIA, and leveraging local or cloud LLMs alongside powerful voice features, Blinky guides users step-by-step with real-time visual highlights directly on their screen.

---

## 🎯 Objective

Blinky serves students, developers, and general users learning to navigate desktop software.

- **Target Users**: Software learners, junior developers, and remote users looking for hands-on, contextual guide steps.
- **Pain Point**: Context-switching, static text manuals, video pacing issues, and lack of visual mapping.
- **Value Provided**: Real-time visual overlay highlighting on the actual screen, hands-free desktop autopilot execution, and a fully interactive voice interface.

---

## 🧠 Team

### Team Name:  
`Tech Nerds`

### Team Members:  
- **Sparsh Khanna** (GitHub: [KhannaSparsh0001](https://github.com/KhannaSparsh0001) / Role: Voice & UI-UX Architect)
- **Sahil** (GitHub: [KingSahil](https://github.com/KingSahil) / Role: Backend & Tauri Developer)
- **FeV-06** (GitHub: [FeV-06](https://github.com/FeV-06) / Role: Mobile and Linux Developer)
- **meharwanfr** (GitHub: [meharwanfr](https://github.com/meharwanfr) / Role: Linux Developer)

---

## 🛠️ Tech Stack

### Core Technologies Used:

| Component                            | Technology                                         |
| ------------------------------------ | -------------------------------------------------- |
| **Desktop Framework**                | Tauri 2 (Rust desktop shell)                       |
| **Frontend**                         | React 19 + TypeScript                              |
| **Backend Runtime**                  | Python 3.11+                                       |
| **AI Runtime**                       | Ollama (Local)                                     |
| **AI Model**                         | `gemma4:e4b`                                       |
| **Cloud AI (optional)**              | Groq — `llama-3.3-70b-versatile`                   |
| **OCR**                              | Windows OCR API (WinRT), Falls back to pytesseract |
| **Screen Capture**                   | `dxcam` (DirectX-based high-frame capture)         |
| **Window Detection**                 | `pywinauto`                                        |
| **Browser Automation**               | Playwright + Microsoft Edge                        |
| **Overlay System**                   | Transparent Tauri Window                           |
| **Hosting & Prototyping**            | Base44 App Hosting (blinky.base44.app)             |
| **Voice Agent / STT**                | AssemblyAI Voice Agent API & Real-time STT API     |
| **TTS (Fallback)**                   | AssemblyAI Voice Output                            |

---

## ✨ Key Features

### 🎙️ AssemblyAI Hackathon Coverage
This project deeply integrates AssemblyAI to fulfill both major paths of the hackathon challenge:

1. **Voice Agent API (End-to-End Voice Agent)**
   - **Full Voice Stack**: Uses AssemblyAI for STT (Universal-3.5 Pro), LLM routing, turn-taking, VAD, and voice output.
   - **JSON-Schema Tool Calling**: Enables the AssemblyAI Voice Agent to actuate and command the PC desktop. When a user asks to click an icon or search the screen, AssemblyAI sends a `tool.call` (`control_desktop`), Blinky executes native Windows UI automation, and returns a `tool.result` for AssemblyAI to speak back the status.

2. **Realtime Speech-to-Text API**
   - **Sub-second Transcription**: Live streaming of 16 kHz PCM16 audio directly to `wss://streaming.assemblyai.com/v3/ws`.
   - **Bring Your Own Orchestration**: Feeds live Universal-3 Pro transcripts into Blinky's local desktop multi-agent tutor pipeline.

### 🗣️ Voice-Driven Agent Mode (Computer Use)
Activate the 🤖 agent mode using voice commands to perform direct computer-use actions without requiring you to click anything:
- **Open any app** — uses app protocol URIs, known executable paths, Windows Start Apps, and Windows Search.
- **Play Spotify tracks** — searches and resolves tracks to open directly in the Spotify desktop app.
- **Press keyboard shortcuts** — parses natural-language shortcut descriptions (`Ctrl+S`, `Alt+H`) and executes them via `pywinauto`.

### 🎧 Audio-Synchronized Visual Highlighting
- Dynamic **Real-time Word Highlighting**: Fades out unspoken text, highlighting the active word dynamically as the AssemblyAI synthesized readback plays in sync with the audio duration timeline.
- Fully integrated speech-to-text dictation and text-to-speech readbacks via AssemblyAI for seamless hands-free operation.

### 🧠 Intent Classification (Preflight Router)
Before any screenshot is taken, Blinky runs a fast **preflight classifier** that routes requests:
- `DESKTOP_AUTOMATION` — needs screen capture + OCR + AI overlay
- `OPEN_APP` — directly launches the named app
- `MEDIA_PLAYBACK` — plays a named song on Spotify
- `SYSTEM_SHORTCUT` — presses a keyboard shortcut
- `INFORMATIONAL_CHAT` — answers without any screen capture

### 🛡️ Dynamic Capture Exclusion (Flicker-Free Mode)
- Excludes Blinky's overlay window from screenshots programmatically using `SetWindowDisplayAffinity`.
- Blinky remains fully visible to you, but the screenshot sent to the AI model is completely clean.

---

## 📽️ Demo & Deliverables

- **Demo Video Link:** [Youtube Video](https://youtu.be/CHFF9J_Jqgw)
- **Deployment Link:** [blinky.base44.app](https://blinky.base44.app) (Landing Page & Releases) 
- **Pitch Deck / PPT:** [Blinky Deck](https://docs.google.com/presentation/d/10isbvsbzb3Xm2RzeHyaA_FQqcjUTUzRipflrhuyABRY/edit)
- **Blog:** [Building Blinky: Fighting CAPTCHAs, Invisible Windows, and the Agony of Visualizing AI](https://medium.com/@khannasparsh0001/building-blinky-fighting-captchas-invisible-windows-and-the-agony-of-visualizing-ai-b1247b9fc324?sharedUserId=khannasparsh0001) 

---

## 🧪 How to Run the Project

### Prerequisites
- **Bun** 1.3+
- **Rust** Stable
- **Python** 3.11+
- **Node.js** & **Expo CLI** (for mobile companion)
- **Ollama** (optional, for local offline inference)
- **Docker** (optional, for local SearXNG search)

---

### 1️⃣ Setup Desktop Core (One-Click)

#### Windows (Recommended):
```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
# or: bun run setup
```
*Checks Bun/Rust/Python, installs npm packages, builds Python `.venv`, installs Playwright browsers, and initializes `.env`.*

#### Linux:
```bash
chmod +x setup.sh && ./setup.sh
```

### 2️⃣ Start Blinky
```bash
bun run dev
```

- **Main Hotkey**: `CTRL + SHIFT + SPACE`
- **Fallback Hotkey**: `CTRL + SHIFT + ENTER`

*(Optional) Start local SearXNG search engine:*
```bash
docker compose -f common/docker-compose.yml up -d
```

---

### 3️⃣ Start Mobile Companion (`common/mobile`)

```bash
cd common/mobile
bun install
bun run start
```
- Scan the QR code using Expo Go or run on a connected Android phone:
```bash
# Connect via USB port forwarding
connect_usb.bat

# Install standalone APK directly
install_apk.bat
```

---

## 📂 Project Structure

```text
Blinky/
├── common/
│   ├── src-tauri/                   Tauri 2 Rust shell, WS gateway (:9001), Windows Credential DLL
│   │   ├── src/lib.rs               Window affinity, hotkeys, and secure WebSocket server
│   │   └── tauri.conf.json          Tauri window and strict CSP security configuration
│   │
│   ├── frontend/src/                React 19 desktop webview UI
│   │   ├── CommandBar.tsx           Primary floating command hub & voice synthesizer
│   │   ├── Overlay.tsx              Transparent screen highlight & companion cursor layer
│   │   └── lib/autopilot.ts         Observe-act bounded autopilot execution loop
│   │
│   ├── mobile/                      Expo SDK 57 / React Native 0.86 companion app
│   │   ├── App.tsx                  Dashboard, tab router, and WebSocket subscriber
│   │   ├── components/              Modular UI screens
│   │   │   ├── SystemScreen.tsx     Sentinel hardware telemetry, power controls, and WoL
│   │   │   ├── FilesScreen.tsx      Remote PC file explorer & camera roll sync
│   │   │   ├── PromoCodeModal.tsx   Offline voucher bypass sheet
│   │   │   ├── SlashCommandMenu.tsx Antigravity IDE slash command bar
│   │   │   └── BottomNavigation.tsx Tab navigation with Pro lock indicators
│   │   ├── lib/purchases.ts         RevenueCat SDK + Offline Promo Code Engine
│   │   ├── usePCWebSocket.ts        Duplex WSS transport with ?token= authentication
│   │   └── eas.json                 EAS standalone Android APK build profiles
│   │
│   └── python/                      Python 3.11 AI & automation daemon
│       ├── main.py                  Screen tutor orchestrator and preflight intent classifier
│       ├── computer_use/            Actuation engine
│       │   ├── backends/cua_driver.py cua-driver (Hermes) background desktop actuator
│       │   ├── backends/base.py     Platform-neutral computer-use abstractions
│       │   └── tools.py             Desktop automation tools (app launch, shortcuts, Spotify)
│       ├── ai/                      Model provider routing (Groq Llama 3.3 / Ollama gemma4)
│       ├── ocr/                     Microsoft OmniParser and WinRT OCR extraction
│       └── whatsapp_backend/        Headless Chromium WhatsApp Web automation
│
├── esp32_firmware/                  ESP32 universal micro-daemon for ambient lighting sync
├── docs/                            Comprehensive architecture, Hermes plan, and security guides
│   ├── HERMES-INTEGRATION-PLAN.md   Detailed cua-driver actuator documentation
│   ├── LINUX-PORT-ROADMAP.md        Wayland/X11 Linux porting progress
│   ├── SECURITY-REMEDIATION.md      WebSocket auth hardening & CSP policy
│   ├── history.md                   Full post-100 commits architectural evolution
│   └── REVENUECAT-AND-ANDROID-DISTRIBUTION-GUIDE.md  RevenueCat audit & APK packaging guide
│
├── setup.ps1                        Automated Windows installation script
└── setup.sh                         Automated Linux installation script
```

---

## 🔒 Security & Privacy

- **Authenticated WebSocket Transport**: Every command sent from the mobile companion requires secret token verification (`?token=`), hardened against unauthorized LAN access.
- **Strict Content Security Policy (CSP)**: Tauri webview CSP strictly prevents credential exfiltration.
- **Automated Firewall Rules**: Windows NSIS installer automatically configures restrictive inbound firewall rules for port `9001`.
- **Local Processing**: Offline-first screen OCR via Windows WinRT and local LLM inference via Ollama ensure zero screenshots leave your machine unless cloud Groq inference is explicitly enabled.

---

## 📎 Resources & Credits

- **Actuation**: Built on [cua-driver](https://github.com/nousresearch) by Nous Research.
- **Voice**: [Sarvam AI](https://sarvam.ai) for multilingual speech-to-text (`saaras:v3`) and text-to-speech (`bulbul:v3`).
- **Vision**: Microsoft OmniParser for bounding-box grounding and DirectX `dxcam` for high-speed capture.
- **Mobile**: Built with [Expo](https://expo.dev) and [React Native](https://reactnative.dev).
- **Desktop**: Powered by [Tauri 2](https://v2.tauri.app) and [React 19](https://react.dev).
