use serde::Serialize;
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, WebviewWindow};

#[derive(Clone, Serialize)]
pub struct GlobalClick {
    pub x: i32,
    pub y: i32,
    pub overlay_x: i32,
    pub overlay_y: i32,
    pub scale_factor: f64,
}

pub fn click_screen_point_impl(x: i32, y: i32) -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
        MOUSEEVENTF_MOVE, MOUSEEVENTF_VIRTUALDESK,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetSystemMetrics, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN, SM_XVIRTUALSCREEN,
        SM_YVIRTUALSCREEN,
    };

    let left = unsafe { GetSystemMetrics(SM_XVIRTUALSCREEN) };
    let top = unsafe { GetSystemMetrics(SM_YVIRTUALSCREEN) };
    let width = unsafe { GetSystemMetrics(SM_CXVIRTUALSCREEN) };
    let height = unsafe { GetSystemMetrics(SM_CYVIRTUALSCREEN) };
    if width <= 1 || height <= 1 {
        return Err("Cannot determine virtual screen size".to_string());
    }

    let absolute_x = ((x - left) as i64 * 65535 / (width - 1) as i64) as i32;
    let absolute_y = ((y - top) as i64 * 65535 / (height - 1) as i64) as i32;
    let flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;
    let mut inputs = [
        mouse_input(absolute_x, absolute_y, flags | MOUSEEVENTF_MOVE),
        mouse_input(absolute_x, absolute_y, flags | MOUSEEVENTF_LEFTDOWN),
        mouse_input(absolute_x, absolute_y, flags | MOUSEEVENTF_LEFTUP),
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

fn mouse_input(
    dx: i32,
    dy: i32,
    flags: u32,
) -> windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        INPUT, INPUT_0, INPUT_MOUSE, MOUSEINPUT,
    };

    INPUT {
        r#type: INPUT_MOUSE,
        Anonymous: INPUT_0 {
            mi: MOUSEINPUT {
                dx,
                dy,
                mouseData: 0,
                dwFlags: flags,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    }
}

pub fn scroll_at_point_impl(x: i32, y: i32, direction: &str, amount: i32) -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_MOUSE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_MOVE,
        MOUSEEVENTF_VIRTUALDESK, MOUSEEVENTF_WHEEL, MOUSEINPUT,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetSystemMetrics, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN, SM_XVIRTUALSCREEN,
        SM_YVIRTUALSCREEN,
    };

    let left = unsafe { GetSystemMetrics(SM_XVIRTUALSCREEN) };
    let top = unsafe { GetSystemMetrics(SM_YVIRTUALSCREEN) };
    let width = unsafe { GetSystemMetrics(SM_CXVIRTUALSCREEN) };
    let height = unsafe { GetSystemMetrics(SM_CYVIRTUALSCREEN) };
    if width <= 1 || height <= 1 {
        return Err("Cannot determine virtual screen size".to_string());
    }

    let absolute_x = ((x - left) as i64 * 65535 / (width - 1) as i64) as i32;
    let absolute_y = ((y - top) as i64 * 65535 / (height - 1) as i64) as i32;
    let flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;

    let wheel_delta = 120;
    let scroll_amount = if direction.eq_ignore_ascii_case("down") {
        -wheel_delta * amount
    } else {
        wheel_delta * amount
    };

    let mut inputs = [
        INPUT {
            r#type: INPUT_MOUSE,
            Anonymous: INPUT_0 {
                mi: MOUSEINPUT {
                    dx: absolute_x,
                    dy: absolute_y,
                    mouseData: 0,
                    dwFlags: flags | MOUSEEVENTF_MOVE,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        },
        INPUT {
            r#type: INPUT_MOUSE,
            Anonymous: INPUT_0 {
                mi: MOUSEINPUT {
                    dx: 0,
                    dy: 0,
                    mouseData: scroll_amount as u32,
                    dwFlags: MOUSEEVENTF_WHEEL,
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

impl GlobalClick {
    pub fn with_overlay_metrics(mut self, overlay: &WebviewWindow) -> Self {
        if let Ok(position) = overlay.outer_position() {
            self.overlay_x = position.x;
            self.overlay_y = position.y;
        }
        self.scale_factor = overlay.scale_factor().unwrap_or(1.0);
        self
    }
}

pub fn read_mouse_click(
    was_left_down: &mut bool,
    was_right_down: &mut bool,
) -> Option<GlobalClick> {
    use windows_sys::Win32::Foundation::POINT;
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        GetAsyncKeyState, VK_LBUTTON, VK_RBUTTON,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::GetCursorPos;

    let is_left_down = unsafe { (GetAsyncKeyState(VK_LBUTTON as i32) & 0x8000u16 as i16) != 0 };
    let is_right_down = unsafe { (GetAsyncKeyState(VK_RBUTTON as i32) & 0x8000u16 as i16) != 0 };
    let clicked = (is_left_down && !*was_left_down) || (is_right_down && !*was_right_down);
    *was_left_down = is_left_down;
    *was_right_down = is_right_down;

    if !clicked {
        return None;
    }

    let mut point = POINT { x: 0, y: 0 };
    let ok = unsafe { GetCursorPos(&mut point) };
    if ok == 0 {
        return None;
    }

    Some(GlobalClick {
        x: point.x,
        y: point.y,
        overlay_x: 0,
        overlay_y: 0,
        scale_factor: 1.0,
    })
}

pub fn read_enter_key(was_enter_down: &mut bool) -> Option<()> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_RETURN};

    let is_enter_down = unsafe { (GetAsyncKeyState(VK_RETURN as i32) & 0x8000u16 as i16) != 0 };
    let pressed = is_enter_down && !*was_enter_down;
    *was_enter_down = is_enter_down;

    if pressed {
        Some(())
    } else {
        None
    }
}

pub fn type_text_impl(text: &str, press_enter: bool) -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE,
    };

    let mut inputs = Vec::new();
    for c in text.encode_utf16() {
        inputs.push(keyboard_input_unicode(c, KEYEVENTF_UNICODE));
        inputs.push(keyboard_input_unicode(
            c,
            KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
        ));
    }

    if !inputs.is_empty() {
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
    }

    if press_enter {
        thread::sleep(Duration::from_millis(100));
        send_keypress(0x0D)?;
    }

    Ok(())
}

fn keyboard_input_unicode(
    wscan: u16,
    flags: u32,
) -> windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT,
    };
    INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: 0,
                wScan: wscan,
                dwFlags: flags,
                time: 0,
                dwExtraInfo: 0,
            },
        },
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

