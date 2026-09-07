# Chat Handoff Index — token-architecture

> Last updated: 2026-09-07
> Status: Phase 5 ready

## How This Works

This is the coordination point for sessions executing this gameplan. A fresh
session gets current state automatically from the Clauderizer SessionStart hook,
then calls `cz_next_phase_context` for the active phase. No manual reading order.

## Pre-Flight Verification

Run `cz_preflight` before any code. If any enabled check fails: STOP, report.

**Current baseline test count**: 0

## Ending Protocol

1. `cz_transition_phase` the finished phase to complete.
2. `cz_add_output` each concrete produced value; `cz_add_phase_summary` the recap;
   `cz_add_correction` / `cz_add_lesson` as earned.
3. `cz_transition_status` on touched entities (fires cascade); `cz_resolve_cascade`
   the verdicts.
4. `cz_write_handoff` for the next phase.
5. Run exit verification; report the test count.

## Phase Status Table

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Batch verdict protocol | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-1-HANDOFF.md |
| 2 | Anthropic engine | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-2-HANDOFF.md |
| 3 | Batch queue | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-3-HANDOFF.md |
| 4 | Batch settings and commands | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-4-HANDOFF.md |
| 5 | Escalation re-check tier | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Release readiness | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |

**Status legend**: ⬜ NOT STARTED · 🟢 READY · 🟡 IN PROGRESS · ✅ COMPLETE · ⚠️ BLOCKED · 🔴 FAILED

## Per-Phase Completion Summaries

### Phase 0 — completed 2026-09-07

Planned from three lenses (batching failure modes, Anthropic API/caching/cost against the bundled reference, ops/config/testing). The decisive finding: prompt caching cannot fire on Haiku 4.5 — its minimum cacheable prefix is 4096 tokens against our ~350–1100 — so D-014 defers caching and batching carries the whole cost win (~65% by the lens estimate). Recorded D-011 (Anthropic Haiku 4.5 + Sonnet 5 re-check), D-012 (strict batching per (guild, key), interval 0 = per-message, hard cap), D-013 (structured per-id verdicts, supersedes D-001), INVARIANT-06 (provider-neutral offline tests), gameplan decisions D1–D5, and open items O-01..O-04 (durable queue, unconfirmed pricing, no live verification, carried baseline). Six phases laid out with machine-checkable criteria.

Fresh-venv proof: anthropic 1.4.0 installs beside openai 2.54.0 and fastapi 0.141.1 (httpx and httpx2 coexist), pip check clean, 217 passing. Plan committed as 718addd.

### Phase 1 — completed 2026-09-07

The batch verdict protocol exists as pure code with no provider attached. verdict.py gained VERDICT_SCHEMA (the json_schema for output_config.format: {"verdicts":[{id, result OK|VIOLATION, severity int|null, reason}]}, additionalProperties:false everywhere, no numeric/length constraints) and parse_batch_verdicts(text, expected_ids) → ParsedBatch, which yields exactly one Outcome per expected id — Verdict, CLEAN, or Unparseable(problem) — failing closed per id: missing, duplicated, or malformed entries degrade only their own id; ids the model invents are reported in unexpected_ids and never applied; a reply that is not JSON at all makes every id Unparseable. parse_verdict is untouched. ai_engine.build_batch_user_turn renders <rules> then <messages> with batch-local 1-based <message id="N"> blocks, tag-neutralised and content-capped per message. snapshots.MessageSnapshot is the frozen record the batcher will queue.

34 new tests; suite 251 green, ruff clean. verdict subsystem 0.2.0 with its doc body written.

### Phase 2 — completed 2026-09-07

