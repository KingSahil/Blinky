pub mod desktop;
pub mod esp32;
pub mod ide_bridge;
pub mod reflex;
pub mod system;
pub mod utility;
pub mod wil;


use crate::providers::ToolDefinition;
use anyhow::{bail, Result};
use async_trait::async_trait;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;

#[async_trait]
pub trait Tool: Send + Sync {
    fn definition(&self) -> ToolDefinition;
    async fn execute(&self, args: Value) -> Result<Value>;
}

#[derive(Default)]
pub struct ToolRegistry {
    tools: HashMap<String, Arc<dyn Tool>>,
}

impl ToolRegistry {
    pub fn new() -> Self {
        let mut registry = Self::default();

        // 1. Desktop & Input Tools
        registry.register(Arc::new(desktop::LaunchAppTool::new()));
        registry.register(Arc::new(desktop::FocusWindowTool::new()));
        registry.register(Arc::new(desktop::CaptureWindowTool::new()));
        registry.register(Arc::new(desktop::CaptureScreenTool::new()));
        registry.register(Arc::new(desktop::ActOnFrameTool::new()));
        registry.register(Arc::new(desktop::KeyboardTypeTool::new()));
        registry.register(Arc::new(desktop::KeyboardKeyTool::new()));

        // 2. System & Media Tools
        registry.register(Arc::new(system::MediaControlTool::new()));
        registry.register(Arc::new(system::SystemSessionTool::new()));

        // 3. Web Intelligence (WIL)
        registry.register(Arc::new(wil::WebSearchTool::new()));
        registry.register(Arc::new(wil::FetchWebPageTool::new()));

        // 4. Utility Tools
        registry.register(Arc::new(utility::CryptoPriceTool::new()));
        registry.register(Arc::new(utility::WikipediaTool::new()));

        // 5. Hardware & IDE Bridges
        registry.register(Arc::new(esp32::Esp32LightTool::new()));
        registry.register(Arc::new(ide_bridge::IdeBridgeTool::new()));

        // 6. System 1 Reflex Engine Bridge
        registry.register(Arc::new(reflex::ConsultReflexTool::new()));



        registry
    }

    pub fn register(&mut self, tool: Arc<dyn Tool>) {
        let def = tool.definition();
        self.tools.insert(def.name, tool);
    }

    pub fn get_definitions(&self) -> Vec<ToolDefinition> {
        self.tools.values().map(|t| t.definition()).collect()
    }

    pub async fn execute(&self, name: &str, args: Value) -> Result<Value> {
        if let Some(tool) = self.tools.get(name) {
            tool.execute(args).await
        } else {
            bail!("Tool '{}' not registered in ToolRegistry", name)
        }
    }
}
