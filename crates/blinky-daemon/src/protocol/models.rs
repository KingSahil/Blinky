use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CaptureKind {
    Fullscreen,
    Window,
    Region,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UIElement {
    pub ref_id: String,
    pub text: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub confidence: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
}

impl UIElement {
    pub fn center(&self) -> (i32, i32) {
        (
            self.x + (self.width as i32 / 2),
            self.y + (self.height as i32 / 2),
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FrameDescriptor {
    pub frame_id: String,
    pub capture_kind: CaptureKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub window_address: Option<String>,
    pub source_bounds: WindowBounds,
    pub image_width: u32,
    pub image_height: u32,
    pub scale: f64,
    pub monitor_id: i64,
    pub timestamp_ms: u64,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub elements: Vec<UIElement>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MonitorInfo {
    pub id: i64,
    pub name: String,
    pub description: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub refresh_rate: f64,
    pub scale: f64,
    pub focused: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct WindowBounds {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

impl WindowBounds {
    pub fn contains_point(&self, px: i32, py: i32) -> bool {
        px >= self.x
            && px < self.x + self.width as i32
            && py >= self.y
            && py < self.y + self.height as i32
    }

    pub fn center(&self) -> (i32, i32) {
        (
            self.x + (self.width as i32 / 2),
            self.y + (self.height as i32 / 2),
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WindowInfo {
    pub address: String,
    pub title: String,
    pub class: String,
    pub initial_class: String,
    pub pid: Option<u32>,
    pub bounds: WindowBounds,
    pub monitor_id: i64,
    pub workspace_id: i64,
    pub focused: bool,
    pub floating: bool,
    pub fullscreen: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct CursorPosition {
    pub x: i32,
    pub y: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AppEntry {
    pub name: String,
    pub desktop_id: String,
    pub exec_line: String,
    pub path: String,
    pub startup_wm_class: String,
    pub categories: Vec<String>,
    pub icon: String,
    pub source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CaptureResult {
    pub path: String,
    pub width: u32,
    pub height: u32,
    pub screen_width: u32,
    pub screen_height: u32,
    pub scale: f64,
    pub elapsed_ms: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frame: Option<FrameDescriptor>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AnchoredTarget {
    pub target_x: i32,
    pub target_y: i32,
    pub window_address: Option<String>,
    pub relative_dx: i32,
    pub relative_dy: i32,
    pub current_bounds: Option<WindowBounds>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ActionResult {
    pub ok: bool,
    pub action: String,
    pub message: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
    pub elapsed_ms: f64,
}
