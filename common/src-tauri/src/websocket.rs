use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use futures_util::{
    stream::{SplitSink, SplitStream},
    SinkExt, StreamExt,
};
use serde::Serialize;
use std::collections::HashMap;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};
use tokio::io::{AsyncBufReadExt, AsyncRead, AsyncWrite, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};
use tokio::process::{Child, ChildStdin, ChildStdout, Command as TokioCommand};
use tokio::sync::Mutex;
use tokio_rustls::{TlsAcceptor, TlsConnector};
use tokio_tungstenite::tungstenite::{client::IntoClientRequest, Message};
use tokio_tungstenite::{client_async, connect_async, WebSocketStream};

type WsSender<S> = std::sync::Arc<Mutex<SplitSink<WebSocketStream<S>, Message>>>;
type DesktopTlsStream = tokio_rustls::client::TlsStream<TcpStream>;
type DesktopWsSender = WsSender<DesktopTlsStream>;

static DESKTOP_SECURE_SOCKETS: OnceLock<Mutex<HashMap<String, DesktopWsSender>>> = OnceLock::new();

fn get_desktop_secure_sockets() -> &'static Mutex<HashMap<String, DesktopWsSender>> {
    DESKTOP_SECURE_SOCKETS.get_or_init(|| Mutex::new(HashMap::new()))
}

#[derive(Debug, Clone, Serialize)]
struct SecureSocketEvent {
    socket_id: String,
    kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    message: Option<String>,
}

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
    let mut candidates = vec![
        root.join("python_runtime").join("Python313"),
        root.join(".venv"),
    ];

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

static ACTIVE_CLIENTS: OnceLock<Mutex<Vec<tokio::sync::mpsc::UnboundedSender<String>>>> = OnceLock::new();

/// Returns the shared registry of connected WebSocket client senders.
fn get_active_clients() -> &'static Mutex<Vec<tokio::sync::mpsc::UnboundedSender<String>>> {
    ACTIVE_CLIENTS.get_or_init(|| Mutex::new(Vec::new()))
}

/// Broadcasts a message and removes clients whose channels have closed.
pub async fn broadcast_to_all_clients(message: &str) {
    let mut clients = get_active_clients().lock().await;
    clients.retain(|tx| tx.send(message.to_string()).is_ok());
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
    let mode = crate::transport::TransportMode::current();
    let tls_acceptor = if mode.is_release() {
        let identity = match crate::tls_identity::TlsIdentity::load_or_generate(&app) {
            Ok(identity) => identity,
            Err(error) => {
                eprintln!("Failed to initialize release WSS identity: {error}");
                return;
            }
        };
        println!("Release WSS identity pin: {}", identity.public_key_pin());
        match identity.server_config() {
            Ok(config) => Some(TlsAcceptor::from(std::sync::Arc::new(config))),
            Err(error) => {
                eprintln!("Failed to initialize release WSS server: {error}");
                return;
            }
        }
    } else {
        None
    };
    println!("WebSocket server listening on {} ({:?})", addr, mode);

    while let Ok((stream, peer_addr)) = listener.accept().await {
        println!("New peer connection: {}", peer_addr);
        let app_clone = app.clone();
        let tls_acceptor = tls_acceptor.clone();
        tauri::async_runtime::spawn(async move {
            if let Err(e) =
                handle_connection(stream, peer_addr, app_clone, mode, tls_acceptor).await
            {
                eprintln!("Error handling connection from {}: {}", peer_addr, e);
            }
        });
    }
}

pub fn secure_transport_info(
    app: &AppHandle,
) -> Result<serde_json::Value, Box<dyn std::error::Error + Send + Sync>> {
    let mode = crate::transport::TransportMode::current();
    let pin = if mode.is_release() {
        Some(
            crate::tls_identity::TlsIdentity::load_or_generate(app)?
                .public_key_pin()
                .to_string(),
        )
    } else {
        None
    };

    Ok(serde_json::json!({
        "mode": if mode.is_release() { "release" } else { "development" },
        "desktop_url": if mode.is_release() {
            "wss://127.0.0.1:9001"
        } else {
            "ws://127.0.0.1:9001"
        },
        "certificate_pin": pin,
    }))
}

