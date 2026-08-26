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

pub use platform_impl::{
    click_screen_point_impl, configure_overlay_passthrough, open_url_impl, register_exit_cursor_restorer,
    scroll_at_point_impl, set_system_cursor_visibility, set_window_capture_exclusion,
    start_global_click_listener, type_text_impl,
};
// execute_volume_* live in the per-OS power module (power.rs), not platform_impl.
pub use power_impl::*;


