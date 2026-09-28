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

/// Wakes display, dismisses the Windows lock screen curtain, and injects PIN using CredentialProviderPipe or Win32 input model.
pub fn execute_unlock(pin: Option<&str>) {
    println!("blinky: execute_unlock invoked (pin_provided: {})", pin.is_some());

    // 1. Force the system and display out of standby/low-power state
    unsafe {
        use windows_sys::Win32::System::Power::{
            SetThreadExecutionState, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED,
        };
        SetThreadExecutionState(ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED);
    }

    // 2. Synthetic mouse jitter to wake monitors
    let _ = wake_monitors_mouse_jitter();

    // 3. Spawn background thread for the automated unlock sequence
    let pin_owned = pin.map(|s| s.to_string());
    std::thread::spawn(move || {
        use std::thread::sleep;
        use std::time::Duration;

        // Wake display and dismiss lock screen curtain (requires pulsing across monitor wake latency)
        let _ = send_mouse_click();
        sleep(Duration::from_millis(250));
        let _ = send_vk_key(0x20, false); // Spacebar
        sleep(Duration::from_millis(350));
        let _ = send_vk_key(0x0D, false); // Enter
        sleep(Duration::from_millis(300));

        if let Some(ref pin_str) = pin_owned {
            let trimmed = pin_str.trim();
            if !trimmed.is_empty() {
                // Primary unlock: Windows Credential Provider (named pipe into LogonUI)
                match try_named_pipe_unlock(trimmed) {
                    Ok(()) => {
                        println!("blinky: Workstation successfully unlocked via CredentialProviderPipe!");
                        return;
                    }
                    Err(err) => {
                        println!("blinky: Named pipe unlock attempt: {err}. Falling back to virtual input...");
                    }
                }

                // Fallback: If Credential Provider is not registered or failed, wait for curtain animation
                // and attempt virtual key typing
                sleep(Duration::from_millis(500));
                let _ = send_vk_key(0x1B, false); // VK_ESCAPE
                sleep(Duration::from_millis(150));
                let _ = send_vk_key(0x20, false); // VK_SPACE
                sleep(Duration::from_millis(250));

                for _ in 0..6 {
                    let _ = send_vk_key(0x08, false); // VK_BACK
                    sleep(Duration::from_millis(25));
                }
                sleep(Duration::from_millis(60));

                for ch in trimmed.chars() {
                    let (vk, shift) = char_to_vk(ch);
                    let _ = send_vk_key(vk, shift);
                    sleep(Duration::from_millis(45));
                }

                sleep(Duration::from_millis(100));
                let _ = send_vk_key(0x0D, false); // VK_RETURN
                println!("blinky: fallback unlock sequence completed for host");
            }
        }
    });
}

fn try_named_pipe_unlock(pin_or_password: &str) -> Result<(), String> {
    use std::io::{Read, Write};
    use std::time::Duration;

    let username = std::env::var("USERNAME").unwrap_or_else(|_| "sahil".to_string());
    let domain = std::env::var("USERDOMAIN").unwrap_or_else(|_| ".".to_string());
    let pipe_path = r"\\.\pipe\CredentialProviderPipe";

    println!("blinky: attempting unlock via named pipe {pipe_path} for user '{username}' (domain: '{domain}')");

    let mut last_err = String::new();
    // Attempt connecting to the named pipe with retries (LogonUI might take up to ~3-5s to initialize upon display wake)
    for attempt in 1..=30 {
        // While waiting for LogonUI to initialize and create the pipe, pulse wake events periodically to dismiss the lock curtain
        if attempt > 1 && attempt % 3 == 0 {
            let _ = wake_monitors_mouse_jitter();
            let _ = send_mouse_click();
            let _ = send_vk_key(0x20, false); // Space
            let _ = send_vk_key(0x0D, false); // Enter
        }

        match std::fs::OpenOptions::new().read(true).write(true).open(pipe_path) {
            Ok(mut file) => {
                // Prepare candidates: try with explicit domain first, then fallback without domain
                let cmds = if !domain.is_empty() && domain != "." && !domain.eq_ignore_ascii_case(&username) {
                    vec![
                        format!("UNLOCK:{domain}\\{username}:{pin_or_password}"),
                        format!("UNLOCK:{username}:{pin_or_password}"),
                    ]
                } else {
                    vec![format!("UNLOCK:{username}:{pin_or_password}")]
                };

                for cmd in cmds {
                    println!("blinky: dispatching credential command to CredentialProviderPipe");
                    if let Err(e) = file.write_all(cmd.as_bytes()) {
                        last_err = format!("Failed to write command to pipe: {e}");
                        continue;
                    }
                    let mut resp_buf = [0u8; 64];
                    let n = file.read(&mut resp_buf).unwrap_or(0);
                    let resp_str = String::from_utf8_lossy(&resp_buf[..n]);
                    println!("blinky: CredentialProviderPipe response: {resp_str}");

                    if resp_str.starts_with("OK") {
                        // Give LogonUI time to complete logon transition and verify unlock state
                        for _ in 0..15 {
                            std::thread::sleep(Duration::from_millis(200));
                            if !is_workstation_locked() {
                                println!("blinky: Workstation confirmed unlocked!");
                                return Ok(());
                            }
                        }
                    } else {
                        last_err = format!("Unlock provider returned: {resp_str}");
                    }
                }

                if !is_workstation_locked() {
                    return Ok(());
                } else {
                    return Err(if !last_err.is_empty() { last_err } else { "LogonUI did not unlock workstation".to_string() });
                }
            }
            Err(e) => {
                last_err = e.to_string();
                if attempt == 30 {
                    println!("blinky: CredentialProviderPipe not reachable after 30 attempts ({e})");
                }
                std::thread::sleep(Duration::from_millis(250));
            }
        }
    }

    Err(format!("Named pipe \\\\.\\pipe\\CredentialProviderPipe not available ({last_err})"))
}

