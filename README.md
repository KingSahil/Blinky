<img width="4320" height="1440" alt="Blinky - AssemblyAI Voice Agent Hackathon" src="https://github.com/user-attachments/assets/c698b2cd-da84-4cb0-9276-125c6a7244aa" />

<div align="center">

# 🧠 Blinky — AI Desktop Tutor & Agent

> An offline-first, privacy-respecting AI desktop tutor that reads your screen and guides you visually or runs autopilot computer automation. Built for the **AssemblyAI - Voice Agent Hackathon**.

<br>

### _Ask. Learn. Click. Done._

<br>

<p align="center">
<img src="https://img.shields.io/badge/Hackathon-AssemblyAI%20Voice%20Agent-blueviolet?style=for-the-badge">
<img src="https://img.shields.io/badge/Tauri-2.x-orange?style=for-the-badge">
<img src="https://img.shields.io/badge/React-TypeScript-61dafb?style=for-the-badge">
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

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)
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

Learning complex software (like VS Code, Blender, or system configurations) typically involves a lot of context switching between tutorials, videos, static documentation, and the application itself. This creates "tutorial hell" and slows down software onboarding.

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
- Bun 1.3+
- Rust Stable
- Python 3.11+
- Ollama
- Tesseract OCR (on Linux, for text extraction)

### 1️⃣ Install Dependencies
**Windows (recommended):**
```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```
**Linux:**
```bash
chmod +x setup.sh && ./setup.sh
```

### 2️⃣ Start Blinky
```bash
bun run dev
```

### ⌨️ Open Blinky
- **Main Hotkey**: `CTRL + SHIFT + SPACE`

---

## 📂 Project Structure

```text
common/
├── src-tauri/             # Rust desktop shell, Global hotkeys, Overlay window
├── frontend/src/          # React 19 UI, CommandBar, Voice logic
├── python/
│   ├── main.py            # Screen tutor orchestrator + intent router
│   ├── computer_use/      # Intent regex router & tools
│   ├── ocr/               # OCR extraction
│   └── ai/                # Preflight routers, LLM clients
├── mobile/                # Expo remote controller UI
└── searxng/               # Local Web Search Configurations
```

---

## 🔒 Privacy & Production Notes
- **Local Processing**: Fully local Ollama inference and local SearXNG search ensure data privacy.
- **Tauri Integration**: Avoids local web servers. Tauri launches the Python sidecar directly and communicates using JSON over stdout/stdin for maximum performance.

---

## 🏁 Final Words
Blinky has been a thrilling journey of integrating Rust (Tauri), React, and Python into a single, cohesive desktop voice assistant. Building for the **AssemblyAI Hackathon** pushed us to make voice the central interaction paradigm, completely transforming the learning experience.
