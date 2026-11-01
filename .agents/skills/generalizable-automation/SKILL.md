---
name: generalizable-automation
description: Design or fix Blinky intent routing, browser and desktop automation, task context, and tool selection using general capabilities rather than patches for individual prompts or websites.
---

# Generalizable Blinky automation

The user wants unfamiliar tasks to use the same sound architecture as familiar tasks. Treat reported prompts as evidence and regression cases, not as the specification for a new phrase matcher. This skill guides implementation; it does not itself change runtime routing or guarantee arbitrary task success.

## Choose the correct abstraction

- Trace the request through the PC and mobile entry points, tool ownership, selected app/tab, observations, planner decisions, and delivery evidence. Identify whether the defect is intent classification, lost context, incomplete observation, unsupported execution, or incorrect success reporting before changing code.
- Preserve fast dedicated tools for capabilities they actually support. Use explicit capability contracts and parameter validation to establish ownership. An unknown request must remain unresolved until intent/context selects a tool; it must not silently default to desktop automation.
- For unfamiliar instructions, use structured intent resolution with current task context and available capabilities. Validate the resolver's output before execution. Keep routing side-effect free; use bounded read-only discovery when context is insufficient, or ask for essential ambiguity.
- Carry structured context across requests and PC/mobile workers: session, task objective, engine, app identity, browser/tab identity, observed URL, observation freshness, and delivery status as appropriate. Follow-ups should inherit the correct target, with explicit user changes and fresh observations overriding stale context. A timestamp or a cached app title alone is a hint, not proof of the current target.
- Browser page interactions belong to the browser adapter; OS controls belong to the desktop adapter. Select targets from live inventory and observed refs. Do not infer the engine solely from a site's name, a single action verb, or whichever window Blinky overlays.

## Avoid example-specific patches

Do not fix a general routing or targeting bug by adding another brand list, exact user sentence, fuzzy label match, fixed coordinate, or guessed DOM selector. Promote the missing intent/capability or context transition into a shared mechanism. Consolidate duplicated routing decisions instead of adding divergent PC/mobile branches.

Deterministic code remains appropriate for tool schemas, native operations such as creating a tab, protocol validation, executable aliases, and provider adapters with real API differences. Put genuine provider-specific behavior behind the adapter boundary. A fast-path parser may recognize a supported operation, but unfamiliar wording must still have a general resolution path rather than requiring more regexes.

For browser composers, discover editable elements through the browser's supported observation mechanisms, including rich-text editors. After navigation, acquire fresh refs. If a control is absent, distinguish page readiness, wrong tab/frame, and observation limitations; do not invent a ref or blindly switch to desktop input.

## Delivery, debugging, and review

- Separate routing, planning, execution, and completion evidence. A successful keypress or accepted fill does not prove a tab opened or a message was sent. Confirm the requested outcome from suitable native results or fresh observations; otherwise report the uncertainty.
- Bound recovery. Reobserve and replan when non-delivery is established; never blindly replay a potentially delivered click, submission, or message.
- Keep routing rationale, chosen engine/target, observations, decisions, delivery results, errors, and useful timing in the existing `screenshots_parsed` debug structure. Avoid logging credentials or unrelated private content.
- When tests are authorized, cover the failed case alongside paraphrases, an unfamiliar site/app, a multi-turn continuation, an explicit target change, an unrelated local task, and stale/missing context. Assert behavior and ownership, not regex text. Respect a user request to handle verification themselves and state what remains unverified.
- Before finishing, explain what general mechanism changed and why it handles unseen examples. If a fix is intentionally narrow, disclose the limitation rather than claiming broad reliability.

## Blinky integration points

Start with the relevant portions of `common/python/main.py`, `common/python/agent_router.py`, `common/python/computer_use/dedicated_routes.py`, `common/python/computer_use/browser_context.py`, `common/python/tools/browser_use_tool.py`, and `common/python/computer_use/vercel_engine.py`. Verify current call paths rather than assuming these files are the complete architecture.

Use [browser-vs-local-tool-routing](../browser-vs-local-tool-routing/SKILL.md) for web/local ownership safeguards and [blinky-tool-registration](../blinky-tool-registration/SKILL.md) when registering a new capability. Their deterministic matchers support explicit capabilities; do not extend them into an exhaustive list of natural-language instructions.
