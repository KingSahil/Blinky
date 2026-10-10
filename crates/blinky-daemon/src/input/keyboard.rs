use anyhow::{bail, Context, Result};
use tokio::process::Command;
use tracing::debug;

fn normalize_key(k: &str) -> &str {
    match k {
        "enter" | "return" => "Return",
        "esc" | "escape" => "Escape",
        "tab" => "Tab",
        "space" => "space",
        "backspace" => "BackSpace",
        "del" | "delete" => "Delete",
        "up" => "Up",
        "down" => "Down",
        "left" => "Left",
        "right" => "Right",
        "home" => "Home",
        "end" => "End",
        "pageup" | "page_up" => "Page_Up",
        "pagedown" | "page_down" => "Page_Down",
        other => other,
    }
}

fn normalize_mod(m: &str) -> &str {
    match m {
        "ctrl" | "control" => "ctrl",
        "shift" => "shift",
        "alt" => "alt",
        "super" | "meta" | "win" => "logo",
        other => other,
    }
}

pub async fn type_text(text: &str) -> Result<()> {
    if text.is_empty() {
        return Ok(());
    }

    // 1. Try wtype (wlroots native)
    let wtype_res = Command::new("wtype").arg(text).output().await;

    if let Ok(output) = wtype_res {
        if output.status.success() {
            debug!("Typed {} chars via wtype", text.len());
            return Ok(());
        }
    }

    // 2. Fallback to ydotool type
    let ydo_output = Command::new("ydotool")
        .args(["type", "--", text])
        .output()
        .await
        .context("Failed to spawn ydotool type")?;

    if !ydo_output.status.success() {
        let stderr = String::from_utf8_lossy(&ydo_output.stderr);
        bail!("Failed to type text via ydotool: {}", stderr);
    }

    debug!("Typed {} chars via ydotool", text.len());
    Ok(())
}

pub async fn press_key_combo(keys: &str) -> Result<()> {
    let key_lower = keys.trim().to_lowercase();
    let parts: Vec<&str> = key_lower
        .split('+')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();

    if parts.is_empty() {
        return Ok(());
    }

    // 1. Try wtype
    let mut cmd = Command::new("wtype");
    if parts.len() == 1 {
        let k = normalize_key(parts[0]);
        cmd.args(["-k", k]);
    } else {
        let mods = &parts[..parts.len() - 1];
        let final_key = normalize_key(parts[parts.len() - 1]);

        for m in mods {
            cmd.args(["-M", normalize_mod(m)]);
        }
        cmd.args(["-k", final_key]);
        for m in mods.iter().rev() {
            cmd.args(["-m", normalize_mod(m)]);
        }
    }

    if let Ok(output) = cmd.output().await {
        if output.status.success() {
            debug!("Pressed key combo '{}' via wtype", keys);
            return Ok(());
        }
    }

    // 2. Fallback to ydotool key
    let ydo_output = Command::new("ydotool")
        .args(["key", &key_lower])
        .output()
        .await
        .context("Failed to run ydotool key")?;

    if !ydo_output.status.success() {
        let stderr = String::from_utf8_lossy(&ydo_output.stderr);
        bail!("Failed to press key combo '{}': {}", keys, stderr);
    }

    Ok(())
}
