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

/// Requests immediate system hibernation through the Windows shutdown utility.
pub fn execute_hibernate() {
    if let Err(e) = Command::new("shutdown").args(&["/h"]).spawn() {
        eprintln!("Failed to execute Windows hibernate: {:?}", e);
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

pub fn is_workstation_locked() -> bool {
    use windows_sys::Win32::System::StationsAndDesktops::{CloseDesktop, OpenInputDesktop};
    let desk = unsafe { OpenInputDesktop(0, 0, 0x0100) };
    if desk.is_null() {
        true
    } else {
        unsafe {
            CloseDesktop(desk);
        }
        false
    }
}

/// Wakes display, dismisses the Windows lock screen curtain, and injects optional PIN/credentials.
pub fn execute_unlock(pin: Option<&str>) {
    // 1. Force the system and display out of standby/low-power state
    unsafe {
        use windows_sys::Win32::System::Power::{
            SetThreadExecutionState, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED,
        };
        SetThreadExecutionState(ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED);
    }

    // 2. Synthetic mouse jitter to wake monitors and trigger input subsystem
    let _ = wake_monitors_mouse_jitter();

    // 3. Spawn a background worker to dismiss the curtain and type PIN if supplied
    let pin_owned = pin.map(|s| s.to_string());
    std::thread::spawn(move || {
        use std::thread::sleep;
        use std::time::Duration;

        // Brief delay to allow screens to power on
        sleep(Duration::from_millis(150));

        // Spacebar to dismiss lock screen curtain and show PIN/password field
        let _ = send_keypress(0x20);

        // If a PIN is provided, wait for the login field to focus, then type it
        if let Some(pin_str) = pin_owned {
            if !pin_str.trim().is_empty() {
                sleep(Duration::from_millis(350));
                for ch in pin_str.chars() {
                    let _ = send_unicode_char(ch);
                    sleep(Duration::from_millis(25));
                }
                sleep(Duration::from_millis(50));
                // Enter to submit
                let _ = send_keypress(0x0D);
            }
        }
    });
}

fn wake_monitors_mouse_jitter() -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_MOUSE, MOUSEEVENTF_MOVE, MOUSEINPUT,
    };
    let mut inputs = [
        INPUT {
            r#type: INPUT_MOUSE,
            Anonymous: windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                mi: MOUSEINPUT {
                    dx: 1,
                    dy: 0,
                    mouseData: 0,
                    dwFlags: MOUSEEVENTF_MOVE,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        },
        INPUT {
            r#type: INPUT_MOUSE,
            Anonymous: windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                mi: MOUSEINPUT {
                    dx: -1,
                    dy: 0,
                    mouseData: 0,
                    dwFlags: MOUSEEVENTF_MOVE,
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
        return Err(format!("SendInput mouse jitter sent {sent} of {} events", inputs.len()));
    }
    Ok(())
}

fn send_unicode_char(ch: char) -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE,
    };
    let mut utf16_buf = [0u16; 2];
    let encoded = ch.encode_utf16(&mut utf16_buf);
    for &code_unit in encoded.iter() {
        let mut inputs = [
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: 0,
                        wScan: code_unit,
                        dwFlags: KEYEVENTF_UNICODE,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: 0,
                        wScan: code_unit,
                        dwFlags: KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
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
            return Err(format!("SendInput unicode char sent {sent} of {} events", inputs.len()));
        }
    }
    Ok(())
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