fn send_mouse_click() -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_MOUSE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, MOUSEINPUT,
    };
    let mut down = INPUT {
        r#type: INPUT_MOUSE,
        Anonymous: INPUT_0 {
            mi: MOUSEINPUT {
                dx: 0,
                dy: 0,
                mouseData: 0,
                dwFlags: MOUSEEVENTF_LEFTDOWN,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    };
    unsafe {
        SendInput(1, &mut down, std::mem::size_of::<INPUT>() as i32);
    }
    std::thread::sleep(std::time::Duration::from_millis(30));
    let mut up = INPUT {
        r#type: INPUT_MOUSE,
        Anonymous: INPUT_0 {
            mi: MOUSEINPUT {
                dx: 0,
                dy: 0,
                mouseData: 0,
                dwFlags: MOUSEEVENTF_LEFTUP,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    };
    unsafe {
        SendInput(1, &mut up, std::mem::size_of::<INPUT>() as i32);
    }
    Ok(())
}

fn char_to_vk(ch: char) -> (u16, bool) {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetKeyboardLayout, VkKeyScanExW};
    let layout = unsafe { GetKeyboardLayout(0) };
    let res = unsafe { VkKeyScanExW(ch as u16, layout) };
    if res != -1 {
        let vk = (res & 0xFF) as u16;
        let shift = (res & 0x100) != 0;
        (vk, shift)
    } else {
        match ch {
            '0'..='9' => (0x30 + (ch as u16 - '0' as u16), false),
            'a'..='z' => (0x41 + (ch as u16 - 'a' as u16), false),
            'A'..='Z' => (0x41 + (ch as u16 - 'A' as u16), true),
            _ => (ch as u16, false),
        }
    }
}

fn send_vk_key(vk: u16, shift: bool) -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP, VK_LSHIFT,
    };

    if shift {
        let mut shift_down = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VK_LSHIFT,
                    wScan: 0,
                    dwFlags: 0,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        unsafe {
            SendInput(1, &mut shift_down, std::mem::size_of::<INPUT>() as i32);
        }
        std::thread::sleep(std::time::Duration::from_millis(15));
    }

    let mut key_down = INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: vk,
                wScan: 0,
                dwFlags: 0,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    };
    unsafe {
        SendInput(1, &mut key_down, std::mem::size_of::<INPUT>() as i32);
    }

    std::thread::sleep(std::time::Duration::from_millis(35));

    let mut key_up = INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: vk,
                wScan: 0,
                dwFlags: KEYEVENTF_KEYUP,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    };
    unsafe {
        SendInput(1, &mut key_up, std::mem::size_of::<INPUT>() as i32);
    }

    if shift {
        std::thread::sleep(std::time::Duration::from_millis(15));
        let mut shift_up = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VK_LSHIFT,
                    wScan: 0,
                    dwFlags: KEYEVENTF_KEYUP,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        unsafe {
            SendInput(1, &mut shift_up, std::mem::size_of::<INPUT>() as i32);
        }
    }

    Ok(())
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

pub fn execute_media_play_pause() {
    let _ = send_keypress(0xB3);
}

pub fn execute_open_browser() {
    let _ = Command::new("cmd")
        .args(["/c", "start", "https://www.google.com"])
        .spawn();
}

pub fn execute_open_terminal() {
    if Command::new("wt").spawn().is_err() {
        let _ = Command::new("powershell").spawn();
    }
}

