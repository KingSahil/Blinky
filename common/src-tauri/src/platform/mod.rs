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
    click_screen_point_impl, configure_overlay_passthrough, open_url_impl, scroll_at_point_impl,
    set_window_capture_exclusion, start_global_click_listener, type_text_impl,
    execute_volume_up, execute_volume_down, execute_volume_mute,
};
pub use power_impl::*;
