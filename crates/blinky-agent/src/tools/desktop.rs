use super::Tool;
use crate::providers::ToolDefinition;
use anyhow::{Context, Result};
use async_trait::async_trait;
use serde_json::{json, Value};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;

pub struct DaemonRpcClient {
    socket_path: std::path::PathBuf,
}

impl DaemonRpcClient {
    pub fn new() -> Self {
        let runtime = std::env::var("XDG_RUNTIME_DIR")
            .unwrap_or_else(|_| format!("/run/user/{}", nix::unistd::getuid()));
        Self {
            socket_path: std::path::PathBuf::from(runtime).join("blinky-daemon.sock"),
        }
    }

    async fn ensure_connected(&self) -> Result<UnixStream> {
        if let Ok(stream) = UnixStream::connect(&self.socket_path).await {
            return Ok(stream);
        }

        // Auto-spawn blinky-daemon if connection fails
        let daemon_bin_candidates = [
            std::path::PathBuf::from("/home/fev/GitRepos/Blinky/target/debug/blinky-daemon"),
            std::env::current_exe().map(|p| p.parent().unwrap().join("blinky-daemon")).unwrap_or_default(),
        ];

        for bin in &daemon_bin_candidates {
            if bin.exists() {
                let _ = tokio::process::Command::new(bin).spawn();
                break;
            }
        }

        // Retry connection with backoff
        for _ in 0..10 {
            tokio::time::sleep(std::time::Duration::from_millis(150)).await;
            if let Ok(stream) = UnixStream::connect(&self.socket_path).await {
                return Ok(stream);
            }
        }

        UnixStream::connect(&self.socket_path)
            .await
            .with_context(|| format!("Failed to connect to daemon socket at {}", self.socket_path.display()))
    }

    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        let mut stream = self.ensure_connected().await?;

        let req = json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        });

        let mut payload = serde_json::to_string(&req)?;
        payload.push('\n');

        stream.write_all(payload.as_bytes()).await?;
        stream.flush().await?;

        let mut reader = BufReader::new(stream);
        let mut line = String::new();
        reader.read_line(&mut line).await?;

        let resp: Value = serde_json::from_str(&line)?;
        if let Some(err) = resp.get("error") {
            if !err.is_null() {
                anyhow::bail!("Daemon error: {}", err);
            }
        }

        Ok(resp.get("result").cloned().unwrap_or(Value::Null))
    }
}

pub struct LaunchAppTool {
    client: DaemonRpcClient,
}

impl LaunchAppTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for LaunchAppTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "launch_app".to_string(),
            description: "Launch an installed desktop application by name (e.g. 'firefox', 'spotify', 'code', 'calculator')".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name or desktop ID of the application to launch"
                    }
                },
                "required": ["name"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let name = args.get("name").and_then(|v| v.as_str()).unwrap_or("");
        self.client.call("blinky.launchApp", json!({ "name": name })).await
    }
}

pub struct FocusWindowTool {
    client: DaemonRpcClient,
}

impl FocusWindowTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for FocusWindowTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "focus_window".to_string(),
            description: "Bring a specific window to the foreground and focus it by name, title, class, or address".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name or title of the window to focus (e.g. 'Firefox', 'Hermes', 'terminal')"
                    },
                    "address": {
                        "type": "string",
                        "description": "Exact window memory address handle if known"
                    }
                }
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        self.client.call("blinky.focusWindow", args).await
    }
}

pub struct CaptureWindowTool {
    client: DaemonRpcClient,
}

impl CaptureWindowTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for CaptureWindowTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "capture_window".to_string(),
            description: "Capture the active or focused window to observe its visual state and receive grounded UI element references (@eN) with a frame_id".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Optional window address to capture. Omit to capture the currently active window."
                    }
                }
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        self.client.call("blinky.captureWindow", args).await
    }
}

pub struct CaptureScreenTool {
    client: DaemonRpcClient,
}

impl CaptureScreenTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for CaptureScreenTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "capture_screen".to_string(),
            description: "Capture the entire desktop screen to observe all open windows and get grounded UI elements with a frame_id".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "monitor": {
                        "type": "string",
                        "description": "Optional monitor output name"
                    }
                }
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        self.client.call("blinky.captureScreen", args).await
    }
}

pub struct ActOnFrameTool {
    client: DaemonRpcClient,
}

impl ActOnFrameTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for ActOnFrameTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "act_on_frame".to_string(),
            description: "Execute a grounded action (click, double_click, right_click, type, scroll) on an observed UI frame using an element reference (@e12) or coordinates".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "frame_id": {
                        "type": "string",
                        "description": "The frame ID returned from capture_window or capture_screen"
                    },
                    "ref": {
                        "type": "string",
                        "description": "Element reference ID (e.g. '@e3') to click/type into"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["click", "double_click", "right_click", "type", "move", "scroll"],
                        "description": "Action type to execute"
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type if action is 'type'"
                    },
                    "target": {
                        "type": "array",
                        "items": { "type": "number" },
                        "description": "Optional normalized [u, v] or pixel [x, y] coordinates if not using ref"
                    }
                },
                "required": ["frame_id", "action"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        self.client.call("blinky.actOnFrame", args).await
    }
}

pub struct KeyboardTypeTool {
    client: DaemonRpcClient,
}

impl KeyboardTypeTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for KeyboardTypeTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "type_text".to_string(),
            description: "Type text into the focused field, document, or active window. For tabular data entry (spreadsheets, tables, forms), once the starting cell (e.g. A1) is focused, pass the entire multi-line TSV table (rows separated by '\\n', columns by '\\t') in a single call for instant, matrix-aligned population.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text string to type into the focused field"
                    }
                },
                "required": ["text"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let text = args.get("text").and_then(|v| v.as_str()).unwrap_or("");
        
        // Intelligent Table Paste Optimization: If text contains tabular data (both \n and \t),
        // clipboard paste ensures a clean 2D grid without diagonal spreadsheet drift.
        if text.contains('\n') && text.contains('\t') {
            use tokio::io::AsyncWriteExt;
            if let Ok(mut child) = tokio::process::Command::new("wl-copy")
                .stdin(std::process::Stdio::piped())
                .spawn()
            {
                if let Some(mut stdin) = child.stdin.take() {
                    let _ = stdin.write_all(text.as_bytes()).await;
                    let _ = stdin.flush().await;
                    drop(stdin);
                    let _ = child.wait().await;
                    tokio::time::sleep(std::time::Duration::from_millis(50)).await;
                    return self.client.call("blinky.keyboardKey", json!({ "keys": "ctrl+v" })).await;
                }
            }
        }

        self.client.call("blinky.keyboardType", args).await
    }
}

pub struct KeyboardKeyTool {
    client: DaemonRpcClient,
}

impl KeyboardKeyTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for KeyboardKeyTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "keyboard_key".to_string(),
            description: "Press a keyboard shortcut combo (e.g. 'ctrl+s', 'ctrl+l', 'ctrl+a') or special key ('Return', 'Escape', 'Tab', 'BackSpace')".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": "Key combo to press (e.g. 'Return', 'ctrl+l', 'Escape')"
                    }
                },
                "required": ["keys"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        self.client.call("blinky.keyboardKey", args).await
    }
}
