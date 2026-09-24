//! Authenticated, resumable mobile-to-desktop file transfers.
//!
//! Control messages use the already-authenticated WebSocket. File bytes use a
//! separate streaming HTTP(S) listener so large files never pass through a
//! WebSocket frame or a React Native JavaScript buffer.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use fs2::available_space;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, OnceLock};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager};
use tokio::io::{
    AsyncBufRead, AsyncBufReadExt, AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, BufReader,
};
use tokio::net::TcpListener;
use tokio::sync::{mpsc::UnboundedSender, Mutex, Semaphore};
use tokio::time::timeout;
use tokio_rustls::TlsAcceptor;

const DEFAULT_MAX_BYTES: u64 = 20 * 1024 * 1024 * 1024;
const MAX_CHUNK_BYTES: u64 = 16 * 1024 * 1024;
const MAX_HEADER_BYTES: usize = 16 * 1024;
const MAX_HTTP_CONNECTIONS: usize = 32;
const TLS_HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(10);
const HEADER_READ_TIMEOUT: Duration = Duration::from_secs(10);
const REQUEST_BODY_IDLE_TIMEOUT: Duration = Duration::from_secs(30);
const SESSION_TTL: Duration = Duration::from_secs(24 * 60 * 60);

type ClientSender = UnboundedSender<String>;

#[derive(Debug)]
struct TransferRecord {
    token_digest: [u8; 32],
    filename: String,
    expected_size: u64,
    expected_sha256: String,
    uploaded_bytes: u64,
    hasher: Sha256,
    staging_path: PathBuf,
    source_path: Option<PathBuf>,
    output_path: Option<PathBuf>,
    output_filename: Option<String>,
    output_size: Option<u64>,
    output_sha256: Option<String>,
    editing: bool,
    writing: bool,
    expires_at: Instant,
    notifier: ClientSender,
}

static TRANSFERS: OnceLock<Mutex<HashMap<String, TransferRecord>>> = OnceLock::new();
static HTTP_CONNECTIONS: OnceLock<Arc<Semaphore>> = OnceLock::new();

fn transfers() -> &'static Mutex<HashMap<String, TransferRecord>> {
    TRANSFERS.get_or_init(|| Mutex::new(HashMap::new()))
}

fn http_connections() -> Arc<Semaphore> {
    HTTP_CONNECTIONS
        .get_or_init(|| Arc::new(Semaphore::new(MAX_HTTP_CONNECTIONS)))
        .clone()
}

pub(crate) async fn start_server(
    app: AppHandle,
    mode: crate::transport::TransportMode,
    tls_acceptor: Option<TlsAcceptor>,
) {
    let listener = match TcpListener::bind("0.0.0.0:9002").await {
        Ok(listener) => listener,
        Err(error) => {
            eprintln!("Failed to bind file transfer server to 0.0.0.0:9002: {error}");
            return;
        }
    };
    let scheme = if mode.is_release() { "https" } else { "http" };
    println!("Blinky file transfer server listening on {scheme}://0.0.0.0:9002");
    let connection_limit = http_connections();

    while let Ok((stream, peer_addr)) = listener.accept().await {
        let Ok(permit) = connection_limit.clone().try_acquire_owned() else {
            // Drop excess connections before they can consume an unbounded task
            // or HTTP parser allocation.
            drop(stream);
            continue;
        };
        let app = app.clone();
        let tls_acceptor = tls_acceptor.clone();
        tauri::async_runtime::spawn(async move {
            let _permit = permit;
            let result = async {
                if let Some(acceptor) = tls_acceptor {
                    let tls_stream =
                        timeout(TLS_HANDSHAKE_TIMEOUT, acceptor.accept(stream)).await??;
                    handle_http_connection(tls_stream, app).await
                } else {
                    handle_http_connection(stream, app).await
                }
            }
            .await;
            if let Err(error) = result {
                eprintln!("File transfer request from {peer_addr} failed: {error}");
            }
        });
    }
}

/// Handle a transfer control message received on an authenticated WSS session.
pub(crate) async fn handle_control_message(
    app: AppHandle,
    message: &Value,
    sender: ClientSender,
    has_presented_token: bool,
    configured_token: bool,
) {
    let request_id = message
        .get("requestId")
        .and_then(Value::as_str)
        .unwrap_or("");
    let kind = message.get("type").and_then(Value::as_str).unwrap_or("");
    if !has_presented_token || !configured_token {
        send_json(
            &sender,
            json!({
                "type": "file_error",
                "requestId": request_id,
                "message": "File transfer requires a configured BLINKY_REMOTE_TOKEN and an authenticated connection."
            }),
        );
        return;
    }

    match kind {
        "file_offer" => offer_file(&app, message, sender).await,
        "file_resume" => resume_file(message, sender).await,
        "file_cancel" => cancel_file(message, sender).await,
        "file_edit" => start_edit(&app, message, sender).await,
        _ => {}
    }
}

