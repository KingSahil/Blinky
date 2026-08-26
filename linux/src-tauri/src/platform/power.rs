use std::process::Command;

// Power/volume/lock/screenshot for Blinky on Linux.
//
// Hyprland-first (roadmap phase 6), but every command degrades gracefully:
// - power: systemctl (any distro with systemd)
// - volume: pactl (PipeWire/PulseAudio — universal on modern distros);
//   amixer dropped (ALSA-only, and pactl covers it)
// - lock: hyprctl (Hyprland) → loginctl (any systemd session)
// - screenshot: grim (wlroots) → gnome-screenshot/spectacle fallbacks (other DEs)

pub fn execute_power_off() {
    if let Err(e) = Command::new("systemctl").arg("poweroff").spawn() {
        eprintln!("Failed to execute Linux/Unix poweroff: {:?}", e);
    }
}

pub fn execute_restart() {
    if let Err(e) = Command::new("systemctl").arg("reboot").spawn() {
        eprintln!("Failed to execute Linux/Unix reboot: {:?}", e);
    }
}

pub fn execute_sleep() {
    if let Err(e) = Command::new("systemctl").arg("suspend").spawn() {
        eprintln!("Failed to execute Linux/Unix suspend: {:?}", e);
    }
}

pub fn execute_volume_up() {
    let _ = Command::new("pactl")
        .args(&["set-sink-volume", "@DEFAULT_SINK@", "+5%"])
        .spawn();
}

pub fn execute_volume_down() {
    let _ = Command::new("pactl")
        .args(&["set-sink-volume", "@DEFAULT_SINK@", "-5%"])
        .spawn();
}

pub fn execute_volume_mute() {
    let _ = Command::new("pactl")
        .args(&["set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        .spawn();
}

pub fn execute_lock() {
    // Hyprland-native lock first (swaylock/hyprlock via the compositor),
    // then loginctl for any systemd session, then DE-specific fallbacks.
    let _ = Command::new("hyprctl").args(&["dispatch", "lock"]).spawn();
    let _ = Command::new("loginctl").args(&["lock-session"]).spawn();
    let _ = Command::new("xdg-screensaver").arg("lock").spawn();
    let _ = Command::new("gnome-screensaver-command").arg("-l").spawn();
}

pub fn execute_screenshot() {
    // grim is headless + prompt-free on wlroots (Hyprland); fall back to
    // DE screenshot tools elsewhere (they may pop a UI — acceptable).
    let _ = Command::new("grim").spawn();
    let _ = Command::new("gnome-screenshot").arg("-i").spawn();
    let _ = Command::new("spectacle").spawn();
}
