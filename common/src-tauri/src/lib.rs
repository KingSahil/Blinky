mod platform;
mod websocket;
mod mcp_bridge;

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

use platform::{
    click_screen_point_impl, configure_overlay_passthrough, open_url_impl, scroll_at_point_impl,
    set_window_capture_exclusion, start_global_click_listener, type_text_impl,
};

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

#[tauri::command]
async fn run_tutor(app: AppHandle, request: TutorRequest) -> Result<serde_json::Value, String> {
    let overlay = app.get_webview_window("overlay");
    let command = app.get_webview_window("command");

    if let Some(ref w) = overlay {
        set_window_capture_exclusion(w, true);
    }
    if let Some(ref w) = command {
        set_window_capture_exclusion(w, true);
    }

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

    if let Some(ref w) = command {
        set_window_capture_exclusion(w, false);
    }
    if let Some(ref w) = overlay {
        set_window_capture_exclusion(w, false);
    }

    let output = output_res.map_err(|error| error)?;

    let parsed: serde_json::Value = serde_json::from_str(&output)
        .map_err(|err| format!("Python worker returned invalid JSON: {err}. Raw: {output}"))?;

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
        let _ = overlay.emit("blinky://guidance", serde_json::json!({ "steps": [] }));
    }
    Ok(())
}

#[tauri::command]
fn click_screen_point(x: i32, y: i32) -> Result<(), String> {
    click_screen_point_impl(x, y)
}

#[tauri::command]
fn scroll_at_point(x: i32, y: i32, direction: String, amount: i32) -> Result<(), String> {
    scroll_at_point_impl(x, y, &direction, amount)
}

