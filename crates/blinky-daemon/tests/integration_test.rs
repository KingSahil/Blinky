use blinky_daemon::protocol::types::{JsonRpcRequest, JsonRpcResponse};
use blinky_daemon::server::DaemonServer;
use serde_json::json;
use std::time::Duration;
use tempfile::NamedTempFile;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;

struct TestClient {
    stream: UnixStream,
    next_id: i64,
}

impl TestClient {
    async fn connect(sock_path: &std::path::Path) -> Self {
        let stream = UnixStream::connect(sock_path).await.expect("Connect failed");
        Self { stream, next_id: 1 }
    }

    async fn call(&mut self, method: &str, params: serde_json::Value) -> JsonRpcResponse {
        let id = self.next_id;
        self.next_id += 1;

        let req = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: Some(blinky_daemon::protocol::types::Id::Num(id)),
            method: method.to_string(),
            params: Some(params),
        };

        let mut payload = serde_json::to_string(&req).unwrap();
        payload.push('\n');

        self.stream.write_all(payload.as_bytes()).await.unwrap();
        self.stream.flush().await.unwrap();

        let mut reader = BufReader::new(&mut self.stream);
        let mut line = String::new();
        reader.read_line(&mut line).await.unwrap();

        serde_json::from_str(&line).expect("Invalid JSON-RPC response")
    }
}

