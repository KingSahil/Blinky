# Browser and desktop refs in Blinky

## Routing priority

Existing dedicated tools run first: Spotify playback and media controls,
YouTube search/playback, SearXNG research, app/folder launchers, supported
Notepad/Store workflows, spreadsheets, and explicit physical-light commands.
`open Spotify and play ...` is normalized to the existing Spotify playback
tool. `search ... on YouTube` opens YouTube results through the fast browser
handler. Vercel's browser/desktop engines handle UI work those tools do not
cover, such as navigating an unfamiliar application's menus.

Guidance questions (`how do I ...`, `what is ...`) are informational and do
not execute tools. Software appearance terms such as light mode, dark mode,
theme and colour scheme are excluded from ESP32 matching unless an explicit
physical device is targeted. A model classification alone cannot authorize
the hardware route without the physical-command matcher confirming it.

Desktop follow-ups reuse the last valid app/window target when the command
bar has focus. Menu/dialog surfaces returned by an action are observed next.
Snapshots expose native action capabilities, so the planner can distinguish
scroll containers from ordinary controls. Safe, explicitly undelivered
failures may trigger a fresh observation/replan twice; uncertain delivery
stops. Error messages include the native failure reason.

Blinky uses `agent-browser` 0.41.0 for browser tasks and `agent-desktop` 1.0.2
for desktop UI actions. These CLIs are actuators: Blinky's selected text model
still plans each action. Agent S has been removed.

Windows app display names are resolved before launch through App Paths,
standard executable locations, PATH, and `Get-StartApps` registrations.
This supports desktop executables and packaged apps without passing display
names such as "VLC media player" to a CLI that expects an executable.
After launch, Blinky observes the matching app window for up to 15 seconds;
it does not repeat the launch or act on an unrelated foreground window.
Named web destinations such as YouTube use the browser backend.

Run `powershell -File scripts/setup-vercel-agents.ps1` once. Binaries are pinned
and installed under `data/agent-tools`, independently of the root project's
Linux-only npm dependency. No separate Chrome download is required to attach.
Restart the Blinky backend after installation or configuration changes.

## Existing signed-in browser

The default `BLINKY_BROWSER_ENGINE=agent-browser` always uses `--auto-connect`
or an explicit `BLINKY_BROWSER_CDP_URL`. It never launches a fresh profile.
For current Chrome versions, open `chrome://inspect/#remote-debugging`, enable
remote debugging, and approve the browser's connection prompt. This lets Blinky
use that running profile's tabs and signed-in sessions. Browser support depends
on the installed version; other Chromium browsers need a working CDP endpoint.
For Edge, set e.g. `BLINKY_BROWSER_CDP_URL=http://127.0.0.1:9222` only when that
browser actually exposes that port. Blinky does not restart browsers, copy
profiles, or export cookies to establish access.

Examples: `open https://example.com and read the heading`, or
`use browser agent to read the current tab`. Browser element actions use the
latest `@eN` refs. Navigation stays in the attached browser. A task may navigate
its selected tab; do not assume it always creates a separate tab.

## Desktop

The default `BLINKY_DESKTOP_ENGINE=agent-desktop` routes clicks, selection,
typing, key presses and scrolling through accessibility. Use
`agent-desktop status` for a read-only health check. PC and mobile share this
route. Existing specialized tools (Excel, WhatsApp, media, hardware) retain
their dedicated paths. `legacy` explicitly selects the older desktop route.

Each step observes a tree, chooses one validated action, executes, and observes
again. Desktop refs are snapshot-qualified (`@snapshot:eN`). The planner can
observe a window from `list-windows`; ref operations then target its tree.
Keyboard actions require an observed window ID. Supported actions are click,
fill/set-value, ref-based typing, select, check/uncheck, scroll, press and launch
by bare application name. Windows Store and File Explorer launch through native
Windows shell activation, then use agent-desktop refs. Minimized target windows
are restored before observation. Each task uses its own desktop ref namespace
and retains the selected window ID across steps. Raw coordinates, generated
scripts, arbitrary CLI commands, model-supplied app arguments and destructive
window-management operations are excluded from this adapter. Apps that do not
expose usable accessibility controls can block a task; there is no automatic
visual fallback. Completion is model-assessed from the latest observation,
not an independent guarantee of application-level persistence.

One OS file lock serializes these tasks across PC/mobile Python processes.
Uncertain delivery stops execution; mutations are never blindly replayed.
Stale-ref errors may trigger fresh observation and replanning only when native
delivery evidence explicitly says nothing was delivered and retrying is safe.
A bounded step limit returns failure when no
completion is observed. Frontend `steps` stays empty so autopilot cannot replay
already executed actions.

## Debug artifacts

Every task writes to `screenshots_parsed/agent-browser/<timestamp>-<id>/` or
`screenshots_parsed/agent-desktop/<timestamp>-<id>/`:

- `task.json`: requested task and backend.
- `NNN-snapshot.json`: raw accessibility snapshot, including refs.
- `NNN-windows.json`: desktop window list.
- `NNN.png` and `NNN-screenshot.json`: screenshot and capture metadata; browser screenshots label element refs.
- `NNN.html`: native desktop debug visualization with refs and element bounds.
- `NNN-decision.json`: the planner's chosen action or final answer.
- `NNN-result.json`: command result, including desktop delivery dispositions.
- `error.txt` or `NNN-screenshot-error.txt`: failure details.

The response includes `debug_dir`. Screenshot failures do not prevent semantic
actions. These local files can contain signed-in page text and desktop content;
the existing ignored `screenshots_parsed` directory keeps them out of Git.
Snapshots go to the selected Blinky model; screenshot files are for local debug
and are not sent by this adapter. Delete old run directories when no longer needed.
The planner receives a compact view of named visible controls/text and scroll
containers; raw snapshots retain the full tree. Provider latency and token
limits still affect planning speed.

## Live Windows verification

The live test typed `Blinky agent-desktop refs are working.` into a new Notepad
tab, observed the text, then cleared and closed only that test tab. Existing
Notepad tabs were preserved. It filled the Store search box, invoked the Search
button by ref, and visually confirmed the Minecraft results grid. It opened
Explorer at `C:\Projects`, invoked the `Blinky` folder ref, and confirmed the
breadcrumb `This PC > OS (C:) > Projects > Blinky`. Evidence is local under
`screenshots_parsed/agent-desktop/live-sequence` and `notepad-close-check`.
These were guided integration checks with native app activation, not proof
that the entire sequence completes unattended: planning hit provider rate
limits and Windows refused some foreground/physical-input attempts. Semantic
ref actions completed the UI steps. Existing-profile browser attachment was
attempted but timed out, so signed-in browser execution remains unverified.

For explicit compatibility testing, `BLINKY_BROWSER_ENGINE=browser_use` selects
the old Python browser-use library. Its launch behavior differs from the new
attach-only backend.

Upstream: https://agent-browser.dev/cdp-mode and
https://github.com/vercel-labs/agent-desktop.
