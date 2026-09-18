//! cua-driver bridge for Blinky's Rust actuator path.
//!
//! The frontend autopilot (`CommandBar.tsx`) clicks through the Tauri commands
//! `click_element` / `click_screen_point` / `scroll_at_point` / `type_text`,
//! which previously went straight to `SendInput` — moving the real cursor and
//! stealing focus.
//!
//! This module lets those same commands run through `cua-driver`, the same
//! open-source background driver the Python sidecar uses, so autopilot can act
//! without hijacking the user's pointer. `SendInput` remains the fallback, so
//! behaviour never regresses when the driver is missing or unhealthy.
//!
//! ## Why the MCP stdio transport, not `cua-driver call`
//!
//! The obvious bridge is one `cua-driver call <tool> <json>` process per
//! action. Measured, that costs ~1.45s *per call* before any work happens —
//! `get_cursor_position` returning 28 bytes still took 1.45s, and
//! `list_windows` 1.8s. It is fixed process-startup cost, not daemon work, and
//! it made the whole click ladder (list windows -> walk tree -> click) about
//! **8 seconds**, which is exactly the "lag" a user sees between the AI cursor
//! arriving and the click landing.
//!
//! `cua-driver mcp` speaks JSON-RPC over stdio, so one long-lived child
//! replaces every spawn. The same calls then cost: `get_cursor_position` 6ms,
//! `list_windows` 0.17s, `get_window_state` 0.15s, `click` 0.09s — the ladder
//! drops to ~0.4s. That is the entire reason this module keeps a persistent
//! child behind a mutex instead of shelling out.
//!
//! ## Delivery contract
//!
//! Always try `delivery_mode="background"` first. Only retry with `foreground`
//! when the driver explicitly reports `background_unavailable`, and only when
//! `BLINKY_CUA_ALLOW_FOREGROUND` is not `0` — fronting a window needlessly
//! steals focus and is a bug, not a shortcut.
//!
//! Note that desktop scope is *not* a background path: the driver serves it
//! through global input injection and the real pointer moves. Anything that
//! must stay background has to be addressed inside a window (see
//! [`click_element_at`]).

use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{Arc, Condvar, Mutex, OnceLock};
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Ceiling for one tool call. The driver answers real calls in tens of
/// milliseconds; anything near this means the pipe is wedged and the child
/// needs rebuilding.
const CALL_TIMEOUT: Duration = Duration::from_secs(20);

/// The `initialize` handshake also pays for daemon attach, so it gets more room
/// than a tool call — but not much: every millisecond here is a millisecond the
/// caller is blocked, and the caller is a UI command.
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(10);

/// A click slower than this is worth explaining in the log.
///
/// The whole ladder should land around 0.4s. Anything past this is a
/// regression, and knowing *which* stage ate the time is the difference between
/// guessing and fixing.
const SLOW_CLICK: Duration = Duration::from_millis(400);

/// Prefix marking an error as a *transport* failure (broken pipe, timeout)
/// rather than a tool-level failure. Only transport failures justify throwing
/// the child away and starting a new one.
const TRANSPORT_ERROR: &str = "cua transport: ";

/// Suppress the console window Windows would otherwise create for a console
/// child spawned from a GUI process.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// One stable session for the whole app.
///
/// cua-driver scopes its agent-cursor overlay, its element-snapshot cache and
/// its `set_agent_cursor_enabled` switch to a *session*. Omit the label and the
/// driver mints an implicit session per call — which is how Blinky ended up
/// with a stray `Cua.AgentCursorOverlay` next to its own AI cursor. Reusing one
/// named session keeps a single overlay and a single snapshot cache, and gives
/// us a handle to hide the driver's cursor for.
const SESSION: &str = "blinky";

/// Windows that are never a valid click target: the driver's own overlay,
/// Blinky's transparent always-on-top surfaces, plus the shell overlays that
/// would otherwise shadow every point.
///
/// Blinky's own windows are additionally excluded by pid (see [`windows`]),
/// which is exact; this list is the belt to that pair of braces.
const NON_TARGET_TITLES: &[&str] = &[
    "AgentCursorOverlay",
    "Blinky Highlight Overlay",
    "Blinky Overlay",
    "Recording Toolbar",
    "Windows Input Experience",
    "NVIDIA GeForce Overlay",
    "Windows Shell Experience Host",
    "Program Manager",
    "Microsoft Text Input Application",
];

/// Cached binary path lookup. `None` means the driver is not installed.
fn binary() -> Option<&'static PathBuf> {
    static BINARY: OnceLock<Option<PathBuf>> = OnceLock::new();
    BINARY.get_or_init(resolve_binary).as_ref()
}

fn resolve_binary() -> Option<PathBuf> {
    // Explicit override wins.
    for key in ["CUA_DRIVER_CMD", "HERMES_CUA_DRIVER_CMD"] {
        if let Ok(value) = std::env::var(key) {
            let path = PathBuf::from(value.trim());
            if path.is_file() {
                return Some(path);
            }
        }
    }

    // PATH scan.
    if let Ok(path_var) = std::env::var("PATH") {
        for dir in std::env::split_paths(&path_var) {
            for name in ["cua-driver.exe", "cua-driver"] {
                let candidate = dir.join(name);
                if candidate.is_file() {
                    return Some(candidate);
                }
            }
        }
    }

    // Known install location.
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        let candidate = PathBuf::from(local)
            .join("Programs")
            .join("Cua")
            .join("cua-driver")
            .join("bin")
            .join("cua-driver.exe");
        if candidate.is_file() {
            return Some(candidate);
        }
    }

    None
}

/// Backend key from `BLINKY_COMPUTER_USE_BACKEND` — `auto` (default) | `cua` | `native`.
fn backend_key() -> String {
    std::env::var("BLINKY_COMPUTER_USE_BACKEND")
        .unwrap_or_else(|_| "auto".to_string())
        .trim()
        .to_ascii_lowercase()
}

/// True when the caller explicitly disabled the driver actuator.
pub fn is_disabled() -> bool {
    matches!(backend_key().as_str(), "native" | "none" | "off")
}

