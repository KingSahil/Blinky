use super::gemini::GeminiProvider;
use super::groq::GroqProvider;
use super::ollama::OllamaProvider;
use super::openai::OpenAiCompatibleProvider;
use super::AiProvider;
use anyhow::Result;
use std::sync::Arc;
use tracing::info;

pub fn create_provider_from_env() -> Result<Arc<dyn AiProvider>> {
    let provider_key = std::env::var("FLICKY_AI_PROVIDER")
        .or_else(|_| std::env::var("BLINKY_AI_PROVIDER"))
        .unwrap_or_else(|_| "groq".to_string())
        .to_lowercase();

    let model_override = std::env::var("FLICKY_AI_MODEL")
        .or_else(|_| std::env::var("BLINKY_AI_MODEL"))
        .ok();

    match provider_key.as_str() {
        "groq" => {
            let api_key = std::env::var("GROQ_API_KEY").unwrap_or_default();
            info!(
                "Instantiating Groq AI Provider (model: {:?})",
                model_override
            );
            Ok(Arc::new(GroqProvider::new(api_key, model_override)))
        }
        "gemini" | "google" => {
            let api_key = std::env::var("GEMINI_API_KEY")
                .or_else(|_| std::env::var("GOOGLE_API_KEY"))
                .unwrap_or_default();
            info!(
                "Instantiating Gemini AI Provider (model: {:?})",
                model_override
            );
            Ok(Arc::new(GeminiProvider::new(api_key, model_override)))
        }
        "ollama" => {
            let base_url = std::env::var("OLLAMA_BASE_URL").ok();
            info!(
                "Instantiating Ollama AI Provider (model: {:?})",
                model_override
            );
            Ok(Arc::new(OllamaProvider::new(base_url, model_override)))
        }
        "openai" | "custom" | "deepseek" => {
            let base_url = std::env::var("OPENAI_BASE_URL")
                .or_else(|_| std::env::var("CUSTOM_AI_BASE_URL"))
                .unwrap_or_else(|_| "https://api.openai.com/v1".to_string());
            let api_key = std::env::var("OPENAI_API_KEY")
                .or_else(|_| std::env::var("CUSTOM_AI_KEY"))
                .unwrap_or_default();
            let model = model_override.unwrap_or_else(|| "gpt-4o-mini".to_string());
            info!(
                "Instantiating OpenAI-compatible Provider at {} (model: {})",
                base_url, model
            );
            Ok(Arc::new(OpenAiCompatibleProvider::new(
                base_url, api_key, model, "openai",
            )))
        }
        other => {
            let api_key = std::env::var("GROQ_API_KEY").unwrap_or_default();
            info!("Unknown provider '{}'; defaulting to Groq", other);
            Ok(Arc::new(GroqProvider::new(api_key, model_override)))
        }
    }
}
