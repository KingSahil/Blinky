use crate::apps::AppRegistry;
use crate::atspi::AtspiBridge;
use crate::capture::ScreenCapturer;
use crate::compositor::Compositor;
use crate::coordinate::{CoordinateEngine, FrameStore};
use crate::input::InputActuator;
use crate::media::MediaController;
use crate::protocol::models::{CaptureKind, FrameDescriptor, UIElement, WindowBounds};
use crate::protocol::types::*;
use crate::system::SystemSessionController;
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};
use tokio::sync::Mutex;
use tracing::{debug, error, info};

pub struct RpcDispatcher {
    compositor: Arc<dyn Compositor>,
    capturer: Arc<ScreenCapturer>,
    input: Arc<Mutex<InputActuator>>,
    frame_store: Arc<FrameStore>,
    system: Arc<SystemSessionController>,
    media: Arc<MediaController>,
    atspi: Arc<AtspiBridge>,
}

impl RpcDispatcher {
    pub fn new(
        compositor: Arc<dyn Compositor>,
        capturer: Arc<ScreenCapturer>,
        input: Arc<Mutex<InputActuator>>,
        system: Arc<SystemSessionController>,
        media: Arc<MediaController>,
        atspi: Arc<AtspiBridge>,
    ) -> Self {
        Self {
            compositor,
            capturer,
            input,
            frame_store: Arc::new(FrameStore::new()),
            system,
            media,
            atspi,
        }
    }

    pub fn with_frame_store(
        compositor: Arc<dyn Compositor>,
        capturer: Arc<ScreenCapturer>,
        input: Arc<Mutex<InputActuator>>,
        frame_store: Arc<FrameStore>,
        system: Arc<SystemSessionController>,
        media: Arc<MediaController>,
        atspi: Arc<AtspiBridge>,
    ) -> Self {
        Self {
            compositor,
            capturer,
            input,
            frame_store,
            system,
            media,
            atspi,
        }
    }

    pub async fn dispatch(&self, req: JsonRpcRequest) -> JsonRpcResponse {
        let id = req.id.unwrap_or(Id::Null);
        let method = req.method.as_str();
        let params = req.params.unwrap_or(Value::Null);

        debug!("Dispatching RPC method: {}", method);

        let result = match method {
            "blinky.getSystemInfo" => self.handle_get_system_info().await,
            "blinky.getMonitors" => self.handle_get_monitors().await,
            "blinky.getWindows" => self.handle_get_windows().await,
            "blinky.getActiveWindow" => self.handle_get_active_window().await,
            "blinky.focusWindow" => self.handle_focus_window(params).await,
            "blinky.getCursorPosition" => self.handle_get_cursor_position().await,
            "blinky.getApps" => self.handle_get_apps().await,
            "blinky.launchApp" => self.handle_launch_app(params).await,
            "blinky.captureScreen" => self.handle_capture_screen(params).await,
            "blinky.captureWindow" => self.handle_capture_window(params).await,
            "blinky.captureInteractive" => self.handle_capture_interactive().await,
            "blinky.attachElements" => self.handle_attach_elements(params).await,
            "blinky.getA11yElements" => self.handle_get_a11y_elements(params).await,
            "blinky.actOnFrame" => self.handle_act_on_frame(params).await,
            "blinky.mouseMove" => self.handle_mouse_move(params).await,
            "blinky.mouseClick" => self.handle_mouse_click(params).await,
            "blinky.mouseScroll" => self.handle_mouse_scroll(params).await,
            "blinky.keyboardType" => self.handle_keyboard_type(params).await,
            "blinky.keyboardKey" => self.handle_keyboard_key(params).await,
            "blinky.reanchorCoordinate" => self.handle_reanchor_coordinate(params).await,
            "blinky.systemSession" => self.handle_system_session(params).await,
            "blinky.mediaControl" => self.handle_media_control(params).await,
            _ => {
                return JsonRpcResponse::error(
                    id,
                    METHOD_NOT_FOUND,
                    format!("Method '{}' not found", method),
                    None,
                );
            }
        };

        match result {
            Ok(val) => JsonRpcResponse::success(id, val),
            Err(e) => {
                error!("RPC method '{}' failed: {:#}", method, e);
                JsonRpcResponse::error(id, INTERNAL_ERROR, e.to_string(), None)
            }
        }
    }