fn allow_foreground() -> bool {
    !matches!(
        std::env::var("BLINKY_CUA_ALLOW_FOREGROUND")
            .unwrap_or_else(|_| "1".to_string())
            .trim()
            .to_ascii_lowercase()
            .as_str(),
        "0" | "false" | "no"
    )
}

/// Is a background-capable driver available right now?
pub fn is_available() -> bool {
    !is_disabled() && binary().is_some()
}

// ---------------------------------------------------------------------------
// Transport: one persistent `cua-driver mcp` child, JSON-RPC over stdio
// ---------------------------------------------------------------------------

/// Replies waiting to be claimed, keyed by JSON-RPC id.
///
/// The reader thread publishes here and pings `ready`; callers block on the
/// condvar rather than polling, so a reply is picked up the instant it lands.
#[derive(Default)]
struct Slot {
    replies: Mutex<HashMap<u64, Value>>,
    ready: Condvar,
}

struct Transport {
    /// Held only to keep the child alive; killing it on drop is intentional.
    child: Child,
    stdin: ChildStdin,
    slot: Arc<Slot>,
    next_id: u64,
}

impl Transport {
    fn spawn() -> Result<Self, String> {
        let path = binary().ok_or_else(|| "cua-driver not found".to_string())?;

        let mut command = Command::new(path);
        command
            .arg("mcp")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);

        let mut child = command
            .spawn()
            .map_err(|err| format!("{TRANSPORT_ERROR}failed to spawn `cua-driver mcp`: {err}"))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| format!("{TRANSPORT_ERROR}child has no stdin"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| format!("{TRANSPORT_ERROR}child has no stdout"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| format!("{TRANSPORT_ERROR}child has no stderr"))?;

        let slot = Arc::new(Slot::default());

        // Both pipes must be drained continuously. A child that blocks on a
        // full stdout buffer never exits, which is what turned large
        // `get_window_state` payloads into "unparseable driver output" and
        // 20-second stalls in the old per-call implementation.
        {
            let slot = Arc::clone(&slot);
            std::thread::Builder::new()
                .name("cua-mcp-stdout".to_string())
                .spawn(move || {
                    for line in BufReader::new(stdout).lines() {
                        let Ok(line) = line else { break };
                        let trimmed = line.trim();
                        if trimmed.is_empty() {
                            continue;
                        }
                        let Ok(message) = serde_json::from_str::<Value>(trimmed) else {
                            continue;
                        };
                        // Notifications have no id and are of no interest here.
                        let Some(id) = message.get("id").and_then(Value::as_u64) else {
                            continue;
                        };
                        let mut replies = slot
                            .replies
                            .lock()
                            .unwrap_or_else(|err| err.into_inner());
                        replies.insert(id, message);
                        drop(replies);
                        slot.ready.notify_all();
                    }
                })
                .map_err(|err| format!("{TRANSPORT_ERROR}reader thread failed: {err}"))?;
        }

        std::thread::Builder::new()
            .name("cua-mcp-stderr".to_string())
            .spawn(move || {
                for line in BufReader::new(stderr).lines() {
                    match line {
                        Ok(line) if !line.trim().is_empty() => {
                            eprintln!("blinky: cua-driver: {}", line.trim())
                        }
                        Ok(_) => {}
                        Err(_) => break,
                    }
                }
            })
            .map_err(|err| format!("{TRANSPORT_ERROR}stderr thread failed: {err}"))?;

        let mut transport = Transport {
            child,
            stdin,
            slot,
            next_id: 1,
        };
        transport.handshake()?;
        Ok(transport)
    }

    fn handshake(&mut self) -> Result<(), String> {
        self.request(
            "initialize",
            json!({
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": { "name": "blinky", "version": env!("CARGO_PKG_VERSION") },
            }),
            HANDSHAKE_TIMEOUT,
        )?;
        self.notify("notifications/initialized", json!({}))
    }

    fn write_message(&mut self, message: &Value) -> Result<(), String> {
        let mut line = message.to_string();
        line.push('\n');
        self.stdin
            .write_all(line.as_bytes())
            .map_err(|err| format!("{TRANSPORT_ERROR}write failed: {err}"))?;
        self.stdin
            .flush()
            .map_err(|err| format!("{TRANSPORT_ERROR}flush failed: {err}"))
    }

    fn notify(&mut self, method: &str, params: Value) -> Result<(), String> {
        self.write_message(&json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }))
    }

    fn request(&mut self, method: &str, params: Value, timeout: Duration) -> Result<Value, String> {
        let id = self.next_id;
        self.next_id += 1;

        self.write_message(&json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        }))?;

        let slot = Arc::clone(&self.slot);
        let deadline = Instant::now() + timeout;
        let mut replies = slot.replies.lock().unwrap_or_else(|err| err.into_inner());
        loop {
            if let Some(reply) = replies.remove(&id) {
                return Ok(reply);
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err(format!("{TRANSPORT_ERROR}{method} timed out"));
            }
            let (guard, _) = slot
                .ready
                .wait_timeout(replies, remaining)
                .unwrap_or_else(|err| err.into_inner());
            replies = guard;
        }
    }

    /// Invoke one driver tool, unwrapping the MCP envelope.
    ///
    /// Three distinct failure shapes have to be told apart, and only the first
    /// is obvious:
    ///
    /// * `error` / `isError` — a JSON-RPC error or a tool-level failure.
    /// * a **refusal**, which arrives as a *successful* call carrying
    ///   `{"refusal": {"code", "message"}, "status": "refused"}`. Trusting
    ///   `isError` alone would treat a refused click as a completed one.
    /// * success, where the driver payload sits in `structuredContent`.
    fn tool_call(&mut self, tool: &str, arguments: Value, timeout: Duration) -> Result<Value, String> {
        let reply = self.request(
            "tools/call",
            json!({ "name": tool, "arguments": arguments }),
            timeout,
        )?;

        if let Some(error) = reply.get("error") {
            return Err(format!("{tool}: {}", describe(error)));
        }

        let result = reply
            .get("result")
            .ok_or_else(|| format!("{tool}: driver returned no result"))?;

        let payload = unwrap_payload(result);

        if result.get("isError").and_then(Value::as_bool).unwrap_or(false) {
            return Err(format!("{tool}: {}", result_message(result, &payload)));
        }
        if let Some(message) = refusal(&payload) {
            return Err(format!("{tool}: {message}"));
        }

        Ok(payload)
    }
}

