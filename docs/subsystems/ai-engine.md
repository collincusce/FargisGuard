---
id: subsys.ai-engine
type: subsystem
version: 0.6.0
status: active
depends_on:
  - subsys.rules@^0.4
  - subsys.verdict@^0.2
last_verified: 2026-09-07
external_deps:
  - ext.anthropic-api
documented_in: docs/ARCHITECTURE.md#ai-engine
key_files:
  - ai_engine.py
  - tests/test_ai_engine.py
  - tests/test_recheck.py
---

# AI Engine

`ai_engine.py`. The only module that talks to the model — Anthropic via
`anthropic.AsyncAnthropic` (D-011), built lazily and injectable so nothing
here touches the network at import or in tests (INVARIANT-06).

## Request

`build_request(rules, contents)` is pure and returns the exact kwargs for one
`messages.create`: `model` (`claude-haiku-4-5`), `max_tokens` sized to the
batch, the static `system` turn (instructions + `<floor>` region, D-008), one
user message from `build_batch_user_turn` (`<rules>` then numbered
`<message id="N">` blocks, tags neutralised, content capped), and
`output_config.format` = `verdict.VERDICT_SCHEMA`. No sampling parameters
(C-01), no `cache_control` (D-014).

## Reply

`classify_batch(rules, contents, *, client, model, ruleset_key, tier)` returns
a `ParsedBatch`: `parse_batch_verdicts` over the first text block when
`stop_reason` is `end_turn`, otherwise every id `Unparseable` (D-013). API and
transport errors are logged with their class (RateLimitError → APIStatusError
→ APIConnectionError, most specific first) and re-raised to the pipeline's
fail-closed boundary. One DEBUG line per request: tier, ruleset key, batch
size, stop reason, rules chars, and the four usage counters
(`input_tokens`, `output_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`; `?` when absent). `LOG_LEVEL=DEBUG` enables it.

`analyze_message(content, guild_id, *, scope, client, rules_loader, resolver)`
is a batch of one and returns that message's `Outcome`. With a `scope` the
rules come from `composer.get_resolver()`; without one, the guild text.

## Key

`get_client()` raises `ConfigError` when `config.ANTHROPIC_API_KEY` is empty —
the one-release bridge (gameplan D4) lets the service start on a legacy
`OPENAI_API_KEY` with a warning and fails closed here on first use.

## Re-check tier (D-011)

`recheck(rules, content, *, client, ruleset_key)` asks `claude-sonnet-5` for a
second opinion on one message: same system turn, same schema, batch of one,
`thinking: {"type": "disabled"}` so `max_tokens` covers only the verdict, and
no sampling parameters (Sonnet 5 rejects them). Logged as `tier=recheck`.
`pipeline.with_recheck` runs it for any verdict of severity >= `RECHECK_AT`
(3) before punishment, and `pipeline.reconcile` folds the answer in: a lower
severity wins, equal or higher changes nothing, a clean second opinion marks
the verdict DISPUTED (still held for a human), a failure keeps the original.
