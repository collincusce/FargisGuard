# token-architecture Gameplan

> Created: 2026-09-07
> Status: Executing
<!-- Optional, advisory-only (D-072) — declare to arm the wind-down advisory:
     "> Budget: N sessions" here, and/or "**Budget**: N sessions" inside a
     "### Phase N" block. Dormant by default; nothing blocks, ever. -->
> Kind: driven
> Procedure: docs/gameplans/GAMEPLAN-PROCEDURE.md

## Project Overview

Cut classifier spend by sending many messages per request instead of one, and
move the classifier to Anthropic Claude. Messages are queued per
(guild, ResolvedRules.key) — the content hash from the scoped-rules gameplan —
and flushed as one request when a moderator-set interval elapses or the bucket
fills. Strict batching: no content-based fast path, because Discord AutoMod
already covers keywords and the model's job is the ambiguous remainder.

Batch model (so later phases do not re-derive it): a bucket freezes the rules
text it was opened with and holds message snapshots, not live objects (D1); the
timer is per bucket; interval 0 means classify per message (today's behaviour,
the default for a fresh guild, and the rollback switch); the interval is
clamped to BATCH_MAX_SECONDS and the size to BATCH_MAX_MESSAGES (D-012, D5).
Verdicts come back as structured JSON keyed by message id and fail closed per
id (D-013, supersedes D-001). Haiku 4.5 classifies every batch; Sonnet 5
re-checks severity >= 3 one message at a time before a hold (D-011).

Prompt caching is **deferred** (D-014): Haiku 4.5's minimum cacheable prefix
is 4096 tokens and ours is ~350–1100, so a breakpoint would write nothing.
The win in this gameplan is amortisation — the lens estimate is ~$0.275 →
~$0.095 per 1,000 messages on Haiku 4.5 (unconfirmed pricing, O-02).

## Subsystems Touched

- subsys.ai-engine — Anthropic client, batch request, structured output, re-check tier (major)
- subsys.verdict — batch protocol builder/parser
- subsys.pipeline — enqueue vs apply split; consolidated failure notices
- new: batcher — buckets, timers, shutdown flush
- subsys.database / subsys.rules — batch_settings row
- subsys.bot-gateway — /batch commands, close() flush
- docs: DEPLOYMENT (env rename, TimeoutStopSec, announcement), SECURITY, README, CHANGELOG
- ext.anthropic-api replaces ext.openai-api

## Source-of-Truth Captures

- Baseline: **217 passed** (`pytest -q`, 2026-09-07) on Python 3.11.15; discord.py 2.3.2, openai 2.54.0, fastapi 0.141.1
- Target SDK: anthropic **1.4.0** (latest on PyPI 2026-09-07); it depends on the separate `httpx2` package (2.12.0), which coexists with `httpx` 0.28.1 — verified in a fresh venv: install clean, `pip check` clean, 217 passed
- Reference facts (bundled claude-api skill, cached 2026-06-24): Haiku 4.5 min cacheable prefix 4096 tokens, Sonnet 5 1024; Sonnet 5 rejects non-default temperature/top_p/top_k (400); structured outputs supported on both; Message Batches API completes "usually within 1 hour, max 24 h" — expiry, not SLA
- Model ids: `claude-haiku-4-5`, `claude-sonnet-5` (exact strings, never date-suffixed)
- OpenAI touchpoints to migrate: requirements.txt:2, config.py:52, .env.example:6, docs/DEPLOYMENT.md:28, ai_engine.py, tests/conftest.py:11, tests/test_config.py, tests/fakes.py (FakeOpenAI), docs/datasources/openai-api.md
- discord.py 2.3.2: `Bot.run()` calls `close()` on SIGTERM/KeyboardInterrupt; no `close()` override exists in bot.py; deploy/fargisguard.service has no TimeoutStopSec (systemd default ~90 s)

## Amendments

_(None yet. Append A-NNN entries here once Phase 0 starts.)_

## Decisions

### D1 — A bucket freezes its rules text at creation and snapshots message content at enqueue

**Context**: RulesResolver invalidates on the guild's rules version, so re-resolving at flush would judge queued messages against rules enacted after they were posted and would break the key-as-identity contract (D-009). Message edits during the window raise the same question for content.
**Decision**: A bucket stores the ResolvedRules (text and key) it was opened with and uses that text at flush. on_message enqueues a frozen snapshot (message id, channel id, author id, content, jump_url, created_at) rather than the live discord.Message; the flush re-fetches nothing. A rules edit mid-window opens a new bucket under the new key; the old bucket flushes on its own timer with its old text.
**Consequences**: What was judged is exactly what was posted under the rules in force at the time — reproducible offline. Deletion at flush uses the message id (discord.NotFound is a no-op) and punishment re-resolves the member by id (a departed member gets history recorded and no live mutation).
**Evidence**: batching lens F3, F4, F5
**Status**: active (2026-09-07)

