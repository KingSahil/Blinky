# Slicky — AI Directory & Developer Guides

Welcome to the AI integration and developer documentation directory for **Slicky** (referred to as Clicky). 

This directory contains comprehensive guides designed to ramp up human developers quickly and instruct offline AI coding agents on the systems architectures, API interfaces, and coordinate mapping formulas used throughout the codebase.

---

## 📖 Available Guides

For a detailed walkthrough of the codebase, select one of the core guides below:

| Guide | Description | Target Audience |
| :--- | :--- | :--- |
| 🏗️ **[System Architecture](file:///c:/projects/Jarvis/ai/architecture.md)** | Multi-process models, high-level Mermaid flowcharts, sequence diagrams, IPC protocols, and coordinate scaling mechanics. | Architects, System Integrators, AI Agents |
| 📝 **[Per-File Specifications](file:///c:/projects/Jarvis/ai/detailed_summaries.md)** | Detailed function signatures, mathematical formulas, coordinate scaling bounds, bucketing, and search scoring algorithms. | Developers, AI Agents |
| 🗂️ **[Files Index](file:///c:/projects/Jarvis/ai/files_index.json)** | Machine-readable JSON listing of core codebase assets and their functional descriptions. | AI Agents, Automations |

---

## 🚀 Quick Repository Overview

```text
  c:\projects\Jarvis  (Slicky Project Root)
   ├── ai/                      ──► AI Documentation Hub (this folder)
   ├── frontend/src/            ──► React TypeScript GUI and Canvas viewports
   ├── src-tauri/src/           ──► Rust Native Core & Mouse Click hooks
   ├── python/                  ──► Capture, OCR Extraction & Targets Fuzzy Matching
   └── tmp/captures/            ──► Captured Telemetry Screen Buffers (temporary)
```

* **Purpose**: Privacy-first, local AI-powered tutor that captures screen states, extracts visible UI controls, coordinates elements fuzzy-matching, and places graphical click targets overlays on screen.
* **Core Tech Stack**: 
  * **Tauri (v2) + Rust**: OS-level hooks, shortcuts, window controllers.
  * **React + TypeScript**: Form inputs, dynamic height rendering, canvas overlay graphics.
  * **Python 3.11**: Screen captures (`dxcam`), WinRT OCR / EasyOCR, UI elements extraction (`pywinauto`).
  * **LLM Intelligence**: Local Ollama (Ollama CLI) or cloud-hosted Groq Vision API.

---

## 🛠️ Rapid Dev Commands

Set up Slicky locally using the following commands:

```powershell
# 1. Install standard dependencies
npm install

# 2. Configure Python virtual environments and pull EasyOCR
npm run setup:python

# 3. Pull default local AI models
ollama pull gemma4:e4b

# 4. Start the application in development mode
npm run dev
```

*For details on configuring `.env` variables and custom shortcut hotkeys, please refer to the [System Architecture Guide](file:///c:/projects/Jarvis/ai/architecture.md#6-environment--settings-variables).*
