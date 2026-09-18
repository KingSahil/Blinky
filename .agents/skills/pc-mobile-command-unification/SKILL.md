---
name: pc-mobile-command-unification
description: Rules and execution pipeline ensuring mobile commands use the exact same logic, coordinate systems, and actuation as the PC desktop Blinky application. Mobile is purely a remote input transmitter for PC Blinky.
---

# PC & Mobile Command Unification Skill

## Core Principle
**The mobile app is strictly an input transmitter for PC Blinky.**
Whenever a user speaks or types a command from mobile (e.g. "click Instagram", "where is search", "open Spotify"):
1. The command must be executed using the **exact same PC Blinky pipeline** as if the user typed it into the PC CommandBar.
2. Never create divergent or headless actuators for mobile.
3. Coordinates must always be centered on the target element and mapped into physical display pixel space (`getPhysicalClickablePoint`).

## Pipeline Architecture

### 1. Ingestion
- Mobile client sends `{ "requestId": string, "query": string }` over WebSocket to the desktop port (9001).
- Tauri receives the frame and emits `blinky://mobile-query` directly to the desktop frontend (`CommandBar.tsx`).

### 2. Execution via PC Tutor (`CommandBar.tsx`)
- `CommandBar.tsx` runs `executeTutor(cleanQuery, false, { resetProgress: true })`.
- PC runs `runTutor`:
  - UI Automation (UIA) tree scanning for controls.
  - Element refs (`ref_0`, `ref_1`, ...).
  - OmniParser / WinRT OCR for visual elements.
  - Matches the requested target.
- For click instructions (`isClickInstruction`):
  - `runAutopilotLoop` runs.
  - `getPhysicalClickablePoint` calculates centered, DPI-scaled physical display coordinates:
    `x = Math.round((match.x + match.width / 2) * (screen_width / screenshot_width))`
    `y = Math.round((match.y + match.height / 2) * (screen_height / screenshot_height))`
  - Overlay glides the visual AI companion cursor to `(x, y)` (`blinky://agent-cursor-move`).
  - Actuates native platform click (`clickElement`).
  - Emits `blinky://agent-cursor-done`.

### 3. Overlay Coordinate Integrity (`Overlay.tsx`)
- When `blinky://agent-cursor-move` receives explicit coordinates `{ x, y }`, it **must never** be overridden by old highlight frames (`framesRef.current`).
- Highlight frame snapping is strictly a fallback when explicit coordinates are absent.

### 4. Status Reporting
- Progress and completion events emit `blinky://mobile-status` which are forwarded back across the WebSocket connection to the mobile client, ensuring mobile displays the exact same feedback as PC.
