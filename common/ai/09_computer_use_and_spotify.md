# Blinky Computer-Use + Spotify Guide (Humans and AI)

This guide explains the desktop **computer-use path** used by Blinky agent mode, including app launch, shortcut execution, and Spotify playback behavior.

## 1. What This Path Is

Computer-use actions are handled inside `python/main.py` when `agent_mode` is enabled.

```text
Desktop command bar (agent mode)
  -> run_tutor(agent_mode=true)
  -> preflight intent + fallback regex routing
  -> python/computer_use/tools.py
  -> immediate tool result (or fallback to screen tutor path)
```

This path is different from the mobile/WebSocket router path (`python/agent_router.py`), which is browser/web focused.

## 2. Human Quick Guide

Use this mode for direct local actions, for example:

- `Open Spotify`
- `Play blinding lights on Spotify`
- `Press Ctrl+S`
- `Open WhatsApp`

Expected behavior:

1. Blinky classifies the intent.
2. It tries a direct tool (`open_app`, `play_spotify`, or `shortcut`).
3. If the tool succeeds, it returns immediately.
4. If the tool fails, Blinky safely falls back to normal screen guidance.

Current practical limits:

- Desktop computer-use tools are Windows-focused.
- In-app navigation phrases like `open new tab` are intentionally not treated as app-launch commands.
- Spotify playback here targets desktop URI playback (`spotify:track:...`) rather than generic web browsing.

## 3. AI Routing Contract

For AI maintainers/agents, the effective contract is:

- `OPEN_APP` -> `open_app_tool(app_name)`
- `MEDIA_PLAYBACK` -> `play_spotify_track_tool(song_name)`
- `SYSTEM_SHORTCUT` -> `shortcut_tool(shortcut)`
- otherwise -> screen-context tutor flow (`DESKTOP_AUTOMATION`)

Safety/quality guards:

- If preflight emits `OPEN_APP` with an in-app action (`open settings`, `open new tab`, etc.), `python/main.py` overrides back to screen mode.
- `python/computer_use/agent.py` provides regex fallback routing when preflight extraction is missing or ambiguous.
- Any direct tool failure returns control to the screen-tutor path instead of forcing risky behavior.

## 4. Spotify Behavior (Desktop Agent Mode)

`play_spotify_track_tool(song_name)` does the following:

1. Normalizes the song query.
2. Tries SearXNG search for `open.spotify.com/track/...` links.
3. Falls back to DuckDuckGo HTML parsing if needed.
4. Converts the first match to `spotify:track:<id>`.
5. Opens it via `os.startfile(...)`.

Related behavior:

- `open_app_tool("spotify")` can open Spotify itself via app protocol (`spotify:`).
- If no track can be resolved, the tool returns a clear failure message and does not guess.

## 5. Files to Read for Changes

- `python/main.py`
- `python/computer_use/agent.py`
- `python/computer_use/tools.py`
- `python/tests/test_computer_use_tools.py`
- `python/tests/test_spotify_tool.py`
- `ai/07_agent_router.md` (boundary with router flow)
- `ai/08_mobile_remote.md` (mobile routing boundary)
