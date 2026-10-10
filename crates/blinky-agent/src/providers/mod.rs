pub mod factory;
pub mod gemini;
pub mod groq;
pub mod ollama;
pub mod openai;
pub mod types;

pub use factory::create_provider_from_env;
pub use types::*;

use anyhow::Result;
use async_trait::async_trait;

#[async_trait]
pub trait AiProvider: Send + Sync {
    async fn name(&self) -> &'static str;
    async fn model_name(&self) -> &str;
    async fn chat(
        &self,
        messages: &[ChatMessage],
        tools: &[ToolDefinition],
    ) -> Result<AiResponse>;
}
