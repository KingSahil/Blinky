# Blinky — AI Directory & Developer Guides

Welcome to the AI integration and developer documentation directory for **Blinky**. 

This directory contains comprehensive guides designed to ramp up human developers quickly and instruct offline AI coding agents on the system architecture, API interfaces, coordinate mapping formulas, matching heuristics, and voice integrations used throughout the codebase.

---

## 📖 Available Guides (Logical Reading Order)

We recommend reading these guides in the following order:

| File | Guide | Description | Target Audience |
| :--- | :--- | :--- | :--- |
| `00` | 🏠 **[Master Entryway](file:///c:/projects/Jarvis/ai/00_repo_summary.md)** | Overview of directory structure, rapid setup commands, and guide index. | All Developers, AI Agents |
| `01` | 🏗️ **[System Architecture](file:///c:/projects/Jarvis/ai/01_architecture.md)** | Multi-process models, high-level system flows, sequence diagrams, and IPC protocols. | Architects, System Integrators, AI Agents |
| `02` | 📐 **[Coordinate Scaling & Normalization](file:///c:/projects/Jarvis/ai/02_coordinate_scaling.md)** | Calculations mapping physical screens to downsampled screenshots and web view CSS layout coordinates. | Developers, QA, AI Agents |
| `03` | 🎯 **[Matching Heuristics & Deduplication](file:///c:/projects/Jarvis/ai/03_matching_heuristics.md)** | Fuzzy target matching algorithms, context scoring bonuses, coordinate grids, and steps post-processing. | Developers, AI Agents |
| `04` | 🧠 **[AI Inference & Prompts](file:///c:/projects/Jarvis/ai/04_ai_inference.md)** | Chat engine prompts, preflight classification, continuation logic, single-step enforcement, and Ollama/Groq configs. | Prompt Engineers, AI Agents |
| `05` | 🗣️ **[Sarvam AI Voice Integration](file:///c:/projects/Jarvis/ai/05_sarvam.md)** | Bulbul (TTS) and Saaras (STT) payload formats, authentication headers, error messages, and frontend hooks. | Audio Engineers, AI Agents |
| `06` | 📝 **[Per-File API Reference](file:///c:/projects/Jarvis/ai/06_detailed_summaries.md)** | Detailed function signatures, classes, arguments, and module-level responsibilities. | Developers, AI Agents |
| `Index` | 🗂️ **[Files Index](file:///c:/projects/Jarvis/ai/files_index.json)** | Machine-readable JSON listing of core codebase assets and their functional descriptions. | AI Agents, Automations |

---

## 🚀 Quick Repository Overview

```text
  /home/fev/GitRepos/clonedGitRepos/Jarvis  (Blinky Project Root - Linux)
  c:\projects\Jarvis                       (Blinky Project Root - Windows)
   ├── ai/                      ──► AI Documentation Hub (this folder)
   ├── frontend/src/            ──► React TypeScript GUI and Canvas viewports
   ├── src-tauri/src/           ──► Rust Native Core & Mouse Click hooks
   ├── python/                  ──► Capture, OCR Extraction & Targets Fuzzy Matching
   └── tmp/captures/            ──► Captured Telemetry Screen Buffers (temporary)
```

* **Purpose**: Privacy-first, local AI-powered tutor that captures screen states, extracts visible UI controls, runs coordinate-aware fuzzy matching, and places graphical click-target overlays on screen — one step at a time.
* **Core Tech Stack (Cross-Platform)**: 
  * **Tauri (v2) + Rust**: OS-level hooks, shortcuts, window controllers, capture exclusion (`WDA_EXCLUDEFROMCAPTURE` on Windows, window coordinate off-sets on Linux to clear system panel).
  * **React + TypeScript**: Form inputs, dynamic height rendering, canvas overlay graphics (with platform-specific coordinate scaling).
  * **Python 3.11**: Screen captures (`dxcam` on Windows; D-Bus Wayland Desktop Portal & `gnome-screenshot` on Linux), OCR (WinRT OCR / EasyOCR on Windows; local `tesseract` OCR on Linux), UI elements extraction (`pywinauto` on Windows; native coordinate OCR parsing on Linux).
  * **LLM Intelligence**: Local Ollama (`gemma4:e4b`) or cloud-hosted Groq Vision API (`llama-4-scout`).

---

## 🛠️ Rapid Dev Commands

Set up Blinky locally using the following commands:

### Windows Setup
```powershell
# 1. Install standard dependencies
bun install

# 2. Configure Python virtual environments and pull EasyOCR
bun run setup:python

# 3. Pull default local AI models
ollama pull gemma4:e4b

# 4. Start the application in development mode
bun run dev
```

### Linux (Fedora/Ubuntu) Setup
```bash
# 1. Install system prerequisites (Tesseract OCR & development libs)
sudo dnf install tesseract tesseract-devel  # Fedora
# or: sudo apt-get install tesseract-ocr libtesseract-dev  # Ubuntu

# 2. Install standard node dependencies
bun install

# 3. Start the application in development mode
bun run dev
```

*For details on configuring `.env` variables and custom shortcut hotkeys, please refer to the [System Architecture Guide](file:///home/fev/GitRepos/clonedGitRepos/Jarvis/ai/01_architecture.md#6-environment--settings-variables).*
