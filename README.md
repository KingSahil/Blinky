# 🧠 Blinky — AI Desktop Tutor for Students

<div align="center">

### *Ask. Learn. Click. Done.*

<br>

<p align="center">

<img src="https://img.shields.io/badge/Tauri-2.x-orange?style=for-the-badge">
<img src="https://img.shields.io/badge/React-TypeScript-61dafb?style=for-the-badge">
<img src="https://img.shields.io/badge/Bun-1.3.14-f9f1e1?style=for-the-badge">
<img src="https://img.shields.io/badge/Python-3.11-yellow?style=for-the-badge">
<img src="https://img.shields.io/badge/Playwright-Edge-green?style=for-the-badge">

</p>

<p align="center">

<img src="https://img.shields.io/badge/Ollama-gemma4:e4b-green?style=for-the-badge">
<img src="https://img.shields.io/badge/Groq-Vision-purple?style=for-the-badge">
<img src="https://img.shields.io/badge/OCR-Windows%20OCR-blue?style=for-the-badge">

</p>

<p align="center">

<img src="https://img.shields.io/badge/EasyOCR-Fallback-red?style=for-the-badge">
<img src="https://img.shields.io/badge/dxcam-Screen%20Capture-black?style=for-the-badge">
<img src="https://img.shields.io/badge/pywinauto-Window%20Detection-darkgreen?style=for-the-badge">

</p>

