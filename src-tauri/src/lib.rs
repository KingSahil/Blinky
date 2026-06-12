mod websocket;

use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Write};
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
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
    previous_question: Option<String>,
    progress: Option<serde_json::Value>,
    conversation_history: Option<serde_json::Value>,
    web_search_enabled: Option<bool>,
    agent_mode: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct AgentQueryRequest {
    query: String,
}

#[cfg(target_os = "windows")]
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
    let overlay = app.get_webview_window("overlay");
    let command = app.get_webview_window("command");

    let overlay_was_visible = overlay
        .as_ref()
        .map(|w| w.is_visible().unwrap_or(false))
        .unwrap_or(false);

    // Exclude windows from captures programmatically so they are not captured by the system,
    // while remaining fully visible and active for the user.
    if let Some(ref w) = overlay {
        set_window_capture_exclusion(w, true);
    }
    if let Some(ref w) = command {
        set_window_capture_exclusion(w, true);
    }

    // Give DWM a tiny moment to apply display affinity before screenshot
    thread::sleep(Duration::from_millis(40));

    let output_res = run_python_worker(
        &app,
        &request.question,
        request.previous_question.as_deref(),
        request.progress.as_ref(),
        request.conversation_history.as_ref(),
        request.web_search_enabled.unwrap_or(false),
        request.agent_mode.unwrap_or(false),
        command.clone(),
        overlay.clone(),
    );

    // Fallback: restore capture visibility in case of errors or if not restored by worker
    if let Some(ref w) = command {
        set_window_capture_exclusion(w, false);
    }
    if let Some(ref w) = overlay {
        set_window_capture_exclusion(w, false);
    }

    let output = output_res.map_err(|error| error)?;

    let parsed: serde_json::Value = serde_json::from_str(&output)
        .map_err(|err| format!("Python worker returned invalid JSON: {err}. Raw: {output}"))?;

    // Now restore/show overlay with highlights if applicable
    if let Some(ref w) = overlay {
        if overlay_was_visible
            || parsed
                .get("steps")
                .and_then(|s| s.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false)
        {
            let _ = w.emit("blinky://guidance", parsed.clone());
            let _ = w.show();
            configure_overlay_passthrough(w);
        }
    }

    Ok(parsed)
}

#[tauri::command]
async fn run_agent_query(
    app: AppHandle,
    request: AgentQueryRequest,
) -> Result<serde_json::Value, String> {
    websocket::run_agent_query(&app, &request.query).await
}

#[tauri::command]
fn show_overlay(app: AppHandle) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        overlay.show().map_err(|err| err.to_string())?;
        configure_overlay_passthrough(&overlay);
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
fn click_screen_point(x: i32, y: i32) -> Result<(), String> {
    click_screen_point_impl(x, y)
}

#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    let trimmed = url.trim();
    if !(trimmed.starts_with("https://") || trimmed.starts_with("http://")) {
        return Err("Only http and https links can be opened.".to_string());
    }

    open_url_impl(trimmed)
}

#[tauri::command]
fn show_command_bar(app: AppHandle) -> Result<(), String> {
    show_command_window(&app);
    Ok(())
}

#[tauri::command]
fn resize_command_window(app: AppHandle, height: f64) -> Result<(), String> {
    if let Some(command) = app.get_webview_window("command") {
        let current_size = command
            .inner_size()
            .unwrap_or(tauri::PhysicalSize::new(760, 580));
        let scale_factor = command.scale_factor().unwrap_or(1.0);
        let current_logical_width = current_size.width as f64 / scale_factor;
        let size = tauri::LogicalSize::new(current_logical_width, height);
        let _ = command.set_size(size);
    }
    Ok(())
}

#[tauri::command]
fn resize_and_move_command_window(
    app: AppHandle,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
) -> Result<(), String> {
    if let Some(command) = app.get_webview_window("command") {
        let size = tauri::LogicalSize::new(width, height);
        let pos = tauri::LogicalPosition::new(x, y);
        let _ = command.set_size(size);
        let _ = command.set_position(pos);
    }
    Ok(())
}

#[derive(Serialize, Deserialize)]
struct BlinkySettings {
    provider: String,
    shortcut: String,
    sarvam_api_key: String,
    groq_api_key: String,
}