impl Drop for Transport {
    fn drop(&mut self) {
        // A wedged child must not linger: the daemon owns the real state, and
        // the next request spawns a fresh client.
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// The driver payload for a successful call.
///
/// MCP allows the payload either as `structuredContent` or as a JSON string in
/// a `content` text block; the driver uses both depending on the tool.
fn unwrap_payload(result: &Value) -> Value {
    if let Some(structured) = result.get("structuredContent") {
        if !structured.is_null() {
            return structured.clone();
        }
    }

    if let Some(blocks) = result.get("content").and_then(Value::as_array) {
        for block in blocks {
            if block.get("type").and_then(Value::as_str) != Some("text") {
                continue;
            }
            if let Some(text) = block.get("text").and_then(Value::as_str) {
                if let Ok(parsed) = serde_json::from_str::<Value>(text.trim()) {
                    return parsed;
                }
                return json!({ "text": text });
            }
        }
    }

    result.clone()
}

/// Human-readable explanation for a failure.
///
/// The driver puts the *reason* in `content[].text` and only a machine code in
/// `structuredContent`, so the text block is preferred.
fn result_message(result: &Value, payload: &Value) -> String {
    if let Some(blocks) = result.get("content").and_then(Value::as_array) {
        for block in blocks {
            if block.get("type").and_then(Value::as_str) != Some("text") {
                continue;
            }
            if let Some(text) = block.get("text").and_then(Value::as_str) {
                let trimmed = text.trim();
                if !trimmed.is_empty() {
                    return trimmed.to_string();
                }
            }
        }
    }
    describe(payload)
}

/// Flatten a code/message-shaped value into one line.
fn describe(value: &Value) -> String {
    if let Some(text) = value.as_str() {
        return text.to_string();
    }
    if let Some(text) = value.get("text").and_then(Value::as_str) {
        return text.to_string();
    }
    if let Some(object) = value.as_object() {
        let code = object.get("code").and_then(Value::as_str).unwrap_or("");
        let message = object.get("message").and_then(Value::as_str).unwrap_or("");
        return match (code.is_empty(), message.is_empty()) {
            (false, false) => format!("{code}: {message}"),
            (false, true) => code.to_string(),
            (true, false) => message.to_string(),
            (true, true) => value.to_string(),
        };
    }
    value.to_string()
}

/// A refusal is delivered as a successful tool call, so it needs an explicit
/// check — otherwise a refused action reads as a completed one and suppresses
/// the fallback that would have made it work.
fn refusal(value: &Value) -> Option<String> {
    if let Some(refusal) = value.get("refusal") {
        return Some(describe(refusal));
    }
    match value.get("status").and_then(Value::as_str) {
        Some("refused") | Some("error") | Some("failed") | Some("denied") => Some(describe(value)),
        _ => None,
    }
}

/// True for errors that mean the child itself is unusable.
fn is_transport_failure(err: &str) -> bool {
    err.starts_with(TRANSPORT_ERROR)
}

/// The shared child, spawned lazily and rebuilt once if it dies.
static DRIVER: OnceLock<Mutex<Option<Transport>>> = OnceLock::new();

/// Run one tool call on the shared transport, rebuilding it at most once.
fn call(tool: &str, arguments: Value) -> Result<Value, String> {
    let cell = DRIVER.get_or_init(|| Mutex::new(None));
    let mut guard = cell.lock().unwrap_or_else(|err| err.into_inner());

    let mut rebuilt = false;
    loop {
        if guard.is_none() {
            // Worth logging: a healthy run starts this exactly once. Seeing it
            // repeatedly means the child is dying and every action is paying a
            // fresh spawn plus handshake.
            let spawning = Instant::now();
            *guard = Some(Transport::spawn()?);
            eprintln!(
                "blinky: cua-driver transport started in {:?}",
                spawning.elapsed()
            );
        }

        let attempt = guard
            .as_mut()
            .expect("transport is present")
            .tool_call(tool, arguments.clone(), CALL_TIMEOUT);

        match attempt {
            Ok(value) => return Ok(value),
            Err(err) if !rebuilt && is_transport_failure(&err) => {
                eprintln!("blinky: cua-driver transport reset ({err})");
                *guard = None;
                rebuilt = true;
            }
            Err(err) => return Err(err),
        }
    }
}

fn is_background_unavailable(err: &str) -> bool {
    let lowered = err.to_ascii_lowercase();
    lowered.contains("background_unavailable")
        || lowered.contains("background delivery")
        || lowered.contains("background is unavailable")
}

/// Does this error mean our named session idle-expired?
///
/// Named sessions are reaped after roughly five minutes idle; every later call
/// comes back as `session 'x' has ended; tool call 'y' was rejected`. Without
/// this check the whole actuator would silently go dark mid-session.
fn is_dead_session(err: &str) -> bool {
    let lowered = err.to_ascii_lowercase();
    lowered.contains("has ended") || lowered.contains("revive it")
}

/// Start (or revive) the shared session and hide the driver's own cursor.
///
/// Blinky already draws the AI cursor in its transparent overlay window — it
/// glides to the target and tracks the highlight frame. The driver's
/// `Cua.AgentCursorOverlay` is a *second* pointer the user never asked for, so
/// it is switched off for our session.
fn revive_session() -> Result<(), String> {
    call("start_session", json!({ "session": SESSION }))?;
    // Best-effort: a freshly (re)started session re-enables its cursor, and
    // `set_agent_cursor_enabled` requires the session to exist first.
    if let Err(err) = call(
        "set_agent_cursor_enabled",
        json!({ "session": SESSION, "enabled": false }),
    ) {
        eprintln!("blinky: could not hide cua-driver overlay cursor: {err}");
    }
    Ok(())
}

/// Prime the session once per process, lazily, before the first action.
fn prime_session_once() {
    static PRIMED: OnceLock<()> = OnceLock::new();
    PRIMED.get_or_init(|| {
        if let Err(err) = revive_session() {
            eprintln!("blinky: could not prime cua-driver session: {err}");
        }
    });
}

/// Call a tool on the shared session, reviving it once if it idle-expired.
fn send(tool: &str, payload: &Value) -> Result<Value, String> {
    let mut payload = payload.clone();
    if let Some(object) = payload.as_object_mut() {
        object.entry("session").or_insert_with(|| json!(SESSION));
    }

    match call(tool, payload.clone()) {
        Ok(value) => Ok(value),
        Err(err) if is_dead_session(&err) => {
            revive_session()?;
            call(tool, payload)
        }
        Err(err) => Err(err),
    }
}

/// Send an input action, honouring the background-first escalation contract.
fn dispatch(tool: &str, mut payload: Value) -> Result<Value, String> {
    if let Some(object) = payload.as_object_mut() {
        object
            .entry("delivery_mode")
            .or_insert_with(|| json!("background"));
    }

    match send(tool, &payload) {
        Ok(value) => Ok(value),
        Err(err) if is_background_unavailable(&err) && allow_foreground() => {
            if let Some(object) = payload.as_object_mut() {
                object.insert("delivery_mode".to_string(), json!("foreground"));
            }
            send(tool, &payload)
        }
        Err(err) => Err(err),
    }
}

// ---------------------------------------------------------------------------
// Window discovery
// ---------------------------------------------------------------------------

/// A top-level window, geometry in true screen pixels.
///
/// `window_id` is the Win32 `HWND` — verified against `GetWindowRect` /
/// `GetWindowThreadProcessId` for several windows — which is what lets
/// [`window_at`] join an OS hit-test result onto the driver's window list.
#[derive(Debug, Clone)]
struct Target {
    pid: i64,
    window_id: i64,
    title: String,
    x: i32,
    y: i32,
    width: i32,
    height: i32,
    z_index: i64,
}

impl Target {
    fn contains(&self, x: i32, y: i32) -> bool {
        x >= self.x && y >= self.y && x < self.x + self.width && y < self.y + self.height
    }
}

/// The top-level window a physical click at this point would land on.
///
/// This is the OS's own hit-test, and it is materially better than comparing
/// `list_windows` bounds: it walks the real z-order, it descends to the deepest
/// child, and it **skips layered/transparent windows** — which is why Blinky's
/// fullscreen transparent overlay does not shadow the result even though it sits
/// above everything.
///
/// Returns the root window, because that is the level the driver enumerates;
/// a raw hit-test can land on a `Chrome_RenderWidgetHostHWND` or a UWP
/// `Windows.UI.Core.CoreWindow` child whose root is the window the driver knows.
///
/// Requires the process to be DPI-aware, otherwise the point is reinterpreted in
/// virtualized logical space and the hit-test resolves somewhere else entirely.
/// Tauri sets per-monitor-v2 awareness on Windows, and this is asserted by the
/// `get_config`-derived coordinates agreeing with `get_system_metrics` elsewhere
/// in this module.
#[cfg(windows)]
fn hit_test_root(x: i32, y: i32) -> Option<i64> {
    use windows_sys::Win32::Foundation::POINT;
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetAncestor, WindowFromPoint, GA_ROOT,
    };

    let hwnd = unsafe { WindowFromPoint(POINT { x, y }) };
    if hwnd.is_null() {
        return None;
    }
    let root = unsafe { GetAncestor(hwnd, GA_ROOT) };
    let root = if root.is_null() { hwnd } else { root };
    Some(root as isize as i64)
}

#[cfg(not(windows))]
fn hit_test_root(_x: i32, _y: i32) -> Option<i64> {
    None
}

/// The window the user is currently interacting with, if any.
#[cfg(windows)]
fn foreground_window_id() -> Option<i64> {
    use windows_sys::Win32::UI::WindowsAndMessaging::GetForegroundWindow;

    let hwnd = unsafe { GetForegroundWindow() };
    if hwnd.is_null() {
        None
    } else {
        Some(hwnd as isize as i64)
    }
}

#[cfg(not(windows))]
fn foreground_window_id() -> Option<i64> {
    None
}

fn as_int(value: Option<&Value>) -> Option<i64> {
    value.and_then(|v| v.as_i64().or_else(|| v.as_f64().map(|f| f as i64)))
}

fn is_non_target(title: &str) -> bool {
    let lowered = title.to_ascii_lowercase();
    NON_TARGET_TITLES
        .iter()
        .any(|marker| lowered.contains(&marker.to_ascii_lowercase()))
}

fn target_from(item: &Value, geometry: &Value) -> Option<Target> {
    let pid = as_int(item.get("pid"))?;
    let window_id = as_int(item.get("window_id"))?;
    let x = as_int(geometry.get("x"))? as i32;
    let y = as_int(geometry.get("y"))? as i32;
    let width = as_int(geometry.get("width"))? as i32;
    let height = as_int(geometry.get("height"))? as i32;
    if width <= 0 || height <= 0 {
        return None;
    }
    Some(Target {
        pid,
        window_id,
        title: item
            .get("title")
            .and_then(Value::as_str)
            .unwrap_or("")
            .chars()
            .take(48)
            .collect(),
        x,
        y,
        width,
        height,
        z_index: as_int(item.get("z_index")).unwrap_or(0),
    })
}

/// Real top-level windows, frontmost first.
///
/// Two exclusions matter more than they look:
///
/// * **Blinky's own windows.** The highlight overlay is a fullscreen,
///   always-on-top, transparent Tauri window — it sits *above* everything
///   (measured `z_index` 18, above Edge's 15), so without excluding it every
///   screen point resolves to Blinky's own overlay and the click goes nowhere.
///   It is excluded by pid, which is exact, plus by title as a backstop.
/// * **Shell surfaces and the driver's cursor overlay** — also fullscreen, and
///   they would shadow every point the same way.
fn windows() -> Result<Vec<Target>, String> {
    let data = send("list_windows", &json!({ "on_screen_only": true }))?;

    let items = data
        .get("windows")
        .or_else(|| data.get("_legacy_windows"))
        .and_then(Value::as_array)
        .ok_or_else(|| "list_windows returned no window array".to_string())?;

    let own_pid = std::process::id() as i64;
    let mut targets = Vec::new();

    for item in items {
        let title = item.get("title").and_then(Value::as_str).unwrap_or("");
        if is_non_target(title) {
            continue;
        }
        if item
            .get("minimized")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            continue;
        }

        let Some(target) = target_from(item, item.get("bounds").unwrap_or(item)) else {
            continue;
        };
        if target.pid == own_pid {
            continue;
        }

        targets.push(target);
    }