async fn offer_file(app: &AppHandle, message: &Value, sender: ClientSender) {
    let request_id = message
        .get("requestId")
        .and_then(Value::as_str)
        .unwrap_or("");
    let fail = |message: &str| {
        send_json(
            &sender,
            json!({
                "type": "file_error",
                "requestId": request_id,
                "message": message
            }),
        );
    };

    let Some(filename) = message.get("name").and_then(Value::as_str) else {
        fail("The file name is missing.");
        return;
    };
    let Some(size) = message.get("size").and_then(Value::as_u64) else {
        fail("The file size is missing or invalid.");
        return;
    };
    let Some(expected_sha256) = message.get("sha256").and_then(Value::as_str) else {
        fail("A SHA-256 file digest is required.");
        return;
    };
    if let Err(reason) = validate_filename(filename) {
        fail(reason);
        return;
    }
    if size == 0 {
        fail("Empty files cannot be transferred.");
        return;
    }
    if !is_sha256(expected_sha256) {
        fail("The SHA-256 file digest is invalid.");
        return;
    }
    let max_size = configured_max_size();
    if size > max_size {
        fail(&format!(
            "File exceeds the configured limit of {}.",
            human_bytes(max_size)
        ));
        return;
    }

    let root = match app.path().download_dir() {
        Ok(path) => path.join("Blinky"),
        Err(error) => {
            fail(&format!("Could not locate the Downloads folder: {error}"));
            return;
        }
    };
    let staging_dir = root.join(".staging");
    if let Err(error) = tokio::fs::create_dir_all(&staging_dir).await {
        fail(&format!(
            "Could not prepare the Blinky transfer folder: {error}"
        ));
        return;
    }
    let edit_requested = message.get("purpose").and_then(Value::as_str) == Some("edit");
    let required_space = if edit_requested {
        size.saturating_mul(2)
    } else {
        size.saturating_add(64 * 1024 * 1024)
    };
    match available_space(&root) {
        Ok(free) if free >= required_space => {}
        Ok(free) => {
            fail(&format!(
                "Not enough free space. This transfer needs about {}, but {} is available.",
                human_bytes(required_space),
                human_bytes(free)
            ));
            return;
        }
        Err(error) => {
            fail(&format!("Could not check free disk space: {error}"));
            return;
        }
    }

    let (transfer_id, token) = match random_id_and_token() {
        Ok(values) => values,
        Err(error) => {
            fail(&format!(
                "Could not create a secure transfer session: {error}"
            ));
            return;
        }
    };
    let staging_path = staging_dir.join(format!("{transfer_id}.part"));
    if let Err(error) = tokio::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&staging_path)
        .await
    {
        fail(&format!(
            "Could not create the temporary upload file: {error}"
        ));
        return;
    }

    expire_old_transfers().await;
    transfers().lock().await.insert(
        transfer_id.clone(),
        TransferRecord {
            token_digest: Sha256::digest(token.as_bytes()).into(),
            filename: filename.to_string(),
            expected_size: size,
            expected_sha256: expected_sha256.to_ascii_lowercase(),
            uploaded_bytes: 0,
            hasher: Sha256::new(),
            staging_path,
            source_path: None,
            output_path: None,
            output_filename: None,
            output_size: None,
            output_sha256: None,
            editing: false,
            writing: false,
            expires_at: Instant::now() + SESSION_TTL,
            notifier: sender.clone(),
        },
    );

    send_json(
        &sender,
        json!({
            "type": "file_offer_result",
            "requestId": request_id,
            "transferId": transfer_id,
            "temporaryToken": token,
            "uploadOffset": 0,
            "chunkSize": MAX_CHUNK_BYTES,
            "expiresInSeconds": SESSION_TTL.as_secs(),
        }),
    );
}

async fn resume_file(message: &Value, sender: ClientSender) {
    let request_id = message
        .get("requestId")
        .and_then(Value::as_str)
        .unwrap_or("");
    let transfer_id = message
        .get("transferId")
        .and_then(Value::as_str)
        .unwrap_or("");
    let token = message
        .get("temporaryToken")
        .and_then(Value::as_str)
        .unwrap_or("");
    let mut records = transfers().lock().await;
    let Some(record) = records.get_mut(transfer_id) else {
        send_json(
            &sender,
            json!({"type":"file_error","requestId":request_id,"message":"Transfer session expired or was cancelled."}),
        );
        return;
    };
    if record.expires_at <= Instant::now() || !token_matches(record, token) {
        send_json(
            &sender,
            json!({"type":"file_error","requestId":request_id,"message":"Transfer session expired or its temporary token is invalid."}),
        );
        return;
    }
    record.notifier = sender.clone();
    send_json(
        &sender,
        json!({
            "type": "file_resume_result",
            "requestId": request_id,
            "transferId": transfer_id,
            "uploadOffset": record.uploaded_bytes,
            "complete": record.source_path.is_some(),
            "editing": record.editing,
            "edited": record.output_path.is_some(),
            "name": record.output_filename,
            "size": record.output_size,
            "sha256": record.output_sha256,
            "downloadPath": format!("/download/{transfer_id}"),
        }),
    );
}

