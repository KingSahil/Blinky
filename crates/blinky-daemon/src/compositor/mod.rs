pub mod hyprland;

use crate::protocol::models::{CursorPosition, MonitorInfo, WindowInfo};
use anyhow::Result;
use async_trait::async_trait;

#[async_trait]
pub trait Compositor: Send + Sync {
    async fn name(&self) -> &'static str;
    async fn is_available(&self) -> bool;
    async fn get_monitors(&self) -> Result<Vec<MonitorInfo>>;
    async fn get_windows(&self) -> Result<Vec<WindowInfo>>;
    async fn get_active_window(&self) -> Result<Option<WindowInfo>>;
    async fn get_cursor_position(&self) -> Result<CursorPosition>;
    async fn move_cursor(&self, x: i32, y: i32) -> Result<()>;
    async fn focus_window(&self, address: &str) -> Result<()>;
}
