#[cfg(target_os = "windows")]
#[path = "../../../../windows/src-tauri/src/platform/windows.rs"]
mod platform_impl;

#[cfg(not(target_os = "windows"))]
#[path = "../../../../linux/src-tauri/src/platform/linux.rs"]
mod platform_impl;

#[cfg(target_os = "windows")]
#[path = "../../../../windows/src-tauri/src/platform/power.rs"]
mod power_impl;

#[cfg(not(target_os = "windows"))]
#[path = "../../../../linux/src-tauri/src/platform/power.rs"]
mod power_impl;

pub use platform_impl::{click_screen_point_impl, scroll_at_point_impl, type_text_impl, start_global_click_listener, configure_overlay_passthrough, set_window_capture_exclusion, open_url_impl};
#[cfg(target_os = "windows")]
pub use platform_impl::GlobalClick;
pub use power_impl::*;
