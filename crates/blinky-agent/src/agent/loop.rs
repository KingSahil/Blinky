use crate::decision::{DecisionRoute, System1Classifier};
use crate::grounding::OcrGrounder;
use crate::providers::{AiProvider, ChatMessage, ToolCall};
use crate::tools::desktop::DaemonRpcClient;
use crate::tools::ToolRegistry;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::Instant;
use tracing::{debug, info, warn};

const SYSTEM_PROMPT: &str = r#"You are Fermas-GUI (Blinky), an autonomous, screen-aware desktop AI supervisor on Linux.
Your goal is to solve the user's task on their computer deterministically with maximum speed and execution velocity.

Operating Principles:
1. High Velocity & Decisive Action: Prioritize speed and direct progress. For quick answers and architectural planning, respond directly and concisely.
2. Perceive & Modality Assessment:
   - Use capture_window or capture_screen to observe UI state and retrieve grounded element references (@eN) with coordinates [x, y, w, h].
   - If the target is textual, match the specific element reference (@eN).
   - If the target is an empty canvas, visual icon, or spatial area, use normalized coordinates [u, v] or call `consult_reflex(intent)`.
3. Action & Batch Input Execution:
   - Use act_on_frame with @ref or [u, v] coordinates to click, type, or scroll.
   - For tabular or multi-line data entry (spreadsheets, tables, forms), do not type cells individually. Select the origin field/cell and pass the entire TSV table (rows delimited by '\n', columns by '\t') to `type_text` in a single call for instant grid population.
   - Use keyboard_key for shortcuts and special keys.
4. Heavy Engineering & Code Delegation:
   - For codebase modification, refactoring, building, running test suites, multi-file inspection, or terminal pipelines, DO NOT try to perform these multi-step engineering tasks in the desktop chat loop.
   - Call `delegate_to_fermas(goal, workspace_path)`: Fermas executes autonomously in a persistent background worker session, leveraging prompt caching, and returns clean verified summaries.
5. Goal Verification: Confirm that the final requested goal is verified or rendered on screen before delivering your final answer."#;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentStep {
    pub turn: usize,
    pub tool_calls: Vec<ToolCall>,
    pub tool_results: Vec<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentResult {
    pub success: bool,
    pub answer: Option<String>,
    pub steps: Vec<AgentStep>,
    pub elapsed_ms: f64,
}

pub struct AgentLoop {
    provider: Arc<dyn AiProvider>,
    tools: Arc<ToolRegistry>,
    daemon: DaemonRpcClient,
}

impl AgentLoop {
    pub fn new(provider: Arc<dyn AiProvider>, tools: Arc<ToolRegistry>) -> Self {
        Self {
            provider,
            tools,
            daemon: DaemonRpcClient::new(),
        }
    }

