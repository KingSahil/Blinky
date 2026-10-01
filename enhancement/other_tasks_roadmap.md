# Enhancement Tasks Architectural Roadmap

This document outlines the detailed technical specifications and execution plans for all enhancement tasks in Blinky.

---

## Task 1: RevenueCat Paywall & Mobile Store Distribution
* **Status:** **Resolved / Active**
* **Architecture:**
  * RevenueCat SDK (`react-native-purchases`) runs exclusively on the mobile companion app (`common/mobile/lib/purchases.ts`).
  * Mobile handles subscription entitlements and promo code redemptions (`@blinky_pc_promo_unlocked`).
  * Mobile broadcasts pro status over local WebSocket (port 9001) to Desktop Blinky (`{ "type": "auth_status", "pro_unlocked": true }`).
  * **Desktop Requires 0 Keys/URLs from Users.**

---

## Task 2: Dedicated OKF + RAG NotebookLM-Style Knowledge Hub
* **Status:** Fully specified in [`enhancement/OKF.md`](file:///c:/Users/khann/Projects/Blinky/enhancement/OKF.md).
* **Architecture:**
  * Uses **OKF (Offline Knowledge Format)** as a direct, full-context substitute for RAG on small/medium documents to prevent context fragmentation.
  * In-app Notebook UI for Desktop & Mobile.
  * Multi-model provider integration (Groq, Ollama, DeepSeek, Gemini).
  * Actionable PC execution buttons (`▶ Execute on PC`).

---

## Task 3: Overall Performance & Latency Optimization
* **Status:** Architectural Design Ready
* **Focus Areas:**
  * **Fast Screen & UI Scanning:** Optimize Windows UIA tree scanning and WinRT/OmniParser OCR caching to achieve sub-300ms element matching.
  * **Token Length & History Trimming:** Dynamic history truncation to prevent model stutter on local Ollama / Qwen setups.
  * **Non-Blocking WebSocket Pipeline:** Async queueing between Desktop Tauri shell and Mobile companion over port 9001.

---

## Task 4: Mobile Video Generation Menu (Higgsfield AI + Prompt Orchestrator)
* **Status:** Architectural Design Ready
* **Architecture:**
  * **Dedicated Mobile Screen:** A new "Video Generator" menu inside the Expo Mobile App (`common/mobile/VideoGenScreen.tsx`).
  * **Orchestration Layer:**
    1. **Prompt Decomposer:** Converts raw user input (*"Generate a 5-second video of a cyberpunk city in neon rain"*) into structured camera, motion, and style parameters.
    2. **API Dispatcher:** Routes video generation requests to **Higgsfield AI** (or fallback video models via Replicate/Fal.ai).
    3. **Progress Tracking & Stream:** Receives status updates via WebSocket/polling and streams the output MP4 video directly to the mobile UI.

---

## Task 5: README Maintenance
* **Status:** **Completed** (Maintained continuously as features ship).

---

## Task 6: Wakeword Engine Overhaul (`openwakeword`)
* **Status:** Architectural Design Ready
* **Problem:** Audio mismatches and false triggers/misfires in `python/wake_word.py`.
* **Fixes & Enhancements:**
  * **16kHz Polyphase Resampling:** Dynamic resampling of Windows default audio capture device (44.1kHz / 48kHz) down to `openwakeword`'s native 16kHz requirement using `scipy.signal.resample_poly`.
  * **Dynamic Noise Floor & RMS Thresholding:** Prevents false positives during background noise while reliably capturing *"Hey Blinky"*.
  * **State Machine Fix:** Reliable pause/resume handling via stdin listener during active TTS speech playback or tutor execution.
  * **ANSI Styled CLI Logging:** Clean dark-mode status logger with badges (`🎤 Hearing speech...`, `⚡ WAKE_WORD_DETECTED`, `💤 Listening...`).

---

## Task 7: Custom PDF Engine (`pdf_engine.py`)
* **Status:** Architectural Design Ready
* **Architecture:**
  * A dedicated Python PDF processing module at `common/python/tools/pdf_engine.py`.
  * **Core Tools:**
    1. **Structured Text & Table Extractor:** Extracts tables and text preserving layout structure for LLM ingestion.
    2. **PDF Manipulator:** Merges multiple PDFs, splits page ranges, reorders pages, and extracts images.
    3. **Annotation & Watermarking Engine:** Stamps custom text, headers/footers, and page numbers.
  * **Agent Integration:** Allows Blinky AI agent to run natural language commands like *"Merge document_A.pdf and document_B.pdf, extract page 3 table into CSV"*.
