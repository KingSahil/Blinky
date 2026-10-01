# OKF Notebook Functionality: Master Implementation Plan

This document outlines the complete multi-phase implementation plan for the **OKF (Offline Knowledge Format) Notebook Functionality** across Python Backend, Desktop Shell, and Standalone Mobile Companion (`Blinky.apk`).

---

## Core Philosophy: OKF as a Substitute for RAG

For small to medium documents, PDFs, notes, and application manuals (which fit into modern 128k–1M context windows), traditional vector RAG fragments text and creates unnecessary chunking loss.

**OKF (Offline Knowledge Format)** acts as a direct, full-context substitute for RAG:
* **Zero Fragment Loss:** Documents are parsed into high-density structured Markdown and injected directly into the LLM context.
* **Inline Source Badging:** Answers cite sources using exact badges (`[Source: filename.pdf]`).
* **Actionable Execution:** Contains desktop navigation metadata so clicking a citation offers a **"▶ Execute on PC"** button to perform shortcuts/clicks on Windows desktop.

---

## Implementation Phases

### Phase 1: Python Backend Core Engine (`common/python/notebooks/`)
* [x] **Document Parser (`document_parser.py`):** Converts PDFs, Markdown, TXT, and HTML files into structured OKF Markdown blocks with source headers.
* [x] **Notebook Store Manager (`notebook_manager.py`):** JSON-backed CRUD engine (`tmp/notebooks/notebooks_store.json`) for notebooks and source attachments.
* [x] **OKF Prompt Builder (`okf_context_builder.py`):** Combines active notebook sources and live desktop app guides (`app_context/registry.py`) into full-context prompts with grounding rules.
* [x] **Automated Tests (`tests/test_notebook_okf.py`):** Unit test suite for parsing, store operations, and prompt construction.

---

### Phase 2: WebSocket API & Grounding Router (`common/python/main.py`)
* [ ] **Grounded LLM Dispatcher:** Route queries through `ai/client.py` enforcing strict grounded output and citation format (`[Source: filename.pdf]`).
* [ ] **WebSocket Protocol Handlers (`main.py`):**
  * `notebook_create` (creates notebook)
  * `notebook_list` (returns all active notebooks)
  * `notebook_add_source` (parses file and attaches source)
  * `notebook_query` (streams grounded answer + citations)
* [ ] **PC Action Payload Generator:** Parse software shortcuts/navigation from OKF responses to include executable PC action triggers (`▶ Execute on PC`).

---

### Phase 3: Desktop UI Component (`NotebookView.tsx` & `styles.css`)
* [x] **3-Column Glassmorphism Workspace Interface:**
  * **Design System Overhaul:** Redesigned `.notebook-overlay`, `.notebook-container`, `.notebook-input-area`, `.send-btn`, and `.message-bubble` with sleek dark glassmorphism, responsive grid column bounds, and glowing focus states.
  * **Typography Control:** Scoped heading bounds (`font-family: "Space Grotesk"`, `font-size: 16px`) to prevent overflow collisions.
  * **Left Column (Sources):** Upload PDFs/documents, drag-and-drop zone, source toggle checkboxes with file meta indicators.
  * **Center Column (Grounded Chat):** Interactive streaming chat with clear user/AI bubble gradients, dense vector RAG toggle pill, and styled input controls.
  * **Right Column (Studio Artifacts):** One-click artifact generator cards (*Executive Summary*, *FAQ*, *Study Guide*, *Action Checklist*) with structured flex layouts.

---

### Phase 4: Standalone Android App Integration (`NotebookScreen.tsx`)
* [ ] **Mobile Notebooks Tab:** Add a **Notebooks** tab in `common/mobile/`.
* [ ] **Document Picker:** Select PDFs and text files from Android phone storage via `expo-document-picker`.
* [ ] **Encrypted KeyStore Sync:** Persist transferred API keys (`Groq`, `DeepSeek`, `Gemini`) in `Expo SecureStore` (`EncryptedSharedPreferences`) for offline mobile usage.
* [ ] **Offline JS Search Engine:** Integrate `MiniSearch` JS index on mobile for offline document search when PC is turned off.

---

## Verification & Final Handshake Plan
1. **Backend Verification:** Validate `notebooks` package and unittest execution.
2. **WebSocket Integration:** Test `notebook_query` frame handling on port 9001.
3. **Standalone APK Build:** Compile `app-release.apk` via `npx expo run:android --variant release` and verify offline phone execution.