async fn cancel_file(message: &Value, sender: ClientSender) {
    let request_id = message
        .get("requestId")
        .and_then(Value::as_str)
        .unwrap_or("");
    let transfer_id = message
        .get("transferId")
        .and_then(Value::as_str)
        .unwrap_or("");
    let token = message
        .get("temporaryToken")
        .and_then(Value::as_str)
        .unwrap_or("");
    let record = {
        let mut records = transfers().lock().await;
        match records.get(transfer_id) {
            Some(record)
                if token_matches(record, token)
                    && record.source_path.is_none()
                    && !record.editing
                    && !record.writing =>
            {
                records.remove(transfer_id)
            }
            Some(record) if token_matches(record, token) => {
                send_json(
                    &sender,
                    json!({"type":"file_error","requestId":request_id,"message":"A completed upload, active upload write, or active AiCut job cannot be cancelled."}),
                );
                return;
            }
            _ => None,
        }
    };
    if let Some(record) = record {
        let _ = tokio::fs::remove_file(record.staging_path).await;
        send_json(
            &sender,
            json!({"type":"file_cancelled","requestId":request_id,"transferId":transfer_id}),
        );
    } else {
        send_json(
            &sender,
            json!({"type":"file_error","requestId":request_id,"message":"Transfer session was not found."}),
        );
    }
}

async fn start_edit(app: &AppHandle, message: &Value, sender: ClientSender) {
    let request_id = message
        .get("requestId")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let transfer_id = message
        .get("transferId")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let token = message
        .get("temporaryToken")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let instruction = message
        .get("instruction")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if instruction.is_empty() || instruction.len() > 8_000 {
        send_json(
            &sender,
            json!({"type":"file_error","requestId":request_id,"message":"Enter an AiCut edit instruction of at most 8,000 characters."}),
        );
        return;
    }

    let source = {
        let mut records = transfers().lock().await;
        let Some(record) = records.get_mut(&transfer_id) else {
            send_json(
                &sender,
                json!({"type":"file_error","requestId":request_id,"message":"Transfer session expired or was cancelled."}),
            );
            return;
        };
        if record.expires_at <= Instant::now() || !token_matches(record, &token) {
            send_json(
                &sender,
                json!({"type":"file_error","requestId":request_id,"message":"Transfer session expired or its temporary token is invalid."}),
            );
            return;
        }
        let Some(source_path) = record.source_path.clone() else {
            send_json(
                &sender,
                json!({"type":"file_error","requestId":request_id,"message":"The upload must finish before AiCut can start."}),
            );
            return;
        };
        if record.editing {
            send_json(
                &sender,
                json!({"type":"file_error","requestId":request_id,"message":"AiCut is already processing this transfer."}),
            );
            return;
        }
        record.editing = true;
        record.expires_at = Instant::now() + SESSION_TTL;
        record.notifier = sender.clone();
        source_path
    };

    send_json(
        &sender,
        json!({"type":"file_edit_started","requestId":request_id,"transferId":transfer_id,"message":"AiCut is preparing the edit."}),
    );
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        match run_aicut_job(&app, &transfer_id, &source, &instruction).await {
            Ok((path, filename, size, sha256)) => {
                let event = {
                    let mut records = transfers().lock().await;
                    records.get_mut(&transfer_id).map(|record| {
                        record.editing = false;
                        record.expires_at = Instant::now() + SESSION_TTL;
                        record.output_path = Some(path);
                        record.output_filename = Some(filename.clone());
                        record.output_size = Some(size);
                        record.output_sha256 = Some(sha256.clone());
                        let event = json!({
                            "type": "file_edit_complete",
                            "requestId": request_id,
                            "transferId": transfer_id,
                            "name": filename,
                            "size": size,
                            "sha256": sha256,
                            "downloadPath": format!("/download/{transfer_id}"),
                        });
                        (record.notifier.clone(), event)
                    })
                };
                if let Some((notifier, event)) = event {
                    send_json(&notifier, event);
                }
            }
            Err(error) => {
                let message = error.to_string();
                let notifier = {
                    let mut records = transfers().lock().await;
                    records.get_mut(&transfer_id).map(|record| {
                        record.editing = false;
                        record.expires_at = Instant::now() + SESSION_TTL;
                        record.notifier.clone()
                    })
                };
                if let Some(notifier) = notifier {
                    send_json(
                        &notifier,
                        json!({"type":"file_edit_error","requestId":request_id,"transferId":transfer_id,"message":message}),
                    );
                }
            }
        }
    });
}

