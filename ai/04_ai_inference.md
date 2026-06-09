# Blinky AI Inference and Prompting

This guide covers the desktop screen-tutor inference path. The remote browser-agent path is documented separately in `07_agent_router.md`.

## 1. Request Routing

`python/main.py` starts with lightweight routing before capture:

1. `extract_locator_target()` detects questions like "where is", "show me", "locate", "highlight", or "point to".
2. `should_force_screen_context()` forces screen mode for UI actions such as click, open, install, search, settings, folder, file, app, button, icon, and locator questions.
3. Otherwise `classify_request()` calls `ask_text_model(build_preflight_prompt(...))`.
4. If `needs_screen=false`, `answer_without_screen()` returns a chat response with `steps: []`.
5. If `is_continuation=true`, the worker reuses `previous_question` as the active goal and treats the current message as `latest_update`.

## 2. Conversation State

`CommandBar.tsx` keeps the last query, completed target/instruction lists, and recent conversation history. It sends:

- `previous_question` for workflow continuation.
- `progress.completed_targets` and `progress.completed_instructions` after highlight clicks or text-entry Enter events.
- Up to recent `conversation_history` entries with roles `student` and `blinky`.

`python/main.py` normalizes this history to the last 10 entries and `prompt.py` includes up to the last 8 entries in prompts.

In command-bar globe/web mode, `runWebActionThenScreenGuidance()` first lets the browser agent open/search the relevant page. Then `runAutopilotLoop()` repeatedly calls the same `runTutor()` screen path after each safe click. There is no separate "multi-step script" prompt for autopilot; the model still returns one immediate next screen action and the frontend handles retry, stopping, and safety.

## 3. Locator Fast Path

Locator-style requests can return without the main LLM screen prompt:

```text
question -> capture -> UIA include_unlabeled=True -> find_best_match_with_score()
```

The fast path accepts a match only when confidence and ambiguity checks pass. For control locator questions, the accepted candidate must be an interactive UIA control and must not be ambiguous. If confidence is low or icon-like controls need visual interpretation, the request falls back to the main screen AI path.

## 4. Screen Prompt Construction

`build_prompt()` receives:

- effective student goal
- active app metadata
- visible OCR/UIA items
- completed workflow context
- optional latest follow-up comment
- recent conversation history

Visible items are serialized compactly:

```text
"Search Extensions in Marketplace" (80,90,320,30,Edit)
"Extensions" (18,170,48,48,TabItem)
```

Prompt selection rules:

- Keep only the immediate next action.
- Return at most one step.
- Use exact visible `target_text` for highlights.
- Use an empty `target_text` only when guidance is needed but no visible target exists.
- Skip navigation steps if the relevant search/filter/find box is already visible.
- Ignore Blinky's own UI unless the user explicitly asks about Blinky settings.
- Never mention coordinates in user-facing text.

## 5. Provider Router

`python/ai/client.py` selects the provider from `BLINKY_AI_PROVIDER`.

| Function | Ollama | Groq |
| :--- | :--- | :--- |
| `ask_model(prompt, screenshot_path)` | `ask_ollama(prompt)` | `ask_groq_vision(prompt, screenshot_path)` |
| `ask_text_model(prompt, max_tokens=300)` | `ask_ollama_text(prompt, max_tokens)` | `ask_groq_text(prompt, max_tokens)` |

Unsupported values raise `RuntimeError("Unsupported BLINKY_AI_PROVIDER...")`.

## 6. Ollama Client

Source: `python/ai/ollama_client.py`

| Setting | Value |
| :--- | :--- |
| URL env | `BLINKY_OLLAMA_URL` |
| Default URL | `http://localhost:11434/api/generate` |
| Model env | `BLINKY_OLLAMA_MODEL` |
| Default model | `gemma4:e4b` |
| Timeout env | `BLINKY_OLLAMA_TIMEOUT` |
| Default timeout | `35` seconds |
| Main output cap | `num_predict: 350` |
| Text output cap | caller default `300` |
| Format | `json` |
| Temperature | `0.1` |

The main guidance call retries twice for non-timeout failures and validates the final payload into `{ summary, steps, warnings }`.

## 7. Groq Client

Source: `python/ai/groq_client.py`

| Setting | Value |
| :--- | :--- |
| URL env | `BLINKY_GROQ_URL` |
| Default URL | `https://api.groq.com/openai/v1/chat/completions` |
| Model env | `BLINKY_GROQ_MODEL` |
| Default model | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Timeout env | `BLINKY_GROQ_TIMEOUT` |
| Default timeout | `90` seconds |
| Main output cap | `max_tokens: 350` |
| Text output cap | caller default `300` |
| Response format | JSON object |
| Temperature | `0.1` |

Groq vision sends the screenshot as a base64 JPEG data URL. The decommissioned `llama-3.2-90b-vision-preview` model is ignored and replaced with the default model.

## 8. Post-Inference Enforcement

After model output:

1. `attach_matches()` links `target_text` to visible coordinates.
2. `skip_completed_navigation_steps()` removes a stale first navigation step when the next target is already visible.
3. `_fill_empty_search_targets()` attaches visible search/filter/find inputs to search-like steps with empty target text.
4. `steps[:1]` enforces single-step mode even if a model returns more.

See `03_matching_heuristics.md` for scoring and merge details.

## 9. Autopilot Continuation

Autopilot uses normal continuation inputs:

- the original user request remains the goal,
- completed instructions/targets are tracked in the command bar,
- each click is followed by a fresh screenshot/OCR/LLM pass,
- the next returned step is rechecked by the frontend safety gate before any new click.

This keeps browser tasks adaptive: if a click changes the page, the next observation decides what to do next. If nothing changes or the next action becomes unsafe, the loop stops and leaves the visible Action Guide for the user.
