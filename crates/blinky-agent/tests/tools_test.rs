use blinky_agent::tools::utility::{CryptoPriceTool, WikipediaTool};
use blinky_agent::tools::wil::{FetchWebPageTool, WebSearchTool};
use blinky_agent::tools::Tool;
use serde_json::json;

#[tokio::test]
async fn test_crypto_price_tool() {
    let tool = CryptoPriceTool::new();
    let res = tool.execute(json!({ "symbol": "BTC" })).await;
    assert!(res.is_ok(), "Crypto tool failed: {:?}", res);
    let val = res.unwrap();
    assert_eq!(val["symbol"], "BTC");
    assert!(val.get("price_usd").is_some());
    println!("Crypto Price Result: {:?}", val);
}

#[tokio::test]
async fn test_wikipedia_lookup_tool() {
    let tool = WikipediaTool::new();
    let res = tool.execute(json!({ "query": "Rust (programming language)" })).await;
    assert!(res.is_ok(), "Wikipedia tool failed: {:?}", res);
    let val = res.unwrap();
    assert!(val["title"].as_str().unwrap().contains("Rust"));
    assert!(val["extract"].as_str().unwrap().len() > 20);
    println!("Wikipedia Result Title: {:?}", val["title"]);
}

#[tokio::test]
async fn test_web_search_tool() {
    let tool = WebSearchTool::new();
    let res = tool.execute(json!({ "query": "Linux kernel", "count": 3 })).await;
    assert!(res.is_ok(), "Web search tool failed: {:?}", res);
    let val = res.unwrap();
    let results = val["results"].as_array().unwrap();
    assert!(!results.is_empty(), "Expected search results");
    println!("Web Search Results count: {}", results.len());
}

#[tokio::test]
async fn test_fetch_web_page_tool() {
    let tool = FetchWebPageTool::new();
    let res = tool.execute(json!({ "url": "https://example.com" })).await;
    assert!(res.is_ok(), "Fetch web page failed: {:?}", res);
    let val = res.unwrap();
    let content = val["content"].as_str().unwrap();
    assert!(content.contains("Example Domain"));
    println!("Fetched content length: {}", content.len());
}
