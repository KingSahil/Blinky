use crate::compositor::Compositor;
use crate::protocol::models::{CursorPosition, MonitorInfo, WindowBounds, WindowInfo};
use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use serde_json::Value;
use std::path::PathBuf;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;
use tracing::{debug, warn};

#[derive(Debug, Clone, Default)]
pub struct HyprlandCompositor {
    socket_path_override: Option<PathBuf>,
}

impl HyprlandCompositor {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_socket(socket_path: PathBuf) -> Self {
        Self {
            socket_path_override: Some(socket_path),
        }
    }

    pub fn find_socket() -> Result<PathBuf> {
        let runtime_dir = std::env::var("XDG_RUNTIME_DIR")
            .unwrap_or_else(|_| format!("/run/user/{}", nix::unistd::getuid()));
        let hypr_base = PathBuf::from(runtime_dir).join("hypr");

        // 1. Try env signature if present
        if let Ok(sig) = std::env::var("HYPRLAND_INSTANCE_SIGNATURE") {
            let direct = hypr_base.join(&sig).join(".socket.sock");
            if direct.exists() {
                return Ok(direct);
            }
        }

        // 2. Scan hypr directory for instances
        if hypr_base.is_dir() {
            let mut candidates = Vec::new();
            if let Ok(entries) = std::fs::read_dir(&hypr_base) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    let sock = path.join(".socket.sock");
                    if sock.exists() {
                        if let Ok(metadata) = std::fs::metadata(&path) {
                            if let Ok(modified) = metadata.modified() {
                                candidates.push((modified, sock));
                            }
                        }
                    }
                }
            }
            if !candidates.is_empty() {
                candidates.sort_by(|a, b| b.0.cmp(&a.0)); // newest first
                return Ok(candidates[0].1.clone());
            }
        }

        bail!("No active Hyprland socket found under {}", hypr_base.display())
    }

    pub async fn send_command(&self, cmd: &str) -> Result<String> {
        let socket_path = match &self.socket_path_override {
            Some(p) => p.clone(),
            None => Self::find_socket()?,
        };

        let mut stream = UnixStream::connect(&socket_path)
            .await
            .with_context(|| format!("Failed to connect to Hyprland socket at {}", socket_path.display()))?;

        stream
            .write_all(cmd.as_bytes())
            .await
            .context("Failed to write command to Hyprland socket")?;
        stream.shutdown().await.ok();

        let mut response = Vec::new();
        stream
            .read_to_end(&mut response)
            .await
            .context("Failed to read response from Hyprland socket")?;

        let text = String::from_utf8(response)
            .context("Hyprland socket response was not valid UTF-8")?;

        Ok(text)
    }

    pub async fn send_json_command(&self, cmd: &str) -> Result<Value> {
        let text = self.send_command(cmd).await?;
        let val: Value = serde_json::from_str(&text)
            .with_context(|| format!("Failed to parse JSON response for command '{}': {}", cmd, text))?;
        Ok(val)
    }
}

