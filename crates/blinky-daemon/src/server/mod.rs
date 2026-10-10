pub mod dispatcher;

use crate::atspi::AtspiBridge;
use crate::capture::ScreenCapturer;
use crate::compositor::hyprland::HyprlandCompositor;
use crate::compositor::Compositor;
use crate::input::InputActuator;
use crate::media::MediaController;
use crate::protocol::types::*;
use crate::system::SystemSessionController;
use anyhow::{Context, Result};
use dispatcher::RpcDispatcher;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::Mutex;
use tracing::{debug, error, info, warn};

pub struct DaemonServer {
    socket_path: PathBuf,
    dispatcher: Arc<RpcDispatcher>,
}

impl DaemonServer {
    pub fn default_socket_path() -> PathBuf {
        let runtime = std::env::var("XDG_RUNTIME_DIR")
            .unwrap_or_else(|_| format!("/run/user/{}", nix::unistd::getuid()));
        PathBuf::from(runtime).join("blinky-daemon.sock")
    }

    pub async fn new(socket_path: Option<PathBuf>) -> Result<Self> {
        let path = socket_path.unwrap_or_else(Self::default_socket_path);

        let compositor: Arc<dyn Compositor> = Arc::new(HyprlandCompositor::new());
        let capturer = Arc::new(ScreenCapturer::new());
        let input_actuator = InputActuator::new(compositor.clone())
            .context("Failed to initialize input actuator")?;
        let input = Arc::new(Mutex::new(input_actuator));

        let system = Arc::new(SystemSessionController::new().await);
        let media = Arc::new(MediaController::new().await);
        let atspi = Arc::new(AtspiBridge::new().await);

        let dispatcher = Arc::new(RpcDispatcher::new(
            compositor, capturer, input, system, media, atspi,
        ));

        Ok(Self {
            socket_path: path,
            dispatcher,
        })
    }

    pub fn with_components(
        socket_path: PathBuf,
        compositor: Arc<dyn Compositor>,
        capturer: Arc<ScreenCapturer>,
        input: Arc<Mutex<InputActuator>>,
        system: Arc<SystemSessionController>,
        media: Arc<MediaController>,
        atspi: Arc<AtspiBridge>,
    ) -> Self {
        let dispatcher = Arc::new(RpcDispatcher::new(
            compositor, capturer, input, system, media, atspi,
        ));
        Self {
            socket_path,
            dispatcher,
        }
    }

    pub async fn run(&self) -> Result<()> {
        // Clean up stale socket file if it exists
        if self.socket_path.exists() {
            debug!("Removing existing socket at {}", self.socket_path.display());
            std::fs::remove_file(&self.socket_path).ok();
        }

        let listener = UnixListener::bind(&self.socket_path)
            .with_context(|| format!("Failed to bind UNIX domain socket at {}", self.socket_path.display()))?;

        info!(
            "Blinky Daemon listening on UNIX socket: {}",
            self.socket_path.display()
        );

        loop {
            match listener.accept().await {
                Ok((stream, _)) => {
                    let dispatcher = self.dispatcher.clone();
                    tokio::spawn(async move {
                        if let Err(e) = Self::handle_client(stream, dispatcher).await {
                            debug!("Client connection closed: {:#}", e);
                        }
                    });
                }
                Err(e) => {
                    warn!("Error accepting socket connection: {}", e);
                }
            }
        }
    }

    async fn handle_client(stream: UnixStream, dispatcher: Arc<RpcDispatcher>) -> Result<()> {
        let (reader, mut writer) = stream.into_split();
        let mut lines = BufReader::new(reader).lines();

        while let Some(line) = lines.next_line().await? {
            let line_trimmed = line.trim();
            if line_trimmed.is_empty() {
                continue;
            }

            debug!("Incoming RPC request: {}", line_trimmed);

            let req_res: Result<JsonRpcRequest, serde_json::Error> = serde_json::from_str(line_trimmed);
            let response = match req_res {
                Ok(req) => dispatcher.dispatch(req).await,
                Err(e) => {
                    error!("JSON-RPC parse error: {:#}", e);
                    JsonRpcResponse::error(Id::Null, PARSE_ERROR, e.to_string(), None)
                }
            };

            let mut out_str = serde_json::to_string(&response)?;
            out_str.push('\n');
            writer.write_all(out_str.as_bytes()).await?;
            writer.flush().await?;
        }

        Ok(())
    }
}

impl Drop for DaemonServer {
    fn drop(&mut self) {
        if self.socket_path.exists() {
            std::fs::remove_file(&self.socket_path).ok();
        }
    }
}
