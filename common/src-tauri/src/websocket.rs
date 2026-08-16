 use futures_util::{SinkExt, StreamExt};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpListener;
use tokio::process::{Child, ChildStdin, ChildStdout, Command as TokioCommand};
use tokio::sync::Mutex;
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;

struct AgentDaemon {
    child: Child,
    stdin: ChildStdin,
    reader: BufReader<ChildStdout>,
}

impl AgentDaemon {
    async fn start() -> Result<Self, std::io::Error> {
        let root = project_root();
        let script_path = root.join("common").join("python").join("agent_router.py");
        let python = python_executable(&root);

        let mut cmd = TokioCommand::new(python);
        cmd.arg("-u")
            .arg(&script_path)
            .current_dir(&root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());

        cmd.envs(read_env_file(&root));

        // Forward environment variables
        for var in &[
            "GROQ_API_KEY",
            "BLINKY_AI_PROVIDER",
            "BLINKY_OLLAMA_URL",
            "BLINKY_OLLAMA_MODEL",
            "BLINKY_GROQ_URL",
            "BLINKY_GROQ_MODEL",
            "BLINKY_SEARXNG_URL",
        ] {
            if let Ok(val) = std::env::var(var) {
                cmd.env(var, val);
            }
        }

        let mut child = cmd.spawn()?;
        let stdin = child.stdin.take().ok_or_else(|| {
            std::io::Error::new(std::io::ErrorKind::Other, "Failed to open stdin")
        })?;
        let stdout = child.stdout.take().ok_or_else(|| {
            std::io::Error::new(std::io::ErrorKind::Other, "Failed to open stdout")
        })?;
        let reader = BufReader::new(stdout);

        Ok(Self {
            child,
            stdin,
            reader,
        })
    }

    async fn send_query(&mut self, request_json: &str) -> Result<(), std::io::Error> {
        self.stdin.write_all(request_json.as_bytes()).await?;
        self.stdin.write_all(b"\n").await?;
        self.stdin.flush().await?;
        Ok(())
    }

    async fn read_response(&mut self) -> Result<String, std::io::Error> {
        let mut line = String::new();
        self.reader.read_line(&mut line).await?;
        Ok(line)
    }
}

fn project_root() -> PathBuf {
    // Walk up from CWD to find the project root (directory containing common/python/)
    if let Ok(cwd) = std::env::current_dir() {
        let mut dir = Some(cwd.as_path());
        while let Some(path) = dir {
            if path.join("common").join("python").is_dir() {
                return path.to_path_buf();
            }
            if path.join("_up_").join("common").join("python").is_dir() {
                return path.join("_up_");
            }
            dir = path.parent();
        }
    }

    // Also try from the executable path
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let mut dir = Some(exe_dir);
            while let Some(path) = dir {
                if path.join("common").join("python").is_dir() {
                    return path.to_path_buf();
                }
                if path.join("_up_").join("common").join("python").is_dir() {
                    return path.join("_up_");
                }
                dir = path.parent();
            }
        }
    }

    PathBuf::from(".")
}

fn python_executable(root: &PathBuf) -> PathBuf {
    let mut candidates = vec![root.join("python_runtime").join("Python313"), root.join(".venv")];

    if let Ok(cwd) = std::env::current_dir() {
        let mut dir = Some(cwd.as_path());
        while let Some(path) = dir {
            candidates.push(path.join(".venv"));
            dir = path.parent();
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let mut dir = Some(exe_dir);
            while let Some(path) = dir {
                candidates.push(path.join(".venv"));
                dir = path.parent();
            }
        }
    }

    for venv in candidates {
        let bin_path = venv.join("bin").join("python");
        let scripts_path = venv.join("Scripts").join("python.exe");
        let direct_path = venv.join("python.exe");
        if bin_path.exists() {
            return bin_path;
        }
        if scripts_path.exists() {
            return scripts_path;
        }
        if direct_path.exists() {
            return direct_path;
        }
    }

    #[cfg(target_os = "windows")]
    {
        PathBuf::from("py")
    }
    #[cfg(not(target_os = "windows"))]
    {
        PathBuf::from("python3")
    }
}

