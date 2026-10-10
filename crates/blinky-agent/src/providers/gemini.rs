use super::{AiProvider, AiResponse, ChatMessage, Role, ToolCall, ToolDefinition};
use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};
use std::time::Duration;
use tracing::{debug, error};

pub struct GeminiProvider {
    client: Client,
    api_key: String,
    model: String,
}

impl GeminiProvider {
    pub fn new(api_key: impl Into<String>, model: Option<String>) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(60))
            .build()
            .unwrap_or_default();

        let model_name = model.unwrap_or_else(|| "gemini-2.5-flash".to_string());

        Self {
            client,
            api_key: api_key.into(),
            model: model_name,
        }
    }
}

#[async_trait]
impl AiProvider for GeminiProvider {
    async fn name(&self) -> &'static str {
        "gemini"
    }

    async fn model_name(&self) -> &str {
        &self.model
    }

    async fn chat(
        &self,
        messages: &[ChatMessage],
        tools: &[ToolDefinition],
    ) -> Result<AiResponse> {
        let endpoint = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}",
            self.model, self.api_key
        );

        debug!("Sending Gemini API request ({})", self.model);

        let mut contents = Vec::new();
        let mut system_instruction: Option<Value> = None;

        for m in messages {
            match m.role {
                Role::System => {
                    if let Some(c) = &m.content {
                        system_instruction = Some(json!({
                            "parts": [{ "text": c }]
                        }));
                    }
                }
                Role::User => {
                    contents.push(json!({
                        "role": "user",
                        "parts": [{ "text": m.content.as_deref().unwrap_or("") }]
                    }));
                }
                Role::Assistant => {
                    let mut parts = Vec::new();
                    if let Some(c) = &m.content {
                        parts.push(json!({ "text": c }));
                    }
                    if let Some(tcs) = &m.tool_calls {
                        for tc in tcs {
                            parts.push(json!({
                                "functionCall": {
                                    "name": tc.name,
                                    "args": tc.arguments
                                }
                            }));
                        }
                    }
                    contents.push(json!({
                        "role": "model",
                        "parts": parts
                    }));
                }
                Role::Tool => {
                    contents.push(json!({
                        "role": "function",
                        "parts": [{
                            "functionResponse": {
                                "name": m.name.as_deref().unwrap_or("tool"),
                                "response": { "result": m.content.as_deref().unwrap_or("") }
                            }
                        }]
                    }));
                }
            }
        }

        let mut payload = json!({
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2
            }
        });

        if let Some(sys) = system_instruction {
            payload["systemInstruction"] = sys;
        }

        if !tools.is_empty() {
            let func_declarations: Vec<Value> = tools
                .iter()
                .map(|t| {
                    json!({
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters
                    })
                })
                .collect();

            payload["tools"] = json!([{
                "functionDeclarations": func_declarations
            }]);
        }

        let res = self
            .client
            .post(&endpoint)
            .json(&payload)
            .send()
            .await
            .context("Failed to send request to Gemini API")?;

        if !res.status().is_success() {
            let status = res.status();
            let text = res.text().await.unwrap_or_default();
            error!("Gemini API error ({}): {}", status, text);
            bail!("Gemini API error ({}): {}", status, text);
        }

        let body: Value = res.json().await.context("Failed to parse Gemini JSON response")?;

        let candidate = body["candidates"]
            .as_array()
            .and_then(|a| a.first())
            .ok_or_else(|| anyhow::anyhow!("No candidate in Gemini response: {}", body))?;

        let content_parts = candidate["content"]["parts"].as_array();

        let mut content_text = String::new();
        let mut tool_calls = Vec::new();

        if let Some(parts) = content_parts {
            for (idx, p) in parts.iter().enumerate() {
                if let Some(t) = p["text"].as_str() {
                    content_text.push_str(t);
                }
                if let Some(fc) = p.get("functionCall") {
                    let name = fc["name"].as_str().unwrap_or("").to_string();
                    let args = fc["args"].clone();
                    if !name.is_empty() {
                        tool_calls.push(ToolCall {
                            id: format!("call_gemini_{}", idx),
                            name,
                            arguments: args,
                        });
                    }
                }
            }
        }

        let finish_reason = candidate["finishReason"].as_str().map(|s| s.to_string());

        Ok(AiResponse {
            content: if content_text.is_empty() { None } else { Some(content_text) },
            tool_calls,
            finish_reason,
        })
    }
}