async fn run_aicut_job(
    app: &AppHandle,
    transfer_id: &str,
    source_path: &Path,
    instruction: &str,
) -> Result<(PathBuf, String, u64, String), Box<dyn std::error::Error + Send + Sync>> {
    let root = crate::websocket::project_root();
    let python = crate::websocket::python_executable(&root);
    let output_dir = app.path().download_dir()?.join("Blinky").join("Edited");
    tokio::fs::create_dir_all(&output_dir).await?;

    let script = root
        .join("common")
        .join("python")
        .join("file_transfer_aicut.py");
    let mut command = tokio::process::Command::new(python);
    command
        .arg("-u")
        .arg(script)
        .current_dir(&root)
        .kill_on_drop(true)
        .envs(crate::websocket::read_env_file(&root))
        .env("BLINKY_TRANSFER_OUTPUT_DIR", &output_dir)
        .env("BLINKY_TRANSFER_ID", transfer_id)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null());

    let mut child = command.spawn()?;
    let payload = json!({"instruction":instruction,"input_path":source_path});
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(payload.to_string().as_bytes()).await?;
        stdin.shutdown().await?;
    }
    let output = tokio::time::timeout(Duration::from_secs(6 * 60 * 60), child.wait_with_output())
        .await
        .map_err(|_| "AiCut timed out after six hours")??;
    let result: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
        format!(
            "AiCut returned invalid JSON ({error}): {}",
            String::from_utf8_lossy(&output.stderr)
        )
    })?;
    if !output.status.success() || result.get("success").and_then(Value::as_bool) != Some(true) {
        let reason = result
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or_else(|| "AiCut could not complete this edit.");
        return Err(reason.to_string().into());
    }

    let path = result
        .get("output_path")
        .or_else(|| result.get("srt_output"))
        .and_then(Value::as_str)
        .ok_or("AiCut completed without an output file path")?;
    let path = PathBuf::from(path).canonicalize()?;
    let output_root = output_dir.canonicalize()?;
    if !path.starts_with(&output_root) || !path.is_file() {
        return Err("AiCut output escaped the Blinky Edited folder".into());
    }

    let original_name = transfers()
        .lock()
        .await
        .get(transfer_id)
        .map(|record| record.filename.clone())
        .ok_or("Transfer session expired while AiCut was running")?;
    let original_stem = Path::new(&original_name)
        .file_stem()
        .and_then(|stem| stem.to_str())
        .unwrap_or("edited-file");
    let mut safe_stem = String::new();
    for character in original_stem.chars() {
        if safe_stem.len() + character.len_utf8() > 220 {
            break;
        }
        safe_stem.push(character);
    }
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("mp4");
    let extension: String = extension.chars().take(16).collect();
    let (size, sha256) = hash_file(&path).await?;
    if size > configured_max_size() {
        let _ = tokio::fs::remove_file(&path).await;
        return Err(format!(
            "AiCut output exceeds the configured limit of {}.",
            human_bytes(configured_max_size())
        )
        .into());
    }
    let final_path = move_to_unique_path(
        &path,
        &output_root,
        &format!("{safe_stem}_edited"),
        &extension,
    )
    .await?;
    let filename = final_path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or("AiCut output file name is invalid")?
        .to_string();
    Ok((final_path, filename, size, sha256))
}

async fn handle_http_connection<S>(
    stream: S,
    _app: AppHandle,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin,
{
    let mut stream = BufReader::new(stream);
    let (request_line, headers) =
        match timeout(HEADER_READ_TIMEOUT, read_request_headers(&mut stream)).await {
            Ok(Ok(parsed)) => parsed,
            Ok(Err(error)) if error.kind() == std::io::ErrorKind::InvalidData => {
                return respond_error(
                    &mut stream,
                    431,
                    "Request header too large or invalid",
                    None,
                )
                .await;
            }
            Ok(Err(error)) => return Err(error.into()),
            Err(_) => return Ok(()),
        };
    let mut parts = request_line.split_whitespace();
    let method = parts.next().unwrap_or("");
    let target = parts.next().unwrap_or("");

    let path = target.split('?').next().unwrap_or(target);
    let route = path.trim_matches('/');
    let parts: Vec<&str> = route.split('/').collect();
    let token = bearer_token(&headers);
    match (method, parts.as_slice()) {
        ("POST", ["upload", transfer_id]) => {
            let offset = headers
                .get("upload-offset")
                .and_then(|value| value.parse::<u64>().ok());
            let content_length = headers
                .get("content-length")
                .and_then(|value| value.parse::<u64>().ok());
            let (Some(offset), Some(content_length)) = (offset, content_length) else {
                return respond_error(
                    &mut stream,
                    400,
                    "Upload-Offset and Content-Length are required",
                    None,
                )
                .await;
            };
            if content_length == 0 || content_length > MAX_CHUNK_BYTES {
                return respond_error(
                    &mut stream,
                    413,
                    "Upload chunks must be between 1 byte and 16 MiB",
                    None,
                )
                .await;
            }
            if let Err(failure) =
                validate_upload_request(transfer_id, &token, offset, content_length).await
            {
                return respond_error(
                    &mut stream,
                    failure.status,
                    &failure.message,
                    failure.offset,
                )
                .await;
            }
            let mut chunk = vec![0u8; content_length as usize];
            match read_exact_with_idle_timeout(&mut stream, &mut chunk).await {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::TimedOut => {
                    return respond_error(
                        &mut stream,
                        408,
                        "Timed out waiting for upload chunk data",
                        None,
                    )
                    .await;
                }
                Err(error) => {
                    return respond_error(
                        &mut stream,
                        400,
                        &format!("Incomplete upload chunk: {error}"),
                        None,
                    )
                    .await;
                }
            }
            let (status, next_offset, completed) =
                match accept_chunk(transfer_id, &token, offset, &chunk).await {
                    Ok(result) => result,
                    Err(failure) => {
                        return respond_error(
                            &mut stream,
                            failure.status,
                            &failure.message,
                            failure.offset,
                        )
                        .await
                    }
                };
            let body = json!({"uploadOffset":next_offset,"complete":completed}).to_string();
            let status_code = if completed { 201 } else { status };
            write_http_response(
                &mut stream,
                status_code,
                "application/json",
                body.as_bytes(),
                &[(&"upload-offset", next_offset.to_string())],
            )
            .await?;
        }
        ("GET", ["download", transfer_id]) => {
            let Some((path, size, sha256, filename)) = get_download(transfer_id, &token).await
            else {
                return respond_error(
                    &mut stream,
                    404,
                    "Download is unavailable or the temporary token is invalid",
                    None,
                )
                .await;
            };
            let Some(range) = headers
                .get("range")
                .and_then(|value| parse_range(value, size))
            else {
                return respond_error(&mut stream, 416, "A valid byte Range is required", None)
                    .await;
            };
            let (start, end) = range;
            let content_length = end - start + 1;
            let header_lines = vec![
                ("accept-ranges", "bytes".to_string()),
                ("content-range", format!("bytes {start}-{end}/{size}")),
                ("x-file-size", size.to_string()),
                ("x-file-sha256", sha256),
                ("x-file-name", percent_encode_header(&filename)),
            ];
            write_http_head(
                &mut stream,
                206,
                "application/octet-stream",
                content_length,
                &header_lines,
            )
            .await?;
            let mut file = tokio::fs::File::open(path).await?;
            tokio::io::AsyncSeekExt::seek(&mut file, std::io::SeekFrom::Start(start)).await?;
            let mut remaining = content_length;
            let mut buffer = vec![0u8; 1024 * 1024];
            while remaining > 0 {
                let limit =
                    usize::try_from(remaining.min(buffer.len() as u64)).unwrap_or(buffer.len());
                let count = file.read(&mut buffer[..limit]).await?;
                if count == 0 {
                    break;
                }
                stream.get_mut().write_all(&buffer[..count]).await?;
                remaining -= count as u64;
            }
            stream.get_mut().flush().await?;
        }
        _ => return respond_error(&mut stream, 404, "Unknown file transfer route", None).await,
    }
    Ok(())
}

async fn read_request_headers<R>(
    reader: &mut R,
) -> std::io::Result<(String, HashMap<String, String>)>
where
    R: AsyncBufRead + Unpin,
{
    let request_line = String::from_utf8(read_bounded_line(reader, MAX_HEADER_BYTES).await?)
        .map_err(|_| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "HTTP request line must be UTF-8",
            )
        })?;
    let mut consumed = request_line.len();
    let mut headers = HashMap::<String, String>::new();

    loop {
        let line = read_bounded_line(reader, MAX_HEADER_BYTES.saturating_sub(consumed)).await?;
        consumed += line.len();
        if line.is_empty() || line == b"\r\n" || line == b"\n" {
            break;
        }
        let line = std::str::from_utf8(&line).map_err(|_| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "HTTP header line must be UTF-8",
            )
        })?;
        if let Some((name, value)) = line.split_once(':') {
            headers.insert(name.trim().to_ascii_lowercase(), value.trim().to_string());
        }
    }

    Ok((request_line, headers))
}

