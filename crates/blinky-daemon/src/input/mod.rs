pub mod keyboard;
pub mod uinput;

use crate::compositor::Compositor;
use crate::protocol::models::ActionResult;
use anyhow::{Context, Result};
use std::sync::Arc;
use std::time::Instant;
use tracing::info;

pub struct InputActuator {
    compositor: Arc<dyn Compositor>,
    mouse: uinput::VirtualMouse,
}

impl InputActuator {
    pub fn new(compositor: Arc<dyn Compositor>) -> Result<Self> {
        let mouse = uinput::VirtualMouse::new().context("Failed to initialize virtual mouse device")?;
        Ok(Self { compositor, mouse })
    }

    pub async fn move_to(&self, x: i32, y: i32) -> Result<ActionResult> {
        let start = Instant::now();
        self.compositor.move_cursor(x, y).await?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
        info!("Moved cursor to ({}, {}) in {:.2}ms", x, y, elapsed_ms);

        Ok(ActionResult {
            ok: true,
            action: "mouse_move".to_string(),
            message: format!("Moved cursor to ({}, {})", x, y),
            data: Some(serde_json::json!({ "x": x, "y": y })),
            elapsed_ms,
        })
    }

    pub async fn click(
        &mut self,
        x: Option<i32>,
        y: Option<i32>,
        button: &str,
        click_count: u32,
    ) -> Result<ActionResult> {
        let start = Instant::now();
        if let (Some(x_val), Some(y_val)) = (x, y) {
            self.compositor.move_cursor(x_val, y_val).await?;
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }

        self.mouse.click(button, click_count)?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
        info!(
            "Clicked {} (x{}) at ({:?}, {:?}) in {:.2}ms",
            button, click_count, x, y, elapsed_ms
        );

        Ok(ActionResult {
            ok: true,
            action: "click".to_string(),
            message: format!("Clicked {} x{}", button, click_count),
            data: Some(serde_json::json!({ "x": x, "y": y, "button": button, "count": click_count })),
            elapsed_ms,
        })
    }

    pub async fn scroll(
        &mut self,
        direction: &str,
        amount: i32,
        x: Option<i32>,
        y: Option<i32>,
    ) -> Result<ActionResult> {
        let start = Instant::now();
        if let (Some(x_val), Some(y_val)) = (x, y) {
            self.compositor.move_cursor(x_val, y_val).await?;
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }

        let clamped = amount.clamp(1, 20);
        let (dx, dy) = match direction.to_lowercase().as_str() {
            "up" => (0, clamped),
            "down" => (0, -clamped),
            "left" => (-clamped, 0),
            "right" => (clamped, 0),
            other => anyhow::bail!("Unknown scroll direction: {}", other),
        };

        self.mouse.scroll(dx, dy)?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
        info!("Scrolled {} x{} in {:.2}ms", direction, amount, elapsed_ms);

        Ok(ActionResult {
            ok: true,
            action: "scroll".to_string(),
            message: format!("Scrolled {} x{}", direction, amount),
            data: Some(serde_json::json!({ "direction": direction, "amount": amount })),
            elapsed_ms,
        })
    }

    pub async fn type_text(&self, text: &str) -> Result<ActionResult> {
        let start = Instant::now();
        keyboard::type_text(text).await?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
        info!("Typed {} characters in {:.2}ms", text.len(), elapsed_ms);

        Ok(ActionResult {
            ok: true,
            action: "type_text".to_string(),
            message: format!("Typed {} characters", text.len()),
            data: Some(serde_json::json!({ "length": text.len() })),
            elapsed_ms,
        })
    }

    pub async fn key_combo(&self, keys: &str) -> Result<ActionResult> {
        let start = Instant::now();
        keyboard::press_key_combo(keys).await?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
        info!("Pressed key combo '{}' in {:.2}ms", keys, elapsed_ms);

        Ok(ActionResult {
            ok: true,
            action: "key_combo".to_string(),
            message: format!("Pressed key combo '{}'", keys),
            data: Some(serde_json::json!({ "keys": keys })),
            elapsed_ms,
        })
    }
}