The classifier now runs on Anthropic. ai_engine.py builds one messages.create request per batch — claude-haiku-4-5, the static system turn (instructions rewritten for numbered messages + the floor), the batch user turn, output_config.format = VERDICT_SCHEMA, max_tokens sized to the batch, and no sampling parameters (C-01: the 1.4.0 SDK's create() has no temperature at all, so D-011's "temperature 0" was dropped rather than smuggled through extra_body). classify_batch parses the first text block when stop_reason is end_turn and fails every id closed otherwise; RateLimitError → APIStatusError → APIConnectionError are logged with their class and re-raised into the pipeline's fail-closed boundary. One DEBUG line per request carries tier, ruleset key, batch size, stop reason, and the four usage counters. analyze_message is a batch of one returning an Outcome; the pipeline's Analyzer contract changed accordingly and branches on Clean / Unparseable / Verdict.

config.resolve_model_key is pure: ANTHROPIC_API_KEY wins; a legacy OPENAI_API_KEY alone starts the service with a WARNING and fails closed on first classification; neither key fails fast naming the new one (gameplan D4). requirements.txt pins anthropic==1.4.0 and keeps openai for one release. FakeAnthropic replaced FakeOpenAI; no test imports openai. Suite 262 green; ai-engine 0.5.0, pipeline 0.4.0, ext.anthropic-api created.

### Phase 3 — completed 2026-09-07

The batch queue exists and is wired, but dormant until Phase 4 gives guilds an interval. batcher.py holds per-(guild, ruleset-key) buckets that freeze their ResolvedRules and hold MessageSnapshots; enqueue is synchronous, each bucket runs its own injected-sleep timer, the size cap flushes at once and cancels the timer, and a flush is swap-and-clear so enqueues during an in-flight flush open a new generation — tests prove nothing is lost or classified twice. _run sorts by message id, classifies once, and applies per message with a shared held map; one apply failure is posted and the rest continue; a classifier failure posts one consolidated notice with links and punishes nobody. shutdown(deadline) flushes everything, cancels stragglers, and posts "unreviewed — shutdown" per unfinished bucket; FargisGuard.close() calls it before super().close().

pipeline.Deps gained batcher, interval_for (default 0 = per message, so all 262 prior tests pass unchanged apart from stub signatures), resolve_rules, and clock; handle_message enqueues a snapshot under the frozen rules on a positive interval and returns queued/queued-flush. apply_outcome mirrors the verdict-onward path from a snapshot: author re-resolved by id (gone → history only), delete by partial message tolerating NotFound/Forbidden, and punish(existing_pending_id=) so a member's second held-tier verdict in a batch joins the first pending action (database.append_pending_reason). 22 new tests; suite 284 green, ruff clean. New subsystem batcher 0.1.0; pipeline 0.5.0, moderation 0.4.0, database 0.4.0, bot-gateway 1.2.0.

### Phase 4 — completed 2026-09-07

Moderators can now turn batching on per guild. batchsettings.py stores interval_seconds in a batch_settings row (0 = per-message, the default and the rollback switch), clamps writes to 1..BATCH_MAX_SECONDS (300), rejects non-integers before any write, and reads the value on every enqueue so /batch set takes effect on the next message with no restart — proven by a test that flips the interval between three messages. /batch set <seconds> and /batch show are Administrator-only and guild-only; show reports the interval, the size cap, the guild's live queue depth, and the exposure-window sentence from D-012. create_bot wires interval_for=get_batch_interval by default. A fake gap surfaced: FakeMessage had no id, so snapshot_of raised inside the queueing boundary and the pipeline correctly answered "error" — fixed in the fake. 20 new tests; suite 304 green. database 0.5.0, batcher 0.2.0, bot-gateway 1.3.0.

## Accumulated Lessons

_(Numbered sequentially across the whole gameplan. Categorized. Pruned of
obsolete items — mark with "(obsolete)" rather than deleting.)_

### Category: Process

_(none yet)_

**1.** Verify a planned request parameter against the installed SDK's signature (inspect.signature) before writing the decision, not after — the reference docs describe the API surface, the SDK pin decides what is expressible.
