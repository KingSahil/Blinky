use super::openai::OpenAiCompatibleProvider;
use super::{AiProvider, AiResponse, ChatMessage, ToolDefinition};
use anyhow::Result;
use async_trait::async_trait;

pub struct GroqProvider {
    inner: OpenAiCompatibleProvider,
}

impl GroqProvider {
    pub fn new(api_key: impl Into<String>, model: Option<String>) -> Self {
        let model_name = model.unwrap_or_else(|| "llama-3.3-70b-versatile".to_string());
        let inner = OpenAiCompatibleProvider::new(
            "https://api.groq.com/openai/v1",
            api_key,
            model_name,
            "groq",
        );
        Self { inner }
    }
}

#[async_trait]
impl AiProvider for GroqProvider {
    async fn name(&self) -> &'static str {
        "groq"
    }

    async fn model_name(&self) -> &str {
        self.inner.model_name().await
    }

    async fn chat(
        &self,
        messages: &[ChatMessage],
        tools: &[ToolDefinition],
    ) -> Result<AiResponse> {
        self.inner.chat(messages, tools).await
    }
}
