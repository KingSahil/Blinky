use super::Tool;
use crate::providers::ToolDefinition;
use anyhow::{Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};
use std::time::Duration;
use tracing::{debug, warn};

pub struct WebSearchTool {
    client: Client,
}

impl WebSearchTool {
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(10))
            .build()
            .unwrap_or_default();
        Self { client }
    }
}

#[async_trait]
impl Tool for WebSearchTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "web_search".to_string(),
            description: "Search the web for up-to-date information, documentation, news, or technical answers using SearXNG".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query keywords"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Maximum number of search results to return (default: 5)"
                    }
                },
                "required": ["query"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let query = args.get("query").and_then(|v| v.as_str()).unwrap_or("");
        let count = args.get("count").and_then(|v| v.as_u64()).unwrap_or(5) as usize;

        // 1. Try local SearXNG instance (http://127.0.0.1:8888)
        let searxng_url = format!("http://127.0.0.1:8888/search?q={}&format=json", urlencoding::encode(query));
        debug!("Querying local SearXNG at {}", searxng_url);

        if let Ok(resp) = self.client.get(&searxng_url).send().await {
            if resp.status().is_success() {
                if let Ok(body) = resp.json::<Value>().await {
                    if let Some(results) = body.get("results").and_then(|r| r.as_array()) {
                        let parsed: Vec<Value> = results
                            .iter()
                            .take(count)
                            .map(|r| {
                                json!({
                                    "title": r.get("title").and_then(|v| v.as_str()).unwrap_or(""),
                                    "url": r.get("url").and_then(|v| v.as_str()).unwrap_or(""),
                                    "content": r.get("content").and_then(|v| v.as_str()).unwrap_or(""),
                                })
                            })
                            .collect();

                        return Ok(json!({
                            "provider": "searxng_local",
                            "query": query,
                            "results": parsed
                        }));
                    }
                }
            }
        }

        // 2. Fallback: DuckDuckGo Lite HTML Search
        warn!("Local SearXNG not reachable; using public search fallback");
        let ddg_url = format!("https://html.duckduckgo.com/html/?q={}", urlencoding::encode(query));
        let ddg_res = self
            .client
            .get(&ddg_url)
            .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            .send()
            .await;

        if let Ok(resp) = ddg_res {
            if let Ok(html) = resp.text().await {
                let re_link = regex::Regex::new(r#"class="result__snippet"[^>]*>([^<]+)<"#).unwrap();
                let mut snippets = Vec::new();
                for cap in re_link.captures_iter(&html).take(count) {
                    snippets.push(json!({
                        "content": cap[1].trim()
                    }));
                }

                return Ok(json!({
                    "provider": "duckduckgo_fallback",
                    "query": query,
                    "results": snippets
                }));
            }
        }

        Ok(json!({
            "query": query,
            "results": []
        }))
    }
}

pub struct FetchWebPageTool {
    client: Client,
}

impl FetchWebPageTool {
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(15))
            .build()
            .unwrap_or_default();
        Self { client }
    }
}

#[async_trait]
impl Tool for FetchWebPageTool {
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "fetch_web_page".to_string(),
            description: "Download and extract the readable text content of a web page URL".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The http/https URL to extract"
                    }
                },
                "required": ["url"]
            }),
        }
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let url = args.get("url").and_then(|v| v.as_str()).unwrap_or("");
        let resp = self
            .client
            .get(url)
            .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            .send()
            .await
            .context("Failed to fetch web page")?;

        let html = resp.text().await.unwrap_or_default();

        // Strip scripts, styles, and HTML tags
        let re_script = regex::Regex::new(r"(?is)<script[^>]*>.*?</script>").unwrap();
        let cleaned1 = re_script.replace_all(&html, " ");
        let re_style = regex::Regex::new(r"(?is)<style[^>]*>.*?</style>").unwrap();
        let cleaned2 = re_style.replace_all(&cleaned1, " ");
        let re_tags = regex::Regex::new(r"<[^>]+>").unwrap();
        let text_only = re_tags.replace_all(&cleaned2, " ");
        let re_spaces = regex::Regex::new(r"\s+").unwrap();
        let normalized = re_spaces.replace_all(&text_only, " ").trim().to_string();

        let truncated = if normalized.len() > 10_000 {
            format!("{}... [truncated]", &normalized[..10_000])
        } else {
            normalized
        };

        Ok(json!({
            "url": url,
            "content": truncated,
            "length": truncated.len(),
        }))
    }
}