### D2 — Graceful shutdown flushes every bucket; anything that cannot be classified in time is posted as unreviewed

**Context**: The queue is in-process. discord.py's run() calls close() on SIGTERM; the systemd unit has no TimeoutStopSec so the default (~90 s) is the implicit budget. INVARIANT-03 forbids silently letting a message stand unreviewed. A hard crash cannot run any handler — durable queueing is out of scope here (open item).
**Decision**: FargisGuard.close() flushes all buckets concurrently with a bounded overall deadline before calling super().close(). Any bucket whose flush fails or does not complete inside the deadline posts one consolidated "N messages unreviewed — shutdown" notice to that guild's mod-log with the jump links. deploy/fargisguard.service sets TimeoutStopSec explicitly to cover the deadline plus one request timeout.
**Consequences**: A redeploy never silently drops queued messages. Crash safety is explicitly not provided and is written down as such.
**Evidence**: batching lens F1; ops lens finding 5
**Status**: active (2026-09-07)

### D3 — Verdicts apply in message order; same-member kick/ban-tier verdicts in one batch collapse into one pending action

**Context**: punish() is atomic per call, so escalation ladders within a batch exactly as across sequential messages — desirable, but only deterministic if application order is fixed. Three kick/ban-tier verdicts for one member would otherwise create three pending rows, three holds, and three mod-log notices.
**Decision**: Verdicts are applied in ascending message id (Discord snowflakes are time-ordered). Within one batch, once a member has a pending action created, further held-tier verdicts for that member in the same batch append their message links to that pending action's reason instead of creating another row; warn/timeout-tier verdicts still apply individually. A classifier or transport failure for a whole bucket posts one consolidated error notice listing the affected messages, not one notice per message.
**Consequences**: Reproducible offline; no mod-log floods. Escalation tests gain a parity case: three violations in one batch equal three sequential ones.
**Evidence**: batching lens F6, F7, F9(b)
**Status**: active (2026-09-07)

### D4 — ANTHROPIC_API_KEY replaces OPENAI_API_KEY with a one-release fallback and a startup warning; openai stays pinned one release

**Context**: config.py validates required secrets at import; deploying against an EnvironmentFile that only has OPENAI_API_KEY would crash-loop under Restart=on-failure every 5 s. Deploys are manual git pull + restart with no CI. L-02 requires fresh-venv verification of any dependency change. anthropic 1.x uses the separate httpx2 package, which coexists with httpx.
**Decision**: config reads ANTHROPIC_API_KEY; if unset and OPENAI_API_KEY is set it starts anyway, logs a WARNING naming the rename, and the classifier fails closed on first use with a clear error — one release only. requirements.txt adds anthropic==1.4.0 and keeps openai==2.54.0 for one release so `git checkout <previous-tag>` remains a working rollback without a pip step. Phase 0 proves the combined requirements install and pass in a fresh venv.
**Consequences**: .env.example, DEPLOYMENT.md, conftest.py, and test_config.py change in lockstep. The release after this one removes both the fallback and the openai pin.
**Evidence**: ops lens findings 2, 3; L-02; cost lens §5 (httpx2 coexistence verified by pip download)
**Status**: active (2026-09-07)

### D5 — Batch interval and size live in a per-guild batch_settings row, set by an Administrator-only /batch command