#[tauri::command]
async fn get_settings(app: AppHandle) -> Result<BlinkySettings, String> {
    let root = project_root(&app)?;
    let env_vars = read_env_file(&root);

    let mut provider = "groq".to_string();
    let mut shortcut = "Enter".to_string();
    let mut sarvam_api_key = "".to_string();
    let mut groq_api_key = "".to_string();

    for (key, val) in env_vars {
        if key == "BLINKY_AI_PROVIDER" {
            provider = val.to_lowercase();
        } else if key == "BLINKY_SHORTCUT" {
            shortcut = val;
        } else if key == "SARVAM_API_KEY" {
            sarvam_api_key = val;
        } else if key == "GROQ_API_KEY" {
            groq_api_key = val;
        }
    }

    Ok(BlinkySettings {
        provider,
        shortcut,
        sarvam_api_key,
        groq_api_key,
    })
}

#[tauri::command]
async fn save_settings(
    app: AppHandle,
    provider: String,
    shortcut: String,
    sarvam_api_key: String,
    groq_api_key: String,
) -> Result<(), String> {
    let root = project_root(&app)?;
    ensure_env_file(&root);
    let env_path = root.join(".env");

    // Read the current contents of .env
    let contents = std::fs::read_to_string(&env_path).unwrap_or_default();

    // Parse lines, update values, and rebuild
    let mut lines: Vec<String> = contents.lines().map(|s| s.to_string()).collect();
    let mut provider_found = false;
    let mut shortcut_found = false;
    let mut sarvam_api_key_found = false;
    let mut groq_api_key_found = false;

    for line in lines.iter_mut() {
        let trimmed = line.trim();
        if trimmed.starts_with("BLINKY_AI_PROVIDER=") {
            *line = format!("BLINKY_AI_PROVIDER={}", provider);
            provider_found = true;
        } else if trimmed.starts_with("BLINKY_SHORTCUT=") {
            *line = format!("BLINKY_SHORTCUT={}", shortcut);
            shortcut_found = true;
        } else if trimmed.starts_with("SARVAM_API_KEY=") {
            *line = format!("SARVAM_API_KEY={}", sarvam_api_key);
            sarvam_api_key_found = true;
        } else if trimmed.starts_with("GROQ_API_KEY=") {
            *line = format!("GROQ_API_KEY={}", groq_api_key);
            groq_api_key_found = true;
        }
    }

    if !provider_found {
        lines.push(format!("BLINKY_AI_PROVIDER={}", provider));
    }
    if !shortcut_found {
        lines.push(format!("BLINKY_SHORTCUT={}", shortcut));
    }
    if !sarvam_api_key_found {
        lines.push(format!("SARVAM_API_KEY={}", sarvam_api_key));
    }
    if !groq_api_key_found {
        lines.push(format!("GROQ_API_KEY={}", groq_api_key));
    }

    let new_contents = lines.join("\n") + "\n";
    std::fs::write(&env_path, new_contents)
        .map_err(|err| format!("Failed to write .env file: {err}"))?;

    Ok(())
}

fn get_active_shortcut_from_env(app: &AppHandle) -> String {
    if let Ok(root) = project_root(app) {
        let env_vars = read_env_file(&root);
        for (key, val) in env_vars {
            if key == "BLINKY_SHORTCUT" {
                return val;
            }
        }
    }
    "Enter".to_string()
}