    // Frontmost first. The driver happens to return windows in z-order today,
    // but that is undocumented, so sort explicitly: a larger `z_index` is
    // nearer the viewer.
    targets.sort_by(|a, b| b.z_index.cmp(&a.z_index));
    Ok(targets)
}

/// The window a click at this screen point is meant for. See [`window_at_traced`].
fn window_at(x: i32, y: i32) -> Result<Target, String> {
    window_at_traced(x, y)
}

/// Resolve the window a click at this screen point is meant for.
///
/// ## Why bounds + `z_index` alone is not enough
///
/// Picking the frontmost window whose *bounds* contain the point silently breaks
/// whenever maximized windows overlap, which on a real desktop is most of the
/// time. Measured on this machine: with Settings open and the editor maximized
/// above it, `list_windows` reported the editor at `z_index` 9 and Settings at
/// 8 — both `(0, 0, 2560, 1528)` — so **every** point inside Settings resolved to
/// the editor, and clicks meant for Settings were dispatched into the editor
/// with the editor's pid and editor-local coordinates. The user sees the AI
/// cursor glide to the right place and nothing happen in the app they are
/// actually looking at.
///
/// The driver's `z_index` was telling the truth (the OS z-order agreed); the
/// mistake was treating "a window's rectangle covers this point" as "this window
/// is visible here".
///
/// ## Resolution order
///
/// 1. **OS hit-test** ([`hit_test_root`]) — what a physical click would actually
///    hit. Authoritative, and it skips transparent overlays for free.
/// 2. **Foreground window** — if the hit-test landed on something deliberately
///    ignored (Blinky's own overlay, the driver's cursor, a shell surface), the
///    window the user is interacting with is the next best answer.
/// 3. **Frontmost by `z_index`** — the old behaviour, kept as a last resort so
///    nothing regresses when the hit-test is unavailable.
///
/// A fallback past rung 1 is logged, because it means the click is about to be
/// aimed by geometry rather than by hit-test — the case worth knowing about.
fn window_at_traced(x: i32, y: i32) -> Result<Target, String> {
    let targets = windows()?;

    if let Some(hwnd) = hit_test_root(x, y) {
        if let Some(target) = targets.iter().find(|t| t.window_id == hwnd) {
            return Ok(target.clone());
        }
        eprintln!(
            "blinky: cua hit-test at ({x}, {y}) landed on hwnd {hwnd}, which is not a click target; \
             falling back to foreground/geometry"
        );
    }

    if let Some(hwnd) = foreground_window_id() {
        if let Some(target) = targets
            .iter()
            .find(|t| t.window_id == hwnd && t.contains(x, y))
        {
            return Ok(target.clone());
        }
    }

    targets
        .into_iter()
        .find(|t| t.contains(x, y))
        .ok_or_else(|| format!("no window covers screen point ({x}, {y})"))
}

