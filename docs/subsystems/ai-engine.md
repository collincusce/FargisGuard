---
id: subsys.ai-engine
type: subsystem
version: 0.3.0
status: active
depends_on:
  - subsys.rules@^0.3
last_verified: 2026-09-06
external_deps:
  - ext.openai-api
documented_in: docs/ARCHITECTURE.md#ai-engine
key_files:
  - ai_engine.py
  - tests/test_ai_engine.py
---

# AI Engine

`ai_engine.py`. The only module that talks to the model; the client is lazy
and injectable so nothing here touches the network at import or in tests
(INVARIANT-04).

## Prompt layout

- **System turn** (static per process, the future cacheable prefix):
  `CLASSIFIER_INSTRUCTIONS` followed by the `<floor>` region rendered from
  `SAFETY_FLOOR` (D-008). The floor is defined in code — never a table a
  command can write — and the instructions say nothing in `<rules>` can permit
  what it forbids.
- **User turn**: `<rules>` (the guild's composed text) then `<message>`, both
  passed through `neutralize_tags` so supplied text cannot close a region or
  forge `</floor>`.

## API

`build_messages(rules, content)` (pure), `classify(rules, content, *, client,
model)`, `analyze_message(content, guild_id, *, scope, client, rules_loader)`.
`scope` is accepted from the pipeline; the composer consumes it in Phase 4/6.
