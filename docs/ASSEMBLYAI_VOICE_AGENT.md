# AssemblyAI Voice Agent Integration (Hackathon Challenge)

This project integrates **AssemblyAI's Real-Time Voice AI technology** into Blinky, an intelligent desktop tutor and AI copilot for Windows and mobile.

Built for the **AssemblyAI - Voice Agent Hackathon**, this integration fulfills both paths of the hackathon challenge:
1. **Voice Agent API (End-to-End Voice Agent)**
2. **Realtime Speech-to-Text API (Universal-3 Pro Streaming)**

---

## 🚀 Hackathon Challenge Paths Implemented

### Path 1: Voice Agent API (`AssemblyAIVoiceAgent`)
Build an end-to-end voice agent through a single connection, with AssemblyAI handling the core voice interaction stack:
- **Speech-to-Text**: Powered by **Universal-3 Pro** (Universal-3.5 Pro Realtime).
- **LLM Routing & Voice Output**: Server-side reasoning with real-time synthesized voice output (`reply.audio`) streamed and decoded at 24 kHz via Web Audio API.
- **Turn-Taking & Voice Activity Detection (VAD)**: Server-side turn detection with automatic barge-in (interruption handling).
- **JSON-Schema Tool Calling**: Custom tool definitions enabling the AssemblyAI Voice Agent to actuate and command the PC desktop:
  - `control_desktop`: Invoked by AssemblyAI when a user asks to click an icon, search the screen, open an app, or execute desktop navigation.
  - `cancel_desktop_action`: Stops any ongoing automation loop.
  - Execution cycle: AssemblyAI sends `tool.call` -> Blinky runs desktop UI automation (`executeTutor`) -> Blinky returns `tool.result` -> AssemblyAI speaks the status back to the user.

### Path 2: Realtime Speech-to-Text API (`AssemblyAIRealtimeSTT`)
Use AssemblyAI's real-time speech-to-text API as the foundation of your voice agent, bringing your own orchestration:
- **WebSocket Streaming**: Connects to `wss://streaming.assemblyai.com/v3/ws` (or local proxy `ws://127.0.0.1:9001/assemblyai-stt`).
- **Sub-Second Transcription**: Live streaming of 16 kHz PCM16 audio with real-time partial and final transcripts.
- **Model**: Flagship `universal-3-5-pro` model.
- **Orchestration**: Feeds live transcripts into Blinky's local/cloud multi-agent tutor pipeline.

### Path 3: REST Audio Transcription Fallback
- For recorded audio files or mobile uploads: uploads to `https://api.assemblyai.com/v2/upload` and transcribes with `speech_model: "universal-3-pro"`.

---

## 🛠 Architecture & Pipeline

```
               [ User Microphone / Push-to-Talk ]
                              │
                    (16kHz PCM16 Chunks)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 Blinky Desktop Frontend                     │
│  [common/frontend/src/lib/assemblyaiVoice.ts]              │
│                                                             │
│  ┌──────────────────────────┐  ┌─────────────────────────┐  │
│  │ AssemblyAIVoiceAgent     │  │ AssemblyAIRealtimeSTT   │  │
│  │ (End-to-End WebSocket)   │  │ (Universal-3 Pro STT)   │  │
│  └─────────────┬────────────┘  └────────────┬────────────┘  │
└────────────────┼────────────────────────────┼───────────────┘
                 │ (ws://127.0.0.1:9001/...)  │
                 ▼                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 Tauri Rust Backend Gateway                  │
│  [common/src-tauri/src/websocket.rs]                        │
│  - Injects Authorization Header from .env                   │
│  - Proxies to wss://agents.assemblyai.com/v1/ws             │
│  - Proxies to wss://streaming.assemblyai.com/v3/ws          │
└────────────────┬────────────────────────────┬───────────────┘
                 │                            │
                 ▼                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   AssemblyAI Cloud Platform                 │
│  - Universal-3 Pro Speech-to-Text                           │
│  - Voice Activity Detection (VAD) & Turn-Taking             │
│  - LLM Orchestration & Voice Synthesis (TTS)               │
│  - JSON-Schema Tool Calling Engine                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ tool.call ("control_desktop")
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                 PC Desktop Actuation & Tutor                │
│  - Element Detection (WinRT OCR & UI Automation tree)       │
│  - Autonomous Mouse Glide & Native Clicking                 │
│  - Status Feedback sent back via tool.result                │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Configuration & Setup

1. **Environment Variables**:
   In `.env`:
   ```bash
   ASSEMBLY_AI_API_KEY=your_assemblyai_api_key_here
   ```

2. **Frontend Settings**:
   - Open Settings via the gear icon or shortcut.
   - Enter your AssemblyAI API Key in the **⚡ AssemblyAI Voice Agent** card.
   - Choose your preferred mode:
     - **Voice Agent API** (End-to-End Voice Agent + Tool Calling)
     - **Realtime STT API** (Universal-3 Pro Streaming)

3. **In-Bar Mode Switcher**:
   - A mode pill badge in the command bar lets you instantly toggle between `AAI Voice Agent` and `AAI Realtime STT`.

4. **Shortcuts**:
   - `Win+Space` or `Ctrl+Space`: Push-to-talk voice recording.
   - Mic Button: Click to start/stop listening.

---

## 📱 Mobile Remote Actuation

- Mobile connects over WebSocket to the PC Blinky desktop port.
- Mobile requests `get_assemblyai_key` upon connection.
- Spoken commands on mobile are transcribed using **AssemblyAI Universal-3 Pro** and executed on the desktop using the unified PC Blinky pipeline as per `pc-mobile-command-unification`.
