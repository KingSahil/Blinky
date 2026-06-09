# Blinky — Sarvam AI Voice Integration Guide

This guide describes how Blinky integrates with Sarvam AI's Indian-context text-to-speech and speech-to-text engines to provide voice interaction and spoken instructions.

---

## 1. Voice Integration Architecture

Voice services in Blinky are driven by the React frontend via direct HTTP requests to Sarvam's API endpoints. The user's subscription key is managed by Tauri and stored inside the local `.env` environment file.

```text
  ┌──────────────────────────────────────────────────────────┐
  │                   CommandBar.tsx / tts.ts                │
  └──────────────────────────────────────────────────────────┘
             │                                    ▲
             ▼ (POST / JSON payload)              │ (POST / Multi-part audio)
  ┌───────────────────────┐            ┌───────────────────────┐
  │    Text-to-Speech     │            │    Speech-to-Text     │
  │ /text-to-speech       │            │ /speech-to-text       │
  │ Model: bulbul:v3      │            │ Model: saaras:v3      │
  └───────────────────────┘            └───────────────────────┘
             │                                    ▲
             ▼                                    │
  ┌───────────────────────┐            ┌───────────────────────┐
  │     Sarvam AI TTS     │            │     Sarvam AI STT     │
  └───────────────────────┘            └───────────────────────┘
```

---

## 2. Text-to-Speech (TTS) Specifications

The TTS module converts Blinky's action instructions into localized speech.

* **API Endpoint**: `https://api.sarvam.ai/text-to-speech`
* **HTTP Method**: `POST`
* **Authentication Header**: `'api-subscription-key': sarvamApiKey`
* **Payload Structure** ([tts.ts](file:///c:/projects/Jarvis/frontend/src/lib/tts.ts)):
  ```json
  {
    "text": "Open the Extensions panel.",
    "model": "bulbul:v3",
    "target_language_code": "en-IN",
    "speaker": "ratan",
    "pace": 1.05,
    "speech_sample_rate": 16000,
    "output_audio_codec": "mp3"
  }
  ```

### Spoken Content Assembly
The helper function `buildSpeechContent` concatenates the overall summary and individual steps list:
* Strips trailing punctuation from summaries.
* Appends numbered guide steps in format: `"Steps: Step 1. {instruction_1} Step 2. {instruction_2}"`.

### Playback Logic
* **Voice-First Constraint**: Voice readback only triggers if the workflow was initiated using the voice input button. Typed workflows remain silent on subsequent step click-advancements.
* Audio is returned as a base64 string, which is converted to a Data URL:
  `data:audio/mpeg;base64,{base64_audio}`
  and played back using the HTML5 `Audio` API.

---

## 3. Speech-to-Text (STT) Specifications

The STT module transcribes the user's voice prompts.

* **API Endpoint**: `https://api.sarvam.ai/speech-to-text`
* **HTTP Method**: `POST`
* **Authentication Header**: `'api-subscription-key': sarvamApiKey`
* **Request Body**: Multipart FormData containing:
  * `file`: Binary audio blob (e.g. `query.webm` captured via browser MediaRecorder).
  * `model`: `"saaras:v3"`
  * `language_code`: `"en-IN"`
* **Transcription Output**: The transcribed string returned under the `transcript` property is inserted into the command input field and immediately triggers `executeTutor`.

---

## 4. Settings Management

* **Storage**: The API key is defined in the `.env` file under `SARVAM_API_KEY`.
* **Flow**:
  1. Frontend retrieves settings on mount by calling Tauri command `get_settings`.
  2. The key is stored in React state `sarvamApiKey`.
  3. When updated in the Settings panel, the key is saved back using Tauri command `save_settings` which edits the `.env` file.

---

## 5. Voice With Web/Autopilot Mode

Voice input still enters through `CommandBar.tsx`, so a spoken prompt can trigger either normal screen guidance or globe/web mode depending on the UI state. Sarvam only handles speech transcription and readback; it does not make browser-routing or autopilot decisions.

Autopilot clicks remain governed by `frontend/src/lib/autopilot.ts` safety gates. Spoken workflows follow the same safe-click rules as typed workflows, and typed follow-up actions stay manual.

---

## 6. Error Handling & Parsing

Sarvam API response structures are parsed by a custom utility `getSarvamErrorMessage`:
* Safely extracts nested error fields (`error`, `message`, `detail`, `code`).
* Formats HTTP error statuses into human-readable alerts:
  * Example: *"Sarvam TTS failed with status 401: Invalid API Key"*

---

## Related Guides & Files
- [TTS Interfaces & Payload Builders](file:///c:/projects/Jarvis/frontend/src/lib/tts.ts)
- [Command Bar Component](file:///c:/projects/Jarvis/frontend/src/CommandBar.tsx)
- [Rust Environment Settings Handler](file:///c:/projects/Jarvis/src-tauri/src/lib.rs)
