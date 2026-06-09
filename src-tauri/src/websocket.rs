use std::process::Command as StdCommand;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::OnceLock;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tokio_tungstenite::accept_async;
use futures_util::{StreamExt, SinkExt};
use tokio::process::{Command as TokioCommand, Child, ChildStdin, ChildStdout};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

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

        // Forward environment variables
        for var in &["GROQ_API_KEY", "BLINKY_AI_PROVIDER", "BLINKY_OLLAMA_URL", "BLINKY_OLLAMA_MODEL", "BLINKY_GROQ_URL", "BLINKY_GROQ_MODEL"] {
            if let Ok(val) = std::env::var(var) {
                cmd.env(var, val);
            }
        }

        let mut child = cmd.spawn()?;
        let stdin = child.stdin.take().ok_or_else(|| std::io::Error::new(std::io::ErrorKind::Other, "Failed to open stdin"))?;
        let stdout = child.stdout.take().ok_or_else(|| std::io::Error::new(std::io::ErrorKind::Other, "Failed to open stdout"))?;
        let reader = BufReader::new(stdout);

        Ok(Self { child, stdin, reader })
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

async fn handle_connection(stream: tokio::net::TcpStream, peer_addr: SocketAddr) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut ws_stream = accept_async(stream).await?;
    println!("WebSocket handshake succeeded with {}", peer_addr);

    while let Some(msg) = ws_stream.next().await {
        let msg = msg?;
        if msg.is_text() || msg.is_binary() {
            let text = msg.to_text()?;
            println!("Received message: {}", text);
            let trimmed = text.trim();

            if trimmed == "power_off" {
                execute_power_off();
            } else if trimmed == "restart" {
                execute_restart();
            } else if trimmed == "sleep" {
                execute_sleep();
            } else if trimmed.starts_with("query:") || trimmed.starts_with("{") {
                let request_id = if trimmed.starts_with("query:") {
                    let parts: Vec<&str> = trimmed.splitn(3, ':').collect();
                    if parts.len() == 3 {
                        parts[1].to_string()
                    } else {
                        "unknown".to_string()
                    }
                } else if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(trimmed) {
                    parsed.get("requestId").and_then(|r| r.as_str()).unwrap_or("unknown").to_string()
                } else {
                    "unknown".to_string()
                };

                let req_payload = if trimmed.starts_with("query:") {
                    let parts: Vec<&str> = trimmed.splitn(3, ':').collect();
                    if parts.len() == 3 {
                        serde_json::json!({
                            "requestId": parts[1],
                            "query": parts[2]
                        }).to_string()
                    } else {
                        serde_json::json!({
                            "requestId": "unknown",
                            "query": trimmed
                        }).to_string()
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
                    let _ = ws_stream.send(tokio_tungstenite::tungstenite::Message::Text(error_resp.to_string().into())).await;
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
    ws_stream: &mut tokio_tungstenite::WebSocketStream<tokio::net::TcpStream>
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
            println!("Starting Python agent sidecar daemon (attempt {})...", attempts);
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
                    if let Err(e) = ws_stream.send(tokio_tungstenite::tungstenite::Message::Text(line.clone().into())).await {
                        eprintln!("Client disconnected while streaming daemon response: {:?}", e);
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

fn execute_power_off() {
    println!("Executing power_off command...");
    #[cfg(target_os = "windows")]
    {
        if let Err(e) = StdCommand::new("shutdown").args(&["/s", "/t", "0"]).spawn() {
            eprintln!("Failed to execute Windows shutdown: {:?}", e);
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        if let Err(e) = StdCommand::new("systemctl").arg("poweroff").spawn() {
            eprintln!("Failed to execute Linux/Unix poweroff: {:?}", e);
        }
    }
}

fn execute_restart() {
    println!("Executing restart command...");
    #[cfg(target_os = "windows")]
    {
        if let Err(e) = StdCommand::new("shutdown").args(&["/r", "/t", "0"]).spawn() {
            eprintln!("Failed to execute Windows restart: {:?}", e);
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        if let Err(e) = StdCommand::new("systemctl").arg("reboot").spawn() {
            eprintln!("Failed to execute Linux/Unix reboot: {:?}", e);
        }
    }
}

fn execute_sleep() {
    println!("Executing sleep command...");
    #[cfg(target_os = "windows")]
    {
        if let Err(e) = StdCommand::new("rundll32.exe").args(&["powrprof.dll,SetSuspendState", "0", "1", "0"]).spawn() {
            eprintln!("Failed to execute Windows sleep: {:?}", e);
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        if let Err(e) = StdCommand::new("systemctl").arg("suspend").spawn() {
            eprintln!("Failed to execute Linux/Unix suspend: {:?}", e);
        }
    }
}

