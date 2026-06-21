# Blinky Remote Agent Router

The agent router is separate from the desktop screen-tutor worker. It powers mobile queries sent over WebSocket and command-bar globe/web requests that need browser intelligence. It lives in `python/agent_router.py`.

## 1. Transport

```text
mobile/usePCWebSocket.ts
  -> ws://<pc-host>:9001
  -> src-tauri/src/websocket.rs
  -> python -u python/agent_router.py
  -> line-delimited JSON responses
```

Rust keeps a persistent `AgentDaemon` with stdin/stdout pipes. If the daemon exits or the pipe breaks, Rust kills/restarts it and retries once.

## 2. WebSocket Message Types

Power commands are raw strings:

```text
power_off
restart
sleep
```

Agent queries are JSON:

```json
{
  "requestId": "uuid",
  "query": "search youtube for Expo router"
}
```

Legacy query format is also accepted:

```text
query:<requestId>:<query text>
```

## 3. Response Envelope

Every router response is JSON printed on one line:

```json
{
  "requestId": "uuid",
  "status": "processing",
  "data": {
    "message": "Analyzing query and routing..."
  },
  "error": null
}
```

Terminal statuses are `success` or `error`. Streaming synthesis chunks use:

```json
{
  "status": "processing",
  "data": { "message": "partial text", "is_chunk": true }
}
```

## 4. Built-In Direct Resolvers

Before registered tool routing and code generation, `agent_router.py` handles browser-opening requests:

- direct `https://...` URLs
- domain-like inputs such as `example.com`
- `search ...` or `google ...`
- `open/search/find/play <terms> on youtube`
- `open/search/find/play <terms> in youtube`
- AI-resolved open/navigation intents such as `open whatsapp`, `open notion`, or `launch spotify` (web URL resolution)

These fast paths avoid generated Playwright tools for common navigation. The browser planner described below is preferred for web tasks that need visible Edge automation.
These resolvers are browser-oriented (`webbrowser.open`) and do not call desktop computer-use tools in `python/computer_use/`.

## 5. Safe Browser Planner

`python/browser_agent.py` asks the LLM for a small JSON plan instead of arbitrary code. Supported actions are intentionally narrow:

- `open_url`
- `web_search`
- `site_search`

Accepted plans run through `python/browser_controller.py`, which launches visible Microsoft Edge through Playwright by default:

```text
chromium.launch(channel="msedge", headless=false)
```

This path is faster and safer than generating a one-off script for prompts like "open YouTube", "search gaming chair on Amazon", or "find Python docs". Unsupported browser actions fall through to the rest of the router instead of being guessed.

## 6. Registered Tools

The router loads `python/tools/registry.json` asynchronously. Current registered tools include:

- `lookup_youtube_stats`
- `find_crypto_price`
- `lookup_wikipedia_entity`
- `search_product_info`

The LLM routing prompt receives tool names, descriptions, and arguments, then returns:

```json
{
  "match": true,
  "tool_calls": [
    { "tool_name": "lookup_wikipedia_entity", "arguments": { "entity_name": "Quantum Computing" } }
  ],
  "confidence": 95,
  "reasoning": "..."
}
```

Confidence below `80` is treated as no confident match.

## 7. Execution and Sufficiency

Tool calls run with a max concurrency of 3. Each script receives JSON args through `sys.argv[1]` and should return JSON on stdout.

After execution, `utils.sufficiency_checker.check_sufficiency(query, combined_result)` decides whether the tool output answers the user. If sufficient, the router streams synthesized final text. If insufficient or unmatched, it enters code generation.

## 8. Generated Tool Lifecycle

For unmatched/insufficient requests:

1. The router asks the selected LLM to generate a Playwright async Python tool.
2. It parses `TOOL_NAME`, `DESCRIPTION`, `ARGUMENTS`, and a Python code block.
3. `repair_generated_playwright_code()` fixes common bad API usage, such as awaiting `set_default_timeout` or putting timeouts on ElementHandle methods.
4. `audit_code()` rejects forbidden imports/calls such as `exec`, `eval`, `os.system`, `subprocess`, `shutil`, and `pty`.
5. The script is written as `python/tools/temp_candidate_<requestId>.py`.
6. The router executes it once for verification.
7. On success, it renames the file to the final tool name and updates `registry.json`.
8. A background generalization task may run through `utils.generalizer.generalize_tool()`.

## 9. Synthesis

`stream_synthesis_llm()` turns raw tool output into a user-facing answer. It streams either:

- Groq chat completion chunks when `BLINKY_AI_PROVIDER=groq`.
- Ollama `/api/generate` response chunks otherwise.

Each chunk is forwarded to the WebSocket client using the `is_chunk` processing envelope.

## 10. Safety Notes

- Prefer the safe browser planner for open/search/site-search tasks.
- Generated tools are audited, but the audit is intentionally simple. Treat router-generated files as untrusted until reviewed.
- The router writes to `python/tools/` and `python/tools/registry.json`.
- Power commands are immediate OS commands from Rust and should only be exposed on trusted local networks.
- WebSocket binding is `0.0.0.0:9001`; firewall/network policy matters.

## 11. Boundary with Desktop Computer-Use Mode

- The router serves mobile and WebSocket-driven browser intelligence requests.
- Desktop direct actions (`open app`, `press shortcut`, `play <song> on Spotify`) are handled by `python/main.py` agent mode through `python/computer_use/agent.py` and `python/computer_use/tools.py`.
- Keep this boundary explicit: router for browser/web flows, computer-use for local OS/app actions.