    async fn handle_get_system_info(&self) -> Result<Value> {
        let comp_name = self.compositor.name().await;
        let comp_avail = self.compositor.is_available().await;
        let atspi_avail = self.atspi.is_available().await;
        let de = std::env::var("XDG_CURRENT_DESKTOP").unwrap_or_default();
        let session = std::env::var("XDG_SESSION_TYPE").unwrap_or_default();

        Ok(json!({
            "compositor": comp_name,
            "compositor_available": comp_avail,
            "atspi_available": atspi_avail,
            "desktop_environment": de,
            "session_type": session,
            "daemon_version": env!("CARGO_PKG_VERSION"),
        }))
    }

    async fn handle_get_monitors(&self) -> Result<Value> {
        let monitors = self.compositor.get_monitors().await?;
        Ok(serde_json::to_value(monitors)?)
    }

    async fn handle_get_windows(&self) -> Result<Value> {
        let windows = self.compositor.get_windows().await?;
        Ok(serde_json::to_value(windows)?)
    }

    async fn handle_get_active_window(&self) -> Result<Value> {
        let window = self.compositor.get_active_window().await?;
        Ok(serde_json::to_value(window)?)
    }

    async fn handle_focus_window(&self, params: Value) -> Result<Value> {
        let start = Instant::now();
        let target_address = if let Some(addr) = params.get("address").and_then(|v| v.as_str()) {
            addr.to_string()
        } else if let Some(q) = params
            .get("title")
            .or_else(|| params.get("class"))
            .or_else(|| params.get("name"))
            .and_then(|v| v.as_str())
        {
            let q_lower = q.to_lowercase();
            let windows = self.compositor.get_windows().await?;
            let matching: Vec<&crate::protocol::models::WindowInfo> = windows
                .iter()
                .filter(|w| {
                    w.title.to_lowercase().contains(&q_lower)
                        || w.class.to_lowercase().contains(&q_lower)
                        || w.initial_class.to_lowercase().contains(&q_lower)
                })
                .collect();

            if matching.is_empty() {
                bail!("No window matching '{}' found", q);
            }

            // Prefer the newest/last matching window
            matching.last().unwrap().address.clone()
        } else if let Some(pid) = params.get("pid").and_then(|v| v.as_u64()) {
            let windows = self.compositor.get_windows().await?;
            let win = windows
                .iter()
                .find(|w| w.pid == Some(pid as u32))
                .ok_or_else(|| anyhow::anyhow!("No window with PID {} found", pid))?;
            win.address.clone()
        } else {
            bail!("Must provide 'address', 'title', 'class', 'name', or 'pid'");
        };

        self.compositor.focus_window(&target_address).await?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;

        Ok(json!({
            "ok": true,
            "action": "focus_window",
            "address": target_address,
            "elapsed_ms": elapsed_ms,
        }))
    }

    async fn handle_get_cursor_position(&self) -> Result<Value> {
        let pos = self.compositor.get_cursor_position().await?;
        Ok(serde_json::to_value(pos)?)
    }

    async fn handle_get_apps(&self) -> Result<Value> {
        let apps = tokio::task::spawn_blocking(AppRegistry::scan_apps).await?;
        Ok(serde_json::to_value(apps)?)
    }

    async fn handle_launch_app(&self, params: Value) -> Result<Value> {
        let query = params
            .get("name")
            .or_else(|| params.get("query"))
            .or_else(|| params.get("desktop_id"))
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'name' or 'query' parameter"))?;

        // 1. Snapshot existing windows before launching
        let before_windows = self.compositor.get_windows().await.unwrap_or_default();
        let before_addrs: std::collections::HashSet<String> =
            before_windows.iter().map(|w| w.address.clone()).collect();

        // 2. Launch application
        let app = AppRegistry::launch(query).await?;

        // 3. Poll for the newly created window (up to 2.5s)
        let mut new_window: Option<crate::protocol::models::WindowInfo> = None;
        for _ in 0..12 {
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
            if let Ok(after_windows) = self.compositor.get_windows().await {
                if let Some(w) = after_windows
                    .iter()
                    .find(|w| !before_addrs.contains(&w.address))
                {
                    new_window = Some(w.clone());
                    break;
                }
            }
        }

        let mut res_obj = serde_json::to_value(&app)?;
        if let Some(w) = new_window {
            // Automatically focus the newly launched window!
            self.compositor.focus_window(&w.address).await.ok();
            res_obj["window_address"] = json!(w.address);
            res_obj["window_bounds"] = json!(w.bounds);
            res_obj["window_title"] = json!(w.title);
            res_obj["window_class"] = json!(w.class);
        }

        Ok(res_obj)
    }

