use std::process::Command;
use tauri::WebviewWindow;

pub fn click_screen_point_impl(_x: i32, _y: i32) -> Result<(), String> {
    Err("Autopilot clicking is only implemented on Windows".to_string())
}

pub fn scroll_at_point_impl(
    _x: i32,
    _y: i32,
    _direction: &str,
    _amount: i32,
) -> Result<(), String> {
    Err("Autopilot scrolling is only implemented on Windows".to_string())
}

pub fn type_text_impl(_text: &str, _press_enter: bool) -> Result<(), String> {
    Err("Autopilot typing is only implemented on Windows".to_string())
}

pub fn configure_overlay_passthrough(window: &WebviewWindow) {
    let _ = window.set_ignore_cursor_events(true);

    if let Ok(Some(monitor)) = window.current_monitor() {
        let scale_factor = monitor.scale_factor();

        let is_gnome = std::env::var("XDG_CURRENT_DESKTOP")
            .map(|val| val.to_uppercase().contains("GNOME"))
            .unwrap_or(false);

        let bar_height = if is_gnome {
            (32.0 * scale_factor) as i32
        } else {
            0
        };

        let size = monitor.size();
        let physical_width = size.width;
        let physical_height = size.height.saturating_sub(bar_height as u32);

        let _ = window.set_size(tauri::Size::Physical(tauri::PhysicalSize {
            width: physical_width,
            height: physical_height,
        }));
        let _ = window.set_position(tauri::Position::Physical(tauri::PhysicalPosition {
            x: 0,
            y: bar_height,
        }));
    }
}

pub fn set_window_capture_exclusion(_window: &WebviewWindow, _exclude: bool) {
    // No-op on Linux
}

pub fn open_url_impl(url: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("open");
        command.arg(url);
        command
    };

    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = {
        let mut command = Command::new("xdg-open");
        command.arg(url);
        command
    };

    command
        .spawn()
        .map_err(|err| format!("Failed to open link in default browser: {err}"))?;
    Ok(())
}

pub fn start_global_click_listener<F>(_app_handle: F)
where
    F: Send + Clone + 'static,
{
    // No-op on Linux to avoid CPU spinning
}
