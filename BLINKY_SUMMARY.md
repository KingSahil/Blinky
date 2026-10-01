# 🧠 Blinky — Project Summary & Feature Overview

> **"Ask. Learn. Click. Done."**
> An offline-first, privacy-respecting AI desktop tutor and autonomous computer-use agent for Windows and Linux, accompanied by a React Native (Expo) mobile companion, an ESP32 hardware daemon, and a WhatsApp bridge.

---

## 1. System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          DESKTOP HOST (Tauri 2)                        │
│                                                                        │
│  ┌───────────────────────┐             ┌────────────────────────────┐  │
│  │  Frontend (React 19)  │             │   Rust Core (Tauri 2)      │  │
│  │  - CommandBar         │◄── IPC ────►│   - Multi-window Overlay   │  │
│  │  - Visual Overlay     │             │   - WS Gateway (:9001)     │  │
│  │  - Sarvam Word Sync   │             │   - File Server (:9002)    │  │
│  └───────────────────────┘             │   - TLS Identity & Pinning │  │
│                                        └─────────────┬──────────────┘  │
│                                                      │ IPC / Sockets   │
│  ┌───────────────────────────────────────────────────▼──────────────┐  │
│  │  Python Backend Daemons                                          │  │
│  │  - Capture: dxcam (Win), Wayland/PipeWire/Portal/X11 (Linux)     │  │
│  │  - Grounding: WinRT OCR, OmniParser (YOLO), ATSPI/UIA Element Tree│ │
│  │  - Actuation: pywinauto, SendInput, ydotool, Hyprland/KDE/GNOME  │  │
│  │  - WIL Engine: Playwright + Edge + SearXNG metasearch            │  │
│  │  - Wake Word: hey_blinky.onnx (local ONNX runtime)               │  │
│  │  - Media / AICut: Subtitle alignment, video pipeline             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────▲───────────────────────────────▲─────────────────────┘
                   │ WSS (:9001) / HTTPS (:9002)   │ Serial / UDP / Web
┌──────────────────▼──────────┐         ┌──────────▼──────────┐
│   Expo Mobile Companion     │         │ External Peripherals│
│   (React Native SDK 57)     │         │ - ESP32 Smart Light │
│   - Sentinel Monitor & WoL  │         │ - WhatsApp Web Bot  │
│   - File Transfer & AICut   │         └─────────────────────┘
│   - Antigravity Approvals   │
└─────────────────────────────┘
```

---

## 2. Core Desktop System (Tauri 2 + Python)

* **Visual On-Screen Guidance:** Transparent, click-through overlay window rendering bounding boxes, directional arrows, and numbered step instructions directly over target desktop software (VS Code, Blender, Audacity). Programmatically excluded from screenshots (`WDA_EXCLUDEFROMCAPTURE`) to avoid visual self-capture feedback loops.
* **Preflight Intent Classifier:** Routes user queries before any screenshot is taken into:
  1. `DESKTOP_AUTOMATION` — needs screen capture + OCR + visual overlay.
  2. `OPEN_APP` — directly launches applications via protocol URIs and Windows Start Apps lookup.
  3. `MEDIA_PLAYBACK` — resolves songs to Spotify URIs and triggers playback.
  4. `SYSTEM_SHORTCUT` — parses natural language shortcuts (e.g. `Ctrl+S`, `Win+D`) and executes them.
  5. `INFORMATIONAL_CHAT` — answers technical questions without taking screenshots.
* **Dynamic App Context Generation:** Automatically queries local SearXNG metasearch for keyboard shortcuts and navigation hierarchies on first encounter of any app, caching structured markdown guides in `python/app_context/`.

---

## 3. Vision, Grounding & Computer-Use Automation

* **Hybrid Vision Engine:** Fuses WinRT OCR / Tesseract with OmniParser YOLO icon detection (`model.pt`) and native OS accessibility trees (UIA on Windows, ATSPI on Linux).
* **`@ref` Spatial Indexing:** Assigns stable `@ref` identifiers (e.g. `@e14`) to every interactive screen element with a 2-second IOU and text-similarity cache.
* **Bounded Autopilot Loop:** Executes full UI tasks (up to 5 autonomous attempts per action) supporting clicks, text typing into focused controls, keyboard shortcuts, and directional scrolling (`SendInput` on Windows / `ydotool` on Linux).
* **Web in the Loop (WIL):** Playwright + Chromium/Edge automation backed by local SearXNG search for autonomous web tasks.

---

## 4. Voice & Audio Sync (Sarvam AI)

* **Speech-to-Text (STT):** Real-time multilingual voice command dictation via Sarvam `saaras:v3`.
* **Text-to-Speech (TTS):** Natural Indian-accented voice guidance and audio read-aloud via Sarvam `bulbul:v3`.
* **Synchronized Word Highlighting:** Fades out unspoken text while dynamically highlighting the active word in real time matching the Sarvam TTS audio timeline.
* **Local Wake Word:** Offline, low-latency wake word detection powered by `hey_blinky.onnx`.

---

## 5. Expo Mobile Companion App (`common/mobile`)

* **Dual-Mode Transport & Security:**
  * **Development:** Direct WebSocket connection (`ws://<ip>:9001`) with automatic `/24` subnet scanning.
  * **Release:** Native `BlinkySecureSocket` module with OkHttp TLS SHA-256 certificate public-key pinning and Android KeyStore AES-256 GCM credential encryption.
* **Sentinel Telemetry Dashboard:** Live monitoring of host CPU/RAM usage, battery status, uptime, active OS/compositor, and network MAC addresses.
* **Power Controls & Wake-on-LAN:** Remote triggers for hibernate, sleep, reboot, shutdown, and lock/unlock (with PIN/password support), plus 3-packet UDP magic packet bursts for sleeping hosts.
* **High-Speed File Streaming:** 16MB chunked bidirectional transfers on port `9002` with native streaming SHA-256 hashing.
* **Native LaTeX & Markdown:** Custom renderer converting complex LaTeX formulas into clean Unicode typography without webviews.
* **Gesture Screenshot Canvas:** Multi-touch canvas with focal-anchored double-tap (1x ↔ 2.5x), smooth pinch zoom (1x–5x), and bounded rubber-band panning.
* **Hardware Volume Rocker Hijack:** Intercepts physical phone volume buttons to adjust PC master volume over the socket.
* **Antigravity Human-in-the-Loop Gate:** Mobile approval modal to accept or deny autonomous desktop agent actions.
* **Monetization & Entitlements:** RevenueCat paywall and promo code redemption engine (`lib/purchases.ts`).

---

## 6. Hardware & External Integrations

* **AICut Video Suite:** Local audio-to-video alignment, forced aligner subtitle generation, and video trimming directly accessible from mobile and desktop.
* **ESP32 Ambient Light Daemon (`BlinkyUniversalDaemon`):** Arduino C++ firmware for ESP32 microcontrollers controlling NeoPixel LEDs for system state signaling.
* **WhatsApp Bridge:** Headless WhatsApp Web bot for conversational commands from outside the local network.
