---
id: subsys.pipeline
type: subsystem
version: 0.3.0
status: active
depends_on:
  - subsys.verdict@^0.1
  - subsys.channels@^0.2
  - subsys.ai-engine@^0.2
last_verified: 2026-09-06
documented_in: docs/ARCHITECTURE.md#pipeline
key_files:
  - pipeline.py
  - tests/test_pipeline.py
---

# Pipeline

`handle_message(message, deps)` is the one function `on_message` calls. Every
side effect is injected through `Deps(analyze, punish, log, immune_role_ids)`
so the whole flow runs offline (INVARIANT-04).

Order: `ignored` (bot author or DM) → `skipped` (nothing to analyze, a pure
check that touches no Discord object) → **fail-closed boundary 1**: NSFW probe
and `resolve_scope` (`exempt`, or `error` posted as "scope resolution failed")
→ **boundary 2**: `deps.analyze(content, guild_id, scope=ScopeChain)` (`error`)
→ sentinel / verdict parse (`clean`, `unparseable`) → **boundary 3**:
`deps.punish` (`error`) → delete + mod-log notice → the action string.

Analyzer contract: `async (content, guild_id, *, scope: ScopeChain) -> str`.
Reading the channel happens inside a `try` on purpose — a thread whose parent
left the cache raises in discord.py, and INVARIANT-03 says that goes to a
human rather than up the stack.