fn run_python_worker(
    app: &AppHandle,
    question: &str,
    previous_question: Option<&str>,
    progress: Option<&serde_json::Value>,
    conversation_history: Option<&serde_json::Value>,
    web_search_enabled: bool,
    agent_mode: bool,
    command_window: Option<WebviewWindow>,
    overlay_window: Option<WebviewWindow>,
) -> Result<String, String> {
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
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|err| format!("Failed to start Python worker: {err}"))?;

    let payload = serde_json::json!({
        "question": question,
        "previous_question": previous_question,
        "progress": progress.unwrap_or(&serde_json::Value::Null),
        "conversation_history": conversation_history.unwrap_or(&serde_json::Value::Null),
        "web_search_enabled": web_search_enabled,
        "agent_mode": agent_mode,
    });

    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(payload.to_string().as_bytes())
            .map_err(|err| format!("Failed to write to Python worker: {err}"))?;
    }

    let child_stdout = child
        .stdout
        .take()
        .ok_or("Failed to open Python worker stdout")?;
    let mut reader = BufReader::new(child_stdout);
    let mut stdout_accumulated = String::new();
    let mut line = String::new();
    let mut restored = false;

    while reader.read_line(&mut line).unwrap_or(0) > 0 {
        let trimmed = line.trim();
        if trimmed == "__BLINKY_CAPTURED__" {
            if !restored {
                // Restore capture visibility immediately after screenshot is captured
                if let Some(ref w) = command_window {
                    set_window_capture_exclusion(w, false);
                }
                if let Some(ref w) = overlay_window {
                    set_window_capture_exclusion(w, false);
                }
                restored = true;
            }
        } else {
            if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(trimmed) {
                if let Some(msg_type) = parsed.get("type").and_then(|value| value.as_str()) {
                    if msg_type == "status" {
                        if let Some(ref w) = command_window {
                            let _ = w.emit("blinky://tutor-status", parsed.clone());
                        }
                    } else if msg_type == "chunk" {
                        if let Some(ref w) = command_window {
                            let _ = w.emit("blinky://tutor-chunk", parsed.clone());
                        }
                    }
                    line.clear();
                    continue;
                }
            }
            stdout_accumulated.push_str(&line);
        }
        line.clear();
    }

    let stderr_reader = child.stderr.take().map(BufReader::new);
    let status = child
        .wait()
        .map_err(|err| format!("Failed to wait for python worker: {err}"))?;

    if !status.success() {
        let mut stderr_str = String::new();
        if let Some(mut r) = stderr_reader {
            let _ = std::io::Read::read_to_string(&mut r, &mut stderr_str);
        }
        if let Some(error) = parse_worker_error(&stdout_accumulated) {
            return Err(error);
        }
        return Err(format!("Python worker exited with {status}: {stderr_str}"));
    }

    Ok(stdout_accumulated)
}

fn ensure_env_file(root: &PathBuf) {
    let env_path = root.join(".env");
    if !env_path.exists() {
        let example_path = root.join(".envexample");
        if example_path.exists() {
            let _ = std::fs::copy(&example_path, &env_path);
        } else {
            let _ = std::fs::write(
                &env_path,
                b"BLINKY_AI_PROVIDER=groq\nBLINKY_SHORTCUT=Space\n",
            );
        }
    }
}

fn read_env_file(root: &PathBuf) -> Vec<(String, String)> {
    ensure_env_file(root);
    let env_path = root.join(".env");
    let Ok(contents) = std::fs::read_to_string(env_path) else {
        return Vec::new();
    };

    contents.lines().filter_map(parse_env_line).collect()
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
    let bin_path = root.join(".venv").join("bin").join("python");
    let scripts_path = root.join(".venv").join("Scripts").join("python.exe");
    if bin_path.exists() {
        bin_path
    } else if scripts_path.exists() {
        scripts_path
    } else {
        #[cfg(target_os = "windows")]
        {
            PathBuf::from("python")
        }
        #[cfg(not(target_os = "windows"))]
        {
            PathBuf::from("python3")
        }
    }
}

fn start_ui_observer(app: &AppHandle) {
    if std::env::var("BLINKY_DISABLE_UI_OBSERVER")
        .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
        .unwrap_or(false)
    {
        return;
    }

    let root = match project_root(app) {
        Ok(root) => root,
        Err(err) => {
            eprintln!("Warning: UI observer skipped because project root was not found: {err}");
            return;
        }
    };
    let script = root.join("python").join("ui_observer.py");
    if !script.exists() {
        eprintln!("Warning: UI observer script was not found: {}", script.display());
        return;
    }

    let mut command = Command::new(python_executable(&root));
    command
        .arg(script)
        .arg("--parent-pid")
        .arg(std::process::id().to_string())
        .current_dir(&root)
        .env("PYTHONWARNINGS", "ignore")
        .envs(read_env_file(&root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    {
        command.creation_flags(0x08000000);
    }

    if let Err(err) = command.spawn() {
        eprintln!("Warning: Failed to start UI observer: {err}");
    }
}

fn open_url_impl(url: &str) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    let mut command = {
        let mut command = Command::new("rundll32");
        command.arg("url.dll,FileProtocolHandler").arg(url);
        command
    };

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

fn configure_overlay_passthrough(window: &WebviewWindow) {
    let _ = window.set_ignore_cursor_events(true);

    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(Some(monitor)) = window.current_monitor() {
            let scale_factor = monitor.scale_factor();

            // Query the desktop environment to only apply panel offsets on GNOME
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

    #[cfg(target_os = "windows")]
    {
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
                    style
                        | WS_EX_TRANSPARENT as i32
                        | WS_EX_LAYERED as i32
                        | WS_EX_TOOLWINDOW as i32,
                );
            }
        }
    }
}