    async fn handle_capture_screen(&self, params: Value) -> Result<Value> {
        let monitor = params.get("monitor").and_then(|v| v.as_str());
        let mut res = self.capturer.capture_fullscreen(monitor).await?;

        let monitors = self.compositor.get_monitors().await?;
        let active_mon = monitors
            .iter()
            .find(|m| monitor.map_or(m.focused, |name| m.name == name))
            .or_else(|| monitors.first());

        let (mon_x, mon_y, mon_w, mon_h, mon_id, mon_scale) = if let Some(m) = active_mon {
            (m.x, m.y, m.width, m.height, m.id, m.scale)
        } else {
            (0, 0, res.width, res.height, 0, 1.0)
        };

        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;

        let frame_id = format!("frm_{}_scr", now_ms);
        let frame = FrameDescriptor {
            frame_id,
            capture_kind: CaptureKind::Fullscreen,
            window_address: None,
            source_bounds: WindowBounds {
                x: mon_x,
                y: mon_y,
                width: mon_w,
                height: mon_h,
            },
            image_width: res.width,
            image_height: res.height,
            scale: mon_scale,
            monitor_id: mon_id,
            timestamp_ms: now_ms,
            elements: Vec::new(),
        };

        self.frame_store.insert(frame.clone());
        res.frame = Some(frame);

        Ok(serde_json::to_value(res)?)
    }

    async fn handle_capture_window(&self, params: Value) -> Result<Value> {
        let (bounds, target_addr): (WindowBounds, Option<String>) = if let Some(b) = params.get("bounds") {
            (serde_json::from_value(b.clone())?, None)
        } else if let Some(addr) = params.get("address").and_then(|v| v.as_str()) {
            let windows = self.compositor.get_windows().await?;
            let win = windows
                .iter()
                .find(|w| w.address == addr)
                .ok_or_else(|| anyhow::anyhow!("Window '{}' not found", addr))?;
            (win.bounds, Some(win.address.clone()))
        } else {
            let active = self
                .compositor
                .get_active_window()
                .await?
                .ok_or_else(|| anyhow::anyhow!("No active window to capture"))?;
            (active.bounds, Some(active.address))
        };

        let scale = params.get("scale").and_then(|v| v.as_f64()).unwrap_or(1.0);
        let mut res = self.capturer.capture_window_crop(&bounds, scale).await?;

        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;

        let frame_id = format!("frm_{}_win", now_ms);
        let frame = FrameDescriptor {
            frame_id,
            capture_kind: CaptureKind::Window,
            window_address: target_addr,
            source_bounds: bounds,
            image_width: res.width,
            image_height: res.height,
            scale,
            monitor_id: 0,
            timestamp_ms: now_ms,
            elements: Vec::new(),
        };

        self.frame_store.insert(frame.clone());
        res.frame = Some(frame);

        Ok(serde_json::to_value(res)?)
    }

    async fn handle_capture_interactive(&self) -> Result<Value> {
        let mut res = self.capturer.capture_interactive().await?;

        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;

        let frame_id = format!("frm_{}_roi", now_ms);
        let frame = FrameDescriptor {
            frame_id,
            capture_kind: CaptureKind::Region,
            window_address: None,
            source_bounds: WindowBounds {
                x: 0,
                y: 0,
                width: res.width,
                height: res.height,
            },
            image_width: res.width,
            image_height: res.height,
            scale: 1.0,
            monitor_id: 0,
            timestamp_ms: now_ms,
            elements: Vec::new(),
        };

        self.frame_store.insert(frame.clone());
        res.frame = Some(frame);

        Ok(serde_json::to_value(res)?)
    }

    async fn handle_attach_elements(&self, params: Value) -> Result<Value> {
        let frame_id = params
            .get("frame_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'frame_id' parameter"))?;

        let elements_val = params
            .get("elements")
            .ok_or_else(|| anyhow::anyhow!("Missing 'elements' array"))?;

        let elements: Vec<UIElement> = serde_json::from_value(elements_val.clone())
            .context("Failed to deserialize elements array into Vec<UIElement>")?;

        let count = elements.len();
        self.frame_store.attach_elements(frame_id, elements)?;

        info!("Attached {} elements to frame '{}'", count, frame_id);