fn read_env_file(root: &PathBuf) -> Vec<(String, String)> {
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

static DAEMON: OnceLock<Mutex<Option<AgentDaemon>>> = OnceLock::new();

fn get_daemon_mutex() -> &'static Mutex<Option<AgentDaemon>> {
    DAEMON.get_or_init(|| Mutex::new(None))
}

pub async fn start_websocket_server(app: AppHandle) {
    let addr = "0.0.0.0:9001";
    let listener = match TcpListener::bind(addr).await {
        Ok(l) => l,
        Err(e) => {
            eprintln!("Failed to bind WebSocket server to {}: {}", addr, e);
            return;
        }
    };
    println!("WebSocket server listening on: {}", addr);

    while let Ok((stream, peer_addr)) = listener.accept().await {
        println!("New peer connection: {}", peer_addr);
        let app_clone = app.clone();
        tauri::async_runtime::spawn(async move {
            if let Err(e) = handle_connection(stream, peer_addr, app_clone).await {
                eprintln!("Error handling connection from {}: {}", peer_addr, e);
            }
        });
    }
}

pub async fn run_agent_query(app: &AppHandle, query: &str) -> Result<serde_json::Value, String> {
    let query = query.trim();
    if query.is_empty() {
        return Err("Question is required.".to_string());
    }

    let request_id = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| format!("desktop-{}", duration.as_nanos()))
        .unwrap_or_else(|_| "desktop-unknown".to_string());
    let req_payload = serde_json::json!({
        "requestId": request_id,
        "query": query,
    })
    .to_string();

    let lines = forward_query_to_daemon_collect(&req_payload, app).await?;
    agent_responses_to_tutor_result(&lines)
}

