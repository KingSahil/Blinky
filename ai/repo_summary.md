# Blinky — AI Directory & Developer Guides

Welcome to the AI integration and developer documentation directory for **Blinky**. 

This directory contains comprehensive guides designed to ramp up human developers quickly and instruct offline AI coding agents on the system architecture, API interfaces, coordinate mapping formulas, and post-processing pipelines used throughout the codebase.

---

## 📖 Available Guides

For a detailed walkthrough of the codebase, select one of the core guides below:

| Guide | Description | Target Audience |
| :--- | :--- | :--- |
| 🏗️ **[System Architecture](file:///c:/projects/Jarvis/ai/architecture.md)** | Multi-process models, high-level flowcharts, sequence diagrams, IPC protocols, coordinate scaling mechanics, and post-processing pipelines. | Architects, System Integrators, AI Agents |
| 📝 **[Per-File Specifications](file:///c:/projects/Jarvis/ai/detailed_summaries.md)** | Detailed function signatures, mathematical formulas, coordinate scaling bounds, bucketing, search scoring algorithms, and step post-processors. | Developers, AI Agents |
| 🗂️ **[Files Index](file:///c:/projects/Jarvis/ai/files_index.json)** | Machine-readable JSON listing of core codebase assets and their functional descriptions. | AI Agents, Automations |

---

## 🚀 Quick Repository Overview

```text
  c:\projects\Jarvis  (Blinky Project Root)
   ├── ai/                      ──► AI Documentation Hub (this folder)
   ├── frontend/src/            ──► React TypeScript GUI and Canvas viewports
   ├── src-tauri/src/           ──► Rust Native Core & Mouse Click hooks
   ├── python/                  ──► Capture, OCR Extraction & Targets Fuzzy Matching
   └── tmp/captures/            ──► Captured Telemetry Screen Buffers (temporary)
```

* **Purpose**: Privacy-first, local AI-powered tutor that captures screen states, extracts visible UI controls, runs coordinate-aware fuzzy matching, and places graphical click-target overlays on screen — one step at a time.
* **Core Tech Stack**: 
  * **Tauri (v2) + Rust**: OS-level hooks, shortcuts, window controllers, capture exclusion (`WDA_EXCLUDEFROMCAPTURE`).
  * **React + TypeScript**: Form inputs, dynamic height rendering, canvas overlay graphics.
  * **Python 3.11**: Screen captures (`dxcam`), WinRT OCR / EasyOCR, UI elements extraction (`pywinauto`).
  * **LLM Intelligence**: Local Ollama (`gemma4:e4b`) or cloud-hosted Groq Vision API (`llama-4-scout`).

---

## 🛠️ Rapid Dev Commands

Set up Blinky locally using the following commands:

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

*For details on configuring `.env` variables and custom shortcut hotkeys, please refer to the [System Architecture Guide](file:///c:/projects/Jarvis/ai/architecture.md#6-environment--settings-variables).*

## Current AI Guidance Behavior

Blinky operates in a **single-step reactive mode**:

* **Preflight Classification**: Before any screen capture, a text-only classifier decides whether the query needs screen analysis. It also detects continuations (follow-ups to a previous active goal) vs. new tasks using `is_continuation`.
* **Single-Step Generation**: The AI prompt enforces exactly **1 step** per response. Token output is capped at 350 to minimise local Ollama inference time. The backend also programmatically slices the steps list to `[:1]` as a safety net.
* **No Background Polling**: Blinky is fully reactive — it only captures the screen and queries the model when the user submits a question or clicks a highlighted target. There is no background polling loop.
* **Flicker-Free Capture**: The Rust backend uses `WDA_EXCLUDEFROMCAPTURE` display affinity to hide Blinky windows from screenshots while keeping them fully visible and interactive on the user's desktop.
* **Search Bar Fallback**: If the AI returns a search/type instruction with empty `target_text`, the backend auto-detects and attaches the first visible search/filter input control so the green pulsing highlight always appears on the search bar.
* **Navigation Step Skipping**: If the AI's first step is a redundant navigation action (e.g. "click Extensions tab") but the target search bar is already visible on screen, the step is automatically skipped.
* **Input Field Highlighting**: When a matched element is an input control (Edit, TextBox, ComboBox), the overlay renders a full-width highlight instead of character-count-based width capping.
* Voice readback speaks the current Action Guide step only for workflows that started from voice input. Typed workflows stay silent on highlight-click continuations.
