use serde::{Deserialize, Serialize};
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, WebviewWindow, WindowEvent,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

#[derive(Debug, Deserialize)]
struct TutorRequest {
    question: String,
}

#[derive(Clone, Serialize)]
struct GlobalClick {
    x: i32,
    y: i32,
    overlay_x: i32,
    overlay_y: i32,
    scale_factor: f64,
}

#[tauri::command]
async fn run_tutor(app: AppHandle, request: TutorRequest) -> Result<serde_json::Value, String> {
    let output = run_python_worker(&app, &request.question).map_err(|error| error)?;

    let parsed: serde_json::Value = serde_json::from_str(&output)
        .map_err(|err| format!("Python worker returned invalid JSON: {err}. Raw: {output}"))?;

    if let Some(overlay) = app.get_webview_window("overlay") {
        configure_overlay_passthrough(&overlay);
        let _ = overlay.emit("clicky://guidance", parsed.clone());
        let _ = overlay.show();
    }

    Ok(parsed)
}

#[tauri::command]
fn show_overlay(app: AppHandle) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        configure_overlay_passthrough(&overlay);
        overlay.show().map_err(|err| err.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn hide_overlay(app: AppHandle) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        overlay.hide().map_err(|err| err.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn show_command_bar(app: AppHandle) -> Result<(), String> {
    show_command_window(&app);
    Ok(())
}

fn run_python_worker(app: &AppHandle, question: &str) -> Result<String, String> {
    let root = project_root(app)?;
    let script = root.join("python").join("main.py");
    let python = python_executable(&root);
    let env_file_vars = read_env_file(&root);

    let mut child = Command::new(python)
        .arg(script)
        .current_dir(&root)
        .env("PYTHONWARNINGS", "ignore")
        .envs(env_file_vars)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| format!("Failed to start Python worker: {err}"))?;

    let payload = serde_json::json!({ "question": question });
    if let Some(stdin) = child.stdin.as_mut() {
        stdin
            .write_all(payload.to_string().as_bytes())
            .map_err(|err| format!("Failed to write to Python worker: {err}"))?;
    }

    let output = child
        .wait_with_output()
        .map_err(|err| format!("Python worker failed: {err}"))?;

    if !output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        if let Some(error) = parse_worker_error(&stdout) {
            return Err(error);
        }

        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python worker exited with {}: {stderr}", output.status));
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn read_env_file(root: &PathBuf) -> Vec<(String, String)> {
    let env_path = root.join(".env");
    let Ok(contents) = std::fs::read_to_string(env_path) else {
        return Vec::new();
    };

    contents
        .lines()
        .filter_map(parse_env_line)
        .collect()
}

fn parse_env_line(line: &str) -> Option<(String, String)> {
    let line = line.trim();
    if line.is_empty() || line.starts_with('#') {
        return None;
    }

    let (key, value) = line.split_once('=')?;
    let key = key.trim();
    if key.is_empty() {
        return None;
    }

    Some((key.to_string(), trim_env_value(value)))
}

fn trim_env_value(value: &str) -> String {
    let value = value.trim();
    if value.len() >= 2 {
        let first = value.as_bytes()[0];
        let last = value.as_bytes()[value.len() - 1];
        if (first == b'"' && last == b'"') || (first == b'\'' && last == b'\'') {
            return value[1..value.len() - 1].to_string();
        }
    }
    value.to_string()
}

fn parse_worker_error(stdout: &str) -> Option<String> {
    let parsed: serde_json::Value = serde_json::from_str(stdout.trim()).ok()?;
    parsed
        .get("error")
        .and_then(|error| error.as_str())
        .map(|error| error.to_string())
}

fn project_root(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join("python").exists() {
            return Ok(cwd);
        }
        if let Some(parent) = cwd.parent() {
            if parent.join("python").exists() {
                return Ok(parent.to_path_buf());
            }
        }
    }

    app.path()
        .resource_dir()
        .map_err(|err| format!("Cannot locate app resource directory: {err}"))
}

fn python_executable(root: &PathBuf) -> PathBuf {
    let venv_python = root.join(".venv").join("Scripts").join("python.exe");
    if venv_python.exists() {
        venv_python
    } else {
        PathBuf::from("python")
    }
}

fn configure_overlay_passthrough(window: &WebviewWindow) {
    let _ = window.set_ignore_cursor_events(true);

    #[cfg(target_os = "windows")]
    {
        use windows_sys::Win32::Foundation::HWND;
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            GetWindowLongW, SetWindowLongW, GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TOOLWINDOW,
            WS_EX_TRANSPARENT,
        };

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
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![run_tutor, show_overlay, hide_overlay, show_command_bar])
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show_command" => show_command_window(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .setup(|app| {
            setup_tray(app)?;

            if let Some(overlay) = app.get_webview_window("overlay") {
                configure_overlay_passthrough(&overlay);
            }

            if let Some(command) = app.get_webview_window("command") {
                let _ = command.show();
                let _ = command.set_focus();
            }

            let app_handle = app.handle().clone();
            start_global_click_listener(app_handle.clone());

            for code in [Code::Enter, Code::Space] {
                let shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), code);
                let app_handle = app_handle.clone();
                if let Err(err) = app.global_shortcut().on_shortcut(shortcut, move |_app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        show_command_window(&app_handle);
                    }
                }) {
                    eprintln!("Failed to register command shortcut {code:?}: {err}");
                }
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Clicky");
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show_command = MenuItem::with_id(app, "show_command", "Open", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Exit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_command, &quit])?;

    let mut tray = TrayIconBuilder::with_id("clicky")
        .tooltip("Clicky")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                show_command_window(app);
            }
        });

    if let Some(icon) = app.default_window_icon().cloned() {
        tray = tray.icon(icon);
    }

    tray.build(app)?;
    Ok(())
}

