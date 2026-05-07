# Clicky

Clicky is a hackathon-ready Windows desktop AI tutor. It captures the current screen, extracts visible text, asks a local Gemma model through Ollama for short steps, and highlights the target UI text with a transparent always-on-top overlay.

## Stack

- Tauri 2, React, TypeScript
- Python 3.11 worker scripts
- Ollama model: `gemma4:e4b`
- OCR: Windows OCR API first, EasyOCR fallback
- Capture: `dxcam`
- Active window and UI fallback: `pywinauto`

## Quick Start

1. Install prerequisites:
   - Node.js 20+
   - Rust stable
   - Python 3.11+
   - Ollama
2. Pull the local model:
   ```powershell
   ollama pull gemma4:e4b
   ```
3. Install app dependencies:
   ```powershell
   npm install
   npm run setup:python
   npm run check:ollama
   npm run dev
   ```

Press `Ctrl + Shift + Space` to open the small command popup. Ask something like "How do I install Python extension?" and Clicky will capture the current screen, run OCR, call Ollama, and highlight the matched target text.

## Project Structure

```text
/src-tauri          Tauri desktop shell, commands, global hotkey, overlay window
/frontend           React UI and overlay views
/python             Worker scripts for capture, OCR, window detection, AI, matching
/shared             JSON schemas and example payloads
/scripts            Setup and startup helpers
```

## Production Notes

This MVP avoids a local web server for AI work. Tauri launches Python directly and receives one JSON payload on stdout. Ollama is the only network-like local dependency and runs on `localhost:11434`.

Supported demo targets are VS Code, Chrome, Paint, and File Explorer. Other apps can work when their visible text is captured clearly.