/// Read a single line without letting a peer grow the destination beyond its
/// remaining request-header budget.
async fn read_bounded_line<R>(reader: &mut R, max_bytes: usize) -> std::io::Result<Vec<u8>>
where
    R: AsyncBufRead + Unpin,
{
    let mut line = Vec::new();
    loop {
        let (consumed, found_newline) = {
            let available = reader.fill_buf().await?;
            if available.is_empty() {
                return Ok(line);
            }
            let newline = available.iter().position(|byte| *byte == b'\n');
            let count = newline.map_or(available.len(), |position| position + 1);
            if count > max_bytes.saturating_sub(line.len()) {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "HTTP request header exceeds the configured limit",
                ));
            }
            line.extend_from_slice(&available[..count]);
            (count, newline.is_some())
        };
        reader.consume(consumed);
        if found_newline {
            return Ok(line);
        }
    }
}

async fn read_exact_with_idle_timeout<R>(
    reader: &mut R,
    mut buffer: &mut [u8],
) -> std::io::Result<()>
where
    R: AsyncRead + Unpin,
{
    while !buffer.is_empty() {
        let count = timeout(REQUEST_BODY_IDLE_TIMEOUT, reader.read(buffer))
            .await
            .map_err(|_| {
                std::io::Error::new(
                    std::io::ErrorKind::TimedOut,
                    "Timed out waiting for upload chunk data",
                )
            })??;
        if count == 0 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::UnexpectedEof,
                "Incomplete upload chunk",
            ));
        }
        buffer = &mut buffer[count..];
    }
    Ok(())
}

struct ChunkFailure {
    status: u16,
    message: String,
    offset: Option<u64>,
}

struct ChunkReservation {
    staging_path: PathBuf,
    filename: String,
    expected_size: u64,
    expected_sha256: String,
    hasher: Sha256,
}

struct WrittenChunk {
    next_offset: u64,
    hasher: Sha256,
    destination: Option<(PathBuf, String)>,
}

