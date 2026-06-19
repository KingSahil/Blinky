# Blinky Remote Mobile Client

This directory contains the React Native Expo mobile application that connects to the Blinky desktop client over local Wi-Fi. It can send power actions and remote browser-agent queries to the desktop WebSocket server.

## Prerequisites

1. **Expo Go App**: Install the **Expo Go** application on your physical device via the Google Play Store (Android) or Apple App Store (iOS).
   * *Note: This project is configured to run on **Expo SDK 54**.*

## Setup and Installation

1. Open your terminal and navigate to the `mobile` directory:
   ```bash
   cd mobile
   ```

2. Install the package dependencies using `npm` (ensuring legacy peer dependencies are handled correctly):
   ```bash
   npm install --legacy-peer-deps
   ```

## Running the Application

1. Ensure your computer and mobile device are connected to the **same local Wi-Fi network**.
2. Run the following command inside the `mobile` directory to spin up the Expo development server:
   ```bash
   npm start
   ```
3. A QR code will display in your terminal:
   * **Android**: Open the **Expo Go** app and scan the terminal's QR code.
   * **iOS**: Scan the QR code using your phone's default Camera app, which will prompt you to open the link inside Expo Go.

## Connecting to Blinky

1. Make sure Blinky is running on your desktop PC (`bun run dev`).
2. Obtain your computer's local IP address.
   * **Linux**: Run `ip route get 1.1.1.1 | awk '{print $7}'` in terminal.
   * **Windows**: Run `ipconfig` in Command Prompt and check your IPv4 address under your wireless adapter.
3. In the mobile application screen, input your PC's IP address (e.g., `192.168.1.15`).
4. Tap **Establish Link** to connect.
5. Use the control buttons on your phone to trigger actions on your PC, or send an agent query from the mobile UI.

## What Mobile Can Control

- Power actions: Sleep, Restart, Shut Down.
- Remote AI/browser queries through `ws://<pc>:9001`.
- Streamed status and final agent responses.

The mobile app does not render the desktop overlay and does not run the command bar autopilot loop. Screen reading, highlighting, and safe desktop clicks are desktop command-bar features.
