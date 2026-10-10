use async_trait::async_trait;
use blinky_agent::agent::AgentLoop;
use blinky_agent::providers::{AiProvider, AiResponse, ChatMessage, ToolCall, ToolDefinition};
use blinky_agent::tools::ToolRegistry;
use serde_json::json;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

struct MockAiProvider {
    turn_counter: AtomicUsize,
}

impl MockAiProvider {
    fn new() -> Self {
        Self {
            turn_counter: AtomicUsize::new(0),
        }
    }
}

#[async_trait]
impl AiProvider for MockAiProvider {
    async fn name(&self) -> &'static str {
        "mock"
    }

    async fn model_name(&self) -> &str {
        "mock-model"
    }

    async fn chat(
        &self,
        _messages: &[ChatMessage],
        _tools: &[ToolDefinition],
    ) -> anyhow::Result<AiResponse> {
        let turn = self.turn_counter.fetch_add(1, Ordering::SeqCst);

        if turn == 0 {
            // First turn: issue two tool calls
            Ok(AiResponse {
                content: None,
                tool_calls: vec![
                    ToolCall {
                        id: "call_1".to_string(),
                        name: "find_crypto_price".to_string(),
                        arguments: json!({ "symbol": "BTC" }),
                    },
                    ToolCall {
                        id: "call_2".to_string(),
                        name: "lookup_wikipedia".to_string(),
                        arguments: json!({ "query": "Linus Torvalds" }),
                    },
                ],
                finish_reason: Some("tool_calls".to_string()),
            })
        } else {
            // Second turn: synthesize final answer
            Ok(AiResponse {
                content: Some("Bitcoin is currently trading near $84,000 USD. Linus Torvalds is the principal developer of the Linux kernel.".to_string()),
                tool_calls: Vec::new(),
                finish_reason: Some("stop".to_string()),
            })
        }
    }
}

#[tokio::test]
async fn test_autonomous_agent_loop_multi_tool_execution() {
    let mock_provider = Arc::new(MockAiProvider::new());
    let tools = Arc::new(ToolRegistry::new());
    let agent = AgentLoop::new(mock_provider, tools);

    let result = agent
        .run("What is the price of BTC and who created Linux?", 5)
        .await
        .expect("Agent loop failed");

    assert!(result.success, "Expected agent loop to succeed");
    assert_eq!(result.steps.len(), 1, "Expected 1 step with tool execution");
    assert_eq!(result.steps[0].tool_calls.len(), 2, "Expected 2 parallel tool calls");

    let btc_res = &result.steps[0].tool_results[0];
    assert_eq!(btc_res["symbol"], "BTC");
    assert!(btc_res.get("price_usd").is_some());

    let wiki_res = &result.steps[0].tool_results[1];
    assert!(wiki_res["title"].as_str().unwrap().contains("Linus"));

    let answer = result.answer.unwrap();
    assert!(answer.contains("Bitcoin"));
    assert!(answer.contains("Linus Torvalds"));
    println!("Final Autonomous Agent Answer:\n{}", answer);
}