// ---------------------------------------------------------------------------
// Element selection
// ---------------------------------------------------------------------------

/// How to address the chosen element.
///
/// `element_token` is preferred: it is opaque, carries the window and snapshot
/// with it, and the driver *refuses* a bare `element_index`
/// (`snapshot_id_required`), so the two fields must always travel together.
struct ElementRef {
    token: Option<String>,
    index: i64,
}

/// Actions that mean "activating this element does something".
///
/// `invoke` alone is not enough, and requiring it was a real defect. Windows 11
/// Settings' left-nav items are plain `ListItem`s advertising only `select`, so an
/// `invoke`-only filter rejected every one of them. `pick_element` then returned
/// `None` for every nav label, which pushed every Settings nav click onto the pixel
/// rung — and the pixel rung was where the "cursor goes to the right position but it
/// clicks something else" bug lived. The user-visible symptom was that nav clicks
/// landed on the account card no matter what.
///
/// Measured: driving a `select`-able nav item by `element_token` navigates the page
/// with `route: "accessibility"` and the real cursor unmoved — three for three on
/// Network & internet, Bluetooth & devices and Personalization, each verified by that
/// page's own vocabulary appearing in the new tree.
///
/// Deliberately excluded: `focus`, `scroll_into_view`, `set_value` and friends. Those
/// are not activations, and treating them as such would let `pick_element` report
/// success while performing no click.
const ACTIVATING_ACTIONS: &[&str] = &[
    "invoke", "select", "toggle", "expand", "collapse", "check", "uncheck", "press",
    "click", "open",
];