async fn validate_upload_request(
    transfer_id: &str,
    token: &str,
    offset: u64,
    content_length: u64,
) -> Result<(), ChunkFailure> {
    let records = transfers().lock().await;
    let record = records.get(transfer_id).ok_or_else(|| ChunkFailure {
        status: 404,
        message: "Transfer session was not found".into(),
        offset: None,
    })?;
    if record.expires_at <= Instant::now() || !token_matches(record, token) {
        return Err(ChunkFailure {
            status: 401,
            message: "Transfer token expired or is invalid".into(),
            offset: None,
        });
    }
    if record.source_path.is_some() {
        return Err(ChunkFailure {
            status: 409,
            message: "Upload is already complete".into(),
            offset: Some(record.uploaded_bytes),
        });
    }
    if record.writing {
        return Err(ChunkFailure {
            status: 423,
            message: "Another upload chunk is still being written".into(),
            offset: None,
        });
    }
    if offset != record.uploaded_bytes {
        return Err(ChunkFailure {
            status: 409,
            message: "Upload offset does not match the server state".into(),
            offset: Some(record.uploaded_bytes),
        });
    }
    let end = match offset.checked_add(content_length) {
        Some(end) => end,
        None => {
            return Err(ChunkFailure {
                status: 413,
                message: "Upload size overflow".into(),
                offset: Some(record.uploaded_bytes),
            });
        }
    };
    if end > record.expected_size {
        return Err(ChunkFailure {
            status: 413,
            message: "Chunk exceeds the offered file size".into(),
            offset: Some(record.uploaded_bytes),
        });
    }
    Ok(())
}

async fn accept_chunk(
    transfer_id: &str,
    token: &str,
    offset: u64,
    chunk: &[u8],
) -> Result<(u16, u64, bool), ChunkFailure> {
    let reservation = {
        let mut records = transfers().lock().await;
        let record = records.get_mut(transfer_id).ok_or_else(|| ChunkFailure {
            status: 404,
            message: "Transfer session was not found".into(),
            offset: None,
        })?;
        if record.expires_at <= Instant::now() || !token_matches(record, token) {
            return Err(ChunkFailure {
                status: 401,
                message: "Transfer token expired or is invalid".into(),
                offset: None,
            });
        }
        if record.source_path.is_some() {
            return Err(ChunkFailure {
                status: 409,
                message: "Upload is already complete".into(),
                offset: Some(record.uploaded_bytes),
            });
        }
        if record.writing {
            return Err(ChunkFailure {
                status: 423,
                message: "Another upload chunk is still being written".into(),
                offset: None,
            });
        }
        if offset != record.uploaded_bytes {
            return Err(ChunkFailure {
                status: 409,
                message: "Upload offset does not match the server state".into(),
                offset: Some(record.uploaded_bytes),
            });
        }
        let end = offset
            .checked_add(chunk.len() as u64)
            .ok_or_else(|| ChunkFailure {
                status: 413,
                message: "Upload size overflow".into(),
                offset: Some(record.uploaded_bytes),
            })?;
        if end > record.expected_size {
            return Err(ChunkFailure {
                status: 413,
                message: "Chunk exceeds the offered file size".into(),
                offset: Some(record.uploaded_bytes),
            });
        }

        record.writing = true;
        ChunkReservation {
            staging_path: record.staging_path.clone(),
            filename: record.filename.clone(),
            expected_size: record.expected_size,
            expected_sha256: record.expected_sha256.clone(),
            hasher: record.hasher.clone(),
        }
    };

    let written = write_upload_chunk(&reservation, offset, chunk).await;
    let written = match written {
        Ok(written) => written,
        Err(failure) => {
            let mut records = transfers().lock().await;
            if failure.status == 422 {
                let staging_path = records
                    .remove(transfer_id)
                    .map(|record| record.staging_path)
                    .unwrap_or(reservation.staging_path);
                drop(records);
                let _ = tokio::fs::remove_file(staging_path).await;
            } else if let Some(record) = records.get_mut(transfer_id) {
                record.writing = false;
            }
            return Err(failure);
        }
    };

    let WrittenChunk {
        next_offset,
        hasher,
        destination,
    } = written;
    let mut records = transfers().lock().await;
    let Some(record) = records.get_mut(transfer_id) else {
        let orphan = destination
            .as_ref()
            .map(|(path, _)| path.clone())
            .unwrap_or(reservation.staging_path);
        drop(records);
        let _ = tokio::fs::remove_file(orphan).await;
        return Err(ChunkFailure {
            status: 404,
            message: "Transfer session was removed while writing the chunk".into(),
            offset: None,
        });
    };
    if !record.writing || !token_matches(record, token) {
        let orphan = destination
            .as_ref()
            .map(|(path, _)| path.clone())
            .unwrap_or_else(|| record.staging_path.clone());
        record.writing = false;
        drop(records);
        let _ = tokio::fs::remove_file(orphan).await;
        return Err(ChunkFailure {
            status: 409,
            message: "Transfer state changed while writing the chunk".into(),
            offset: None,
        });
    }

    record.writing = false;
    record.uploaded_bytes = next_offset;
    record.hasher = hasher;
    let completed = if let Some((destination, filename)) = destination {
        record.source_path = Some(destination);
        Some((
            record.notifier.clone(),
            filename,
            record.expected_size,
            record.expected_sha256.clone(),
        ))
    } else {
        None
    };
    drop(records);

    if let Some((notifier, filename, size, sha256)) = completed.as_ref() {
        send_json(
            notifier,
            json!({
                "type":"file_received",
                "transferId":transfer_id,
                "name":filename,
                "size":size,
                "sha256":sha256,
            }),
        );
    }

    Ok((
        if completed.is_some() { 201 } else { 200 },
        next_offset,
        completed.is_some(),
    ))
}

