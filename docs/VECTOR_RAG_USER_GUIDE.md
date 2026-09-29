# Blinky Vector Database RAG & Encrypted Key Sync User Guide

Welcome to the **Blinky Vector Database RAG & Encrypted Key Sync System**!

This guide explains how to use **Dense Vector Search**, **Hybrid OKF Grounding**, and **Standalone Mobile PC-Offline RAG** on Desktop (Tauri + Python) and Mobile (`Blinky.apk` via Expo).

---

## 🌟 Key Features

1. **Dual RAG Strategy:**
   * **Full-Context OKF Mode:** High-density structured Markdown context injection for standard documents (zero-loss, 100% fidelity).
   * **Dense Vector RAG Mode:** Top-K vector chunk retrieval powered by SQLite & Cosine Similarity search for large PDFs and multi-file research notebooks.
2. **Encrypted Hardware KeyStore API Key Sync:**
   * When Mobile pairs with Desktop Blinky over WebSocket (Port 9001), API keys (`Groq`, `Gemini`, `DeepSeek`, `OpenAI`) are transferred via base64/encrypted payload.
   * Mobile stores keys in **Android KeyStore** (`EncryptedSharedPreferences`) via `Expo.SecureStore`.
3. **Standalone Mobile Autonomy:**
   * When the PC is turned off, `Blinky.apk` runs on-device Top-K vector search and queries cloud APIs directly from the phone.

---

## 💻 Desktop Usage (Python + React UI)

### 1. Opening the Notebook Hub
* Click the **Book Open (📖)** icon in the Blinky Command Bar or press `Ctrl+N` to open the Notebook Hub.

### 2. Switching Between RAG Modes
* In the workspace header, click the mode toggle button:
  * **`⚡ Dense Vector RAG`**: Indexes document chunks and retrieves top-5 vector matches per query.
  * **`📄 Full Context OKF`**: Injects full active document sources into LLM context.

### 3. Uploading & Indexing Documents
* Drag and drop `.pdf`, `.md`, `.txt`, or `.json` files into the **Sources** column on the left.
* Documents are automatically chunked (`512 words`, `64 word overlap`) and indexed into SQLite (`tmp/notebooks/vector_store.db`).

### 4. Running Grounded Queries & Generating Artifacts
* Type your question in the chat input to view grounded answers with citation badges (`[Source: filename.pdf]`).
* Click any button in **Studio Artifacts** (Right Column) to instant-generate *Executive Summaries*, *FAQs*, *Study Guides*, or *Action Checklists*.

---

## 📱 Mobile Usage (`Blinky.apk` Android App)

### 1. Standalone Document Indexing
* Open the **Notebooks** tab in the Blinky Mobile app.
* Tap **`📎 Attach File`** to pick PDFs or text documents from your phone storage via `expo-document-picker`.

### 2. Toggling Mobile Vector RAG
* Tap the mode toggle button on mobile:
  * **`⚡ Vector RAG`**: Executes local JS/TS tokenization and cosine similarity vector retrieval on mobile.
  * **`📄 Full Context`**: Grounded response across all active mobile sources.

### 3. PC-Offline Mobile Operation
1. Connect mobile to PC once over Wi-Fi (Port 9001) to automatically sync encrypted API keys.
2. Mobile saves keys into **Android Hardware KeyStore**.
3. Turn off your PC! Mobile continues executing vector RAG queries independently.

---

## 🧪 Automated Testing

Run the master vector test suite:
```powershell
$env:PYTHONPATH="common/python"; python -m unittest common/python/tests/test_vector_rag_master.py
```
