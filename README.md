# 🧠 Clicky — AI Desktop Tutor for Students

Clicky is a hackathon-ready Windows desktop AI tutor. It captures the current screen, extracts visible text, asks an AI model for short steps, and highlights the target UI text with a transparent always-on-top overlay.

<div align="center">

### *Ask. Learn. Click. Done.*

- Tauri 2, React, TypeScript
- Python 3.11 worker scripts
- AI providers:
  - Ollama model (default): `gemma4:e4b`
  - Groq vision model (optional): `meta-llama/llama-4-scout-17b-16e-instruct`
- OCR: Windows OCR API first, EasyOCR fallback
- Capture: `dxcam`
- Active window and UI fallback: `pywinauto`

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Tauri](https://img.shields.io/badge/Tauri-2.x-orange)
![React](https://img.shields.io/badge/React-TypeScript-61dafb)
![Python](https://img.shields.io/badge/Python-3.11-yellow)
![AI](https://img.shields.io/badge/AI-Gemma4%3Ae4b-green)
![License](https://img.shields.io/badge/license-MIT-purple)

An AI-powered Windows desktop tutor that teaches users software directly on their screen using local AI.

1. Install prerequisites:
   - Node.js 20+
   - Rust stable
   - Python 3.11+
   - Ollama
2. Pull the local model (default provider):
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

Press `Ctrl + Shift + Enter` to open the small command popup. `Ctrl + Shift + Space` also works as a fallback. Ask something like "How do I install Python extension?" and Clicky will capture the current screen, run OCR, call the configured AI provider, and highlight the matched target text.

## Provider Configuration

By default Clicky uses Ollama. To switch to Groq with image understanding, set these environment variables before running:

```powershell
$env:CLICKY_AI_PROVIDER="groq"
$env:GROQ_API_KEY="your-groq-api-key"
```

Optional overrides:

```powershell
$env:CLICKY_GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"
$env:CLICKY_GROQ_URL="https://api.groq.com/openai/v1/chat/completions"
```

For Ollama overrides:

```powershell
$env:CLICKY_AI_PROVIDER="ollama"
$env:CLICKY_OLLAMA_MODEL="gemma4:e4b"
$env:CLICKY_OLLAMA_URL="http://localhost:11434/api/generate"
```
</div>

---

# 🚀 What is Clicky?

Clicky is a hackathon-ready AI desktop tutor that helps students learn software in real time.

Instead of:
- searching YouTube tutorials
- reading long documentation
- switching tabs repeatedly

Users can simply ask:

```text
"How do I install Python extension?"
"How do I crop an image?"
"How do I export this?"
```

Clicky:
1. Captures the current screen
2. Reads visible UI text
3. Detects the active application
4. Uses local AI to generate instructions
5. Highlights the exact button/menu to click

Everything runs locally for speed, privacy, and zero API cost.

---

# 🎯 Why It Matters

Students waste hours learning basic software workflows.

Clicky transforms software learning into an interactive real-time experience.

## Benefits

✅ Learn directly inside apps  
✅ No long tutorials  
✅ No cloud dependency  
✅ Beginner-friendly guidance  
✅ Privacy-first local AI  
✅ Fast workflow assistance  

---

# ✨ Features

## 🖥️ Real-Time Screen Capture
Captures the active screen when the user asks a question.

## 🔍 OCR-Based UI Understanding
Extracts visible text/buttons/menus from applications.

## 🧠 Local AI Reasoning
Uses:
- Ollama
- Gemma (`gemma4:e4b`)

for offline AI guidance.

## 🎯 Smart Overlay Highlighting
Highlights buttons and menus directly on the screen.

## ⚡ Global Hotkey Workflow

Press:

```text
CTRL + SHIFT + SPACE
```

to instantly ask Clicky for help.

## 🔒 Privacy Friendly

- Fully local processing
- No cloud screenshots
- No external APIs required

---

# 🏗️ Architecture

```text
┌─────────────────────┐
│ User Question       │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Global Hotkey       │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Screen Capture      │
│ dxcam               │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ OCR Extraction      │
│ Windows OCR         │
│ EasyOCR Fallback    │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Active Window       │
│ pywinauto           │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Ollama + Gemma      │
│ AI Step Generation  │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ JSON Instructions   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Overlay Highlight   │
│ Guidance            │
└─────────────────────┘
```

---

# 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Desktop Framework | Tauri 2 |
| Frontend | React + TypeScript |
| AI Runtime | Ollama |
| AI Model | `gemma4:e4b` |
| OCR | Windows OCR API |
| OCR Fallback | EasyOCR |
| Screen Capture | `dxcam` |
| Window Detection | `pywinauto` |
| Overlay System | Transparent Tauri Window |
| Backend Runtime | Python 3.11+ |

---

# 📂 Project Structure

```text
/src-tauri
    Tauri desktop shell
    Overlay window
    Global hotkeys

/frontend
    React UI
    Overlay rendering
    Chat interface

/python
    Capture scripts
    OCR pipeline
    AI integration
    Window detection
    Matching logic

/shared
    Shared schemas
    JSON payloads

/scripts
    Setup scripts
    Startup helpers
```

---

# ⚡ Installation

## 1. Install Requirements

### Required Software

- Node.js 20+
- Rust Stable
- Python 3.11+
- Ollama

---

## 2. Pull Local AI Model

```powershell
ollama pull gemma4:e4b
```

---

## 3. Install Dependencies

```powershell
npm install
npm run setup:python
npm run check:ollama
```

---

## 4. Start Development Server

```powershell
npm run dev
```

---

# ⌨️ Usage

Press:

```text
CTRL + SHIFT + SPACE
```

Then ask:

```text
How do I install Python extension?
```

Clicky will:
1. Capture the current screen
2. Extract visible UI text
3. Detect the current application
4. Generate AI instructions
5. Highlight matching buttons/menus

---

# 🧠 Example Workflow

## User Opens VS Code

User asks:

```text
How do I install Python extension?
```

## Clicky Detects:

```text
Visible UI:
- File
- Edit
- Terminal
- Extensions
- Search
```

## AI Response:

```json
{
  "summary": "You can install the Python extension from the Extensions panel.",
  "steps": [
    {
      "step": 1,
      "instruction": "Click Extensions on the left sidebar.",
      "target_text": "Extensions"
    },
    {
      "step": 2,
      "instruction": "Search for Python.",
      "target_text": "Python"
    }
  ]
}
```

## Overlay Highlights:
✅ Extensions button  
✅ Search field  

---

# 🎮 Supported MVP Apps

Optimized for:
- VS Code
- Chrome
- Paint
- File Explorer

Other applications may work depending on OCR quality.

---

# 🔮 Future Improvements

## Planned Features

- Interactive step tracking
- Voice assistant mode
- Better UI matching
- Accessibility features
- Multi-monitor support
- Auto-guided walkthroughs
- Cursor tracking
- AI memory for workflows

---

# 🔒 Privacy

Clicky is designed to be privacy-first.

## Local Processing

- No cloud screenshots
- No remote AI dependency
- No external tracking
- Local AI inference

Everything stays on the user's device.

---

# 🧪 Production Notes

This MVP intentionally avoids:
- FastAPI
- local web servers
- microservices
- cloud APIs

Tauri launches Python worker scripts directly and receives JSON over stdout.

This makes the app:
- simpler
- faster
- more reliable for hackathons

Ollama runs locally on:

```text
localhost:11434
```

---

# 📸 Demo Assets

Recommended hackathon assets:

- Main UI screenshot
- Overlay demo GIF
- Hotkey popup GIF
- VS Code walkthrough demo
- Before/after comparison

---

# 🏆 Hackathon Pitch

> “Clicky is an AI desktop tutor that teaches students software directly on their screen using local AI.”

---

# 🤝 Contributing

Contributions, ideas, and feedback are welcome.

Feel free to:
- open issues
- suggest features
- improve OCR
- optimize overlays
- add app-specific workflows

---

# 📜 License

MIT License

---

# ⭐ Support

If you like this project:
- Star the repository
- Share it with friends
- Contribute improvements

---

<div align="center">

## 🚀 Built for students, hackers, and curious learners.

</div>
