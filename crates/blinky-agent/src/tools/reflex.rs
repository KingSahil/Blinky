use super::Tool;
use crate::decision::System1Classifier;
use crate::providers::ToolDefinition;
use anyhow::Result;
use async_trait::async_trait;
use serde_json::{json, Value};

pub struct ConsultReflexTool;

impl ConsultReflexTool {
    pub fn new() -> Self {
        Self
    }
}

#[async_trait]
impl Tool for ConsultReflexTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "consult_reflex".to_string(),
            description: "Consult the local System 1 reflex decision engine to get calibrated interaction modalities (OCR text vs. visual coordinates vs. system D-Bus) and operational advice for an intended sub-action.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "The specific sub-action or target you intend to perform (e.g. 'click cell A1', 'click blue submit button', 'mute audio', 'type multi-row table')"
                    }
                },
                "required": ["intent"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let intent = args.get("intent").and_then(|v| v.as_str()).unwrap_or("");
        let advice = System1Classifier::classify(intent);

        Ok(json!({
            "intent": intent,
            "route": advice.route,
            "confidence": advice.confidence,
            "is_atomic_fast_path": advice.is_atomic_fast_path,
            "extracted_target": advice.extracted_target,
            "advice": advice.guidance_prompt,
        }))
    }
}