fn set_window_capture_exclusion(window: &WebviewWindow, exclude: bool) {
    #[cfg(target_os = "windows")]
    {
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
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            run_tutor,
            run_agent_query,
            show_overlay,
            hide_overlay,
            click_screen_point,
            open_url,
            show_command_bar,
            resize_command_window,
            resize_and_move_command_window,
            get_settings,
            save_settings
        ])
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
            start_ui_observer(&app.handle());

            // Start background WebSocket server for remote control
            tauri::async_runtime::spawn(async move {
                websocket::start_websocket_server().await;
            });

            #[cfg(target_os = "windows")]
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
                if let Err(err) =
                    app.global_shortcut()
                        .on_shortcut(shortcut, move |_app, _shortcut, event| {
                            if event.state() == ShortcutState::Pressed {
                                let active = get_active_shortcut_from_env(&app_handle);
                                let is_match = match code {
                                    Code::Enter => active == "Enter",
                                    Code::Space => active == "Space",
                                    _ => false,
                                };
                                if is_match {
                                    show_command_window(&app_handle);
                                }
                            }
                        })
                {
                    eprintln!("Failed to register command shortcut {code:?}: {err}");
                }
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Blinky");
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show_command = MenuItem::with_id(app, "show_command", "Open", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Exit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_command, &quit])?;

    let mut tray = TrayIconBuilder::with_id("blinky")
        .tooltip("Blinky")
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

    match tray.build(app) {
        Ok(_) => {}
        Err(err) => {
            eprintln!("Warning: Failed to setup system tray (might be unsupported/restricted in this DE): {err}");
        }
    }
    Ok(())
}

fn show_command_window(app: &AppHandle) {
    if let Some(command) = app.get_webview_window("command") {
        let _ = command.emit("blinky://open-command", ());
        let _ = command.unminimize();
        let _ = command.show();
        let _ = command.set_focus();
    }
}

#[cfg(target_os = "windows")]
fn start_global_click_listener(app: AppHandle) {
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

#[cfg(not(target_os = "windows"))]
fn start_global_click_listener(_app: AppHandle) {
    // No-op on Linux/macOS to avoid CPU spinning or panic
}

#[cfg(target_os = "windows")]
fn click_screen_point_impl(x: i32, y: i32) -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, MOUSEEVENTF_MOVE,
        MOUSEEVENTF_VIRTUALDESK, MOUSEEVENTF_ABSOLUTE,
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

#[cfg(target_os = "windows")]
fn mouse_input(dx: i32, dy: i32, flags: u32) -> windows_sys::Win32::UI::Input::KeyboardAndMouse::INPUT {
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

#[cfg(not(target_os = "windows"))]
fn click_screen_point_impl(_x: i32, _y: i32) -> Result<(), String> {
    Err("Autopilot clicking is only implemented on Windows".to_string())
}

#[cfg(target_os = "windows")]
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

#[cfg(target_os = "windows")]
fn read_enter_key(was_enter_down: &mut bool) -> Option<()> {
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
            parse_env_line(r#"BLINKY_GROQ_MODEL="meta-llama/llama-4-scout-17b-16e-instruct""#),
            Some((
                "BLINKY_GROQ_MODEL".to_string(),
                "meta-llama/llama-4-scout-17b-16e-instruct".to_string()
            ))
        );
    }
}