pub async fn secure_socket_connect(
    app: AppHandle,
    socket_id: String,
    url: String,
    expected_pin: Option<String>,
) -> Result<(), String> {
    let (host, port, path) = parse_local_wss_url(&url)?;
    if crate::transport::TransportMode::current() != crate::transport::TransportMode::Release {
        return Err(
            "The native secure socket bridge is only available in the release transport variant"
                .into(),
        );
    }

    let identity = crate::tls_identity::TlsIdentity::load_or_generate(&app)
        .map_err(|error| format!("Failed to load WSS identity: {error}"))?;
    let tls_config = identity
        .client_config(expected_pin.as_deref())
        .map_err(|error| format!("Failed to configure WSS certificate pinning: {error}"))?;
    let tcp_stream = TcpStream::connect((host.as_str(), port))
        .await
        .map_err(|error| format!("Failed to connect to local WSS gateway: {error}"))?;
    let connector = TlsConnector::from(std::sync::Arc::new(tls_config));
    let server_name = rustls::pki_types::ServerName::try_from(host.clone())
        .map_err(|error| format!("Invalid WSS server name: {error}"))?;
    let tls_stream = connector
        .connect(server_name, tcp_stream)
        .await
        .map_err(|error| format!("WSS certificate verification failed: {error}"))?;

    let request_url = format!("wss://{host}:{port}{path}");
    let request = request_url
        .into_client_request()
        .map_err(|error| format!("Invalid WSS request URL: {error}"))?;
    let (websocket, _) = client_async(request, tls_stream)
        .await
        .map_err(|error| format!("WSS WebSocket handshake failed: {error}"))?;
    let (sender, mut receiver) = websocket.split();
    let sender = std::sync::Arc::new(Mutex::new(sender));

    if let Some(previous) = get_desktop_secure_sockets()
        .lock()
        .await
        .insert(socket_id.clone(), sender.clone())
    {
        let _ = previous.lock().await.send(Message::Close(None)).await;
    }

    let _ = app.emit(
        "blinky://secure-socket-open",
        SecureSocketEvent {
            socket_id: socket_id.clone(),
            kind: "open".to_string(),
            data: None,
            message: None,
        },
    );

    let app_for_receiver = app.clone();
    let socket_id_for_receiver = socket_id.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(message) = receiver.next().await {
            match message {
                Ok(Message::Text(text)) => {
                    let _ = app_for_receiver.emit(
                        "blinky://secure-socket-message",
                        SecureSocketEvent {
                            socket_id: socket_id_for_receiver.clone(),
                            kind: "text".to_string(),
                            data: Some(text.to_string()),
                            message: None,
                        },
                    );
                }
                Ok(Message::Binary(bytes)) => {
                    let _ = app_for_receiver.emit(
                        "blinky://secure-socket-message",
                        SecureSocketEvent {
                            socket_id: socket_id_for_receiver.clone(),
                            kind: "binary".to_string(),
                            data: Some(BASE64.encode(bytes)),
                            message: None,
                        },
                    );
                }
                Ok(Message::Close(_)) => break,
                Ok(Message::Ping(_) | Message::Pong(_)) => {}
                Err(error) => {
                    let _ = app_for_receiver.emit(
                        "blinky://secure-socket-error",
                        SecureSocketEvent {
                            socket_id: socket_id_for_receiver.clone(),
                            kind: "error".to_string(),
                            data: None,
                            message: Some(error.to_string()),
                        },
                    );
                    break;
                }
                Ok(Message::Frame(_)) => {}
            }
        }

        let mut sockets = get_desktop_secure_sockets().lock().await;
        let is_current = sockets
            .get(&socket_id_for_receiver)
            .map(|current| std::sync::Arc::ptr_eq(current, &sender))
            .unwrap_or(false);
        if is_current {
            sockets.remove(&socket_id_for_receiver);
        }
        drop(sockets);

        if is_current {
            let _ = app_for_receiver.emit(
                "blinky://secure-socket-close",
                SecureSocketEvent {
                    socket_id: socket_id_for_receiver,
                    kind: "close".to_string(),
                    data: None,
                    message: None,
                },
            );
        }
    });

    Ok(())
}

