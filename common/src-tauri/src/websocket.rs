use futures_util::{SinkExt, StreamExt};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter};
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
        let script_path = root.join("python").join("agent_router.py");
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
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join("python").exists() {
            return cwd;
        }
        if cwd.join("_up_").join("python").exists() {
            return cwd.join("_up_");
        }
        if let Some(parent) = cwd.parent() {
            if parent.join("python").exists() {
                return parent.to_path_buf();
            }
            if parent.join("_up_").join("python").exists() {
                return parent.join("_up_");
            }
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            if exe_dir.join("python").exists() {
                return exe_dir.to_path_buf();
            }
            if exe_dir.join("_up_").join("python").exists() {
                return exe_dir.join("_up_");
            }
        }
    }

    PathBuf::from(".")
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

pub async fn start_websocket_server() {
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
        tauri::async_runtime::spawn(async move {
            if let Err(e) = handle_connection(stream, peer_addr).await {
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
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let path = std::sync::Arc::new(std::sync::Mutex::new(String::new()));
    let path_clone = path.clone();
    let mut ws_stream = tokio_tungstenite::accept_hdr_async(stream, move |req: &tokio_tungstenite::tungstenite::handshake::server::Request, response| {
        if let Ok(mut p) = path_clone.lock() {
            *p = req.uri().path().to_string();
        }
        Ok(response)
    }).await?;

    let active_path = {
        let p = path.lock().unwrap();
        p.clone()
    };
    println!("WebSocket handshake succeeded with {} for path {}", peer_addr, active_path);

    if active_path == "/sarvam-stt" {
        return handle_sarvam_stt_proxy(ws_stream).await;
    } else if active_path == "/sarvam-tts" {
        return handle_sarvam_tts_proxy(ws_stream).await;
    }

    while let Some(msg) = ws_stream.next().await {
        let msg = msg?;
        if msg.is_text() || msg.is_binary() {
            let text = msg.to_text()?;
            println!("Received message: {}", text);
            let trimmed = text.trim();

            if trimmed == "power_off" {
                crate::platform::execute_power_off();
            } else if trimmed == "restart" {
                crate::platform::execute_restart();
            } else if trimmed == "sleep" {
                crate::platform::execute_sleep();
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

                if let Err(e) = forward_query_to_daemon(&req_payload, &mut ws_stream).await {
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
                    let _ = ws_stream
                        .send(tokio_tungstenite::tungstenite::Message::Text(
                            error_resp.to_string().into(),
                        ))
                        .await;
                }
            } else {
                eprintln!("Unknown command: {}", text);
            }
        }
    }
    Ok(())
}

async fn forward_query_to_daemon(
    req_json: &str,
    ws_stream: &mut tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>,
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
                    if let Err(e) = ws_stream
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

                    // Check for terminal state
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
}

fn get_sarvam_api_key() -> String {
    let root = project_root();
    let envs = read_env_file(&root);
    envs.into_iter()
        .find(|(k, _)| k == "SARVAM_API_KEY")
        .map(|(_, v)| v)
        .unwrap_or_default()
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
    request.headers_mut().insert("api-subscription-key", api_key.parse()?);

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
                println!("STT: Client -> Sarvam text: {:?}", msg.to_text().unwrap_or(""));
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
                println!("STT: Sarvam -> Client text: {:?}", msg.to_text().unwrap_or(""));
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
        if !err_str.contains("closed") && !err_str.contains("Closing") && !err_str.contains("reset") {
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
    request.headers_mut().insert("api-subscription-key", api_key.parse()?);

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
                println!("TTS: Client -> Sarvam text: {:?}", msg.to_text().unwrap_or(""));
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
                println!("TTS: Sarvam -> Client text: {:?}", msg.to_text().unwrap_or(""));
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
        if !err_str.contains("closed") && !err_str.contains("Closing") && !err_str.contains("reset") {
            eprintln!("TTS Proxy error: {}", err_str);
        }
    }
    Ok(())
}