#[tokio::test]
async fn test_daemon_rpc_lifecycle() {
    let tmp = NamedTempFile::new().unwrap();
    let sock_path = tmp.path().to_path_buf();
    // Drop the tempfile handle so the path is free for UnixListener
    drop(tmp);

    let server = DaemonServer::new(Some(sock_path.clone()))
        .await
        .expect("Server init failed");

    let server_handle = tokio::spawn(async move {
        server.run().await.ok();
    });

    // Give the server 50ms to bind
    tokio::time::sleep(Duration::from_millis(50)).await;

    let mut client = TestClient::connect(&sock_path).await;

    // 1. blinky.getSystemInfo
    let res = client.call("blinky.getSystemInfo", json!({})).await;
    assert!(res.error.is_none());
    let sys_info = res.result.unwrap();
    assert_eq!(sys_info["compositor"], "hyprland");
    assert_eq!(sys_info["daemon_version"], "0.1.0");

    // 2. blinky.getMonitors
    let res = client.call("blinky.getMonitors", json!({})).await;
    assert!(res.error.is_none());
    let monitors = res.result.unwrap();
    assert!(monitors.is_array());
    let monitor_list = monitors.as_array().unwrap();
    assert!(!monitor_list.is_empty());
    println!("Detected {} monitor(s)", monitor_list.len());

    // 3. blinky.getWindows
    let res = client.call("blinky.getWindows", json!({})).await;
    assert!(res.error.is_none());
    let windows = res.result.unwrap();
    assert!(windows.is_array());
    println!("Detected {} mapped window(s)", windows.as_array().unwrap().len());

    // 4. blinky.getActiveWindow
    let res = client.call("blinky.getActiveWindow", json!({})).await;
    assert!(res.error.is_none());
    println!("Active window: {:?}", res.result);

    // 4b. blinky.focusWindow
    if let Some(first_win) = windows.as_array().and_then(|a| a.first()) {
        if let Some(addr) = first_win.get("address").and_then(|a| a.as_str()) {
            let res = client.call("blinky.focusWindow", json!({ "address": addr })).await;
            assert!(res.error.is_none());
            if let Some(focus_res) = res.result {
                println!("Focus window result: {:?}", focus_res);
            }
        }
    }

    // 5. blinky.getCursorPosition
    let res = client.call("blinky.getCursorPosition", json!({})).await;
    assert!(res.error.is_none());
    let pos = res.result.unwrap();
    assert!(pos.get("x").is_some());
    assert!(pos.get("y").is_some());
    println!("Cursor position: ({}, {})", pos["x"], pos["y"]);

    // 6. blinky.getApps
    let res = client.call("blinky.getApps", json!({})).await;
    assert!(res.error.is_none());
    let apps = res.result.unwrap();
    assert!(apps.is_array());
    let app_list = apps.as_array().unwrap();
    assert!(!app_list.is_empty());
    println!("Scanned {} installed .desktop application(s)", app_list.len());

    // 7. blinky.reanchorCoordinate
    if let Some(first_win) = windows.as_array().unwrap().first() {
        let addr = first_win["address"].as_str().unwrap();
        let res = client
            .call(
                "blinky.reanchorCoordinate",
                json!({
                    "window_address": addr,
                    "dx": 50,
                    "dy": 50
                }),
            )
            .await;
        assert!(res.error.is_none());
        let anchored = res.result.unwrap();
        assert_eq!(anchored["window_address"], addr);
        assert_eq!(anchored["relative_dx"], 50);
        assert_eq!(anchored["relative_dy"], 50);
        println!("Re-anchored target coordinate: {:?}", anchored);
    }

    // 8. blinky.captureScreen
    let res = client.call("blinky.captureScreen", json!({})).await;
    if res.error.is_none() {
        let cap = res.result.unwrap();
        let path_str = cap["path"].as_str().unwrap();
        assert!(std::path::Path::new(path_str).exists());
        println!("Screen capture saved to: {}", path_str);
    } else {
        println!("Screen capture skipped in headless environment: {:?}", res.error);
    }

    // 9. blinky.captureWindow + 9b. blinky.actOnFrame
    if let Some(first_win) = windows.as_array().and_then(|a| a.first()) {
        if let Some(addr) = first_win.get("address").and_then(|a| a.as_str()) {
            let res = client.call("blinky.captureWindow", json!({ "address": addr })).await;
            if res.error.is_none() {
                let cap = res.result.unwrap();
                let path_str = cap["path"].as_str().unwrap();
                assert!(std::path::Path::new(path_str).exists());
                println!("Window capture saved to: {}", path_str);

                if let Some(frame_id) = cap["frame"]["frame_id"].as_str() {
                    println!("Received Frame ID: {}", frame_id);

                    // Test actOnFrame: normalized center [0.5, 0.5] move
                    let act_res = client
                        .call(
                            "blinky.actOnFrame",
                            json!({
                                "frame_id": frame_id,
                                "target": [0.5, 0.5],
                                "normalized": true,
                                "action": "move"
                            }),
                        )
                        .await;
                    assert!(act_res.error.is_none());
                    let act_data = act_res.result.unwrap();
                    assert!(act_data["ok"].as_bool().unwrap());
                    println!("actOnFrame Result: {:?}", act_data);
                }
            } else {
                println!("Window capture skipped in headless environment: {:?}", res.error);
            }
        }
    }

    // 10. Input actions: mouseMove
    let res = client.call("blinky.mouseMove", json!({ "x": 500, "y": 500 })).await;
    assert!(res.error.is_none());

    // 11. Input actions: mouseClick
    let res = client
        .call(
            "blinky.mouseClick",
            json!({ "x": 500, "y": 500, "button": "left", "click_count": 1 }),
        )
        .await;
    assert!(res.error.is_none());

    // 12. Input actions: mouseScroll
    let res = client
        .call(
            "blinky.mouseScroll",
            json!({ "direction": "down", "amount": 2, "x": 500, "y": 500 }),
        )
        .await;
    assert!(res.error.is_none());

    // 13. Input actions: keyboardType
    let res = client.call("blinky.keyboardType", json!({ "text": "" })).await;
    assert!(res.error.is_none());

    // 14. AT-SPI: blinky.getA11yElements
    let res = client.call("blinky.getA11yElements", json!({ "max_elements": 100 })).await;
    assert!(res.error.is_none());
    let a11y_elems = res.result.unwrap();
    println!("AT-SPI returned {} element(s)", a11y_elems.as_array().map_or(0, |a| a.len()));

    // 15. Media: blinky.mediaControl (status / get_state)
    let res = client.call("blinky.mediaControl", json!({ "command": "get_state" })).await;
    println!("Media control response: {:?}", res);

    // 16. Error handling: Unknown method
    let res = client.call("blinky.nonExistentMethod", json!({})).await;
    assert!(res.error.is_some());
    assert_eq!(
        res.error.unwrap().code,
        blinky_daemon::protocol::types::METHOD_NOT_FOUND
    );

    // Clean up
    server_handle.abort();
    std::fs::remove_file(&sock_path).ok();
}
