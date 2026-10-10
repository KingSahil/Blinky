use super::{AiProvider, AiResponse, ChatMessage, Role, ToolCall, ToolDefinition};
use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};
use std::time::Duration;
use tracing::{debug, error};

pub struct OpenAiCompatibleProvider {
    client: Client,
    base_url: String,
    api_key: String,
    model: String,
    provider_name: &'static str,
}

impl OpenAiCompatibleProvider {
    pub fn new(
        base_url: impl Into<String>,
        api_key: impl Into<String>,
        model: impl Into<String>,
        provider_name: &'static str,
    ) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(60))
            .build()
            .unwrap_or_default();

        Self {
            client,
            base_url: base_url.into().trim_end_matches('/').to_string(),
            api_key: api_key.into(),
            model: model.into(),
            provider_name,
        }
    }

    fn format_messages(&self, messages: &[ChatMessage]) -> Vec<Value> {
        messages
            .iter()
            .map(|m| {
                let role_str = match m.role {
                    Role::System => "system",
                    Role::User => "user",
                    Role::Assistant => "assistant",
                    Role::Tool => "tool",
                };

                let mut obj = json!({ "role": role_str });

                if let Some(c) = &m.content {
                    obj["content"] = json!(c);
                }

                if let Some(tcs) = &m.tool_calls {
                    obj["tool_calls"] = Value::Array(
                        tcs.iter()
                            .map(|tc| {
                                json!({
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.name,
                                        "arguments": tc.arguments.to_string()
                                    }
                                })
                            })
                            .collect(),
                    );
                }

                if let Some(tcid) = &m.tool_call_id {
                    obj["tool_call_id"] = json!(tcid);
                }

                if let Some(n) = &m.name {
                    obj["name"] = json!(n);
                }

                obj
            })
            .collect()
    }

    fn format_tools(&self, tools: &[ToolDefinition]) -> Vec<Value> {
        tools
            .iter()
            .map(|t| {
                json!({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters
                    }
                })
            })
            .collect()
    }
}

#[async_trait]
impl AiProvider for OpenAiCompatibleProvider {
    async fn name(&self) -> &'static str {
        self.provider_name
    }

    async fn model_name(&self) -> &str {
        &self.model
    }

    async fn chat(
        &self,
        messages: &[ChatMessage],
        tools: &[ToolDefinition],
    ) -> Result<AiResponse> {
        let endpoint = format!("{}/chat/completions", self.base_url);
        debug!("Sending chat request to {} ({})", endpoint, self.model);

        let mut payload = json!({
            "model": self.model,
            "messages": self.format_messages(messages),
            "temperature": 0.2,
        });

        if !tools.is_empty() {
            payload["tools"] = Value::Array(self.format_tools(tools));
            payload["tool_choice"] = json!("auto");
        }

        let mut req = self.client.post(&endpoint).json(&payload);
        if !self.api_key.is_empty() {
            req = req.header("Authorization", format!("Bearer {}", self.api_key));
        }

        let res = req
            .send()
            .await
            .with_context(|| format!("Failed to connect to AI provider endpoint {}", endpoint))?;

        if !res.status().is_success() {
            let status = res.status();
            let text = res.text().await.unwrap_or_default();
            error!("AI Provider error ({}): {}", status, text);
            bail!("AI Provider error ({}): {}", status, text);
        }

        let body: Value = res.json().await.context("Failed to parse AI JSON response")?;

        let choice = body["choices"]
            .as_array()
            .and_then(|a| a.first())
            .ok_or_else(|| anyhow::anyhow!("No choices in AI response: {}", body))?;

        let msg = &choice["message"];
        let content = msg["content"].as_str().map(|s| s.to_string());
        let finish_reason = choice["finish_reason"].as_str().map(|s| s.to_string());

        let mut tool_calls = Vec::new();
        if let Some(tcs) = msg["tool_calls"].as_array() {
            for tc in tcs {
                let id = tc["id"].as_str().unwrap_or("").to_string();
                let fn_obj = &tc["function"];
                let name = fn_obj["name"].as_str().unwrap_or("").to_string();
                let args_str = fn_obj["arguments"].as_str().unwrap_or("{}");
                let args: Value = serde_json::from_str(args_str).unwrap_or(Value::Null);

                if !name.is_empty() {
                    tool_calls.push(ToolCall {
                        id,
                        name,
                        arguments: args,
                    });
                }
            }
        }

        Ok(AiResponse {
            content,
            tool_calls,
            finish_reason,
        })
    }
}