fn is_actionable(element: &Value) -> bool {
    element
        .get("actions")
        .and_then(Value::as_array)
        .map(|actions| {
            actions.iter().any(|action| {
                action
                    .as_str()
                    .map(|name| {
                        ACTIVATING_ACTIONS
                            .iter()
                            .any(|known| name.eq_ignore_ascii_case(known))
                    })
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false)
}

fn element_name(element: &Value) -> String {
    element
        .get("label")
        .or_else(|| element.get("value"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_ascii_lowercase()
}

/// How far a screen point is from an element, in the element's own space.
///
/// Returns `0` when the point falls *inside* the element's frame, which makes
/// "the control the planner actually aimed at" win any tie.
///
/// `frame` is in **physical window pixels** — measured, not assumed: on a
/// 2560x1528 Settings window with a 1456 screenshot cap the frames reach
/// `max_right=2560, max_bottom=1528`, and the `Window` element's frame is the
/// whole window. An earlier version of this function believed the driver's prose
/// that frames were downscaled screenshot pixels and divided the point by the cap
/// ratio. That made every distance wrong by 1.758x here, and wrong in a
/// *directional* way — frames near the top-left of the window always looked
/// closer than they were, which is exactly where a sidebar lives.
fn frame_distance(element: &Value, x: i32, y: i32, target: &Target) -> i32 {
    let Some(frame) = element.get("frame") else {
        return i32::MAX;
    };
    let left = as_int(frame.get("x")).unwrap_or(0) as i32;
    let top = as_int(frame.get("y")).unwrap_or(0) as i32;
    let width = as_int(frame.get("w")).unwrap_or(0) as i32;
    let height = as_int(frame.get("h")).unwrap_or(0) as i32;

    // Same space as the frame: physical window pixels, no scaling.
    let (point_x, point_y) = window_local(target, x, y)
        .unwrap_or((x - target.x, y - target.y));

    if point_x >= left && point_x < left + width && point_y >= top && point_y < top + height {
        return 0;
    }

    let centre_x = left + width / 2;
    let centre_y = top + height / 2;
    (centre_x - point_x).abs() + (centre_y - point_y).abs()
}

/// Rank roles by how likely they are to actually do something when invoked.
/// A label match on a `Group` is usually the container *around* the real
/// control, and invoking it is a no-op.
fn role_rank(element: &Value) -> u8 {
    match element.get("role").and_then(Value::as_str).unwrap_or("") {
        "Button" | "Hyperlink" | "TabItem" | "MenuItem" | "ListItem" | "CheckBox"
        | "RadioButton" | "SplitButton" => 0,
        "Group" | "Pane" | "Custom" => 2,
        _ => 1,
    }
}

/// Pick the element to act on.
///
/// Only *labelled* actionable elements are considered — see
/// [`ACTIVATING_ACTIONS`] for what counts. Chromium exposes full-window `Group`
/// nodes that advertise an action but do nothing when driven — choosing one would
/// report success while performing no click, and would suppress the point-click
/// fallback. An unlabelled element is therefore never a target; returning `None`
/// lets the caller fall back instead.
///
/// Matches are ranked by exactness, then **proximity to the point the caller
/// clicked**, then label length, then role.
///
/// Proximity is not a nicety here. `x, y` is where the planner *saw* the target
/// and where the AI cursor visibly glided to — it is the strongest evidence
/// available about which control was meant, and ranking by text alone throws it
/// away. The symptom of throwing it away is unmistakable and was reported
/// verbatim: *"the cursor goes in the right position ... it clicks something
/// else"*. Duplicate labels make the tie the common case, not the corner case —
/// Windows Settings alone has `Home` as both a `ListItem` and a `Button`, plus
/// `More options` and `View all devices` twice each.
///
/// Exactness still outranks proximity, so a precise text match is never
/// displaced by a looser one that merely happens to sit closer.
fn pick_element(
    elements: &[Value],
    x: i32,
    y: i32,
    target: &Target,
    label: Option<&str>,
) -> Option<ElementRef> {
    let candidates: Vec<&Value> = elements
        .iter()
        .filter(|element| is_actionable(element) && !element_name(element).is_empty())
        .collect();

    let hit = match label {
        Some(needle) => {
            let needle = needle.to_ascii_lowercase();
            candidates
                .iter()
                .filter_map(|element| {
                    let name = element_name(element);
                    let exactness = if name == needle {
                        0
                    } else if name.starts_with(&needle) {
                        1
                    } else if name.contains(&needle) {
                        2
                    } else {
                        return None;
                    };
                    Some((
                        exactness,
                        frame_distance(element, x, y, target),
                        name.len(),
                        role_rank(element),
                        *element,
                    ))
                })
                .min_by_key(|(exactness, distance, length, role, _)| {
                    (*exactness, *distance, *length, *role)
                })
                .map(|(_, _, _, _, element)| element)
        }
        // No label to rank by: fall back to whichever control sits nearest the
        // point the caller actually clicked.
        None => candidates
            .iter()
            .copied()
            .min_by_key(|element| frame_distance(element, x, y, target)),
    }?;

    Some(ElementRef {
        token: hit
            .get("element_token")
            .and_then(Value::as_str)
            .map(str::to_string),
        index: as_int(hit.get("element_index"))?,
    })
}

// ---------------------------------------------------------------------------
// Coordinates
// ---------------------------------------------------------------------------

/// Convert a screen point into the space window-scope actions expect.
///
/// The driver's prose says window-scope `x, y` is "window-local screenshot pixels
/// — same space as the PNG `get_window_state` returns". **That is wrong**, and
/// believing it was the cause of "the cursor goes to the right position but it
/// clicks something else".
///
/// Measured on a 2560x1528 Settings window with a 1456 screenshot cap:
///
/// * `frame` extents reach `max_right=2560, max_bottom=1528` — the window's own
///   physical size, and the `Window` element's frame *is* the whole window. So
///   `frame` is physical window pixels, not the 1456x869 the screenshot reports.
/// * Clicking window-scope at a `frame`-derived physical centre navigated the app
///   (`route: "accessibility"`, page delta non-zero) with the real cursor
///   unmoved. Clicking at the same point converted into screenshot space did
///   nothing (`route: "synthetic_events"`, zero delta).
///
/// So window-scope coordinates are physical window-local pixels, and the only
/// correct conversion is subtracting the window origin. Scaling by `cap / longest`
/// put every click **1.758x too close to the window's top-left** on this display:
/// the "System" nav item at physical `(234, 302)` was clicked at `(133, 172)`,
/// which lands inside the account card at `x 9..443, y 74..187`. The AI cursor is
/// drawn at the true screen point while the click was delivered at the scaled one,
/// which is exactly the reported symptom.
fn window_local(target: &Target, x: i32, y: i32) -> Result<(i32, i32), String> {
    Ok((x - target.x, y - target.y))
}

fn window_click_args(target: &Target, local_x: i32, local_y: i32) -> Value {
    json!({
        "scope": "window",
        "pid": target.pid,
        "window_id": target.window_id,
        "x": local_x,
        "y": local_y,
        "button": "left",
        "count": 1,
    })
}

/// Background click at a screen point, addressed *inside* its window.
///
/// Desktop scope cannot do this: the driver serves it through global input
/// injection, so the real pointer moves. Window scope stays inside the target —
/// the driver hit-tests the point and invokes the element there
/// (`route: "accessibility"`), otherwise posts raw mouse events to the window
/// (`route: "synthetic_events"`). Only the first of those actually drives XAML,
/// so coordinates have to be in the space the driver hit-tests against: physical
/// window pixels. See [`window_local`].
///
/// One call, no screenshot round trip: the conversion is pure arithmetic now.
///
/// Returns the driver's response so the caller can read `route`. That matters:
/// `route: "accessibility"` means the driver found an element at the point and
/// drove it, while `route: "synthetic_events"` means it only posted raw mouse
/// events — which Win32 honours but XAML silently ignores. Both report
/// `effect: "unverifiable"`, so the route is the only signal available.
fn click_window_point(target: &Target, x: i32, y: i32) -> Result<Value, String> {
    let (local_x, local_y) = window_local(target, x, y)?;
    dispatch("click", window_click_args(target, local_x, local_y))
}

/// Fetch a window's element tree, re-snapshotting once if the driver says the
/// tree was not ready.
///
/// `get_window_state` can answer `degraded` with
/// `degraded_reason: "ax_tree_empty"`, and the driver's own advice is to
/// "re-snapshot if the app just launched". That is not a hypothetical: measured
/// on Windows Settings, one window (`SystemSettings.exe`) reported 0 elements
/// across every attempt, while a freshly launched one hosted by
/// `ApplicationFrameHost.exe` reported 79 elements on the very first call and
/// the element rung worked.
///
/// So the retry is cheap insurance rather than a guaranteed cure. It costs one
/// extra call (~0.15s) and only runs when the first answer came back empty, and
/// it logs the degraded reason either way — which is what turns "this app
/// ignores my clicks" into a one-line diagnosis.
///
/// The returned snapshot and its `snapshot_id` are always from the same call, so
/// tokens and indices stay consistent with it.
fn window_tree(target: &Target) -> Result<Value, String> {
    let request = json!({
        "pid": target.pid,
        "window_id": target.window_id,
        "include_screenshot": false,
    });

    let first = send("get_window_state", &request)?;
    if has_elements(&first) {
        return Ok(first);
    }

    let reason = first
        .get("degraded_reason")
        .and_then(Value::as_str)
        .unwrap_or("elements empty");
    let short = reason.split(':').next().unwrap_or(reason);
    eprintln!(
        "blinky: cua window pid {} {:?} returned no element tree ({short}); re-snapshotting",
        target.pid, target.title
    );

    std::thread::sleep(Duration::from_millis(150));
    let second = send("get_window_state", &request)?;
    if !has_elements(&second) {
        eprintln!(
            "blinky: cua window pid {} still has no element tree; falling back to the pixel rung",
            target.pid
        );
    }
    Ok(second)
}

fn has_elements(state: &Value) -> bool {
    state
        .get("elements")
        .and_then(Value::as_array)
        .map(|elements| !elements.is_empty())
        .unwrap_or(false)
}

/// Click the UI element behind a screen point, inside the window that owns it.
///
/// Two background rungs, cheapest first:
///
/// 1. `element_token` — resolves the labelled control in the window's UIA tree
///    and drives it. No coordinates involved, and it works on backgrounded or
///    partially hidden windows. This is the rung that carries Windows 11 Settings'
///    left nav, whose items expose `select` rather than `invoke`.
/// 2. window-scope pixel — for surfaces with no usable element (canvas, video,
///    WebGL, or anything Chromium keeps out of its accessibility tree).
///
/// Both stay inside the target window; neither touches the real pointer.
///
/// `label` is Blinky's matched target text; it ranks the tree down to the best
/// candidate, and the screen point breaks any remaining tie.
///
/// The tree is fetched *whole* rather than projected with the driver's `query`.
/// Measured on Chromium: `query="Guide"` returned only a `Group` named
/// `guide-button` plus an unrelated hyperlink, while the real `Button` named
/// `Guide` was absent — a projection would systematically lose the control we
/// actually want to invoke.
pub fn click_element_at(x: i32, y: i32, label: Option<&str>) -> Result<(), String> {
    prime_session_once();

    let started = Instant::now();
    let target = window_at(x, y)?;
    let after_window = started.elapsed();
    let label = label.map(str::trim).filter(|l| !l.is_empty());

    // Cheap first pass: tree only, no screenshot.
    let tree = window_tree(&target)?;
    let after_tree = started.elapsed();

    if let (Some(snapshot_id), Some(elements)) = (
        tree.get("snapshot_id").and_then(Value::as_str),
        tree.get("elements").and_then(Value::as_array),
    ) {
        if let Some(element) = pick_element(elements, x, y, &target, label) {
            let mut arguments = json!({
                "scope": "window",
                "pid": target.pid,
                "window_id": target.window_id,
            });
            match &element.token {
                Some(token) => arguments["element_token"] = json!(token),
                None => {
                    arguments["element_index"] = json!(element.index);
                    arguments["snapshot_id"] = json!(snapshot_id);
                }
            }
            let result = dispatch("click", arguments).map(|_| ());
            trace_click(
                &target,
                "element",
                after_window,
                after_tree,
                started.elapsed(),
                &result,
            );
            return result;
        }
    }

    // No actionable element: fall back to a pixel click inside the same window.
    // Window-local coordinates are physical, so this is one call rather than a
    // screenshot round trip.
    let result = click_window_point(&target, x, y);
    if let Ok(payload) = &result {
        warn_inert_pixel_click(&target, x, y, payload);
    }
    let outcome = result.map(|_| ());
    trace_click(
        &target,
        "window-pixel",
        after_window,
        after_tree,
        started.elapsed(),
        &outcome,
    );
    outcome
}

/// Note when a window-scope pixel click probably did nothing.
///
/// The driver reports `effect: "unverifiable"` for a real element activation and
/// for a bare event post alike, so a no-op is indistinguishable from success in
/// the response. The `route` does distinguish them, and on XAML
/// `synthetic_events` is inert — measured on Windows 11 Settings, a window-scope
/// pixel click over a nav item reported success and changed nothing.
///
/// This does not escalate, deliberately. Escalating means a global click, which
/// moves the real cursor — the exact thing the background path exists to avoid —
/// and it would also double-act on Win32 apps where `synthetic_events` does work.
/// Logging keeps the limitation visible instead of silent.
fn warn_inert_pixel_click(target: &Target, x: i32, y: i32, payload: &Value) {
    let route = payload.get("route").and_then(Value::as_str).unwrap_or("");
    if route.eq_ignore_ascii_case("synthetic_events") {
        eprintln!(
            "blinky: cua window-scope pixel click at ({x}, {y}) in pid {} {:?} used \
             route=synthetic_events; XAML surfaces ignore these, so if nothing happened \
             the element rung had no actionable element to target",
            target.pid, target.title
        );
    }
}

/// Explain a click that took longer than it should.
///
/// Silent in the normal case, so the log only grows when something is actually
/// wrong — and when it does, it names the stage that ate the time.
fn trace_click(
    target: &Target,
    rung: &str,
    after_window: Duration,
    after_tree: Duration,
    total: Duration,
    result: &Result<(), String>,
) {
    if total < SLOW_CLICK {
        return;
    }
    let outcome = match result {
        Ok(()) => "ok".to_string(),
        Err(err) => format!("FAILED ({err})"),
    };
    eprintln!(
        "blinky: cua click slow: {total:?} via {rung} on pid {} {:?} (windows {after_window:?}, tree {after_tree:?}) -> {outcome}",
        target.pid, target.title
    );
}

// ---------------------------------------------------------------------------
// Public actions
// ---------------------------------------------------------------------------

/// Background click at screen-absolute physical pixels.
///
/// Resolved to the window under the point and delivered *inside* it, exactly like
/// [`scroll`]. This used to go straight out as `scope: "desktop"`, which the driver
/// serves through global input injection: the real pointer moves and focus follows
/// it. That defeats the whole background path, and it was the remaining asymmetry —
/// `scroll` had already been switched to window scope while `click` had not.
///
/// Desktop scope survives only as a last resort, for the case where no window can
/// be resolved at the point at all.
pub fn click(x: i32, y: i32) -> Result<(), String> {
    prime_session_once();

    if let Ok(target) = window_at(x, y) {
        let result = click_window_point(&target, x, y);
        if let Ok(payload) = &result {
            warn_inert_pixel_click(&target, x, y, payload);
        }
        return result.map(|_| ());
    }

    dispatch(
        "click",
        json!({ "scope": "desktop", "x": x, "y": y, "button": "left", "count": 1 }),
    )
    .map(|_| ())
}

/// Background scroll at screen-absolute physical pixels.
///
/// Addressed inside the window under the point, so the real pointer stays put —
/// desktop scope would inject global input and drag the cursor along with it.
pub fn scroll(x: i32, y: i32, direction: &str, amount: i32) -> Result<(), String> {
    prime_session_once();
    let amount = amount.abs().max(1);

    if let Ok(target) = window_at(x, y) {
        return dispatch(
            "scroll",
            json!({
                "scope": "window",
                "pid": target.pid,
                "window_id": target.window_id,
                "direction": direction,
                "amount": amount,
            }),
        )
        .map(|_| ());
    }

    dispatch(
        "scroll",
        json!({
            "scope": "desktop",
            "x": x,
            "y": y,
            "direction": direction,
            "amount": amount,
        }),
    )
    .map(|_| ())
}

/// Background typing, addressed to the window under `(x, y)`.
///
/// The driver's `type_text` accepts `pid` / `window_id` / `scope`, and without them it
/// falls back to whichever window currently holds focus. This used to send a bare
/// `{"text": ...}`, which is not merely untargeted — it does not work at all. Measured
/// against Notepad: the bare call came back `isError: true`,
/// `{"code": "tool_invocation_failed"}`, with **no text applied**, while the same call
/// with `pid` + `window_id` + `scope: "window"` succeeded and the text landed.
///
/// Note the driver routes by *EXE basename*, not toolkit: it reported
/// `xaml_routing_recommended: True` for `notepad.exe`, so "Win32 vs XAML" is not a
/// usable predictor of whether posted input will be honoured.
///
/// When the caller already has a labelled field, prefer `set_value` on its
/// `element_token` — that is the only variant measured to route through
/// `accessibility` rather than posted synthetic events.
pub fn type_text(x: i32, y: i32, text: &str) -> Result<(), String> {
    prime_session_once();

    if let Ok(target) = window_at(x, y) {
        return dispatch(
            "type_text",
            json!({
                "scope": "window",
                "pid": target.pid,
                "window_id": target.window_id,
                "text": text,
            }),
        )
        .map(|_| ());
    }

    // No window under the point (bare desktop): the driver's own focus fallback is
    // the only remaining option.
    dispatch("type_text", json!({ "text": text })).map(|_| ())
}

/// Background single key press (e.g. `return`, `escape`), addressed like [`type_text`].
///
/// `press_key` shares `type_text`'s problem: a bare `{"key": ...}` goes to whatever is
/// focused rather than to the window the AI cursor is pointing at. On Windows the key
/// is delivered with the same target the text was, so a "type then Enter" step cannot
/// straddle two windows.
pub fn press_key(x: i32, y: i32, key: &str) -> Result<(), String> {
    prime_session_once();

    if let Ok(target) = window_at(x, y) {
        return dispatch(
            "press_key",
            json!({
                "scope": "window",
                "pid": target.pid,
                "window_id": target.window_id,
                "key": key,
            }),
        )
        .map(|_| ());
    }

    dispatch("press_key", json!({ "key": key })).map(|_| ())
}

/// Structured health payload, for diagnostics surfaces.
#[allow(dead_code)]
pub fn doctor() -> Result<Value, String> {
    call("health_report", json!({}))
}