        Ok(json!({
            "ok": true,
            "frame_id": frame_id,
            "element_count": count,
        }))
    }

    async fn handle_get_a11y_elements(&self, params: Value) -> Result<Value> {
        let max_elements = params
            .get("max_elements")
            .and_then(|v| v.as_u64())
            .unwrap_or(300) as usize;

        let elements = self.atspi.get_elements(max_elements).await?;

        if let Some(frame_id) = params.get("attach_to_frame").and_then(|v| v.as_str()) {
            self.frame_store.attach_elements(frame_id, elements.clone()).ok();
        }

        Ok(serde_json::to_value(elements)?)
    }

    async fn handle_act_on_frame(&self, params: Value) -> Result<Value> {
        let start = Instant::now();

        let frame_id = params
            .get("frame_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'frame_id' parameter"))?;

        let frame = self
            .frame_store
            .get(frame_id)
            .ok_or_else(|| anyhow::anyhow!("Frame '{}' not found or expired from frame store", frame_id))?;

        let target_ref = params
            .get("ref")
            .or_else(|| params.get("target_ref"))
            .and_then(|v| v.as_str());

        let target_text = params
            .get("target_text")
            .or_else(|| params.get("text_target"))
            .and_then(|v| v.as_str());

        let target_raw: Option<(f64, f64)> = if let Some(arr) = params.get("target").and_then(|v| v.as_array()) {
            if arr.len() >= 2 {
                let x = arr[0].as_f64().context("Invalid target X coordinate")?;
                let y = arr[1].as_f64().context("Invalid target Y coordinate")?;
                Some((x, y))
            } else {
                None
            }
        } else {
            None
        };

        let force_norm = params.get("normalized").and_then(|v| v.as_bool());

        let action = params
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("click");

        // 1. Fetch live desktop geometry
        let live_windows = self.compositor.get_windows().await?;
        let monitors = self.compositor.get_monitors().await?;

        // 2. Resolve anchored target coordinate
        let anchored = CoordinateEngine::resolve_frame_target(
            &frame,
            target_raw,
            target_ref,
            target_text,
            force_norm,
            &live_windows,
            &monitors,
        )?;

        info!(
            "Resolved frame target: Frame '{}' -> Target ({}, {}) on window {:?}",
            frame_id, anchored.target_x, anchored.target_y, anchored.window_address
        );

        // 3. Dispatch requested action
        let mut input = self.input.lock().await;

        let result = match action {
            "move" => {
                input.move_to(anchored.target_x, anchored.target_y).await?
            }
            "click" => {
                let button = params.get("button").and_then(|v| v.as_str()).unwrap_or("left");
                let count = params.get("click_count").and_then(|v| v.as_u64()).unwrap_or(1) as u32;
                input
                    .click(Some(anchored.target_x), Some(anchored.target_y), button, count)
                    .await?
            }
            "double_click" => {
                input
                    .click(Some(anchored.target_x), Some(anchored.target_y), "left", 2)
                    .await?
            }
            "right_click" => {
                input
                    .click(Some(anchored.target_x), Some(anchored.target_y), "right", 1)
                    .await?
            }
            "type" => {
                input
                    .click(Some(anchored.target_x), Some(anchored.target_y), "left", 1)
                    .await?;
                tokio::time::sleep(std::time::Duration::from_millis(50)).await;

                let text = params
                    .get("text")
                    .and_then(|v| v.as_str())
                    .ok_or_else(|| anyhow::anyhow!("Missing 'text' parameter for type action"))?;
                input.type_text(text).await?
            }
            "scroll" => {
                let direction = params.get("direction").and_then(|v| v.as_str()).unwrap_or("down");
                let amount = params.get("amount").and_then(|v| v.as_i64()).unwrap_or(3) as i32;
                input
                    .scroll(
                        direction,
                        amount,
                        Some(anchored.target_x),
                        Some(anchored.target_y),
                    )
                    .await?
            }
            other => bail!("Unsupported frame action '{}'", other),
        };

        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;

        // Safeguard: Closed-Loop Post-Action Position Verification
        let actual_pos = self.compositor.get_cursor_position().await.ok();
        let verified = if let Some(pos) = actual_pos {
            let dx = (pos.x - anchored.target_x).abs();
            let dy = (pos.y - anchored.target_y).abs();
            dx <= 2 && dy <= 2
        } else {
            false
        };

        Ok(json!({
            "ok": result.ok,
            "verified": verified,
            "action": action,
            "frame_id": frame_id,
            "anchored_target": serde_json::to_value(anchored)?,
            "actual_cursor": actual_pos.map(|p| json!({ "x": p.x, "y": p.y })),
            "elapsed_ms": elapsed_ms,
        }))
    }

    async fn handle_mouse_move(&self, params: Value) -> Result<Value> {
        let x = params
            .get("x")
            .and_then(|v| v.as_i64())
            .ok_or_else(|| anyhow::anyhow!("Missing 'x' coordinate"))? as i32;
        let y = params
            .get("y")
            .and_then(|v| v.as_i64())
            .ok_or_else(|| anyhow::anyhow!("Missing 'y' coordinate"))? as i32;

        let input = self.input.lock().await;
        let res = input.move_to(x, y).await?;
        Ok(serde_json::to_value(res)?)
    }

    async fn handle_mouse_click(&self, params: Value) -> Result<Value> {
        let x = params.get("x").and_then(|v| v.as_i64()).map(|v| v as i32);
        let y = params.get("y").and_then(|v| v.as_i64()).map(|v| v as i32);
        let button = params
            .get("button")
            .and_then(|v| v.as_str())
            .unwrap_or("left");
        let count = params
            .get("click_count")
            .and_then(|v| v.as_u64())
            .unwrap_or(1) as u32;

        let mut input = self.input.lock().await;
        let res = input.click(x, y, button, count).await?;
        Ok(serde_json::to_value(res)?)
    }

    async fn handle_mouse_scroll(&self, params: Value) -> Result<Value> {
        let direction = params
            .get("direction")
            .and_then(|v| v.as_str())
            .unwrap_or("down");
        let amount = params
            .get("amount")
            .and_then(|v| v.as_i64())
            .unwrap_or(3) as i32;
        let x = params.get("x").and_then(|v| v.as_i64()).map(|v| v as i32);
        let y = params.get("y").and_then(|v| v.as_i64()).map(|v| v as i32);

        let mut input = self.input.lock().await;
        let res = input.scroll(direction, amount, x, y).await?;
        Ok(serde_json::to_value(res)?)
    }

    async fn handle_keyboard_type(&self, params: Value) -> Result<Value> {
        let text = params
            .get("text")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'text' parameter"))?;

        let input = self.input.lock().await;
        let res = input.type_text(text).await?;
        Ok(serde_json::to_value(res)?)
    }

    async fn handle_keyboard_key(&self, params: Value) -> Result<Value> {
        let keys = params
            .get("keys")
            .or_else(|| params.get("key"))
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'keys' parameter"))?;

        let input = self.input.lock().await;
        let res = input.key_combo(keys).await?;
        Ok(serde_json::to_value(res)?)
    }

    async fn handle_reanchor_coordinate(&self, params: Value) -> Result<Value> {
        let window_address = params
            .get("window_address")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'window_address'"))?;

        let dx = params
            .get("dx")
            .and_then(|v| v.as_i64())
            .ok_or_else(|| anyhow::anyhow!("Missing 'dx'"))? as i32;

        let dy = params
            .get("dy")
            .and_then(|v| v.as_i64())
            .ok_or_else(|| anyhow::anyhow!("Missing 'dy'"))? as i32;

        // Fetch live bounds of this window
        let windows = self.compositor.get_windows().await?;
        let win = windows
            .iter()
            .find(|w| w.address == window_address)
            .ok_or_else(|| anyhow::anyhow!("Window '{}' not found on current desktop", window_address))?;

        let target = CoordinateEngine::resolve_target(window_address, dx, dy, &win.bounds)?;
        Ok(serde_json::to_value(target)?)
    }

    async fn handle_system_session(&self, params: Value) -> Result<Value> {
        let start = Instant::now();
        let cmd = params
            .get("command")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'command' parameter (lock/suspend/hibernate/reboot/poweroff)"))?;

        match cmd.to_lowercase().as_str() {
            "lock" => self.system.lock().await?,
            "suspend" => self.system.suspend().await?,
            "hibernate" => self.system.hibernate().await?,
            "reboot" => self.system.reboot().await?,
            "poweroff" | "power_off" | "shutdown" => self.system.power_off().await?,
            other => bail!("Unknown system command: {}", other),
        }

        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
        Ok(json!({
            "ok": true,
            "action": "system_session",
            "command": cmd,
            "elapsed_ms": elapsed_ms,
        }))
    }

    async fn handle_media_control(&self, params: Value) -> Result<Value> {
        let start = Instant::now();
        let cmd = params
            .get("command")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'command' parameter"))?;

        let mut data = Value::Null;

        match cmd.to_lowercase().as_str() {
            "play_pause" | "toggle" => self.media.play_pause().await?,
            "next" => self.media.next().await?,
            "prev" | "previous" => self.media.previous().await?,
            "volume_up" => self.media.volume_up().await?,
            "volume_down" => self.media.volume_down().await?,
            "mute" | "mute_toggle" => self.media.volume_mute_toggle().await?,
            "get_state" | "status" => {
                let state = self.media.get_state().await?;
                data = serde_json::to_value(state)?;
            }
            other => bail!("Unknown media command: {}", other),
        }

        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
        Ok(json!({
            "ok": true,
            "action": "media_control",
            "command": cmd,
            "data": data,
            "elapsed_ms": elapsed_ms,
        }))
    }
}