async fn write_upload_chunk(
    reservation: &ChunkReservation,
    offset: u64,
    chunk: &[u8],
) -> Result<WrittenChunk, ChunkFailure> {
    let end = offset
        .checked_add(chunk.len() as u64)
        .filter(|end| *end <= reservation.expected_size)
        .ok_or_else(|| ChunkFailure {
            status: 413,
            message: "Chunk exceeds the offered file size".into(),
            offset: Some(offset),
        })?;
    let failure_offset = Some(offset);
    let mut file = tokio::fs::OpenOptions::new()
        .write(true)
        .open(&reservation.staging_path)
        .await
        .map_err(|error| ChunkFailure {
            status: 500,
            message: error.to_string(),
            offset: failure_offset,
        })?;
    tokio::io::AsyncSeekExt::seek(&mut file, std::io::SeekFrom::Start(offset))
        .await
        .map_err(|error| ChunkFailure {
            status: 500,
            message: error.to_string(),
            offset: failure_offset,
        })?;
    file.write_all(chunk).await.map_err(|error| ChunkFailure {
        status: 500,
        message: error.to_string(),
        offset: failure_offset,
    })?;
    file.sync_data().await.map_err(|error| ChunkFailure {
        status: 500,
        message: error.to_string(),
        offset: failure_offset,
    })?;

    let mut hasher = reservation.hasher.clone();
    hasher.update(chunk);
    if end == reservation.expected_size
        && format!("{:x}", hasher.clone().finalize()) != reservation.expected_sha256
    {
        return Err(ChunkFailure {
            status: 422,
            message: "The completed file SHA-256 did not match the offered digest".into(),
            offset: None,
        });
    }

    let destination = if end == reservation.expected_size {
        let (parent, filename) =
            destination_for_upload(&reservation.staging_path, &reservation.filename).map_err(
                |error| ChunkFailure {
                    status: 500,
                    message: error.to_string(),
                    offset: Some(end),
                },
            )?;
        let path = move_to_unique_path(
            &reservation.staging_path,
            &parent,
            Path::new(&filename)
                .file_stem()
                .and_then(|value| value.to_str())
                .unwrap_or("file"),
            Path::new(&filename)
                .extension()
                .and_then(|value| value.to_str())
                .unwrap_or(""),
        )
        .await
        .map_err(|error| ChunkFailure {
            status: 500,
            message: error.to_string(),
            offset: Some(end),
        })?;
        let safe_name = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or(&filename)
            .to_string();
        Some((path, safe_name))
    } else {
        None
    };

    Ok(WrittenChunk {
        next_offset: end,
        hasher,
        destination,
    })
}

async fn get_download(transfer_id: &str, token: &str) -> Option<(PathBuf, u64, String, String)> {
    let records = transfers().lock().await;
    let record = records.get(transfer_id)?;
    if record.expires_at <= Instant::now() || !token_matches(record, token) {
        return None;
    }
    Some((
        record.output_path.clone()?,
        record.output_size?,
        record.output_sha256.clone()?,
        record.output_filename.clone()?,
    ))
}

async fn expire_old_transfers() {
    let expired: Vec<PathBuf> = {
        let mut records = transfers().lock().await;
        let ids: Vec<String> = records
            .iter()
            .filter_map(|(id, record)| {
                (!record.editing && !record.writing && record.expires_at <= Instant::now())
                    .then_some(id.clone())
            })
            .collect();
        ids.into_iter()
            .filter_map(|id| records.remove(&id).map(|record| record.staging_path))
            .collect()
    };
    for staging in expired {
        // Received inputs and edited outputs are user files under Downloads/Blinky.
        // Expiring the temporary bearer capability must never delete those files.
        let _ = tokio::fs::remove_file(staging).await;
    }
}

fn token_matches(record: &TransferRecord, token: &str) -> bool {
    let actual: [u8; 32] = Sha256::digest(token.as_bytes()).into();
    constant_time_eq(&actual, &record.token_digest)
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .fold(0u8, |difference, (a, b)| difference | (a ^ b))
        == 0
}

fn random_id_and_token() -> Result<(String, String), getrandom::Error> {
    let mut id = [0u8; 16];
    let mut token = [0u8; 32];
    getrandom::fill(&mut id)?;
    getrandom::fill(&mut token)?;
    Ok((hex(&id), URL_SAFE_NO_PAD.encode(token)))
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn validate_filename(filename: &str) -> Result<(), &'static str> {
    if filename.trim().is_empty() || filename.len() > 255 {
        return Err("File name must be between 1 and 255 bytes.");
    }
    if filename == "." || filename == ".." || filename.starts_with('.') {
        return Err("Hidden and relative file names cannot be uploaded.");
    }
    if filename.chars().any(|c| {
        c.is_control() || matches!(c, '/' | '\\' | ':' | '<' | '>' | '"' | '|' | '?' | '*')
    }) {
        return Err("File name contains a path separator or invalid character.");
    }
    if filename.ends_with('.') || filename.ends_with(' ') {
        return Err("File names cannot end with a dot or space.");
    }
    let device_name = filename
        .split('.')
        .next()
        .unwrap_or("")
        .to_ascii_uppercase();
    if matches!(device_name.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || ["COM", "LPT"].iter().any(|prefix| {
            device_name.strip_prefix(prefix).is_some_and(|tail| {
                matches!(tail, "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9")
            })
        })
    {
        return Err("This file name is reserved by Windows.");
    }
    Ok(())
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn configured_max_size() -> u64 {
    std::env::var("BLINKY_FILE_TRANSFER_MAX_BYTES")
        .ok()
        .or_else(|| {
            let root = crate::websocket::project_root();
            crate::websocket::read_env_file(&root)
                .into_iter()
                .find(|(key, _)| key == "BLINKY_FILE_TRANSFER_MAX_BYTES")
                .map(|(_, value)| value)
        })
        .and_then(|value| value.parse::<u64>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_MAX_BYTES)
}

fn human_bytes(bytes: u64) -> String {
    const GIB: u64 = 1024 * 1024 * 1024;
    if bytes >= GIB {
        format!("{} GiB", (bytes as f64 / GIB as f64 * 10.0).round() / 10.0)
    } else {
        format!(
            "{} MiB",
            (bytes as f64 / (1024 * 1024) as f64 * 10.0).round() / 10.0
        )
    }
}

fn destination_for_upload(
    staging_path: &Path,
    filename: &str,
) -> std::io::Result<(PathBuf, String)> {
    let directory = staging_path
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::NotFound,
                "transfer folder does not exist",
            )
        })?;
    Ok((directory.to_path_buf(), filename.to_string()))
}

