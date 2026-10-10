use super::desktop::DaemonRpcClient;
use super::Tool;
use crate::providers::ToolDefinition;
use anyhow::Result;
use async_trait::async_trait;
use serde_json::{json, Value};

pub struct MediaControlTool {
    client: DaemonRpcClient,
}

impl MediaControlTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for MediaControlTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "media_control".to_string(),
            description: "Control media playback and audio volume across the desktop (play/pause, next track, previous track, mute, volume up/down)".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["play_pause", "next", "prev", "volume_up", "volume_down", "mute", "get_state"],
                        "description": "Media command to execute"
                    }
                },
                "required": ["command"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        self.client.call("blinky.mediaControl", args).await
    }
}

pub struct SystemSessionTool {
    client: DaemonRpcClient,
}

impl SystemSessionTool {
    pub fn new() -> Self {
        Self { client: DaemonRpcClient::new() }
    }
}

#[async_trait]
impl Tool for SystemSessionTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "system_session".to_string(),
            description: "Control workstation power and security session states (lock, suspend/sleep, hibernate, reboot, poweroff)".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["lock", "suspend", "hibernate", "reboot", "poweroff"],
                        "description": "Session power/lock command to execute"
                    }
                },
                "required": ["command"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        self.client.call("blinky.systemSession", args).await
    }
}
