# Blinky Expo Mobile Remote

The mobile app in `mobile/` is an Expo React Native controller for a running Blinky desktop instance.

## 1. Purpose

The app connects to the desktop WebSocket server and offers:

- local link setup by PC IP/hostname
- remote AI browser-assistant queries (router/web path)
- streamed progress and final results
- power operations: sleep, restart, shutdown

It does not call `run_tutor` directly, does not render desktop overlay highlights, and does not run the desktop command-bar autopilot loop. Its query path goes through `src-tauri/src/websocket.rs` and `python/agent_router.py`.

## 2. Main Files

| File | Role |
| :--- | :--- |
| `mobile/App.tsx` | Main UI, connection form, query card, power controls, response rendering. |
| `mobile/usePCWebSocket.ts` | WebSocket lifecycle hook and message send helpers. |
| `mobile/package.json` | Expo 54 / React Native 0.81 app dependencies and scripts. |
| `mobile/AGENTS.md` | Requires checking exact Expo versioned docs before code edits. |

## 3. Connection Flow

`usePCWebSocket.connect(ipAddress)`:

1. Closes any existing socket.
2. Trims the host value.
3. Appends `:9001` when no port is supplied.
4. Opens `ws://<host>:9001`.
5. Updates status as `connecting`, `connected`, `disconnected`, or `error`.
6. Parses incoming JSON and exposes the latest response to `App.tsx`.

The host string is saved in AsyncStorage under `@blinky_pc_ip`.

## 4. Query Flow

`App.tsx` sends:

```json
{
  "requestId": "generated-uuid",
  "query": "user text"
}
```

Incoming responses update:

- `agentStatus`
- `agentProgressMsg`
- `agentResult`
- `agentError`
- optional `confidence`
- optional `reasoning`

When `data.is_chunk` is true, chunks are appended to `agentProgressMsg` for streamed synthesis.

Mobile browser-agent queries can open/search through the router's safe browser planner or use registered/generated tools, but the phone is not the screen-observe/click actor. Bounded safe clicks are handled only by the desktop command bar, where the app can observe the screen and call `click_screen_point`.

Computer-use note: this mobile query path does not invoke `python/computer_use/*` tools directly. Requests are handled by `python/agent_router.py` first.

## 5. Power Commands

The app sends raw strings:

```text
sleep
restart
power_off
```

`App.tsx` shows a destructive confirmation alert before sending each command. Rust executes the OS command:

- Windows: `shutdown`, `rundll32.exe powrprof.dll,SetSuspendState`
- non-Windows: `systemctl poweroff`, `systemctl reboot`, `systemctl suspend`

## 6. Development Commands

```powershell
cd mobile
npm install
npm run start
npm run android
npm run ios
npm run web
```

Before editing mobile code, follow `mobile/AGENTS.md`: check the Expo docs for the exact project version.

## 7. Computer-Use and Spotify Boundary

- Mobile remote query messages go to `python/agent_router.py` (browser/web intelligence path).
- Desktop agent-mode actions such as local app launch, shortcut keypress, and URI-based Spotify track playback are implemented in `python/main.py` + `python/computer_use/`.
- If you need deterministic desktop Spotify playback (`play ... on Spotify` via `spotify:track:...`), prefer desktop command-bar agent mode rather than mobile remote routing.
