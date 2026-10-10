use super::Tool;
use crate::providers::ToolDefinition;
use anyhow::{Context, Result};
use async_trait::async_trait;
use serde_json::{json, Value};
use tokio::net::UdpSocket;

pub struct Esp32LightTool;

impl Esp32LightTool {
    pub fn new() -> Self {
        Self
    }
}

#[async_trait]
impl Tool for Esp32LightTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "esp32_light_control".to_string(),
            description: "Control RGB lighting color and brightness on connected ESP32 hardware via local UDP broadcast".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "r": { "type": "integer", "description": "Red channel (0-255)" },
                    "g": { "type": "integer", "description": "Green channel (0-255)" },
                    "b": { "type": "integer", "description": "Blue channel (0-255)" },
                    "brightness": { "type": "integer", "description": "Brightness percentage (0-100)" }
                },
                "required": ["r", "g", "b"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let r = args.get("r").and_then(|v| v.as_u64()).unwrap_or(255) as u8;
        let g = args.get("g").and_then(|v| v.as_u64()).unwrap_or(255) as u8;
        let b = args.get("b").and_then(|v| v.as_u64()).unwrap_or(255) as u8;
        let brightness = args.get("brightness").and_then(|v| v.as_u64()).unwrap_or(100) as u8;

        let payload = json!({
            "type": "rgb",
            "r": r,
            "g": g,
            "b": b,
            "brightness": brightness
        });

        // Broadcast to local UDP port 4210 (Blinky ESP32 listener)
        let socket = UdpSocket::bind("0.0.0.0:0").await.context("Failed to bind UDP socket")?;
        socket.set_broadcast(true).ok();
        let bytes = serde_json::to_vec(&payload)?;
        socket.send_to(&bytes, "255.255.255.255:4210").await.ok();

        Ok(json!({
            "status": "sent",
            "r": r,
            "g": g,
            "b": b,
            "brightness": brightness
        }))
    }
}
