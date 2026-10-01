# Implementation Plan - Modern Settings Dialog & Modal Architecture

## 1. Problem Diagnosis & Why the Current Dropdown Looks Messy
- **Spatial Constraint**: The desktop `CommandBar` is a floating launcher widget (560px wide). Squeezing multi-agent routing, dynamic model search dropdowns, API key inputs, voice switches, and mobile pairing into a 320px–400px floating dropdown causes severe visual crowding, text wrapping bugs (e.g. `& RAG` breaking onto new lines), and cramped button bars.
- **Visual Clutter**: The popover dropdown overlays the input bar awkwardly and feels like a rushed widget instead of a professional desktop application.

---

## 2. Proposed Architecture: Dedicated Settings Dialog Modal

Instead of a cramped floating dropdown, clicking the **Settings Gear (⚙️)** will open a **Centered Glassmorphic Settings Dialog** (`640px` wide, `480px` tall) with a rich two-column layout inspired by Raycast, Linear, and MacOS System Settings.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ⚙️ Blinky Settings                                                      ✕  │
├───────────────────┬─────────────────────────────────────────────────────────┤
│                   │ 🖥️ AGENT 1: ACTUATOR (COMPUTER-USE)                     │
│ 🤖 Agent Routing  │ Provider: [ Groq ] [ Ollama ] [ DeepSeek ] [ Custom ]   │
│                   │ Model:    [ Search qwen, llama, gpt... 🔍 ] [Test ⚡]   │
│ 🔑 API Keys       │ Latency:  ✓ Online (142ms) • qwen/qwen3.8-27b           │
│                   ├─────────────────────────────────────────────────────────┤
│ 📱 Mobile & Link  │ 📚 AGENT 2: KNOWLEDGE & RAG                             │
│                   │ Model:    [ gemini-2.5-flash ] [ FastEmbed Hybrid ]     │
│ ⚡ Shortcuts      ├─────────────────────────────────────────────────────────┤
│                   │ 🎙️ AGENT 3: REALTIME VOICE                              │
│ ℹ️ About & Theme  │ Engine:   (•) AssemblyAI Universal-3  ( ) Sarvam AI     │
└───────────────────┴─────────────────────────────────────────────────────────┘
```

---

## 3. Key Improvements & Features

### A. Two-Column Desktop Settings Modal
1. **Left Navigation Sidebar (180px)**:
   - 🤖 **Agent Routing**: Multi-agent model assignments (Actuator, RAG, Voice)
   - 🔑 **API Credentials**: Groq, Gemini, DeepSeek, AssemblyAI, Sarvam, Custom endpoints
   - 📱 **Mobile & Integrations**: Integrated Pairing QR, LAN IP dropdown, WhatsApp bridge
   - ⚡ **Shortcuts & Audio**: Activation hotkeys (`Ctrl+Shift+Enter` vs `Ctrl+Win+Space`), Push-to-Talk
   - ℹ️ **About & Diagnostics**: Offline engine status, theme (`Ember`), version (`v1.0.0`)
2. **Right Content Area (Spacious 440px with smooth scroll)**:
   - Full-width, un-truncated model names and badges.
   - Clean segmented cards with generous padding (`16px`), glowing flame borders (`#FF5A36`), and status badges.
   - Real-time **"Test Ping ⚡"** latency check chips with animated spin loaders.

### B. Polish & Interaction Enhancements
- **Backdrop Blur & Escape Key**: Click-outside backdrop or pressing `Escape` smoothly dismisses the modal.
- **Ember & Deep Space Styling**: High-contrast `#0c0a09` background, `rgba(255, 90, 54, 0.25)` active glowing borders, glassmorphic blur, and `Astonpoliz`/`Okine Sans` typography.
- **Embedded Mobile Companion**: Direct QR scan canvas embedded in the "Mobile & Link" tab without needing nested secondary popups.

---

## 4. Files to Update
- [`common/frontend/src/CommandBar.tsx`](file:///c:/Users/khann/Projects/Blinky/common/frontend/src/CommandBar.tsx): Convert `showSettings` from a dropdown into the centered Settings Modal Dialog component with two-column navigation.
- [`common/frontend/src/styles.css`](file:///c:/Users/khann/Projects/Blinky/common/frontend/src/styles.css): Add styles for `.settings-modal-backdrop`, `.settings-modal-dialog`, `.settings-sidebar`, `.settings-content-panel`, and clean card components.

---

## 5. Verification Plan
- **Build Verification**: Run `bun run typecheck` and `bun run build`.
- **UI Functional Check**: Verify all 5 sidebar tabs, model search filter, API key persistence, Test Ping latency triggers, and QR code rendering.
