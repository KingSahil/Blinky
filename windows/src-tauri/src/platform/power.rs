use std::process::Command;

pub fn execute_power_off() {
    if let Err(e) = Command::new("shutdown").args(&["/s", "/t", "0"]).spawn() {
        eprintln!("Failed to execute Windows shutdown: {:?}", e);
    }
}

pub fn execute_restart() {
    if let Err(e) = Command::new("shutdown").args(&["/r", "/t", "0"]).spawn() {
        eprintln!("Failed to execute Windows restart: {:?}", e);
    }
}

pub fn execute_sleep() {
    if let Err(e) = Command::new("rundll32.exe")
        .args(&["powrprof.dll,SetSuspendState", "0", "1", "0"])
        .spawn()
    {
        eprintln!("Failed to execute Windows sleep: {:?}", e);
    }
}

pub fn execute_lock() {
    if let Err(e) = Command::new("rundll32.exe")
        .args(&["user32.dll,LockWorkStation"])
        .spawn()
    {
        eprintln!("Failed to execute Windows lock: {:?}", e);
    }
}

pub fn execute_screenshot() {
    if let Err(e) = Command::new("snippingtool")
        .arg("/clip")
        .spawn()
    {
        eprintln!("Failed to execute Windows screenshot: {:?}", e);
    }
}

fn send_keypress(vk: u16) -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP,
    };
    let mut inputs = [
        INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: vk,
                    wScan: 0,
                    dwFlags: 0,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        },
        INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: vk,
                    wScan: 0,
                    dwFlags: KEYEVENTF_KEYUP,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        },
    ];
    let sent = unsafe {
        SendInput(
            inputs.len() as u32,
            inputs.as_mut_ptr(),
            std::mem::size_of::<INPUT>() as i32,
        )
    };
    if sent != inputs.len() as u32 {
        return Err(format!("SendInput sent {sent} of {} events", inputs.len()));
    }
    Ok(())
}

pub fn execute_volume_up() {
    let _ = send_keypress(0xAF);
}

pub fn execute_volume_down() {
    let _ = send_keypress(0xAE);
}

pub fn execute_volume_mute() {
    let _ = send_keypress(0xAD);
}