pub fn start_global_click_listener(app: AppHandle) {
    thread::spawn(move || {
        let mut was_left_down = false;
        let mut was_right_down = false;
        let mut was_enter_down = false;

        loop {
            if let Some(click) = read_mouse_click(&mut was_left_down, &mut was_right_down) {
                if let Some(overlay) = app.get_webview_window("overlay") {
                    if overlay.is_visible().unwrap_or(false) {
                        let click = click.with_overlay_metrics(&overlay);
                        let _ = overlay.emit("blinky://global-click", click);
                    }
                }
            }

            if let Some(()) = read_enter_key(&mut was_enter_down) {
                let _ = app.emit("blinky://global-enter", ());
            }

            thread::sleep(Duration::from_millis(16));
        }
    });
}

pub fn configure_overlay_passthrough(window: &WebviewWindow) {
    use windows_sys::Win32::Foundation::HWND;
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetWindowLongW, SetWindowLongW, GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TOOLWINDOW,
        WS_EX_TRANSPARENT,
    };

    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten());
    if let Some(monitor) = monitor {
        let size = monitor.size();
        let position = monitor.position();
        let _ = window.set_size(tauri::Size::Physical(tauri::PhysicalSize {
            width: size.width,
            height: size.height,
        }));
        let _ = window.set_position(tauri::Position::Physical(tauri::PhysicalPosition {
            x: position.x,
            y: position.y,
        }));
    }

    if let Ok(hwnd) = window.hwnd() {
        unsafe {
            let hwnd = hwnd.0 as HWND;
            let style = GetWindowLongW(hwnd, GWL_EXSTYLE);
            SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                style | WS_EX_TRANSPARENT as i32 | WS_EX_LAYERED as i32 | WS_EX_TOOLWINDOW as i32,
            );
        }
    }
}

pub fn set_window_capture_exclusion(window: &WebviewWindow, exclude: bool) {
    use windows_sys::Win32::Foundation::HWND;
    use windows_sys::Win32::UI::WindowsAndMessaging::SetWindowDisplayAffinity;

    if let Ok(hwnd) = window.hwnd() {
        unsafe {
            let hwnd = hwnd.0 as HWND;
            let affinity = if exclude { 0x00000011 } else { 0x00000000 };
            let _ = SetWindowDisplayAffinity(hwnd, affinity);
        }
    }
}

pub fn open_url_impl(url: &str) -> Result<(), String> {
    let mut command = std::process::Command::new("rundll32");
    command.arg("url.dll,FileProtocolHandler").arg(url);
    command
        .spawn()
        .map_err(|err| format!("Failed to open link in default browser: {err}"))?;
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
