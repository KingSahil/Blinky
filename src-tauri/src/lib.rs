use serde::{Deserialize, Serialize};
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use tauri::{AppHandle, Emitter, Manager, WebviewWindow};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

#[derive(Debug, Deserialize)]
struct TutorRequest {
    question: String,
}

#[derive(Debug, Serialize)]
struct WorkerError {
    error: String,
}

#[tauri::command]
async fn run_tutor(app: AppHandle, request: TutorRequest) -> Result<serde_json::Value, String> {
    let output = run_python_worker(&app, &request.question)
        .map_err(|error| serde_json::to_string(&WorkerError { error }).unwrap_or_default())?;

    let parsed: serde_json::Value = serde_json::from_str(&output)
        .map_err(|err| format!("Python worker returned invalid JSON: {err}. Raw: {output}"))?;

    if let Some(overlay) = app.get_webview_window("overlay") {
        let _ = overlay.emit("clicky://guidance", parsed.clone());
        let _ = overlay.show();
        let _ = overlay.set_focus();
    }

    Ok(parsed)
}

#[tauri::command]
fn show_overlay(app: AppHandle) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
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

fn run_python_worker(app: &AppHandle, question: &str) -> Result<String, String> {
    let root = project_root(app)?;
    let script = root.join("python").join("main.py");
    let python = python_executable(&root);

    let mut child = Command::new(python)
        .arg(script)
        .current_dir(&root)
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
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python worker exited with {}: {stderr}", output.status));
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
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
        .invoke_handler(tauri::generate_handler![run_tutor, show_overlay, hide_overlay])
        .setup(|app| {
            if let Some(overlay) = app.get_webview_window("overlay") {
                configure_overlay_passthrough(&overlay);
            }

            let shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::Space);
            let app_handle = app.handle().clone();
            app.global_shortcut().on_shortcut(shortcut, move |_app, _shortcut, event| {
                if event.state() == ShortcutState::Pressed {
                    if let Some(command) = app_handle.get_webview_window("command") {
                        let _ = command.emit("clicky://open-command", ());
                        let _ = command.show();
                        let _ = command.set_focus();
                    }
                }
            })?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Clicky");
}