#[async_trait]
impl Compositor for HyprlandCompositor {
    async fn name(&self) -> &'static str {
        "hyprland"
    }

    async fn is_available(&self) -> bool {
        Self::find_socket().is_ok()
    }

    async fn get_monitors(&self) -> Result<Vec<MonitorInfo>> {
        let val = self.send_json_command("j/monitors").await?;
        let array = val.as_array().context("j/monitors did not return an array")?;

        let mut monitors = Vec::new();
        for item in array {
            let id = item.get("id").and_then(|v| v.as_i64()).unwrap_or(0);
            let name = item
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let description = item
                .get("description")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let x = item.get("x").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
            let y = item.get("y").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
            let width = item.get("width").and_then(|v| v.as_u64()).unwrap_or(1920) as u32;
            let height = item.get("height").and_then(|v| v.as_u64()).unwrap_or(1080) as u32;
            let refresh_rate = item
                .get("refreshRate")
                .and_then(|v| v.as_f64())
                .unwrap_or(60.0);
            let scale = item.get("scale").and_then(|v| v.as_f64()).unwrap_or(1.0);
            let focused = item
                .get("focused")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);

            monitors.push(MonitorInfo {
                id,
                name,
                description,
                x,
                y,
                width,
                height,
                refresh_rate,
                scale,
                focused,
            });
        }

        Ok(monitors)
    }

    async fn get_windows(&self) -> Result<Vec<WindowInfo>> {
        let val = self.send_json_command("j/clients").await?;
        let array = val.as_array().context("j/clients did not return an array")?;

        let mut windows = Vec::new();
        for item in array {
            let mapped = item.get("mapped").and_then(|v| v.as_bool()).unwrap_or(true);
            let hidden = item.get("hidden").and_then(|v| v.as_bool()).unwrap_or(false);
            if !mapped || hidden {
                continue;
            }

            let address = item
                .get("address")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let title = item
                .get("title")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let class = item
                .get("class")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let initial_class = item
                .get("initialClass")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let pid = item.get("pid").and_then(|v| v.as_u64()).map(|p| p as u32);

            let at = item.get("at").and_then(|v| v.as_array());
            let size = item.get("size").and_then(|v| v.as_array());

            let (x, y) = if let Some(arr) = at {
                (
                    arr.get(0).and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                    arr.get(1).and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                )
            } else {
                (0, 0)
            };

            let (width, height) = if let Some(arr) = size {
                (
                    arr.get(0).and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                    arr.get(1).and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                )
            } else {
                (0, 0)
            };

            let monitor_id = item.get("monitor").and_then(|v| v.as_i64()).unwrap_or(0);
            let workspace_id = item
                .get("workspace")
                .and_then(|w| w.get("id"))
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
            let focused = item
                .get("focused")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let floating = item
                .get("floating")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let fullscreen = item
                .get("fullscreen")
                .and_then(|v| v.as_u64())
                .map(|f| f > 0)
                .unwrap_or(false);

            windows.push(WindowInfo {
                address,
                title,
                class,
                initial_class,
                pid,
                bounds: WindowBounds {
                    x,
                    y,
                    width,
                    height,
                },
                monitor_id,
                workspace_id,
                focused,
                floating,
                fullscreen,
            });
        }

        Ok(windows)
    }

    async fn get_active_window(&self) -> Result<Option<WindowInfo>> {
        let val = self.send_json_command("j/activewindow").await?;
        if val.is_null() || val.as_object().map_or(true, |o| o.is_empty()) {
            return Ok(None);
        }

        let address = val
            .get("address")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        if address.is_empty() {
            return Ok(None);
        }

        let title = val
            .get("title")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let class = val
            .get("class")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let initial_class = val
            .get("initialClass")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let pid = val.get("pid").and_then(|v| v.as_u64()).map(|p| p as u32);

        let at = val.get("at").and_then(|v| v.as_array());
        let size = val.get("size").and_then(|v| v.as_array());

        let (x, y) = if let Some(arr) = at {
            (
                arr.get(0).and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                arr.get(1).and_then(|v| v.as_i64()).unwrap_or(0) as i32,
            )
        } else {
            (0, 0)
        };

        let (width, height) = if let Some(arr) = size {
            (
                arr.get(0).and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                arr.get(1).and_then(|v| v.as_u64()).unwrap_or(0) as u32,
            )
        } else {
            (0, 0)
        };

        let monitor_id = val.get("monitor").and_then(|v| v.as_i64()).unwrap_or(0);
        let workspace_id = val
            .get("workspace")
            .and_then(|w| w.get("id"))
            .and_then(|v| v.as_i64())
            .unwrap_or(0);
        let floating = val
            .get("floating")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let fullscreen = val
            .get("fullscreen")
            .and_then(|v| v.as_u64())
            .map(|f| f > 0)
            .unwrap_or(false);

        Ok(Some(WindowInfo {
            address,
            title,
            class,
            initial_class,
            pid,
            bounds: WindowBounds {
                x,
                y,
                width,
                height,
            },
            monitor_id,
            workspace_id,
            focused: true,
            floating,
            fullscreen,
        }))
    }

    async fn get_cursor_position(&self) -> Result<CursorPosition> {
        let val = self.send_json_command("j/cursorpos").await?;
        let x = val.get("x").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
        let y = val.get("y").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
        Ok(CursorPosition { x, y })
    }

    async fn move_cursor(&self, x: i32, y: i32) -> Result<()> {
        let script = format!("eval hl.dispatch(hl.dsp.cursor.move({{ x = {x}, y = {y} }}))");
        let res = self.send_command(&script).await?;
        if !res.trim().starts_with("ok") {
            warn!("Hyprland cursor move response: {}", res);
        }
        Ok(())
    }

    async fn focus_window(&self, address: &str) -> Result<()> {
        let clean_addr = if address.starts_with("address:") {
            address.to_string()
        } else {
            format!("address:{}", address)
        };
        let script = format!("eval hl.dispatch(hl.dsp.focus({{ window = \"{clean_addr}\" }}))");
        let res = self.send_command(&script).await?;
        if !res.trim().starts_with("ok") {
            bail!("Hyprland focus window failed: {}", res);
        }
        debug!("Focused window: {}", address);
        Ok(())
    }
}