#[tauri::command]
fn type_text(text: String, press_enter: bool) -> Result<(), String> {
    type_text_impl(&text, press_enter)
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
fn log_debug_message(message: String) {
    use std::fs::OpenOptions;
    use std::io::Write;
    let _ = std::fs::create_dir_all("tmp");
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open("tmp/overlay_debug.log") {
        let _ = writeln!(file, "{}", message);
    }
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
    deepseek_api_key: String,
}

#[tauri::command]
async fn get_settings(app: AppHandle) -> Result<BlinkySettings, String> {
    let root = project_root(&app)?;
    let env_vars = read_env_file(&root);

    let mut provider = "groq".to_string();
    let mut shortcut = "Enter".to_string();
    let mut sarvam_api_key = "".to_string();
    let mut groq_api_key = "".to_string();
    let mut deepseek_api_key = "".to_string();

    for (key, val) in env_vars {
        if key == "BLINKY_AI_PROVIDER" {
            provider = val.to_lowercase();
        } else if key == "BLINKY_SHORTCUT" {
            shortcut = val;
        } else if key == "SARVAM_API_KEY" {
            sarvam_api_key = val;
        } else if key == "GROQ_API_KEY" {
            groq_api_key = val;
        } else if key == "DEEPSEEK_API_KEY" {
            deepseek_api_key = val;
        }
    }

    Ok(BlinkySettings {
        provider,
        shortcut,
        sarvam_api_key,
        groq_api_key,
        deepseek_api_key,
    })
}

#[tauri::command]
async fn save_settings(
    app: AppHandle,
    provider: String,
    shortcut: String,
    sarvam_api_key: String,
    groq_api_key: String,
    deepseek_api_key: String,
) -> Result<(), String> {
    let root = project_root(&app)?;
    ensure_env_file(&root);
    let env_path = root.join(".env");

    let contents = std::fs::read_to_string(&env_path).unwrap_or_default();

    let mut lines: Vec<String> = contents.lines().map(|s| s.to_string()).collect();
    let mut provider_found = false;
    let mut shortcut_found = false;
    let mut sarvam_api_key_found = false;
    let mut groq_api_key_found = false;
    let mut deepseek_api_key_found = false;

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
        } else if trimmed.starts_with("DEEPSEEK_API_KEY=") {
            *line = format!("DEEPSEEK_API_KEY={}", deepseek_api_key);
            deepseek_api_key_found = true;
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
    if !deepseek_api_key_found {
        lines.push(format!("DEEPSEEK_API_KEY={}", deepseek_api_key));
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
    let script = root.join("common").join("python").join("main.py");
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

    let mut command_rect = serde_json::Value::Null;
    if let Some(ref w) = command_window {
        if let (Ok(pos), Ok(size)) = (w.outer_position(), w.outer_size()) {
            command_rect = serde_json::json!({
                "x": pos.x,
                "y": pos.y,
                "width": size.width,
                "height": size.height,
            });
        }
    }

    let payload = serde_json::json!({
        "question": question,
        "previous_question": previous_question,
        "progress": progress.unwrap_or(&serde_json::Value::Null),
        "conversation_history": conversation_history.unwrap_or(&serde_json::Value::Null),
        "web_search_enabled": web_search_enabled,
        "agent_mode": agent_mode,
        "ignored_rects": if command_rect.is_null() { vec![] } else { vec![command_rect] },
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
        let example_path = root.join("common").join(".envexample");
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
    // Walk up from CWD to find the project root (directory containing common/python/)
    if let Ok(cwd) = std::env::current_dir() {
        let mut dir = Some(cwd.as_path());
        while let Some(path) = dir {
            if path.join("common").join("python").is_dir() {
                return Ok(path.to_path_buf());
            }
            dir = path.parent();
        }
    }

    // Also try from the executable path (useful in bundled/tests)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let mut dir = Some(exe_dir);
            while let Some(path) = dir {
                if path.join("common").join("python").is_dir() {
                    return Ok(path.to_path_buf());
                }
                dir = path.parent();
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
    let script = root.join("common").join("python").join("ui_observer.py");
    if !script.exists() {
        eprintln!(
            "Warning: UI observer script was not found: {}",
            script.display()
        );
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

// Spawns the Node.js WhatsApp backend server in the background
fn start_whatsapp_backend(app: &AppHandle) {
    if std::env::var("BLINKY_DISABLE_WHATSAPP")
        .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
        .unwrap_or(false)
    {
        return;
    }

    let root = match project_root(app) {
        Ok(root) => root,
        Err(err) => {
            eprintln!("Warning: WhatsApp backend skipped because project root was not found: {err}");
            return;
        }
    };
    let script = root.join("common").join("whatsapp_backend").join("server.js");
    if !script.exists() {
        eprintln!(
            "Warning: WhatsApp backend server.js was not found: {}",
            script.display()
        );
        return;
    }

    let mut command = Command::new("node");
    command
        .arg(&script)
        .current_dir(&root)
        .envs(read_env_file(&root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    {
        command.creation_flags(0x08000000);
    }

    match command.spawn() {
        Ok(_) => {
            eprintln!("WhatsApp backend server started successfully via Node");
        }
        Err(e) => {
            eprintln!("Warning: Failed to start WhatsApp backend via Node: {e}. Trying Bun...");
            let mut command_bun = Command::new("bun");
            command_bun
                .arg("run")
                .arg(&script)
                .current_dir(&root)
                .envs(read_env_file(&root))
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());

            #[cfg(target_os = "windows")]
            {
                command_bun.creation_flags(0x08000000);
            }

            if let Err(err) = command_bun.spawn() {
                eprintln!("Warning: Failed to start WhatsApp backend via Bun: {err}");
            } else {
                eprintln!("WhatsApp backend server started successfully via Bun");
            }
        }
    }
}

#[allow(dead_code)]
fn start_ydotoold() {
    #[cfg(target_os = "linux")]
    std::thread::spawn(|| {
        match std::process::Command::new("ydotoold")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
        {
            Ok(_) => eprintln!("ydotoold auto-started"),
            Err(_) => {}
        }
    });
}

struct WakeWordState {
    stdin: std::sync::Mutex<Option<std::process::ChildStdin>>,
}

#[tauri::command]
fn pause_wake_word(state: tauri::State<'_, WakeWordState>) -> Result<(), String> {
    if let Ok(mut lock) = state.stdin.lock() {
        if let Some(stdin) = lock.as_mut() {
            let _ = stdin.write_all(b"PAUSE\n");
            let _ = stdin.flush();
        }
    }
    Ok(())
}

#[tauri::command]
fn resume_wake_word(state: tauri::State<'_, WakeWordState>) -> Result<(), String> {
    if let Ok(mut lock) = state.stdin.lock() {
        if let Some(stdin) = lock.as_mut() {
            let _ = stdin.write_all(b"RESUME\n");
            let _ = stdin.flush();
        }
    }
    Ok(())
}

fn start_wake_word_detector(app: &AppHandle) {
    let state = WakeWordState {
        stdin: std::sync::Mutex::new(None),
    };
    app.manage(state);

    let root = match project_root(app) {
        Ok(root) => root,
        Err(err) => {
            eprintln!("Warning: Wake word detector skipped because project root was not found: {err}");
            return;
        }
    };
    let script = root.join("python").join("wake_word.py");
    if !script.exists() {
        eprintln!(
            "Warning: Wake word script was not found: {}",
            script.display()
        );
        return;
    }

    let model_path = root.join("python").join("hey_blinky.onnx");

    let mut command = Command::new(python_executable(&root));
    command
        .arg(script)
        .arg("--model")
        .arg(model_path)
        .current_dir(&root)
        .env("PYTHONWARNINGS", "ignore")
        .envs(read_env_file(&root))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());

    #[cfg(target_os = "windows")]
    {
        command.creation_flags(0x08000000);
    }

    match command.spawn() {
        Ok(mut child) => {
            if let Some(stdin) = child.stdin.take() {
                if let Some(state) = app.try_state::<WakeWordState>() {
                    if let Ok(mut lock) = state.stdin.lock() {
                        *lock = Some(stdin);
                    }
                }
            }
            let stdout = child.stdout.take().expect("Failed to open stdout");
            let app_handle = app.clone();
            
            thread::spawn(move || {
                let reader = BufReader::new(stdout);
                for line in reader.lines() {
                    match line {
                        Ok(text) => {
                            if text.trim() == "WAKE_WORD_DETECTED" {
                                if let Some(command_window) = app_handle.get_webview_window("command") {
                                    let _ = command_window.emit("blinky://wake-word-detected", ());
                                }
                            }
                        }
                        Err(e) => {
                            eprintln!("Error reading wake word detector output: {}", e);
                            break;
                        }
                    }
                }
                let _ = child.wait();
            });
        }
        Err(err) => {
            eprintln!("Warning: Failed to start wake word detector: {err}");
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
            scroll_at_point,
            type_text,
            open_url,
            show_command_bar,
            resize_command_window,
            resize_and_move_command_window,
            get_settings,
            save_settings,
            log_debug_message,
            pause_wake_word,
            resume_wake_word
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
            start_whatsapp_backend(&app.handle());
            start_wake_word_detector(&app.handle());

            #[cfg(target_os = "linux")]
            {
                mcp_bridge::start_mcp_bridge();
                start_ydotoold();
            }

            tauri::async_runtime::spawn(async move {
                websocket::start_websocket_server().await;
            });

            #[cfg(target_os = "windows")]
            if let Some(overlay) = app.get_webview_window("overlay") {
                configure_overlay_passthrough(&overlay);
                let _ = overlay.emit("blinky://guidance", serde_json::json!({ "steps": [] }));
                let _ = overlay.show();
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
                                    toggle_command_window(&app_handle);
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

fn toggle_command_window(app: &AppHandle) {
    if let Some(command) = app.get_webview_window("command") {
        let is_visible = command.is_visible().unwrap_or(false);
        let is_focused = command.is_focused().unwrap_or(false);
        if is_visible && is_focused {
            let _ = command.hide();
        } else {
            let _ = command.emit("blinky://open-command", ());
            let _ = command.unminimize();
            let _ = command.show();
            let _ = command.set_focus();
        }
    }
}

fn show_command_window(app: &AppHandle) {
    if let Some(command) = app.get_webview_window("command") {
        let _ = command.emit("blinky://open-command", ());
        let _ = command.unminimize();
        let _ = command.show();
        let _ = command.set_focus();
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
