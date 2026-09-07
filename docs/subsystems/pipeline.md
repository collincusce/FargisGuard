---
id: subsys.pipeline
type: subsystem
version: 0.6.0
status: active
depends_on:
  - subsys.verdict@^0.2
  - subsys.channels@^0.2
  - subsys.ai-engine@^0.6
  - subsys.rules@^0.4
  - subsys.moderation@^0.4
last_verified: 2026-09-07
documented_in: docs/ARCHITECTURE.md#pipeline
key_files:
  - pipeline.py
  - tests/test_pipeline.py
  - tests/test_batcher.py
  - tests/test_recheck.py
---

# Pipeline

`handle_message(message, deps)` is the one function `on_message` calls. Every
side effect is injected through `Deps(analyze, punish, log, immune_role_ids)`
so the whole flow runs offline (INVARIANT-04).

Order: `ignored` (bot author or DM) → `skipped` (nothing to analyze, a pure
check that touches no Discord object) → **fail-closed boundary 1**:
`resolve_scope` (`error` posted as "scope resolution failed") → **batching
branch** (D-012): with a batcher and a positive `interval_for(guild)`, resolve
the rules, snapshot the message, `batcher.enqueue` and return `queued` /
`queued-flush` (a failure here is `error`, "queueing failed") → otherwise
**boundary 2**: `deps.analyze(content, guild_id, scope=ScopeChain)` (`error`)
→ outcome branch (`clean`, `unparseable`) → **boundary 3**:
`deps.punish` (`error`) → delete + mod-log notice → the action string.

Analyzer contract: `async (content, guild_id, *, scope: ScopeChain) -> verdict.Outcome`
(`Verdict`, `CLEAN`, or `Unparseable(problem)`); the pipeline branches on the type.
Reading the channel happens inside a `try` on purpose — a thread whose parent
left the cache raises in discord.py, and INVARIANT-03 says that goes to a
human rather than up the stack.

## Applying a batch verdict (`apply_outcome`)

Called by the batcher per snapshot, in ascending message id: `Clean` does
nothing; `Unparseable` posts "needs a human"; a `Verdict` re-resolves the
author by id (gone → `moderation.record_history_only`, delete, notice),
punishes with `existing_pending_id` from the batch's `held` map so a member's
second held-tier verdict joins the first pending action (gameplan D3), deletes
by id through a partial message (`NotFound`/`Forbidden` are no-ops), and posts
the violation notice. One message's failure never aborts the rest.

## Re-check before a hold (D-011)

On both paths, a `Verdict` of severity >= `RECHECK_AT` (3) goes through
`with_recheck` → `deps.recheck(rules_text, content, ruleset_key=)` →
`reconcile` before `punish`. The batch path uses the bucket's frozen rules
text; the per-message path resolves the scope's rules. A re-check never
escalates, never clears (a clean second opinion is "DISPUTED" in the reason,
and severity >= 3 is held for a human regardless), and never raises.
`Deps.recheck=None` disables the tier.