async fn handle_connection(
    stream: tokio::net::TcpStream,
    peer_addr: SocketAddr,
    app: AppHandle,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let path = std::sync::Arc::new(std::sync::Mutex::new(String::new()));
    let path_clone = path.clone();
    let ws_stream = tokio_tungstenite::accept_hdr_async(
        stream,
        move |req: &tokio_tungstenite::tungstenite::handshake::server::Request, response| {
            if let Ok(mut p) = path_clone.lock() {
                *p = req.uri().path_and_query()
                    .map(|pq| pq.as_str().to_string())
                    .unwrap_or_else(|| req.uri().path().to_string());
            }
            Ok(response)
        },
    )
    .await?;

    let active_path = {
        let p = path.lock().unwrap();
        p.clone()
    };
    println!(
        "WebSocket handshake succeeded with {} for path {}",
        peer_addr,
        uri_without_query(&active_path)
    );

    // Extract the optional `?token=` query param if present.
    let uri_token = extract_query_token(&active_path);
    let server_token = get_remote_token();
    let is_loopback = peer_addr.ip().is_loopback();
    let remote_authed = is_loopback
        || uri_token
            .as_deref()
            .map(|t| token_equals(t, &server_token))
            .unwrap_or(false);

    if active_path.starts_with("/sarvam-stt") || active_path.starts_with("/sarvam-tts") {
        // STT/TTS proxies also require authentication (they consume the API key).
        // Loopback callers (the desktop frontend) are trusted; remote callers must
        // present the token.
        if !remote_authed {
            eprintln!("REJECTED unauthenticated Sarvam proxy connection from {}", peer_addr);
            return Ok(());
        }
        if active_path.starts_with("/sarvam-stt") {
            return handle_sarvam_stt_proxy(ws_stream).await;
        }
        return handle_sarvam_tts_proxy(ws_stream).await;
    }

    let (ws_sender, mut ws_receiver) = ws_stream.split();
    let ws_sender = std::sync::Arc::new(tokio::sync::Mutex::new(ws_sender));

    let mut authenticated = remote_authed;
    if !authenticated {
        eprintln!(
            "WARN: unauthenticated remote connection from {} — awaiting auth frame (commands will be denied)",
            peer_addr
        );
    }

    /// Builds an auth-denied JSON error frame for a command that requires a token.
    fn auth_denied(request_id: &str) -> String {
        serde_json::json!({
            "requestId": request_id,
            "status": "error",
            "data": {},
            "error": {
                "code": "UNAUTHORIZED",
                "message": "This connection is not authenticated with a BLINKY_REMOTE_TOKEN",
                "details": ""
            }
        })
        .to_string()
    }

    while let Some(msg) = ws_receiver.next().await {
        let msg = msg?;
        if msg.is_text() || msg.is_binary() {
            let text = msg.to_text()?;
            println!("Received message: {}", text);
            let trimmed = text.trim();

            // Accept an `auth:<token>` frame as an in-band authentication step.
            if let Some(provided) = trimmed.strip_prefix("auth:") {
                authenticated = token_equals(provided.trim(), &server_token);
                if authenticated {
                    println!("{} authenticated successfully", peer_addr);
                } else {
                    eprintln!("{} failed authentication", peer_addr);
                    authenticated = false;
                }
                continue;
            }

            if !authenticated {
                eprintln!("BLOCKED unauthenticated command from {}: {}", peer_addr, trimmed);
                let denied = auth_denied("unknown");
                let _ = ws_sender
                    .lock()
                    .await
                    .send(tokio_tungstenite::tungstenite::Message::Text(denied.into()))
                    .await;
                continue;
            }

            if trimmed == "power_off" {
                crate::platform::execute_power_off();
            } else if trimmed == "restart" {
                crate::platform::execute_restart();
            } else if trimmed == "sleep" {
                crate::platform::execute_sleep();
            } else if trimmed == "volume_up" {
                crate::platform::execute_volume_up();
            } else if trimmed == "volume_down" {
                crate::platform::execute_volume_down();
            } else if trimmed == "volume_mute" || trimmed == "mute" {
                crate::platform::execute_volume_mute();
            } else if trimmed == "lock" {
                crate::platform::execute_lock();
            } else if trimmed == "screenshot" {
                crate::platform::execute_screenshot();
            } else if trimmed == "get_sarvam_key" {
                let key = get_sarvam_api_key();
                let resp = serde_json::json!({
                    "type": "sarvam_key",
                    "key": key
                });
                let _ = ws_sender.lock().await
                    .send(tokio_tungstenite::tungstenite::Message::Text(
                        resp.to_string().into(),
                    ))
                    .await;
            } else if trimmed.starts_with("query:") || trimmed.starts_with("{") {
                let request_id = if trimmed.starts_with("query:") {
                    let parts: Vec<&str> = trimmed.splitn(3, ':').collect();
                    if parts.len() == 3 {
                        parts[1].to_string()
                    } else {
                        "unknown".to_string()
                    }
                } else if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(trimmed) {
                    parsed
                        .get("requestId")
                        .and_then(|r| r.as_str())
                        .unwrap_or("unknown")
                        .to_string()
                } else {
                    "unknown".to_string()
                };

                let req_payload = if trimmed.starts_with("query:") {
                    let parts: Vec<&str> = trimmed.splitn(3, ':').collect();
                    if parts.len() == 3 {
                        serde_json::json!({
                            "requestId": parts[1],
                            "query": parts[2]
                        })
                        .to_string()
                    } else {
                        serde_json::json!({
                            "requestId": "unknown",
                            "query": trimmed
                        })
                        .to_string()
                    }
                } else {
                    trimmed.to_string()
                };

                let sender_clone = ws_sender.clone();
                let app_clone = app.clone();
                tokio::spawn(async move {
                    if let Err(e) = forward_query_to_daemon(&req_payload, sender_clone.clone(), app_clone).await {
                        eprintln!("Error handling agent query: {:?}", e);
                        let error_resp = serde_json::json!({
                            "requestId": request_id,
                            "status": "error",
                            "data": {},
                            "error": {
                                "code": "DAEMON_ERROR",
                                "message": "Failed to communicate with python sidecar daemon",
                                "details": e.to_string()
                            }
                        });
                        let _ = sender_clone.lock().await
                            .send(tokio_tungstenite::tungstenite::Message::Text(
                                error_resp.to_string().into(),
                            ))
                            .await;
                    }
                });
            } else {
                eprintln!("Unknown command: {}", text);
            }
        }
    }
    Ok(())
}

