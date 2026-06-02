# Blinky — AI Inference & Client Configurations

This guide details LLM prompt engineering, request routing, preflight classification, continuation detection, and provider configurations for local and cloud models.

---

## 1. Request Flow & Preflight Classification

Blinky processes incoming user queries through a preflight checks model before performing screen capture operations:

```text
               [ User Question ]
                       │
                       ▼
          ┌──────────────────────────┐
          │   Preflight Classifier   │  (Text-only prompt)
          └──────────────────────────┘
           /                        \
 (needs_screen=False)             (needs_screen=True)
         /                            \
  ┌──────────────┐             ┌──────────────┐
  │ Chat Engine  │             │ Screen Engine│
  │ (No Capture) │             │ (Screen Cap) │
  └──────────────┘             └──────────────┘
```

---

## 2. Classifier & Conversation Logic

### 2.1 Preflight Classifier (`build_preflight_prompt`)
Determines if a request requires active screen context.
* **Continuation Detection (`is_continuation`)**: Analyzes if a request is a follow-up to the active workflow (e.g. *"what next?"*, *"now what?"*, *"it worked"*, *"done"*, *"next step"*).
* **Behavior**: If `is_continuation` is true, the engine swaps the effective query to the `previous_question` context while passing the current message as `latest_update`.

### 2.2 Chat Engine (`build_chat_prompt`)
Used for conversational queries (e.g. *"how does Rust compile?"*). Chat prompts return direct summaries immediately with an empty `steps: []` list. This prevents system instructions from leaking into the UI.

---

## 3. Screen-Bound Prompt Construction (`build_prompt`)

When screen analysis is triggered, the builder compiles coordinates and text tags into a highly optimized visual structure:

* **Compact Item Format**: Screen targets are serialized into a dense representation to minimize context window size and local inference times:
  ```text
  "Extensions" (18, 170, 48, 48, Tab)
  "Search Extensions in Marketplace" (80, 90, 320, 30, Edit)
  ```
  *Maximum element capacity is capped at 45 items.*

* **Blinky UI Filtering**: OCR terms associated with Blinky's overlay or settings labels (defined in `blinky_ignored_terms`) are stripped out.
* **Single-Step Rule**: The prompt template contains instructions strictly forbidding the generation of more than **1 step**.
* **Search-Bar Policy**: If a placeholder search box is visible, the AI must skip any navigation/sidebar steps and target the search field directly.
* **Target Text Requirement**: For typing actions, `target_text` must contain the exact placeholder text of the input.

---

## 4. Provider Client Specifications

Requests are routed via [client.py](file:///c:/projects/Jarvis/python/ai/client.py) based on the `BLINKY_AI_PROVIDER` environment variable.

### 4.1 Local Ollama Client (`ollama_client.py`)
Executes inference on local machines (typically utilizing `gemma4:e4b`).
* **Main Prompt Parameters**:
  * `num_predict`: 350
  * `temperature`: 0.1
  * `timeout`: 120 seconds
* **Preflight/Chat Prompt Parameters**:
  * `num_predict`: 300
* **Retry Strategy**: 2 attempt fallback sequence on endpoint failures.

### 4.2 Cloud Groq Client (`groq_client.py`)
Routes vision/text request payloads to cloud API endpoints.
* **Main Prompt Parameters**:
  * `max_tokens`: 350
  * `timeout`: Configurable via `BLINKY_GROQ_TIMEOUT` (Default: 90s)
* **Preflight/Chat Prompt Parameters**:
  * `max_tokens`: 300
* **Model Fallback**: If the configured vision model fails, falls back gracefully to `meta-llama/llama-4-scout-17b-16e-instruct` or standard default engines.
* **Format**: Captures are transmitted as Base64-encoded Data URLs.

---

## Related Guides & Files
- [01 System Architecture](file:///c:/projects/Jarvis/ai/01_architecture.md)
- [Prompt Compiler](file:///c:/projects/Jarvis/python/ai/prompt.py)
- [Model Router](file:///c:/projects/Jarvis/python/ai/client.py)
- [Ollama Integration](file:///c:/projects/Jarvis/python/ai/ollama_client.py)
- [Groq Integration](file:///c:/projects/Jarvis/python/ai/groq_client.py)
