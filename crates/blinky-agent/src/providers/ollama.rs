use super::openai::OpenAiCompatibleProvider;
use super::{AiProvider, AiResponse, ChatMessage, ToolDefinition};
use anyhow::Result;
use async_trait::async_trait;

pub struct OllamaProvider {
    inner: OpenAiCompatibleProvider,
}

impl OllamaProvider {
    pub fn new(base_url: Option<String>, model: Option<String>) -> Self {
        let url = base_url.unwrap_or_else(|| "http://127.0.0.1:11434/v1".to_string());
        let model_name = model.unwrap_or_else(|| "llama3.2".to_string());
        let inner = OpenAiCompatibleProvider::new(
            url,
            "ollama", // dummy key
            model_name,
            "ollama",
        );
        Self { inner }
    }
}

#[async_trait]
impl AiProvider for OllamaProvider {
    async fn name(&self) -> &'static str {
        "ollama"
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