async fn forward_query_to_daemon(
    req_json: &str,
    ws_sender: std::sync::Arc<tokio::sync::Mutex<futures_util::stream::SplitSink<tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>, tokio_tungstenite::tungstenite::Message>>>,
    app: AppHandle,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let daemon_mutex = get_daemon_mutex();
    let mut guard = daemon_mutex.lock().await;

    let mut attempts = 0;
    while attempts < 2 {
        attempts += 1;

        let mut is_running = false;
        if let Some(daemon) = guard.as_mut() {
            if let Ok(None) = daemon.child.try_wait() {
                is_running = true;
            }
        }

        if !is_running {
            println!(
                "Starting Python agent sidecar daemon (attempt {})...",
                attempts
            );
            match AgentDaemon::start().await {
                Ok(d) => {
                    *guard = Some(d);
                }
                Err(e) => {
                    return Err(format!("Failed to start sidecar daemon: {}", e).into());
                }
            }
        }

        let daemon = guard.as_mut().unwrap();

        // Write query to daemon stdin
        if let Err(e) = daemon.send_query(req_json).await {
            eprintln!("Failed to write to daemon: {:?}. Retrying...", e);
            *guard = None;
            continue;
        }

        // Stream response lines back
        let mut success_stream = true;
        loop {
            match daemon.read_response().await {
                Ok(line) => {
                    if line.is_empty() {
                        eprintln!("Daemon EOF. Process may have crashed.");
                        success_stream = false;
                        break;
                    }

                    // Forward line to websocket
                    if let Err(e) = ws_sender.lock().await
                        .send(tokio_tungstenite::tungstenite::Message::Text(
                            line.clone().into(),
                        ))
                        .await
                    {
                        eprintln!(
                            "Client disconnected while streaming daemon response: {:?}",
                            e
                        );
                        let _ = daemon.child.kill().await;
                        *guard = None;
                        return Ok(());
                    }

                    // Check for terminal state & emit overlay guidance
                    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&line) {
                        emit_agent_progress(&app, &line);
                        if let Some(status) = parsed.get("status").and_then(|s| s.as_str()) {
                            if status == "success" {
                                if let Some(data) = parsed.get("data") {
                                    if let Some(steps) = data.get("steps") {
                                        if let Some(overlay) = app.get_webview_window("overlay") {
                                            let _ = overlay.emit("blinky://guidance", serde_json::json!({
                                                "summary": data.get("response").unwrap_or(&serde_json::Value::String("".to_string())),
                                                "steps": steps,
                                                "active_app": data.get("active_app").unwrap_or(&serde_json::json!({ "title": "", "process": "", "supported": false })),
                                                "ocr": data.get("ocr").unwrap_or(&serde_json::json!({ "count": 0, "items": [] })),
                                                "screenshot": data.get("screenshot").unwrap_or(&serde_json::Value::Null),
                                            }));
                                        }
                                    }
                                }
                                break;
                            } else if status == "error" {
                                break;
                            }
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Error reading from daemon: {:?}.", e);
                    success_stream = false;
                    break;
                }
            }
        }

        if success_stream {
            return Ok(());
        } else {
            let _ = daemon.child.kill().await;
            *guard = None;
            if attempts >= 2 {
                return Err("Daemon crashed repeatedly during execution".into());
            }
        }
    }

    Err("Failed to execute query".into())
}


async fn forward_query_to_daemon_collect(
    req_json: &str,
    app: &AppHandle,
) -> Result<Vec<String>, String> {
    let daemon_mutex = get_daemon_mutex();
    let mut guard = daemon_mutex.lock().await;

    let mut attempts = 0;
    while attempts < 2 {
        attempts += 1;

        let mut is_running = false;
        if let Some(daemon) = guard.as_mut() {
            if let Ok(None) = daemon.child.try_wait() {
                is_running = true;
            }
        }

        if !is_running {
            println!(
                "Starting Python agent sidecar daemon (attempt {})...",
                attempts
            );
            match AgentDaemon::start().await {
                Ok(d) => {
                    *guard = Some(d);
                }
                Err(e) => {
                    return Err(format!("Failed to start sidecar daemon: {}", e));
                }
            }
        }

        let daemon = guard.as_mut().unwrap();

        if let Err(e) = daemon.send_query(req_json).await {
            eprintln!("Failed to write to daemon: {:?}. Retrying...", e);
            *guard = None;
            continue;
        }

        let mut lines = Vec::new();
        let mut success_stream = true;
        loop {
            match daemon.read_response().await {
                Ok(line) => {
                    if line.is_empty() {
                        eprintln!("Daemon EOF. Process may have crashed.");
                        success_stream = false;
                        break;
                    }

                    emit_agent_progress(app, &line);
                    lines.push(line.clone());

                    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&line) {
                        if let Some(status) = parsed.get("status").and_then(|s| s.as_str()) {
                            if status == "success" || status == "error" {
                                break;
                            }
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Error reading from daemon: {:?}.", e);
                    success_stream = false;
                    break;
                }
            }
        }

        if success_stream {
            return Ok(lines);
        } else {
            let _ = daemon.child.kill().await;
            *guard = None;
            if attempts >= 2 {
                return Err("Daemon crashed repeatedly during execution".to_string());
            }
        }
    }

    Err("Failed to execute query".to_string())
}

fn emit_agent_progress(app: &AppHandle, line: &str) {
    let Ok(parsed) = serde_json::from_str::<serde_json::Value>(line) else {
        return;
    };

    // Forward workflow-save prompts emitted by the agent loop
    // ({"type":"status","phase":"recipe_prompt","data":{...}}).
    if parsed.get("type").and_then(|t| t.as_str()) == Some("status")
        && parsed.get("phase").and_then(|p| p.as_str()) == Some("recipe_prompt")
    {
        let _ = app.emit(
            "blinky://recipe-prompt",
            parsed.get("data").cloned().unwrap_or(serde_json::Value::Null),
        );
        return;
    }

    if parsed.get("status").and_then(|s| s.as_str()) != Some("processing") {
        return;
    }

    let data = parsed.get("data").unwrap_or(&serde_json::Value::Null);
    let message = data.get("message").and_then(|m| m.as_str()).unwrap_or("");
    if message.is_empty() {
        return;
    }

    if data
        .get("is_chunk")
        .and_then(|c| c.as_bool())
        .unwrap_or(false)
    {
        let _ = app.emit(
            "blinky://tutor-chunk",
            serde_json::json!({ "message": message }),
        );
    } else {
        let _ = app.emit(
            "blinky://tutor-status",
            serde_json::json!({ "phase": "agent", "message": message }),
        );
    }
}

pub(crate) fn agent_responses_to_tutor_result(
    lines: &[String],
) -> Result<serde_json::Value, String> {
    let mut streamed = String::new();
    let mut final_response = String::new();

    for line in lines {
        let parsed: serde_json::Value = match serde_json::from_str(line.trim()) {
            Ok(value) => value,
            Err(_) => continue,
        };

        let status = parsed.get("status").and_then(|s| s.as_str()).unwrap_or("");
        let data = parsed.get("data").unwrap_or(&serde_json::Value::Null);

        if status == "processing"
            && data
                .get("is_chunk")
                .and_then(|c| c.as_bool())
                .unwrap_or(false)
        {
            if let Some(message) = data.get("message").and_then(|m| m.as_str()) {
                streamed.push_str(message);
            }
        } else if status == "success" {
            final_response = data
                .get("response")
                .and_then(|r| r.as_str())
                .unwrap_or("")
                .trim()
                .to_string();
        } else if status == "error" {
            let error = parsed.get("error").unwrap_or(&serde_json::Value::Null);
            let message = error
                .get("message")
                .and_then(|m| m.as_str())
                .unwrap_or("Agent query failed");
            let details = error.get("details").and_then(|d| d.as_str()).unwrap_or("");
            if details.is_empty() {
                return Err(message.to_string());
            }
            return Err(format!("{message}: {details}"));
        }
    }

    let summary = if final_response.is_empty() {
        streamed.trim().to_string()
    } else {
        final_response
    };

    Ok(serde_json::json!({
        "summary": if summary.is_empty() { "Done." } else { &summary },
        "steps": [],
        "active_app": { "title": "", "process": "", "supported": false },
        "ocr": { "count": 0, "items": [] },
        "elapsed_ms": 0,
        "provider": "agent-router",
        "warnings": [],
        "is_continuation": false
    }))
}

#[cfg(test)]
mod tests {
    use super::agent_responses_to_tutor_result;

    #[test]
    fn agent_result_uses_terminal_success_response() {
        let lines = vec![
            r#"{"requestId":"abc","status":"processing","data":{"message":"Opening YouTube..."},"error":null}"#.to_string(),
            r#"{"requestId":"abc","status":"success","data":{"response":"Opened YouTube."},"error":null}"#.to_string(),
        ];

        let result = agent_responses_to_tutor_result(&lines).expect("agent result");

        assert_eq!(result["summary"], "Opened YouTube.");
        assert_eq!(result["provider"], "agent-router");
        assert_eq!(result["steps"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn agent_result_uses_streamed_chunks_when_terminal_response_is_empty() {
        let lines = vec![
            r#"{"requestId":"abc","status":"processing","data":{"message":"Hello ","is_chunk":true},"error":null}"#.to_string(),
            r#"{"requestId":"abc","status":"processing","data":{"message":"there","is_chunk":true},"error":null}"#.to_string(),
            r#"{"requestId":"abc","status":"success","data":{"response":""},"error":null}"#.to_string(),
        ];

        let result = agent_responses_to_tutor_result(&lines).expect("agent result");

        assert_eq!(result["summary"], "Hello there");
    }

    #[test]
    fn agent_result_surfaces_terminal_error() {
        let lines = vec![
            r#"{"requestId":"abc","status":"error","data":{},"error":{"code":"OPEN_URL_FAILED","message":"Failed to open YouTube","details":"no browser"}}"#.to_string(),
        ];

        let error = agent_responses_to_tutor_result(&lines).expect_err("agent error");

        assert!(error.contains("Failed to open YouTube"));
        assert!(error.contains("no browser"));
    }

    #[test]
    fn token_equals_matches_exact_token() {
        assert!(super::token_equals("abc123", "abc123"));
    }

    #[test]
    fn token_equals_rejects_different_tokens() {
        assert!(!super::token_equals("abc123", "abc124"));
        assert!(!super::token_equals("abc123", "abc12"));
        assert!(!super::token_equals("", "abc123"));
        assert!(!super::token_equals("abc123", ""));
    }

    #[test]
    fn extract_query_token_parses_token_param() {
        assert_eq!(
            super::extract_query_token("/?token=deadbeef"),
            Some("deadbeef".to_string())
        );
        assert_eq!(
            super::extract_query_token("/sarvam-stt?token=abc&foo=1"),
            Some("abc".to_string())
        );
    }

    #[test]
    fn extract_query_token_returns_none_without_token() {
        assert_eq!(super::extract_query_token("/"), None);
        assert_eq!(super::extract_query_token("/?foo=bar"), None);
        assert_eq!(super::extract_query_token("/?token="), None);
    }

    #[test]
    fn uri_without_query_strips_query_string() {
        assert_eq!(super::uri_without_query("/"), "/");
        assert_eq!(super::uri_without_query("/?token=x"), "/");
        assert_eq!(super::uri_without_query("/sarvam-stt?token=x"), "/sarvam-stt");
    }

    #[test]
    fn generate_remote_token_is_nonempty_and_unique() {
        let a = super::generate_remote_token();
        let b = super::generate_remote_token();
        assert_eq!(a.len(), 32);
        assert_ne!(a, b);
    }
}

fn get_sarvam_api_key() -> String {
    let root = project_root();
    let envs = read_env_file(&root);
    envs.into_iter()
        .find(|(k, _)| k == "SARVAM_API_KEY")
        .map(|(_, v)| v)
        .unwrap_or_default()
}

/// Generates (and persists) a per-install remote-control token on first use,
/// then returns it. The token gates every WebSocket command so an unauthenticated
/// host on the LAN cannot drive power/automation actions.
fn get_remote_token() -> String {
    let root = project_root();
    let envs = read_env_file(&root);
    let existing = envs
        .iter()
        .find(|(k, _)| k == "BLINKY_REMOTE_TOKEN")
        .map(|(_, v)| v.clone())
        .unwrap_or_default();
    if !existing.is_empty() {
        return existing;
    }

    // Generate an unpredictable token and persist it in .env
    let token = generate_remote_token();

    let env_path = root.join(".env");
    let contents = std::fs::read_to_string(&env_path).unwrap_or_default();
    let mut lines: Vec<String> = contents.lines().map(|s| s.to_string()).collect();
    let mut found = false;
    for line in lines.iter_mut() {
        if line.trim().starts_with("BLINKY_REMOTE_TOKEN=") {
            *line = format!("BLINKY_REMOTE_TOKEN={}", token);
            found = true;
        }
    }
    if !found {
        lines.push(format!("BLINKY_REMOTE_TOKEN={}", token));
    }
    let _ = std::fs::write(&env_path, lines.join("\n") + "\n");
    token
}

/// Simple constant-time comparison to avoid leaking token length/timing.
fn token_equals(provided: &str, expected: &str) -> bool {
    if provided.len() != expected.len() {
        return false;
    }
    let provided = provided.as_bytes();
    let expected = expected.as_bytes();
    let mut diff = 0u8;
    for (a, b) in provided.iter().zip(expected.iter()) {
        diff |= a ^ b;
    }
    diff == 0
}

/// Strips the `?query` part from a stored path_and_query for logging.
fn uri_without_query(path_and_query: &str) -> String {
    match path_and_query.find('?') {
        Some(idx) => path_and_query[..idx].to_string(),
        None => path_and_query.to_string(),
    }
}

/// Extracts the `?token=<value>` query param from a stored path_and_query.
fn extract_query_token(path_and_query: &str) -> Option<String> {
    let query = path_and_query.split('?').nth(1)?;
    for pair in query.split('&') {
        if let Some((key, value)) = pair.split_once('=') {
            if key == "token" && !value.is_empty() {
                return Some(value.to_string());
            }
        }
    }
    None
}

/// RFC 4122-ish random hex token, dependency-free (no `rand` crate needed).
/// Uses `SystemTime` + address entropy + `RandomState` (OS-seeded) so two
/// process invocations produce effectively unpredictable values.
fn generate_remote_token() -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};
    use std::sync::atomic::{AtomicU64, Ordering};

    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let t = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0);
    let addr = &COUNTER as *const AtomicU64 as u64 as u64;
    let ctr = COUNTER.fetch_add(1, Ordering::Relaxed);
    let entropy = t ^ addr ^ ctr ^ (addr.rotate_left(17));

    // RandomState's internal seed is randomized per process from OS entropy,
    // so hashing the entropy with it yields an unpredictable, fresh token.
    let mut hasher = RandomState::new().build_hasher();
    hasher.write_u64(entropy);
    let a = hasher.finish();
    let mut hasher2 = RandomState::new().build_hasher();
    hasher2.write_u64(entropy >> 1);
    let b = hasher2.finish();

    format!("{:016x}{:016x}", a, b)
}

async fn handle_sarvam_stt_proxy(
    client_ws: tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let api_key = get_sarvam_api_key();
    if api_key.is_empty() {
        return Err("SARVAM_API_KEY is not configured in environment".into());
    }

    let url = "wss://api.sarvam.ai/speech-to-text/ws?model=saaras:v3&language-code=en-IN";
    let mut request = url.into_client_request()?;
    request
        .headers_mut()
        .insert("api-subscription-key", api_key.parse()?);

    let (sarvam_ws, _) = connect_async(request).await?;
    println!("Successfully connected proxy to Sarvam STT WebSocket");

    let (mut client_write, mut client_read) = client_ws.split();
    let (mut sarvam_write, mut sarvam_read) = sarvam_ws.split();

    let client_to_sarvam = async {
        while let Some(msg) = client_read.next().await {
            let msg = msg?;
            if msg.is_close() {
                println!("STT: Client sent close");
                let _ = sarvam_write.send(msg).await;
                break;
            }
            if msg.is_text() {
                println!(
                    "STT: Client -> Sarvam text: {:?}",
                    msg.to_text().unwrap_or("")
                );
            } else if msg.is_binary() {
                println!("STT: Client -> Sarvam binary ({} bytes)", msg.len());
            }
            if let Err(e) = sarvam_write.send(msg).await {
                eprintln!("STT: Error sending to Sarvam: {:?}", e);
                break;
            }
        }
        println!("STT: client_to_sarvam ended");
        Ok::<(), Box<dyn std::error::Error + Send + Sync>>(())
    };

    let sarvam_to_client = async {
        while let Some(msg) = sarvam_read.next().await {
            let msg = msg?;
            if msg.is_close() {
                println!("STT: Sarvam sent close");
                let _ = client_write.send(msg).await;
                break;
            }
            if msg.is_text() {
                println!(
                    "STT: Sarvam -> Client text: {:?}",
                    msg.to_text().unwrap_or("")
                );
            } else if msg.is_binary() {
                println!("STT: Sarvam -> Client binary ({} bytes)", msg.len());
            }
            if let Err(e) = client_write.send(msg).await {
                eprintln!("STT: Error sending to client: {:?}", e);
                break;
            }
        }
        println!("STT: sarvam_to_client ended");
        Ok::<(), Box<dyn std::error::Error + Send + Sync>>(())
    };

    let res = tokio::select! {
        r1 = client_to_sarvam => r1,
        r2 = sarvam_to_client => r2,
    };

    if let Err(e) = res {
        let err_str = e.to_string();
        if !err_str.contains("closed") && !err_str.contains("Closing") && !err_str.contains("reset")
        {
            eprintln!("STT Proxy error: {}", err_str);
        }
    }
    Ok(())
}

async fn handle_sarvam_tts_proxy(
    client_ws: tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let api_key = get_sarvam_api_key();
    if api_key.is_empty() {
        return Err("SARVAM_API_KEY is not configured in environment".into());
    }

    let url = "wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3";
    let mut request = url.into_client_request()?;
    request
        .headers_mut()
        .insert("api-subscription-key", api_key.parse()?);

    let (sarvam_ws, _) = connect_async(request).await?;
    println!("Successfully connected proxy to Sarvam TTS WebSocket");

    let (mut client_write, mut client_read) = client_ws.split();
    let (mut sarvam_write, mut sarvam_read) = sarvam_ws.split();

    let client_to_sarvam = async {
        while let Some(msg) = client_read.next().await {
            let msg = msg?;
            if msg.is_close() {
                println!("TTS: Client sent close");
                let _ = sarvam_write.send(msg).await;
                break;
            }
            if msg.is_text() {
                println!(
                    "TTS: Client -> Sarvam text: {:?}",
                    msg.to_text().unwrap_or("")
                );
            } else if msg.is_binary() {
                println!("TTS: Client -> Sarvam binary ({} bytes)", msg.len());
            }
            if let Err(e) = sarvam_write.send(msg).await {
                eprintln!("TTS: Error sending to Sarvam: {:?}", e);
                break;
            }
        }
        println!("TTS: client_to_sarvam ended");
        Ok::<(), Box<dyn std::error::Error + Send + Sync>>(())
    };

    let sarvam_to_client = async {
        while let Some(msg) = sarvam_read.next().await {
            let msg = msg?;
            if msg.is_close() {
                println!("TTS: Sarvam sent close");
                let _ = client_write.send(msg).await;
                break;
            }
            if msg.is_text() {
                println!(
                    "TTS: Sarvam -> Client text: {:?}",
                    msg.to_text().unwrap_or("")
                );
            } else if msg.is_binary() {
                println!("TTS: Sarvam -> Client binary ({} bytes)", msg.len());
            }
            if let Err(e) = client_write.send(msg).await {
                eprintln!("TTS: Error sending to client: {:?}", e);
                break;
            }
        }
        println!("TTS: sarvam_to_client ended");
        Ok::<(), Box<dyn std::error::Error + Send + Sync>>(())
    };

    let res = tokio::select! {
        r1 = client_to_sarvam => r1,
        r2 = sarvam_to_client => r2,
    };

    if let Err(e) = res {
        let err_str = e.to_string();
        if !err_str.contains("closed") && !err_str.contains("Closing") && !err_str.contains("reset")
        {
            eprintln!("TTS Proxy error: {}", err_str);
        }
    }
    Ok(())
}
