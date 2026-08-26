use std::process::Command;
use tauri::WebviewWindow;

/// Physical input for Blinky on Linux (Hyprland-first, compositor-agnostic
/// injection primitives).
///
/// Design (per docs/LINUX-PORT-ROADMAP.md):
/// - **Cursor positioning** uses the compositor's native dispatcher
///   (`hl.dsp.cursor.move` on Hyprland) — pixel-exact and immune to libinput
///   pointer acceleration, which corrupts ydotool's REL-based absolute
///   emulation on large jumps.
/// - **Click/wheel/key injection** uses ydotool (uinput) — kernel-level,
///   identical on every compositor. Typing uses wtype (wlroots-native).
///
/// The only compositor-dependent piece is cursor positioning; when GNOME/KDE
/// backends land (phase 8), only that function changes.

pub fn click_screen_point_impl(x: i32, y: i32) -> Result<(), String> {
    move_cursor(x, y)?;
    // ydotool click 0xC0 = left button down+up
    Command::new("ydotool")
        .args(["click", "0xC0"])
        .spawn()
        .map_err(|err| format!("Failed to run ydotool click: {err}"))?;
    Ok(())
}

pub fn scroll_at_point_impl(x: i32, y: i32, direction: &str, amount: i32) -> Result<(), String> {
    move_cursor(x, y)?;
    let amount = amount.clamp(1, 20);
    // REL_WHEEL: up = +amount, down = -amount; REL_HWHEEL: left/right
    let (dx, dy): (i32, i32) = match direction {
        "up" => (0, amount),
        "down" => (0, -amount),
        "left" => (-amount, 0),
        "right" => (amount, 0),
        other => return Err(format!("Unknown scroll direction: {other}")),
    };
    Command::new("ydotool")
        .args(["mousemove", "-w", "--", &dx.to_string(), &dy.to_string()])
        .spawn()
        .map_err(|err| format!("Failed to run ydotool mousemove: {err}"))?;
    Ok(())
}

pub fn type_text_impl(text: &str, press_enter: bool) -> Result<(), String> {
    if !text.is_empty() {
        Command::new("wtype")
            .arg(text)
            .spawn()
            .map_err(|err| format!("Failed to run wtype: {err}"))?;
    }
    if press_enter {
        Command::new("wtype")
            .args(["-k", "Return"])
            .spawn()
            .map_err(|err| format!("Failed to run wtype enter: {err}"))?;
    }
    Ok(())
}

/// Move the pointer to absolute logical (x, y) via the compositor dispatcher.
fn move_cursor(x: i32, y: i32) -> Result<(), String> {
    // Hyprland 0.56+: `hyprctl eval 'hl.dispatch(hl.dsp.cursor.move({ x, y }))'`
    let script = format!("hl.dispatch(hl.dsp.cursor.move({{ x = {x}, y = {y} }}))");
    let output = Command::new("hyprctl")
        .args(["eval", &script])
        .output()
        .map_err(|err| format!("Failed to run hyprctl eval: {err}"))?;
    if !output.status.success() {
        return Err(format!(
            "hyprctl cursor move failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(())
}

pub fn configure_overlay_passthrough(window: &WebviewWindow) {
    let _ = window.set_ignore_cursor_events(true);
    let _ = window.set_fullscreen(true);

    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten());

    if let Some(monitor) = monitor {
        let size = monitor.size();
        let _ = window.set_size(tauri::Size::Physical(*size));
        let _ = window.set_position(tauri::Position::Physical(tauri::PhysicalPosition {
            x: 0,
            y: 0,
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

pub fn set_system_cursor_visibility(_visible: bool) {
    // No-op on Linux
}