fn show_command_window(app: &AppHandle) {
    if let Some(command) = app.get_webview_window("command") {
        let _ = command.emit("clicky://open-command", ());
        let _ = command.unminimize();
        let _ = command.show();
        let _ = command.set_focus();
    }
}

fn start_global_click_listener(app: AppHandle) {
    thread::spawn(move || {
        let mut was_left_down = false;
        let mut was_right_down = false;

        loop {
            if let Some(click) = read_mouse_click(&mut was_left_down, &mut was_right_down) {
                if let Some(overlay) = app.get_webview_window("overlay") {
                    if overlay.is_visible().unwrap_or(false) {
                        let click = click.with_overlay_metrics(&overlay);
                        let _ = overlay.emit("clicky://global-click", click);
                    }
                }
            }

            thread::sleep(Duration::from_millis(16));
        }
    });
}

impl GlobalClick {
    fn with_overlay_metrics(mut self, overlay: &WebviewWindow) -> Self {
        if let Ok(position) = overlay.outer_position() {
            self.overlay_x = position.x;
            self.overlay_y = position.y;
        }
        self.scale_factor = overlay.scale_factor().unwrap_or(1.0);
        self
    }
}

#[cfg(target_os = "windows")]
fn read_mouse_click(was_left_down: &mut bool, was_right_down: &mut bool) -> Option<GlobalClick> {
    use windows_sys::Win32::Foundation::POINT;
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON, VK_RBUTTON};
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

#[cfg(not(target_os = "windows"))]
fn read_mouse_click(_was_left_down: &mut bool, _was_right_down: &mut bool) -> Option<GlobalClick> {
    None
}

#[cfg(test)]
mod tests {
    use super::{parse_env_line, parse_worker_error};

    #[test]
    fn parses_worker_json_error_from_stdout() {
        let stdout = r#"{"error":"Ollama is not running","steps":[],"warnings":[]}"#;

        assert_eq!(
            parse_worker_error(stdout),
            Some("Ollama is not running".to_string())
        );
    }

    #[test]
    fn ignores_non_json_worker_stdout() {
        assert_eq!(parse_worker_error("not json"), None);
    }

    #[test]
    fn parses_env_line_with_quoted_value() {
        assert_eq!(
            parse_env_line(r#"CLICKY_GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct""#),
            Some((
                "CLICKY_GROQ_MODEL".to_string(),
                "meta-llama/llama-4-scout-17b-16e-instruct".to_string()
            ))
        );
    }
}
