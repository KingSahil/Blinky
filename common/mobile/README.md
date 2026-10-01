# Blinky Remote Mobile Client

This directory contains the React Native Expo mobile application that connects to the Blinky desktop client over local Wi-Fi. It can send remote commands and transfer files to the PC.

## Prerequisites

1. Install a **custom Blinky development or release build** on the device. The app uses Expo SDK 57 and project-local native modules for secure connections and file transfer. Expo Go cannot run the complete app.

## Setup and Installation

1. Open your terminal and navigate to the mobile directory from the repository root:
   ```bash
   cd common/mobile
   ```

2. Install the locked dependencies:
   ```bash
   bun install --frozen-lockfile
   ```

3. Build and install a new native app whenever Expo SDK, a native package (such as `expo-image-picker`), or native app configuration changes. For an internal Android APK, run:
   ```bash
   bunx eas-cli init
   bun run build:release --platform android
   ```
   Run `init` once to link the existing EAS project, or set one up if this is the first build. Install the APK produced by EAS on the phone. The build profiles are defined in [eas.json](eas.json).

## Running the Application

1. Ensure your computer and mobile device are connected to the **same local Wi-Fi network**.
2. For a custom development build, run the following command inside `common/mobile` to start Metro:
   ```bash
   bun run start:clear
   ```
3. Open the Metro link in the installed Blinky development build. A release APK uses its bundled JavaScript and does not need Metro.

If the app shows `Cannot find native module 'ExponentImagePicker'`, the JavaScript is running in an older build or Expo Go without that native module. Install a new custom build made from this checkout, then reopen the app. Clearing Metro's cache alone does not add native modules to an installed app.

## Connecting to Blinky

Release builds open the link setup on the **QR** tab by default; debug builds
show the manual form directly.

**Option A — QR (release builds only, fastest, recommended)**

1. Make sure Blinky is running on your desktop PC (`bun run dev`).
2. In the PC app, click the **QR icon** in the Blinky header to show the pairing code.
3. In the mobile app's **QR** tab, point the camera at the code — you connect instantly, no typing.

**Option B — Manual**

1. Make sure Blinky is running on your desktop PC (`bun run dev`).
2. Obtain your computer's local IP address.
   * **Linux**: Run `ip route get 1.1.1.1 | awk '{print $7}'` in terminal.
   * **Windows**: Run `ipconfig` in Command Prompt and check your IPv4 address under your wireless adapter.
3. Switch to the **Manual** tab, input your PC's IP address (e.g., `192.168.1.15`).
   Release builds also need the remote token and certificate pin (shown in the PC app).
4. Tap **Establish Link** to connect.
5. Use the control buttons on your phone to trigger actions on your PC, or send an agent query from the mobile UI.

## What Mobile Can Control

- Power actions: Sleep, Restart, Shut Down.
- Remote AI/browser queries over the desktop WebSocket connection on port 9001 (WS in development, WSS in release).
- Streamed status and final agent responses.
- Transfer multiple files to a selected PC folder and optionally request AiCut edits for video or audio files.

The mobile app does not render the desktop overlay and does not run the command bar autopilot loop. Screen reading, highlighting, and safe desktop clicks are desktop command-bar features.
