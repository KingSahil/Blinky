use super::Tool;
use crate::providers::ToolDefinition;
use anyhow::{Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};
use std::time::Duration;

pub struct IdeBridgeTool {
    client: Client,
}

impl IdeBridgeTool {
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .unwrap_or_default();
        Self { client }
    }
}

#[async_trait]
impl Tool for IdeBridgeTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "antigravity_ide_prompt".to_string(),
            description: "Send a programming prompt or refactoring task to the Antigravity IDE coding bridge".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The coding or engineering prompt to execute in the IDE"
                    }
                },
                "required": ["prompt"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let prompt = args.get("prompt").and_then(|v| v.as_str()).unwrap_or("");
        let ide_url = std::env::var("ANTIGRAVITY_IDE_URL")
            .unwrap_or_else(|_| "http://127.0.0.1:20128/v1/chat/completions".to_string());

        let payload = json!({
            "messages": [{"role": "user", "content": prompt}],
            "model": "antigravity"
        });

        let res = self
            .client
            .post(&ide_url)
            .json(&payload)
            .send()
            .await
            .context("Failed to connect to Antigravity IDE bridge")?;

        if res.status().is_success() {
            let body: Value = res.json().await.unwrap_or_default();
            Ok(json!({
                "status": "success",
                "response": body
            }))
        } else {
            Ok(json!({
                "status": "queued",
                "prompt": prompt
            }))
        }
    }
}