<br>

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![License](https://img.shields.io/badge/license-MIT-purple)

</div>

---

An AI-powered Windows desktop tutor that teaches users software directly on their screen using local AI. In web mode it can also open/search in your default Edge browser and run a bounded safe-click loop after reading the screen.

# ⚡ Quick Start

## 1️⃣ Install Prerequisites

Install the following software:

- Bun 1.3+
- Rust Stable
- Python 3.11+
- Ollama

---

## 2️⃣ Pull the AI Model

```powershell
ollama pull gemma4:e4b
```

---

## 3️⃣ Install Dependencies

```powershell
bun install
bun run setup:python
bun run check:ollama
```

---

## 4️⃣ Start Blinky

```powershell
bun run dev
```


## ⌨️ Open Blinky

### Main Hotkey

```text
CTRL + SHIFT + SPACE
```

### Fallback Hotkey

```text
CTRL + SHIFT + ENTER
```

---

Ask something like:

```text
How do I install Python extension?
```

Blinky will:

* Capture the current screen
* Run OCR
* Detect the active application
* Generate AI instructions
* Highlight matching UI elements
* In globe/web mode, optionally click safe matched targets for up to 5 observe-act attempts


## Provider Configuration

By default Blinky uses Ollama. To switch to Groq with image understanding, set these environment variables before running:

```powershell
$env:BLINKY_AI_PROVIDER="groq"
$env:GROQ_API_KEY="your-groq-api-key"
```

Optional overrides:

```powershell
$env:BLINKY_GROQ_MODEL="llama-3.2-90b-vision-preview"
$env:BLINKY_GROQ_URL="https://api.groq.com/openai/v1/chat/completions"
```

For Ollama overrides:

```powershell
$env:BLINKY_AI_PROVIDER="ollama"
$env:BLINKY_OLLAMA_MODEL="gemma4:e4b"
$env:BLINKY_OLLAMA_URL="http://localhost:11434/api/generate"
```
</div>

---

# 🚀 What is Blinky?

Blinky is a **hackathon-ready AI desktop tutor** that helps students learn software in real time.

Instead of:

- Watching long YouTube tutorials
- Reading confusing documentation
- Switching tabs repeatedly

Users can simply ask:

```text
"How do I install Python extension?"
"How do I crop an image?"
"How do I export this?"
```

Blinky will:

1. Capture the current screen
2. Read visible UI text
3. Detect the active application
4. Generate AI instructions
5. Highlight the exact button/menu to click

---

# ✨ Features

## 🌟 Recent Enhancements

### 🧭 Bounded Autopilot Loop
Blinky can now run a small observe-act-observe loop from the command bar's globe/web mode.
- It first lets the browser agent open or search in Edge when the request is a web task.
- It then reads the visible screen, chooses one immediate next step, and clicks only matched safe actions such as click/open/select/choose/go to.
- It stops after 5 attempts, when the task is complete, when the same target repeats, or when the next action is unsafe.
- Typing, searching into forms, buying, paying, installing, enabling, deleting, login, and submit actions stay manual.

### 🌐 Edge Browser Intelligence
The Python router now has a safer browser-planning path before generated tools.
- Common open/search/site-search requests are planned as JSON actions.
- Playwright launches visible Microsoft Edge (`msedge`) instead of a hidden throwaway browser when possible.
- Generated Playwright code is still available as a fallback, but common API mistakes are repaired before safety auditing and verification.

### 🛡️ Dynamic Capture Exclusion (Flicker-Free Mode)
Blinky now uses the native Windows API (`SetWindowDisplayAffinity` / `WDA_EXCLUDEFROMCAPTURE`) to exclude its own command and overlay windows from screen captures programmatically. 
- **The Blinky UI remains fully visible and active to you.**
- **The screenshots captured for the AI model are completely clean**, hiding the Blinky UI from its own vision without needing to minimize or hide the app.
- **Manual user screenshots (e.g., `Ctrl + Win + S` / `Win + Shift + S`) still capture Blinky correctly** because capture exclusion is dynamically restored immediately after the AI's screenshot is captured (under 100ms).

### 🎯 Full-Width Search & Input Highlighting
Highlight boxes for search bars and text inputs are no longer constrained or shrunk to specific OCR words. 
- Blinky automatically detects when OCR text lies within a native text-input control (using UIA boundaries).
- It scales and extends the highlight overlay to cover the **entire width of the input field**, providing a clean, clear visual guide.

### 📋 Robust Action Guides & Fallbacks
Action-oriented tasks (such as searching, downloading, or configuring settings) will **always generate a step-by-step Action Guide**, even when the target view, panel, or extension marketplace is currently closed.
- Instead of defaulting to a plain text summary, Blinky guides you to open the appropriate panel or sidebar view first, followed by the search and interaction steps.
- Non-visible targets are listed as text guidance with `target_text: ""` to keep guidance clear without drawing empty highlights.

### ⚡ Local Inference Performance Optimizations
Local Ollama (Gemma) execution speed has been optimized to **5-7 seconds** (down from 15+ seconds) through:
- **Duplicate Capture Elimination:** Removed redundant screenshot and OCR execution loops in the Python worker.
- **Prompt Compression:** Compressed OCR layout tokens by converting items to a compact coordinate string representation, reducing prompt tokens by ~1800.
- **Timeout Tuning:** Extended connection timeouts to 120 seconds to prevent local model load-time failures.

## 🖥️ Real-Time Screen Capture
Captures the active screen instantly when the user asks a question.

## 🔍 OCR-Based UI Understanding
Extracts visible text, buttons, menus, and labels from applications.

- Windows OCR API (primary)
- EasyOCR fallback

## 🧠 Local AI Reasoning
Runs fully offline using:

- Ollama
- `gemma4:e4b`

## 🎯 Smart Overlay Highlighting
Highlights buttons and menus directly on the user's screen.

## 🖱️ Safe Autopilot Clicking
When globe/web mode is active, Blinky can convert matched screenshot coordinates back to physical screen coordinates and call the native Windows click command. The AI still sees the optimized screenshot; the click lands in the real desktop coordinate space.

## ⚡ Global Hotkey Workflow

Open Blinky instantly using:

```text
CTRL + SHIFT + SPACE
```

## 🔒 Privacy Friendly

- Fully local processing
- No cloud screenshots
- No tracking
- No mandatory external APIs

---

# 🎯 Why It Matters

Students waste hours learning basic software workflows.

Blinky transforms software learning into an **interactive real-time experience**.

### Benefits

✅ Learn directly inside apps  
✅ No long tutorials  
✅ No cloud dependency  
✅ Beginner-friendly guidance  
✅ Privacy-first local AI  
✅ Fast workflow assistance

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

Globe/web mode adds:

┌─────────────────────┐
│ Browser Planner     │
│ Playwright + Edge   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Screen Tutor        │
│ Observe Next Step   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Native Safe Click   │
│ Max 5 Attempts      │
└─────────────────────┘
```

---

# 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Desktop Framework | Tauri 2 |
| Frontend | React + TypeScript |
| JavaScript Runtime / Package Manager | Bun |
| Backend Runtime | Python 3.11+ |
| AI Runtime | Ollama |
| AI Model | `gemma4:e4b` |
| OCR | Windows OCR API |
| OCR Fallback | EasyOCR |
| Screen Capture | `dxcam` |
| Window Detection | `pywinauto` |
| Browser Automation | Playwright + Microsoft Edge |
| Overlay System | Transparent Tauri Window |

---

# 📂 Project Structure

```text
src-tauri/
├── Tauri desktop shell
├── Overlay window
└── Global hotkeys

frontend/
├── React UI
├── Overlay rendering
└── Chat interface

python/
├── Capture scripts
├── OCR pipeline
├── AI integration
├── Edge browser agent
├── Window detection
└── Matching logic

shared/
├── Shared schemas
└── JSON payloads

scripts/
├── Setup scripts
└── Startup helpers
```

---

# ⚡ Installation

## 1️⃣ Install Requirements

### Required Software

- Bun 1.3+
- Rust Stable
- Python 3.11+
- Ollama

---

## 2️⃣ Pull the Local AI Model

```powershell
ollama pull gemma4:e4b
```

---

## 3️⃣ Install Dependencies

```powershell
bun install
bun run setup:python
bun run check:ollama
```

---

## 4️⃣ Start Development Server

```powershell
bun run dev
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

Blinky will:

1. Capture the current screen
2. Extract visible UI text
3. Detect the active application
4. Generate AI instructions
5. Highlight matching buttons/menus

With the globe icon enabled, Blinky may also open/search in Edge and perform safe matched clicks for up to 5 attempts.

---

# 🧠 Example Workflow

## User Opens VS Code

### User asks:

```text
How do I install Python extension?
```

---

### Blinky detects:

```text
Visible UI:
- File
- Edit
- Terminal
- Extensions
- Search
```

---

### AI response:

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

---

### Overlay highlights

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

### Planned Features

- Interactive step tracking
- Voice assistant mode
- Better UI matching
- Accessibility improvements
- Multi-monitor support
- Cursor tracking
- AI workflow memory
- Richer autopilot verification
- Safe typed-input handoff

---

# 🔒 Privacy

Blinky is designed to be **privacy-first**.

### Local Processing

- No cloud screenshots
- No remote AI dependency
- No external tracking
- Local AI inference only

Everything stays on the user's device.

---

# 🧪 Production Notes

This MVP intentionally avoids:

- FastAPI
- Local web servers
- Microservices
- Cloud APIs

Tauri launches Python worker scripts directly and communicates using JSON over stdout.

### Why?

This makes the app:

- Simpler
- Faster
- Easier to debug
- More reliable for hackathons

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

> **“Blinky is an AI desktop tutor that teaches students software directly on their screen using local AI.”**

---

# 🤝 Contributing

Contributions, ideas, and feedback are welcome.

Feel free to:

- Open issues
- Suggest features
- Improve OCR
- Optimize overlays
- Add app-specific workflows

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
