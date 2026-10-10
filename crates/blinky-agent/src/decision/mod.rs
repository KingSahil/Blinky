use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DecisionRoute {
    DaemonSystem,
    OcrExact,
    VisionSpatial,
    VisionVisual,
    HybridConsensus,
    ComplexGoal,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DecisionAdvice {
    pub route: DecisionRoute,
    pub confidence: f64,
    pub is_atomic_fast_path: bool,
    pub extracted_target: Option<String>,
    pub guidance_prompt: String,
}

pub struct System1Classifier;

impl System1Classifier {
    pub fn classify(query: &str) -> DecisionAdvice {
        let q_lower = query.trim().to_lowercase();

        // 1. Quoted text extraction (e.g. "Click 'Artifacts'")
        let extracted_target = if let Some(start) = query.find('\'') {
            if let Some(end) = query[start + 1..].find('\'') {
                Some(query[start + 1..start + 1 + end].to_string())
            } else {
                None
            }
        } else if let Some(start) = query.find('"') {
            if let Some(end) = query[start + 1..].find('"') {
                Some(query[start + 1..start + 1 + end].to_string())
            } else {
                None
            }
        } else {
            None
        };

        // 2. Pure Atomic System / Media Commands (Confidence 1.0)
        if q_lower == "mute"
            || q_lower == "unmute"
            || q_lower == "mute audio"
            || q_lower == "toggle mute"
        {
            return DecisionAdvice {
                route: DecisionRoute::DaemonSystem,
                confidence: 1.0,
                is_atomic_fast_path: true,
                extracted_target: None,
                guidance_prompt:
                    "Atomic media mute command. Execute via media_control {\"command\": \"mute\"} immediately."
                        .to_string(),
            };
        }

        if q_lower.starts_with("volume up")
            || q_lower.starts_with("increase volume")
            || q_lower.starts_with("turn up the volume")
        {
            return DecisionAdvice {
                route: DecisionRoute::DaemonSystem,
                confidence: 0.99,
                is_atomic_fast_path: true,
                extracted_target: None,
                guidance_prompt:
                    "Atomic media volume up. Execute via media_control {\"command\": \"volume_up\"}."
                        .to_string(),
            };
        }

        if q_lower.starts_with("volume down")
            || q_lower.starts_with("lower the volume")
            || q_lower.starts_with("decrease volume")
        {
            return DecisionAdvice {
                route: DecisionRoute::DaemonSystem,
                confidence: 0.99,
                is_atomic_fast_path: true,
                extracted_target: None,
                guidance_prompt:
                    "Atomic media volume down. Execute via media_control {\"command\": \"volume_down\"}."
                        .to_string(),
            };
        }

        if q_lower == "lock" || q_lower == "lock screen" || q_lower == "lock workstation" {
            return DecisionAdvice {
                route: DecisionRoute::DaemonSystem,
                confidence: 1.0,
                is_atomic_fast_path: true,
                extracted_target: None,
                guidance_prompt:
                    "Atomic workstation lock. Execute via system_session {\"command\": \"lock\"}."
                        .to_string(),
            };
        }

        if (q_lower.starts_with("open ") || q_lower.starts_with("launch "))
            && !q_lower.contains(" and ")
            && !q_lower.contains(" then ")
            && !q_lower.contains(" within ")
        {
            let app_name = query
                .split_whitespace()
                .skip(1)
                .collect::<Vec<_>>()
                .join(" ");
            return DecisionAdvice {
                route: DecisionRoute::DaemonSystem,
                confidence: 0.98,
                is_atomic_fast_path: true,
                extracted_target: Some(app_name),
                guidance_prompt: "Atomic app launch. Execute via launch_app.".to_string(),
            };
        }

        // 3. Quoted Single-Step Text Click -> OCR_EXACT Fast Path
        if (q_lower.starts_with("click ")
            || q_lower.starts_with("select ")
            || q_lower.starts_with("tap "))
            && extracted_target.is_some()
            && !q_lower.contains(" and ")
            && !q_lower.contains(" then ")
            && !q_lower.contains("second")
            && !q_lower.contains("blue")
            && !q_lower.contains("red")
        {
            let target = extracted_target.clone().unwrap();
            return DecisionAdvice {
                route: DecisionRoute::OcrExact,
                confidence: 0.98,
                is_atomic_fast_path: true,
                extracted_target: Some(target.clone()),
                guidance_prompt: format!(
                    "Single-step named button/link click. Capture window -> match element text '{}' -> click via act_on_frame.",
                    target
                ),
            };
        }

        // 4. Spatial / Positional Queries
        if q_lower.contains("second")
            || q_lower.contains("third")
            || q_lower.contains("bottom-left")
            || q_lower.contains("top-right")
            || q_lower.contains("below ")
            || q_lower.contains("above ")
        {
            return DecisionAdvice {
                route: DecisionRoute::VisionSpatial,
                confidence: 0.95,
                is_atomic_fast_path: false,
                extracted_target,
                guidance_prompt:
                    "[ROUTING ADVICE]: Target has relative spatial references. Use visual bounding boxes or normalized coordinates [u, v] to select the relative item."
                        .to_string(),
            };
        }

        // 5. Visual Colors & Icons
        if q_lower.contains("blue ")
            || q_lower.contains("red ")
            || q_lower.contains("green ")
            || q_lower.contains("magnifying glass")
            || q_lower.contains("gear icon")
            || q_lower.contains("avatar")
        {
            return DecisionAdvice {
                route: DecisionRoute::VisionVisual,
                confidence: 0.96,
                is_atomic_fast_path: false,
                extracted_target,
                guidance_prompt:
                    "[ROUTING ADVICE]: Target references visual styling or iconography. Inspect visual image coordinates or visual element bounding regions."
                        .to_string(),
            };
        }

        // 6. Compound / Multi-Step Goal (System 2 Escalation)
        DecisionAdvice {
            route: DecisionRoute::ComplexGoal,
            confidence: 0.88,
            is_atomic_fast_path: false,
            extracted_target,
            guidance_prompt:
                "[ROUTING ADVICE]: Compound workflow detected. Plan sequential sub-steps: launch/focus app -> capture window -> ground elements -> type/click -> verify outcome."
                    .to_string(),
        }
    }
}