    pub async fn run(&self, user_goal: &str, max_turns: usize) -> Result<AgentResult> {
        let start_time = Instant::now();
        info!("Starting autonomous agent loop for goal: '{}'", user_goal);

        // --- SYSTEM 1 GATEWAY & CLASSIFICATION ---
        let advice = System1Classifier::classify(user_goal);
        info!(
            "System 1 Decision: Route={:?}, Confidence={:.4}, FastPath={}",
            advice.route, advice.confidence, advice.is_atomic_fast_path
        );

        // System 1 Reflex Fast-Path (<5ms)
        if advice.is_atomic_fast_path {
            match advice.route {
                DecisionRoute::DaemonSystem => {
                    let q_lower = user_goal.trim().to_lowercase();
                    if q_lower == "mute" || q_lower == "unmute" || q_lower.contains("mute") {
                        self.tools.execute("media_control", json!({ "command": "mute" })).await.ok();
                        let elapsed_ms = start_time.elapsed().as_secs_f64() * 1000.0;
                        return Ok(AgentResult {
                            success: true,
                            answer: Some("Audio mute toggled successfully.".to_string()),
                            steps: Vec::new(),
                            elapsed_ms,
                        });
                    }
                    if q_lower.contains("volume up") || q_lower.contains("increase volume") {
                        self.tools.execute("media_control", json!({ "command": "volume_up" })).await.ok();
                        let elapsed_ms = start_time.elapsed().as_secs_f64() * 1000.0;
                        return Ok(AgentResult {
                            success: true,
                            answer: Some("Audio volume increased.".to_string()),
                            steps: Vec::new(),
                            elapsed_ms,
                        });
                    }
                    if q_lower.contains("volume down") || q_lower.contains("lower volume") || q_lower.contains("decrease volume") {
                        self.tools.execute("media_control", json!({ "command": "volume_down" })).await.ok();
                        let elapsed_ms = start_time.elapsed().as_secs_f64() * 1000.0;
                        return Ok(AgentResult {
                            success: true,
                            answer: Some("Audio volume decreased.".to_string()),
                            steps: Vec::new(),
                            elapsed_ms,
                        });
                    }
                    if q_lower.contains("lock") {
                        self.tools.execute("system_session", json!({ "command": "lock" })).await.ok();
                        let elapsed_ms = start_time.elapsed().as_secs_f64() * 1000.0;
                        return Ok(AgentResult {
                            success: true,
                            answer: Some("Workstation locked.".to_string()),
                            steps: Vec::new(),
                            elapsed_ms,
                        });
                    }
                    if let Some(app) = advice.extracted_target {
                        self.tools.execute("launch_app", json!({ "name": app })).await.ok();
                        let elapsed_ms = start_time.elapsed().as_secs_f64() * 1000.0;
                        return Ok(AgentResult {
                            success: true,
                            answer: Some(format!("Launched application '{}'.", app)),
                            steps: Vec::new(),
                            elapsed_ms,
                        });
                    }
                }
                _ => {}
            }
        }

        // --- SYSTEM 2 ESCALATION WITH SYSTEM 1 GUIDANCE PRIOR ---
        let enriched_system_prompt = format!(
            "{}\n\n[SYSTEM 1 ROUTING GUIDANCE]\n{}",
            SYSTEM_PROMPT, advice.guidance_prompt
        );

        let mut messages = vec![
            ChatMessage::system(enriched_system_prompt),
            ChatMessage::user(user_goal),
        ];

        let mut steps = Vec::new();
        let mut final_answer = None;
        let mut success = false;

        for turn in 1..=max_turns {
            debug!("Agent Loop Turn {}/{}", turn, max_turns);

            let tool_defs = self.tools.get_definitions();
            let ai_res = self
                .provider
                .chat(&messages, &tool_defs)
                .await
                .with_context(|| format!("AI provider failed on turn {}", turn))?;

            if ai_res.tool_calls.is_empty() {
                final_answer = ai_res.content;
                success = true;
                info!("Agent achieved goal on turn {}: {:?}", turn, final_answer);
                break;
            }

            messages.push(ChatMessage::assistant(
                ai_res.content.clone(),
                Some(ai_res.tool_calls.clone()),
            ));

            let mut step_results = Vec::new();

            for tc in &ai_res.tool_calls {
                info!("Executing tool call: {} {:?}", tc.name, tc.arguments);

                let result = if tc.name == "capture_window" || tc.name == "capture_screen" {
                    self.execute_grounded_capture(&tc.name, tc.arguments.clone()).await
                } else {
                    self.tools.execute(&tc.name, tc.arguments.clone()).await
                };

                let result_val = match result {
                    Ok(val) => val,
                    Err(e) => {
                        warn!("Tool {} error: {:#}", tc.name, e);
                        json!({ "error": e.to_string() })
                    }
                };

                step_results.push(result_val.clone());

                messages.push(ChatMessage::tool_result(
                    &tc.id,
                    &tc.name,
                    serde_json::to_string(&result_val)?,
                ));
            }

            steps.push(AgentStep {
                turn,
                tool_calls: ai_res.tool_calls,
                tool_results: step_results,
            });
        }

        let elapsed_ms = start_time.elapsed().as_secs_f64() * 1000.0;

        Ok(AgentResult {
            success,
            answer: final_answer,
            steps,
            elapsed_ms,
        })
    }

    async fn execute_grounded_capture(&self, method: &str, args: Value) -> Result<Value> {
        let rpc_method = if method == "capture_screen" {
            "blinky.captureScreen"
        } else {
            "blinky.captureWindow"
        };

        let cap_res = self.daemon.call(rpc_method, args).await?;
        let img_path = cap_res
            .get("path")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let frame_id = cap_res
            .get("frame")
            .and_then(|f| f.get("frame_id"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        if img_path.is_empty() || frame_id.is_empty() {
            return Ok(cap_res);
        }

        // Run high-speed Tesseract OCR
        let elements = OcrGrounder::extract_elements(&img_path).await.unwrap_or_default();
        let elem_count = elements.len();

        // Attach elements to daemon frame
        self.daemon
            .call(
                "blinky.attachElements",
                json!({
                    "frame_id": frame_id,
                    "elements": serde_json::to_value(&elements)?
                }),
            )
            .await
            .ok();

        // Compact representation with bounding boxes for LLM spatial awareness
        let compact_elements: Vec<String> = elements
            .iter()
            .take(100)
            .map(|e| {
                format!(
                    "[{}] \"{}\" at [{}, {}, {}, {}]",
                    e.ref_id, e.text, e.x, e.y, e.width, e.height
                )
            })
            .collect();

        Ok(json!({
            "status": "captured",
            "frame_id": frame_id,
            "image_path": img_path,
            "total_elements_grounded": elem_count,
            "detected_ui_elements": compact_elements
        }))
    }
}
