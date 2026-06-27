#![allow(dead_code)]

use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, BufWriter};
use tokio::net::{TcpListener, TcpStream};
use tokio::process::Command;

/// Start a persistent TCP bridge for `computer-use-linux mcp`.
/// Forces ydotool backend to avoid portal permission prompts.
pub fn start_mcp_bridge() {
    std::thread::spawn(|| {
        let rt = match tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
        {
            Ok(rt) => rt,
            Err(e) => {
                eprintln!("MCP bridge: failed to create runtime: {e}");
                return;
            }
        };

        rt.block_on(async {
            let listener = match TcpListener::bind("127.0.0.1:0").await {
                Ok(l) => l,
                Err(e) => {
                    eprintln!("MCP bridge: failed to bind: {e}");
                    return;
                }
            };

            let port = listener.local_addr().unwrap().port();

            let port_file = dirs_runtime_dir().join("blinky_mcp_port");
            let _ = std::fs::write(&port_file, port.to_string());

            eprintln!("MCP bridge: listening on 127.0.0.1:{port}");

            loop {
                match listener.accept().await {
                    Ok((stream, addr)) => {
                        eprintln!("MCP bridge: client {addr}");
                        tokio::spawn(handle_client(stream));
                    }
                    Err(e) => eprintln!("MCP bridge: accept error: {e}"),
                }
            }
        });
    });
}

async fn handle_client(stream: TcpStream) {
    let binary = find_mcp_binary();

    let mut child = match Command::new(&binary)
        .arg("mcp")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::inherit())
        .env("COMPUTER_USE_LINUX_FORCE_YDOTOOL_POINTER", "1")
        .env("COMPUTER_USE_LINUX_FORCE_YDOTOOL_KEYBOARD", "1")
        .kill_on_drop(true)
        .spawn()
    {
        Ok(c) => {
            eprintln!("MCP bridge: spawned mcp (pid {})", c.id().unwrap_or(0));
            c
        }
        Err(e) => {
            eprintln!("MCP bridge: spawn failed: {e}");
            return;
        }
    };

    let child_stdin = child.stdin.take().expect("no stdin");
    let child_stdout = child.stdout.take().expect("no stdout");

    let (stream_read, stream_write) = tokio::io::split(stream);

    let mut child_writer = BufWriter::new(child_stdin);
    let mut child_reader = BufReader::new(child_stdout);
    let mut stream_reader = BufReader::new(stream_read);
    let mut stream_writer = BufWriter::new(stream_write);

    let t1 = tokio::spawn(async move {
        let mut buf = String::new();
        loop {
            buf.clear();
            match stream_reader.read_line(&mut buf).await {
                Ok(0) => break,
                Ok(_) => {
                    if child_writer.write_all(buf.as_bytes()).await.is_err()
                        || child_writer.flush().await.is_err()
                    {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    let t2 = tokio::spawn(async move {
        let mut buf = String::new();
        loop {
            buf.clear();
            match child_reader.read_line(&mut buf).await {
                Ok(0) => break,
                Ok(_) => {
                    if stream_writer.write_all(buf.as_bytes()).await.is_err()
                        || stream_writer.flush().await.is_err()
                    {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    tokio::select! {
        _ = t1 => {},
        _ = t2 => {},
    }

    eprintln!("MCP bridge: client disconnected");
}

fn find_mcp_binary() -> String {
    for candidate in &[
        "/home/fev/.cargo/bin/computer-use-linux",
        "/usr/local/bin/computer-use-linux",
        "/usr/bin/computer-use-linux",
    ] {
        if std::path::Path::new(candidate).exists() {
            return candidate.to_string();
        }
    }
    "computer-use-linux".to_string()
}

fn dirs_runtime_dir() -> std::path::PathBuf {
    if let Ok(dir) = std::env::var("XDG_RUNTIME_DIR") {
        std::path::PathBuf::from(dir)
    } else {
        std::path::PathBuf::from("/tmp")
    }
}