async fn move_to_unique_path(
    source: &Path,
    directory: &Path,
    stem: &str,
    extension: &str,
) -> std::io::Result<PathBuf> {
    let extension = extension.trim_start_matches('.');
    for index in 0..100_000 {
        let name = if index == 0 {
            stem.to_string()
        } else {
            format!("{stem} ({index})")
        };
        let candidate = if extension.is_empty() {
            directory.join(name)
        } else {
            directory.join(format!("{name}.{extension}"))
        };
        match tokio::fs::hard_link(source, &candidate).await {
            Ok(()) => {
                if let Err(error) = tokio::fs::remove_file(source).await {
                    let _ = tokio::fs::remove_file(&candidate).await;
                    return Err(error);
                }
                return Ok(candidate);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::AlreadyExists,
        "could not find an unused destination name",
    ))
}

async fn hash_file(path: &Path) -> std::io::Result<(u64, String)> {
    let mut file = tokio::fs::File::open(path).await?;
    let mut hasher = Sha256::new();
    let mut size = 0u64;
    let mut buffer = vec![0u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer).await?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
        size += count as u64;
    }
    Ok((size, format!("{:x}", hasher.finalize())))
}

fn bearer_token(headers: &HashMap<String, String>) -> String {
    headers
        .get("authorization")
        .and_then(|value| {
            value
                .strip_prefix("Bearer ")
                .or_else(|| value.strip_prefix("bearer "))
        })
        .unwrap_or("")
        .trim()
        .to_string()
}

fn parse_range(header: &str, total: u64) -> Option<(u64, u64)> {
    let range = header.strip_prefix("bytes=")?;
    let (start, end) = range.split_once('-')?;
    let start = start.parse::<u64>().ok()?;
    let end = if end.is_empty() {
        total.checked_sub(1)?
    } else {
        end.parse::<u64>().ok()?.min(total.checked_sub(1)?)
    };
    if start >= total || end < start || end - start + 1 > MAX_CHUNK_BYTES {
        return None;
    }
    Some((start, end))
}

fn percent_encode_header(value: &str) -> String {
    value
        .bytes()
        .map(|byte| {
            if byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-') {
                (byte as char).to_string()
            } else {
                format!("%{byte:02X}")
            }
        })
        .collect()
}

async fn respond_error<S>(
    stream: &mut BufReader<S>,
    status: u16,
    message: &str,
    offset: Option<u64>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin,
{
    let body = json!({"error":message}).to_string();
    let extra = offset
        .map(|value| vec![("upload-offset", value.to_string())])
        .unwrap_or_default();
    write_http_response(stream, status, "application/json", body.as_bytes(), &extra).await
}

async fn write_http_response<S>(
    stream: &mut BufReader<S>,
    status: u16,
    content_type: &str,
    body: &[u8],
    extra: &[(&str, String)],
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin,
{
    write_http_head(stream, status, content_type, body.len() as u64, extra).await?;
    stream.get_mut().write_all(body).await?;
    stream.get_mut().flush().await?;
    Ok(())
}

async fn write_http_head<S>(
    stream: &mut BufReader<S>,
    status: u16,
    content_type: &str,
    content_length: u64,
    extra: &[(&str, String)],
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    S: AsyncRead + AsyncWrite + Unpin,
{
    let reason = match status {
        200 => "OK",
        201 => "Created",
        206 => "Partial Content",
        400 => "Bad Request",
        401 => "Unauthorized",
        404 => "Not Found",
        409 => "Conflict",
        413 => "Payload Too Large",
        416 => "Range Not Satisfiable",
        422 => "Unprocessable Content",
        431 => "Request Header Fields Too Large",
        _ => "Internal Server Error",
    };
    let mut response = format!("HTTP/1.1 {status} {reason}\r\nContent-Type: {content_type}\r\nContent-Length: {content_length}\r\nConnection: close\r\n");
    for (name, value) in extra {
        response.push_str(&format!("{}: {}\r\n", name, value));
    }
    response.push_str("\r\n");
    stream.get_mut().write_all(response.as_bytes()).await?;
    Ok(())
}

fn send_json(sender: &ClientSender, value: Value) {
    let _ = sender.send(value.to_string());
}
