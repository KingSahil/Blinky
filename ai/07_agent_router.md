# Blinky Remote Agent Router

The remote agent router is separate from the desktop screen-tutor worker. It powers mobile queries sent over WebSocket and lives in `python/agent_router.py`.

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

Before tool routing and code generation, `agent_router.py` handles browser-opening requests:

- direct `https://...` URLs
- domain-like inputs such as `example.com`
- `search ...` or `google ...`
- `open/search/find/play <terms> on youtube`
- `open/search/find/play <terms> in youtube`
- AI-resolved open/navigation intents such as `open whatsapp`, `open notion`, or `launch spotify`

These use Python `webbrowser.open()` after either deterministic parsing or an AI URL-resolution step. Open/navigation intents do not generate Playwright tools unless the AI URL resolver cannot confidently map them to a public URL.

## 5. Registered Tools

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

## 6. Execution and Sufficiency

Tool calls run with a max concurrency of 3. Each script receives JSON args through `sys.argv[1]` and should return JSON on stdout.

After execution, `utils.sufficiency_checker.check_sufficiency(query, combined_result)` decides whether the tool output answers the user. If sufficient, the router streams synthesized final text. If insufficient or unmatched, it enters code generation.

## 7. Generated Tool Lifecycle

For unmatched/insufficient requests:

1. The router asks the selected LLM to generate a Playwright async Python tool.
2. It parses `TOOL_NAME`, `DESCRIPTION`, `ARGUMENTS`, and a Python code block.
3. `audit_code()` rejects forbidden imports/calls such as `exec`, `eval`, `os.system`, `subprocess`, `shutil`, and `pty`.
4. The script is written as `python/tools/temp_candidate_<requestId>.py`.
5. The router executes it once for verification.
6. On success, it renames the file to the final tool name and updates `registry.json`.
7. A background generalization task may run through `utils.generalizer.generalize_tool()`.

## 8. Synthesis

`stream_synthesis_llm()` turns raw tool output into a user-facing answer. It streams either:

- Groq chat completion chunks when `BLINKY_AI_PROVIDER=groq`.
- Ollama `/api/generate` response chunks otherwise.

Each chunk is forwarded to the WebSocket client using the `is_chunk` processing envelope.

## 9. Safety Notes

- Generated tools are audited, but the audit is intentionally simple. Treat router-generated files as untrusted until reviewed.
- The router writes to `python/tools/` and `python/tools/registry.json`.
- Power commands are immediate OS commands from Rust and should only be exposed on trusted local networks.
- WebSocket binding is `0.0.0.0:9001`; firewall/network policy matters.