pub async fn secure_socket_send(
    socket_id: String,
    kind: String,
    data: String,
) -> Result<(), String> {
    let sender = get_desktop_secure_sockets()
        .lock()
        .await
        .get(&socket_id)
        .cloned()
        .ok_or_else(|| format!("No secure socket exists for {socket_id}"))?;
    let message = match kind.as_str() {
        "text" => Message::Text(data.into()),
        "binary" => Message::Binary(
            BASE64
                .decode(data)
                .map_err(|error| format!("Invalid base64 WebSocket payload: {error}"))?
                .into(),
        ),
        other => return Err(format!("Unsupported secure socket frame kind: {other}")),
    };
    let result = sender
        .lock()
        .await
        .send(message)
        .await
        .map_err(|error| format!("Failed to send WSS frame: {error}"));
    result
}

pub async fn secure_socket_close(socket_id: String) -> Result<(), String> {
    let sender = get_desktop_secure_sockets().lock().await.remove(&socket_id);
    if let Some(sender) = sender {
        sender
            .lock()
            .await
            .send(Message::Close(None))
            .await
            .map_err(|error| format!("Failed to close WSS socket: {error}"))?;
    }
    Ok(())
}

fn parse_local_wss_url(url: &str) -> Result<(String, u16, String), String> {
    let rest = url
        .strip_prefix("wss://")
        .ok_or_else(|| "Secure desktop sockets require a wss:// URL".to_string())?;
    let (authority, path) = rest.split_once('/').unwrap_or((rest, ""));
    let (host, port) = authority
        .rsplit_once(':')
        .ok_or_else(|| "WSS URL must include an explicit port".to_string())?;
    if host != "127.0.0.1" && host != "localhost" {
        return Err(
            "The desktop secure socket bridge only permits localhost WSS connections".into(),
        );
    }
    let port = port
        .parse::<u16>()
        .map_err(|error| format!("Invalid WSS port: {error}"))?;
    let path = if path.is_empty() {
        "/".to_string()
    } else {
        format!("/{path}")
    };
    Ok((host.to_string(), port, path))
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

/// Authenticates a client and handles commands received over its WebSocket.
async fn handle_connection(
    stream: TcpStream,
    peer_addr: SocketAddr,
    app: AppHandle,
    mode: crate::transport::TransportMode,
    tls_acceptor: Option<TlsAcceptor>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    if let Some(tls_acceptor) = tls_acceptor {
        let tls_stream = tls_acceptor.accept(stream).await?;
        return handle_websocket_stream(tls_stream, peer_addr, app, mode).await;
    }

    handle_websocket_stream(stream, peer_addr, app, mode).await
}

async fn handle_websocket_stream<S>(
    stream: S,
    peer_addr: SocketAddr,
    app: AppHandle,
    mode: crate::transport::TransportMode,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin + Send + 'static,
{
    let path = std::sync::Arc::new(std::sync::Mutex::new(String::new()));
    let path_clone = path.clone();
    let ws_stream = tokio_tungstenite::accept_hdr_async(
        stream,
        move |req: &tokio_tungstenite::tungstenite::handshake::server::Request, response| {
            if let Ok(mut p) = path_clone.lock() {
                *p = req
                    .uri()
                    .path_and_query()
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

    let server_token = get_remote_token();
    let is_loopback = peer_addr.ip().is_loopback();
    let remote_auth_required =
        crate::transport::remote_auth_required(mode, is_loopback, !server_token.is_empty());
    let uri_token = (mode == crate::transport::TransportMode::Development)
        .then(|| extract_query_token(&active_path))
        .flatten();
    let mut authenticated = !remote_auth_required
        || uri_token
            .as_deref()
            .map(|token| token_equals(token, &server_token))
            .unwrap_or(false);

    let (ws_sender, mut ws_receiver) = ws_stream.split();
    let ws_sender = std::sync::Arc::new(tokio::sync::Mutex::new(ws_sender));

    let (client_tx, mut client_rx) = tokio::sync::mpsc::unbounded_channel::<String>();
    {
        let mut clients = get_active_clients().lock().await;
        clients.push(client_tx);
    }

    let ws_sender_writer = ws_sender.clone();
    tokio::spawn(async move {
        while let Some(msg_text) = client_rx.recv().await {
            let _ = ws_sender_writer
                .lock()
                .await
                .send(tokio_tungstenite::tungstenite::Message::Text(msg_text.into()))
                .await;
        }
    });
    if !authenticated {
        eprintln!(
            "WARN: unauthenticated remote connection from {} — awaiting auth frame",
            peer_addr
        );
    }

    if active_path.starts_with("/sarvam-stt") || active_path.starts_with("/sarvam-tts") {
        if !authenticated {
            authenticated =
                authenticate_websocket(&mut ws_receiver, &ws_sender, &server_token, mode).await?;
        }
        if !authenticated {
            eprintln!(
                "REJECTED unauthenticated Sarvam proxy connection from {}",
                peer_addr
            );
            return Ok(());
        }
        if active_path.starts_with("/sarvam-stt") {
            return handle_sarvam_stt_proxy(ws_sender, ws_receiver).await;
        }
        return handle_sarvam_tts_proxy(ws_sender, ws_receiver).await;
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
            let trimmed = text.trim();

            if let Some(provided) = auth_token_from_frame(trimmed, mode) {
                authenticated =
                    !remote_auth_required || token_equals(provided.trim(), &server_token);
                if authenticated {
                    println!("{} authenticated successfully", peer_addr);
                } else {
                    eprintln!("{} failed authentication", peer_addr);
                }
                if mode.is_release() {
                    let _ = ws_sender
                        .lock()
                        .await
                        .send(Message::Text(
                            serde_json::json!({
                                "type": "auth_result",
                                "ok": authenticated,
                            })
                            .to_string()
                            .into(),
                        ))
                        .await;
                }
                continue;
            }

            if !authenticated {
                eprintln!("BLOCKED unauthenticated command from {}", peer_addr);
                let denied = auth_denied("unknown");
                let _ = ws_sender
                    .lock()
                    .await
                    .send(Message::Text(denied.into()))
                    .await;
                continue;
            }

            if trimmed == "get_system_info" || trimmed == "system_info" {
                let info = crate::platform::get_system_telemetry();
                let _ = ws_sender.lock().await
                    .send(tokio_tungstenite::tungstenite::Message::Text(
                        info.to_string().into(),
                    ))
                    .await;
            } else if trimmed == "hibernate" {
                let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
                let evt = serde_json::json!({
                    "type": "power_event",
                    "action": "hibernate",
                    "status": "triggered",
                    "message": "Hibernate triggered by Sentinel.",
                    "timestamp": now
                });
                let _ = app.emit("blinky://power-event", evt.clone());
                broadcast_to_all_clients(&evt.to_string()).await;
                crate::platform::execute_hibernate();
            } else if trimmed == "power_off" {
                let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
                let evt = serde_json::json!({
                    "type": "power_event",
                    "action": "power_off",
                    "status": "triggered",
                    "message": "Shutdown triggered by Sentinel.",
                    "timestamp": now
                });
                let _ = app.emit("blinky://power-event", evt.clone());
                broadcast_to_all_clients(&evt.to_string()).await;
                crate::platform::execute_power_off();
            } else if trimmed == "restart" {
                let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
                let evt = serde_json::json!({
                    "type": "power_event",
                    "action": "restart",
                    "status": "triggered",
                    "message": "Reboot triggered by Sentinel.",
                    "timestamp": now
                });
                let _ = app.emit("blinky://power-event", evt.clone());
                broadcast_to_all_clients(&evt.to_string()).await;
                crate::platform::execute_restart();
            } else if trimmed == "sleep" {
                let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
                let evt = serde_json::json!({
                    "type": "power_event",
                    "action": "sleep",
                    "status": "triggered",
                    "message": "Sleep mode triggered by Sentinel.",
                    "timestamp": now
                });
                let _ = app.emit("blinky://power-event", evt.clone());
                broadcast_to_all_clients(&evt.to_string()).await;
                crate::platform::execute_sleep();
            } else if trimmed == "volume_up" {
                crate::platform::execute_volume_up();
            } else if trimmed == "volume_down" {
                crate::platform::execute_volume_down();
            } else if trimmed == "volume_mute" || trimmed == "mute" {
                crate::platform::execute_volume_mute();
            } else if trimmed == "lock" {
                let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
                let evt = serde_json::json!({
                    "type": "power_event",
                    "action": "lock",
                    "status": "triggered",
                    "message": "Workstation locked by Sentinel.",
                    "timestamp": now
                });
                let _ = app.emit("blinky://power-event", evt.clone());
                broadcast_to_all_clients(&evt.to_string()).await;
                crate::platform::execute_lock();
            } else if trimmed == "unlock"
                || trimmed.starts_with("unlock:")
                || (trimmed.starts_with('{')
                    && serde_json::from_str::<serde_json::Value>(trimmed)
                        .ok()
                        .and_then(|v| v.get("action").and_then(|a| a.as_str()).map(|s| s == "unlock"))
                        .unwrap_or(false))
            {
                let parsed_pin = if trimmed.starts_with("unlock:") {
                    trimmed.strip_prefix("unlock:").map(|s| s.trim().to_string())
                } else if trimmed.starts_with('{') {
                    serde_json::from_str::<serde_json::Value>(trimmed)
                        .ok()
                        .and_then(|v| v.get("pin").and_then(|p| p.as_str()).map(|s| s.to_string()))
                } else {
                    None
                };

                println!("blinky: received unlock command from client (has_pin: {})", parsed_pin.is_some());

                let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
                let evt = serde_json::json!({
                    "type": "power_event",
                    "action": "unlock",
                    "status": "triggered",
                    "message": "Workstation unlock sequence dispatched by Sentinel.",
                    "timestamp": now
                });
                let _ = app.emit("blinky://power-event", evt.clone());
                broadcast_to_all_clients(&evt.to_string()).await;
                crate::platform::execute_unlock(parsed_pin.as_deref());
            } else if trimmed == "screenshot" {
                crate::platform::execute_screenshot();
            } else if trimmed == "get_sarvam_key" {
                let key = get_sarvam_api_key();
                let resp = serde_json::json!({
                    "type": "sarvam_key",
                    "key": key
                });
                let _ = ws_sender
                    .lock()
                    .await
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
                    if let Err(e) =
                        forward_query_to_daemon(&req_payload, sender_clone.clone(), app_clone).await
                    {
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
                        let _ = sender_clone
                            .lock()
                            .await
                            .send(tokio_tungstenite::tungstenite::Message::Text(
                                error_resp.to_string().into(),
                            ))
                            .await;
                    }
                });
            } else {
                eprintln!("Unknown WebSocket command from {}", peer_addr);
            }
        }
    }
    Ok(())
}

fn auth_token_from_frame(frame: &str, mode: crate::transport::TransportMode) -> Option<String> {
    if let Some(token) = frame.strip_prefix("auth:") {
        return (mode == crate::transport::TransportMode::Development)
            .then(|| token.trim().to_string());
    }

    if mode.is_release() {
        let payload = serde_json::from_str::<serde_json::Value>(frame).ok()?;
        if payload.get("type").and_then(|kind| kind.as_str()) == Some("auth") {
            return payload
                .get("token")
                .and_then(|token| token.as_str())
                .map(str::to_string);
        }
    }

    None
}

async fn authenticate_websocket<S>(
    receiver: &mut SplitStream<WebSocketStream<S>>,
    sender: &WsSender<S>,
    server_token: &str,
    mode: crate::transport::TransportMode,
) -> Result<bool, Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin + Send + 'static,
{
    let Some(message) = receiver.next().await else {
        return Ok(false);
    };
    let message = message?;
    let provided = message
        .to_text()
        .ok()
        .and_then(|frame| auth_token_from_frame(frame.trim(), mode));
    let authenticated = provided
        .as_deref()
        .map(|token| token_equals(token, server_token))
        .unwrap_or(false);

    if mode.is_release() {
        sender
            .lock()
            .await
            .send(Message::Text(
                serde_json::json!({
                    "type": "auth_result",
                    "ok": authenticated,
                })
                .to_string()
                .into(),
            ))
            .await?;
    }

    Ok(authenticated)
}

async fn forward_query_to_daemon<S>(
    req_json: &str,
    ws_sender: WsSender<S>,
    app: AppHandle,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin + Send + 'static,
{
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
                    if let Err(e) = ws_sender
                        .lock()
                        .await
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
            parsed
                .get("data")
                .cloned()
                .unwrap_or(serde_json::Value::Null),
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
    fn token_equals_rejects_empty_server_token() {
        assert!(!super::token_equals("", ""));
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
        assert_eq!(
            super::uri_without_query("/sarvam-stt?token=x"),
            "/sarvam-stt"
        );
    }

    #[test]
    fn generate_remote_token_is_nonempty_and_unique() {
        let a = super::generate_remote_token();
        let b = super::generate_remote_token();
        assert_eq!(a.len(), 32);
        assert_ne!(a, b);
    }

    #[test]
    fn development_accepts_legacy_auth_frame() {
        assert_eq!(
            super::auth_token_from_frame(
                "auth:secret",
                crate::transport::TransportMode::Development
            ),
            Some("secret".to_string())
        );
    }

    #[test]
    fn release_accepts_only_json_auth_frame() {
        assert_eq!(
            super::auth_token_from_frame(
                r#"{"type":"auth","token":"secret"}"#,
                crate::transport::TransportMode::Release
            ),
            Some("secret".to_string())
        );
        assert_eq!(
            super::auth_token_from_frame("auth:secret", crate::transport::TransportMode::Release),
            None
        );
    }

    #[test]
    fn secure_bridge_only_accepts_local_wss_urls_with_paths() {
        assert_eq!(
            super::parse_local_wss_url("wss://127.0.0.1:9001/sarvam-stt"),
            Ok(("127.0.0.1".to_string(), 9001, "/sarvam-stt".to_string()))
        );
        assert!(super::parse_local_wss_url("ws://127.0.0.1:9001/sarvam-stt").is_err());
        assert!(super::parse_local_wss_url("wss://192.168.1.4:9001/sarvam-stt").is_err());
        assert!(super::parse_local_wss_url("wss://localhost/sarvam-stt").is_err());
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

/// Reads the remote token if explicitly configured by the user in environment or .env.
/// Development may continue without one for compatibility; release remote peers then fail auth.
fn get_remote_token() -> String {
    if let Ok(val) = std::env::var("BLINKY_REMOTE_TOKEN") {
        let trimmed = val.trim().to_string();
        if !trimmed.is_empty() {
            return trimmed;
        }
    }
    let root = project_root();
    let envs = read_env_file(&root);
    envs.iter()
        .find(|(k, _)| k == "BLINKY_REMOTE_TOKEN")
        .map(|(_, v)| v.trim().to_string())
        .unwrap_or_default()
}

/// Reject an unconfigured secret, then compare equal-length token bytes without early exit.
fn token_equals(provided: &str, expected: &str) -> bool {
    if expected.is_empty() || provided.len() != expected.len() {
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
#[allow(dead_code)]
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

async fn handle_sarvam_stt_proxy<S>(
    client_write: WsSender<S>,
    mut client_read: SplitStream<WebSocketStream<S>>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin + Send + 'static,
{
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

    let (mut sarvam_write, mut sarvam_read) = sarvam_ws.split();

    let client_to_sarvam = async {
        while let Some(msg) = client_read.next().await {
            let msg = msg?;
            if msg.is_close() {
                println!("STT: Client sent close");
                let _ = sarvam_write.send(msg).await;
                break;
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
                let _ = client_write.lock().await.send(msg).await;
                break;
            }
            if let Err(e) = client_write.lock().await.send(msg).await {
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

async fn handle_sarvam_tts_proxy<S>(
    client_write: WsSender<S>,
    mut client_read: SplitStream<WebSocketStream<S>>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin + Send + 'static,
{
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

    let (mut sarvam_write, mut sarvam_read) = sarvam_ws.split();

    let client_to_sarvam = async {
        while let Some(msg) = client_read.next().await {
            let msg = msg?;
            if msg.is_close() {
                println!("TTS: Client sent close");
                let _ = sarvam_write.send(msg).await;
                break;
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
                let _ = client_write.lock().await.send(msg).await;
                break;
            }
            if let Err(e) = client_write.lock().await.send(msg).await {
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