**Context**: The interval is moderator-set and per guild, so it cannot be env (process-wide). rules_version is the precedent for a tiny per-guild row. /rules is Administrator-gated; the interval is a safety-latency knob of the same weight.
**Decision**: Table batch_settings(guild_id PK, interval_seconds INT NOT NULL DEFAULT 0). 0 means classify per message (today's behaviour and the rollback switch); values are clamped to 1..BATCH_MAX_SECONDS (system constant, initial 300). BATCH_MAX_MESSAGES is a system constant (initial 25). /batch set <seconds> and /batch show, Administrator-only, guild-only; show also prints the current queue depth for the guild. Default for a fresh guild is 0 so nothing changes until a moderator opts in.
**Consequences**: Per-guild rollback without a redeploy. The dashboard gains no new route in this gameplan; /batch show is the operator's view.
**Evidence**: ops lens findings 1, 6
**Status**: active (2026-09-07)

## Open Items

**O-01.** Durable queue: the in-memory bucket is lost on a hard crash (SIGKILL/OOM). A SQLite-backed queue written at enqueue and swept at startup would close that gap; deferred until batching has run in production and O-01's baseline exists.

**O-02.** Pricing and cost figures in D-014 come from the bundled reference's worked example (Haiku 4.5 $1/$5, Sonnet 5 $2/$10 per MTok), not the live pricing page. Confirm before quoting a cost commitment to anyone.

**O-03.** Nothing in this gameplan has been exercised against the live Anthropic API or a live Discord guild (no keys in the session). The operator must run one real classification with LOG_LEVEL=DEBUG after deploy and confirm: the structured-output verdict parses, stop_reason is end_turn, and usage fields are populated.

**O-04.** Carried from the scoped-rules gameplan: the live deployment showed 0 API requests in 30 days (its O-01). The token baseline this gameplan is meant to improve is still unmeasured; run `sudo journalctl -u fargisguard -n 50 --no-pager` and record the diagnosis.

## Phase Breakdown

### Phase 0: Bootstrap

**Goal**: _(one sentence.)_
**Depends on**: nothing (first phase).

| Task | Description | Effort |
|------|-------------|--------|
| 0.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [x] Baseline recorded: 217 tests passing on Python 3.11.15, discord.py 2.3.2, openai 2.54.0; anthropic 1.4.0 identified as the target pin
- [x] A fresh venv installs requirements.txt with anthropic==1.4.0 added beside openai==2.54.0 and fastapi==0.141.1, and the existing suite passes in it (L-02)
- [x] GAMEPLAN.md overview states the batch model (per-(guild,key) buckets, frozen rules text, interval 0 = per-message, hard cap) and the caching deferral (D-014) so later phases do not re-derive them
- [x] Plan committed on claude/moderation-bot-optimization-qpmfn2; working tree clean

### Phase 1: Batch verdict protocol

**Goal**: A pure, provider-neutral batch protocol: build the numbered <message id=N> user turn, define the JSON schema for output_config.format, and parse a reply into per-id verdicts that fail closed per message (D-013). Supersedes verdict.parse_verdict's single-line contract while keeping it for the escalation re-check.
**Depends on**: 0.

| Task | Description | Effort |
|------|-------------|--------|
| 1.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [x] A pure build_batch_user_turn(rules, snapshots) renders <rules> then one <message id=N> block per snapshot with neutralized tags and the content ceiling applied per message
- [x] VERDICT_SCHEMA is a JSON schema with additionalProperties:false on every object and no numeric/length constraints, usable as output_config.format
- [x] parse_batch_verdicts(reply_json, expected_ids) returns a per-id result where each id is exactly one of clean / Verdict / unparseable; tests cover missing id, duplicate id, extra id, invalid severity, empty reason, empty or non-JSON reply (every id unparseable)
- [x] verdict.parse_verdict is unchanged and its tests still pass (the escalation re-check keeps using it or the single-message JSON form)
- [x] Full suite green, count recorded

### Phase 2: Anthropic engine

**Goal**: ai_engine talks to Anthropic: AsyncAnthropic, claude-haiku-4-5, structured output, stop_reason and exception handling per D-011/D-013, usage logging with cache fields; FakeAnthropic replaces FakeOpenAI; ANTHROPIC_API_KEY with the one-release fallback (D4). classify_batch(rules, snapshots) is the one call path; a single message is a batch of one.
**Depends on**: 1.

| Task | Description | Effort |
|------|-------------|--------|
| 2.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [x] ai_engine uses anthropic.AsyncAnthropic lazily; MODEL is claude-haiku-4-5; the request carries system=SYSTEM_PROMPT, the batch user turn, output_config.format=VERDICT_SCHEMA, temperature 0, no thinking parameter, and a max_tokens sized to the batch
- [x] stop_reason other than end_turn marks every id unparseable; the anthropic exception chain is caught most-specific-first and re-raised to the pipeline's fail-closed boundary
- [x] One DEBUG line per request logs ruleset key, batch size, input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
- [x] tests/fakes.py has FakeAnthropic (client.messages.create, content blocks with .type/.text, stop_reason, usage with the four token fields); FakeOpenAI is removed and no test imports openai
- [x] config.ANTHROPIC_API_KEY is required unless OPENAI_API_KEY is set, in which case startup logs a WARNING naming the rename and classify fails closed; test_config covers both; conftest seeds ANTHROPIC_API_KEY
- [x] requirements.txt pins anthropic==1.4.0 and keeps openai==2.54.0; full suite green, count recorded

### Phase 3: Batch queue

**Goal**: batcher.py: per-(guild, key) buckets with frozen rules text and message snapshots (D1), injected clock and sleep, flush on interval or size with generation swap, consolidated failure notices, deterministic application order and same-member collapse (D3), and FargisGuard.close() flush with the unreviewed fallback (D2). The pipeline splits into enqueue and apply_verdict; interval 0 keeps today's per-message path.
**Depends on**: 2.

| Task | Description | Effort |
|------|-------------|--------|
| 3.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [x] batcher.py: Bucket freezes ResolvedRules at creation and holds MessageSnapshot values; Batcher.enqueue returns without awaiting the network; flush fires on interval (injected clock and sleep) or size cap, whichever first; a size-triggered flush cancels the pending timer; enqueues during an in-flight flush land in the next generation (tests prove no loss and no double-processing)
- [x] Verdicts apply in ascending message id; a same-member held-tier verdict after the first in one batch appends to the existing pending action instead of creating another (test with three violations from one member)
- [x] A transport or classifier failure for a bucket posts ONE consolidated mod-log notice listing every affected message and punishes nobody (INVARIANT-03)
- [x] message.delete() tolerates discord.NotFound; a member who left is re-resolved by id and gets history recorded with no live mutation; one failing message does not abort the rest of the batch
- [x] FargisGuard.close() flushes all buckets under a deadline and posts an 'unreviewed — shutdown' notice for anything that did not complete, before super().close(); a test drives it with a fake that never completes
- [x] Interval 0 keeps the per-message path byte-for-byte: existing pipeline tests pass unchanged apart from the Recorder helper
- [x] Full suite green, count recorded

### Phase 4: Batch settings and commands

**Goal**: batch_settings table, get/set with clamping to BATCH_MAX_SECONDS, /batch set and /batch show (Administrator-only, guild-only) with the exposure-window wording from D-012, wired into the batcher's per-guild interval lookup.
**Depends on**: 3.

| Task | Description | Effort |
|------|-------------|--------|
| 4.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [x] batch_settings table created via SCHEMA; get_batch_interval(guild_id) returns 0 for an unknown guild; set_batch_interval clamps to 0..BATCH_MAX_SECONDS and rejects non-integers
- [x] /batch set <seconds> and /batch show exist, Administrator-only by default_permissions and a has_permissions check, guild-only; show prints the interval, the size cap, the guild's current queue depth, and the exposure-window sentence from D-012
- [x] The batcher reads the guild's interval per enqueue (no restart needed after /batch set)
- [x] Full suite green, count recorded

### Phase 5: Escalation re-check tier

**Goal**: Any verdict of severity >= 3 is re-checked one message at a time by claude-sonnet-5 (temperature omitted, thinking disabled) before punish() creates the pending action; a downward disagreement lowers the severity, a failure keeps the original and logs (D-011). Usage logged per tier.
**Depends on**: 3.

| Task | Description | Effort |
|------|-------------|--------|
| 5.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [x] recheck(rules, snapshot, verdict) calls claude-sonnet-5 with NO temperature/top_p/top_k, thinking disabled, the single-message batch form, and the same schema; a test asserts the request kwargs contain no sampling parameter
- [x] A verdict of severity >= 3 is re-checked before punish(); a lower re-check severity replaces it, a clean re-check downgrades to 'held for review' with both opinions in the notice (never silently clean), a failed or unparseable re-check keeps the original and logs the failure
- [x] Severity 1-2 verdicts never trigger a re-check (test counts calls)
- [x] The DEBUG line for the re-check is tagged tier=recheck with its own usage fields
- [x] Full suite green, count recorded

### Phase 6: Release readiness

**Goal**: Everything an operator needs: DEPLOYMENT.md sequence (env rename before restart, TimeoutStopSec, moderator announcement), .env.example, service unit, CHANGELOG, README, subsystem docs and versions, ext.anthropic-api entity with ext.openai-api retired, fresh-venv verification, cascades resolved, post-mortem inputs.
**Depends on**: 4, 5.

| Task | Description | Effort |
|------|-------------|--------|
| 6.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] docs/DEPLOYMENT.md upgrade sequence: announce batching latency to moderators, add ANTHROPIC_API_KEY to the EnvironmentFile BEFORE restart, pip install, DB backup, restart, journalctl checks including the new DEBUG line shape; deploy/fargisguard.service sets TimeoutStopSec explicitly
- [ ] .env.example, README (commands table, how-it-works diagram, model name), CHANGELOG Unreleased, ARCHITECTURE, and subsystem docs (ai-engine, pipeline, bot-gateway, new batcher) are updated with versions bumped; ext.anthropic-api entity created and ext.openai-api retired; every cascade resolved
- [ ] A fresh venv installs requirements.txt and passes the full suite; ruff clean
- [ ] Post-mortem inputs recorded: estimated per-1,000-message cost before/after from D-014 (labelled estimate) and the measured baseline status (O-04)
- [ ] Full suite green, count recorded
