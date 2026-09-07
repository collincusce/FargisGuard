# Operational Truth: Observability, Durable Queue, Moderator UI Gameplan

> Created: 2026-09-07
> Status: Planning
<!-- Optional, advisory-only (D-072) — declare to arm the wind-down advisory:
     "> Budget: N sessions" here, and/or "**Budget**: N sessions" inside a
     "### Phase N" block. Dormant by default; nothing blocks, ever. -->
> Kind: driven
> Procedure: docs/gameplans/GAMEPLAN-PROCEDURE.md

## Project Overview

FargisGuard can moderate, but it cannot yet prove that it does. The live deployment
has shown zero API requests over thirty days, every cost figure in the project is an
estimate from a worked pricing example rather than a measurement, and nothing has ever
been exercised against the live Anthropic API or a live Discord guild. Six modules in
the moderation path contain no logging at all, so the difference between "working and
quiet" and "silently skipping every message" is currently invisible from the outside.
This gameplan makes the deployment legible first — structured logging with a redaction
policy, token and cost metering, a selfcheck command that returns pass or fail instead
of asking an operator to read logs, and a health surface that can actually fail.

On that foundation it then pays down the two debts the last gameplan deferred: the
in-memory batch queue that a hard crash discards, and the release cleanups that have
been carried a version longer than intended. Only then does it build the moderator web
UI the token-architecture post-mortem handed forward — last, because it is the largest
new attack surface in the project's history and it needs per-moderator identity, real
per-guild authorisation, and a front door that does not exist yet.

## Subsystems Touched

- `subsys.pipeline` — logging on every outcome branch; no silent returns.
- `subsys.batcher` — durable write-through persistence, startup replay, idempotency.
- `subsys.ai-engine` — usage/token metering promoted out of a DEBUG-only log line.
- `subsys.database` — new queue table, WAL and busy timeout, retention policy.
- `subsys.dashboard` — honest health, authenticated stats, then the moderator UI.
- `subsys.rules` / `subsys.channels` / `subsys.moderation` — logging, cleanups, UI write model.
- `ext.anthropic-api` — the selfcheck host tier's one live round trip.
- `ext.discord-api` — intent verification, mod-log channel resolution, OAuth2 sign-in.

## Source-of-Truth Captures

Captured 2026-09-07 in a fresh venv built from `requirements-dev.txt` on the build
sandbox. These have authority over anything the gameplan body says.

| Value | Measured |
|---|---|
| Baseline test count | **321 passed**, 1 warning, ~2.9 s |
| Lint | `ruff check .` — all checks passed |
| Dependency health | `pip check` — no broken requirements |
| Package version | `pyproject.toml` 0.2.0 |
| Pinned runtime deps | discord.py 2.3.2, anthropic 1.4.0, openai 2.54.0 (rollback pin, dropped in Phase 5), fastapi 0.141.1, uvicorn 0.29.0 |
| Dev deps | pytest 9.1.1, pytest-asyncio 1.4.0, ruff 0.16.6 |
| Python | 3.11 (`requires-python >= 3.11`) |
| Build-host sqlite3 | 3.45.1 (**not** the constraint — see note) |

**Not yet captured — blocks Phase 6.** The *deploy host's* `sqlite3` version is the
value that governs the queue table's SQL, and it is not knowable from this sandbox.
L-07 records the trap directly: Amazon Linux 2 ships sqlite 3.7 while `RETURNING`
needs 3.35. Capture it on the instance (`python3 -c "import sqlite3;
print(sqlite3.sqlite_version)"`) before Phase 6 writes any SQL. The build host's own
version is recorded here only as a contrast, never as the constraint.

**Unmeasured, and must stay tagged as such.** Every token and dollar figure inherited
from the token-architecture gameplan is an estimate from a bundled reference's worked
example. Phase 2 is what turns them into measurements; until it has run on the live
deployment, no cost figure in this project may be quoted outside it.

## Amendments

_(None yet. Append A-NNN entries here once Phase 0 starts.)_

## Decisions

### D1 — Observability comes before cleanups, durability, and UI: the deployment must prove what it is doing before more is built on it

**Context**: The live deployment has shown zero API requests over 30 days (carried O-04) and every cost figure in the project is an unverified estimate (O-02). Nothing has been exercised against the live Anthropic API or a live Discord guild (O-03). Meanwhile pipeline.py, moderation.py, appeals.py, channels.py, rulecmds.py and composer.py contain no logging at all, on_ready uses print rather than logging, and pipeline.handle_message returns silently when should_analyze(message.content) is false. make_intents() requests message_content, a privileged intent: if it is not granted in the developer portal, every message arrives with empty content, every message is silently skipped, and the bot looks perfectly healthy while making zero API calls. That is the leading hypothesis for the zero-traffic mystery, and today nothing in the system could distinguish it from any other cause.
**Decision**: Sequence the gameplan observability first (structured logging with redaction, cost metering, a two-tier selfcheck, a real health and stats surface), then release cleanups, then the durable queue, then the moderator UI. A planning lens argued for cleanups first because they have no dependents; that optimises the cheapest work rather than the largest unknown. The same lens argued for the durable queue last to avoid rewriting against Batcher's constructor twice — that reasoning inverts: landing the queue before the UI is what makes Batcher.depth semantics stable, so the UI queue-depth view is written once against the durable store rather than the in-memory dict.
**Consequences**: The first shippable value is diagnostic, not functional: nothing a moderator can see changes until the cleanup phase. In exchange every later phase can be verified rather than assumed, and the operator gets one command that says pass or fail instead of grepping journalctl. The moderator UI is the last phase group and may not land in this gameplan if the earlier diagnosis reopens design questions; that is an accepted cost of building on measured ground.
**Evidence**: pipeline.py:191 (silent return on empty content); pipeline.py:62-64 (should_analyze); bot.py:31 (make_intents requests privileged message_content); bot.py:75 (on_ready uses print); ai_engine.py:208 (the only usage/token log line, DEBUG-only, not persisted); dashboard.py:34 (/health returns a fixed ok); dashboard.py:69 (start_dashboard refuses to start when DASHBOARD_TOKEN is unset, which .env.example ships blank); POST-MORTEM.md O-02/O-03/O-04.
**Status**: active (2026-09-07)

### D2 — selfcheck is one command with two tiers: an offline tier that runs anywhere and a host tier that makes exactly one real call to each external service

**Context**: DEPLOYMENT.md step 4 currently asks a human to eyeball journalctl after a deploy and judge whether a live classification worked. That is the only proof the system has ever had that its request shape, credentials, intents and channel wiring are correct, and it is unreliable: the operator must know what a good log looks like. INVARIANT-06 forbids the test suite from contacting Discord or any model provider, so this verification cannot live in pytest — but that is a constraint on the suite, not a reason to leave the check to human eyes.
**Decision**: Ship a selfcheck entry point with two tiers. The offline tier asserts config resolution against the target EnvironmentFile, database.init_db against a scratch path, and that the request builders produce well-formed payloads; it makes no network calls and is itself covered by the offline suite. The host tier, run explicitly on the instance, makes one trivial messages.create round trip and asserts stop_reason is end_turn and usage fields are populated; connects the Discord gateway and asserts the privileged intents were actually granted, that the configured MOD_LOG_CHANNEL resolves in every guild the bot is in, and that DASHBOARD_TOKEN is set so the dashboard will in fact start. Each check prints an individual pass or fail; the command exits non-zero if any fails and never swallows an exception into a pass.
**Consequences**: The host tier is exempt from INVARIANT-06 by construction, which must be stated explicitly so a future reader does not treat it as a violation; the offline suite tests the host tier through injected boundaries, never by running it. The runbook gains a numbered selfcheck step that replaces eyeballing logs. A check that cannot be made deterministic does not go in selfcheck; it becomes a tracked open item instead.
**Evidence**: docs/DEPLOYMENT.md step 4; INVARIANT-06; config.py resolve_model_key; database.py init_db; bot.py:31 make_intents; bot.py:34 mod_log_poster no-ops when the channel lookup returns None; dashboard.py:69 start_dashboard.
**Status**: active (2026-09-07)

### D3 — The durable batch queue is a write-through crash log in the existing SQLite file, not a new authoritative store: in-memory buckets stay the read path

**Context**: Batcher holds buckets in memory and a hard crash loses them (carried O-01). The obvious fix — make SQLite the authoritative queue — would rewrite Batcher.enqueue, which today is deliberately synchronous with no await so bucket-key selection cannot interleave, and would invalidate the assertions of the existing batcher tests, which read depth(), _buckets and _inflight directly. L-07 also warns that the deploy target's sqlite3 may be far older than the build host's, so version-gated syntax such as RETURNING cannot be assumed.
**Decision**: Persist buckets as a write-through crash log: enqueue writes a row, a successful flush deletes it, and depth() and bucket selection continue to read the in-memory structure. On startup, surviving rows are replayed into buckets before new enqueues are accepted. Rows carry an idempotency key so a bucket that crashed after the classifier call but before the actions were applied cannot double-punish on replay. The queue table is added to database.SCHEMA with WAL and a busy timeout, using only syntax the deploy host's sqlite version supports — the version is captured as a source-of-truth value before the phase writes any SQL.
**Consequences**: The existing batcher tests keep their meaning because the in-memory read path is unchanged; the new persistence is tested underneath them. Durability is bounded by the write-through window rather than absolute, and whether enqueue must become async to close that window is an open question this decision deliberately leaves to the phase with the code in front of it. Raw message content now lands on disk for the first time, which creates a retention obligation the same phase must discharge.
**Evidence**: batcher.py:108 (enqueue is synchronous by design); batcher.py:133 (depth reads in-memory buckets); batcher.py:32 SHUTDOWN_FLUSH_SECONDS and deploy/fargisguard.service TimeoutStopSec=40; database.py:152 connect opens a fresh connection per call with no WAL configured; database.py:22 SCHEMA/MIGRATIONS; L-07 (Amazon Linux 2 ships sqlite 3.7; RETURNING needs 3.35).
**Status**: active (2026-09-07)

## Open Items

**O-01.** _(phase 3)_ Leading hypothesis for the 30-day zero-traffic mystery, to be confirmed or killed on the host in Phase 3: make_intents() (bot.py:31) requests message_content, a privileged intent. If it is not granted in the developer portal, discord.py either refuses to connect or — if the running deploy predates that intent request — delivers every message with empty content, pipeline.handle_message returns silently at line 191 via should_analyze, and the bot makes zero API calls while appearing healthy. Confirm with `sudo journalctl -u fargisguard -n 100 --no-pager` and the developer portal's intent toggles before assuming any other cause.

**O-02.** _(phase 6)_ Whether Batcher.enqueue must become async to close the write-through durability window is deliberately left to Phase 6 with the code in front of it. Today enqueue is synchronous by design (batcher.py:108) so bucket-key selection cannot interleave; an awaited durable write reopens that interleaving. A crash between a synchronous enqueue and a deferred write still loses the message, which is the gap the phase exists to close — so the phase must either make enqueue async and prove the interleaving is safe, or state plainly what the residual window is.

**O-03.** _(phase 7)_ True durability under an OS-level kill cannot be proven offline. The suite can assert the write-through rows exist, that replay reconstructs buckets, and that replay is idempotent — that is the plumbing, not proof that SQLite survives SIGKILL mid-write on the deploy host's filesystem. Treat this as an open item, never an exit criterion, and have the operator confirm once with a deliberate kill -9 on the instance.

**O-04.** _(phase 2)_ Carried from the token-architecture gameplan: pricing figures still come from a bundled reference's worked example, not the live pricing page. Phase 2 supplies measured token counts; the dollar conversion is only as good as the rate, so confirm the rate against Anthropic's published pricing before quoting a cost commitment to anyone.

**O-05.** _(phase 9)_ Moving the moderator UI off loopback needs a TLS-terminating reverse proxy, a certificate, and an OAuth redirect URI — infrastructure that lives outside this repository. DEPLOYMENT.md today says never move DASHBOARD_HOST off loopback; Phase 11 must replace that flat prohibition with a real front-door procedure, and the operator must stand it up before any moderator can reach the UI.

## Phase Breakdown

### Phase 0: Bootstrap

**Goal**: _(one sentence.)_
**Depends on**: nothing (first phase).

| Task | Description | Effort |
|------|-------------|--------|
| 0.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] Source-of-truth captures recorded: 321 tests green, ruff clean, pip check clean, pyproject version 0.2.0, pinned discord.py 2.3.2 / anthropic 1.4.0 / fastapi 0.141.1
- [ ] INVARIANT-04 marked superseded by INVARIANT-06, which already states that it generalises it, so the register stops carrying the same rule twice
- [ ] The plan is committed on claude/next-gameplan-m09or3 so the first do-phase pre-flight finds a clean tree

### Phase 1: Structured logging and no silent returns

**Goal**: Structured logging across the whole moderation path, with the redaction policy of INVARIANT-07 and the no-silent-return rule of INVARIANT-08. Every module that currently has no logging at all (pipeline, moderation, appeals, channels, rulecmds, composer) gains it; on_ready stops using print; the silent return on empty content, the mod-log channel lookup that no-ops when the channel is missing, and both _log_safely swallow points each emit a named reason. This is the phase that would have made the zero-traffic mystery diagnosable.
**Depends on**: 0.

| Task | Description | Effort |
|------|-------------|--------|
| 1.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] pipeline.py, moderation.py, appeals.py, channels.py, rulecmds.py and composer.py each obtain a module logger and emit at least one record on every outcome branch
- [ ] bot.on_ready logs rather than prints
- [ ] The empty-content skip in pipeline.handle_message emits a record naming the reason, so a guild whose messages all arrive empty is visible in the log
- [ ] mod_log_poster logs a warning when the configured channel does not resolve, instead of silently no-opping
- [ ] Both _log_safely swallow points log the exception they swallow
- [ ] A test asserts no log record emitted by the moderation path contains message content, appeal text, or rules text (INVARIANT-07)
- [ ] Full suite green with no test removed or skipped

### Phase 2: Token and cost metering

**Goal**: Token and cost metering: a pure aggregator over the usage fields ai_engine already collects, persisted as counters rather than left in a DEBUG-only log line, so the project can finally answer what it spends. Resolves the measurement half of the carried O-02 and O-04 once the operator runs it.
**Depends on**: 1.

| Task | Description | Effort |
|------|-------------|--------|
| 2.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] A pure aggregator turns the usage fields into running totals and is tested against fixed usage dicts with no fakes beyond what tests/fakes.py already provides
- [ ] Token counters persist across a restart rather than living only in a DEBUG log line
- [ ] The usage record is emitted at the default log level, not only under LOG_LEVEL=DEBUG
- [ ] Missing usage (the case ai_engine reports as unknown) is counted as unknown rather than as zero, so an absent value can never read as a free request
- [ ] A test asserts the metering path records no message content (INVARIANT-07)
- [ ] Full suite green

### Phase 3: Two-tier selfcheck

**Goal**: Build the selfcheck entry point of D2: an offline tier covering config resolution, database.init_db against a scratch path, and request-builder shape; and a host tier making exactly one live Anthropic round trip, connecting the gateway to prove the privileged intents were actually granted, resolving MOD_LOG_CHANNEL in every guild, and asserting DASHBOARD_TOKEN is set. Per-check pass or fail, non-zero exit on any failure, no swallowed exception. This is the command that answers the zero-traffic question definitively.
**Depends on**: 1, 2.

| Task | Description | Effort |
|------|-------------|--------|
| 3.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] selfcheck runs its offline tier with no network access and exits non-zero when any check fails
- [ ] The offline tier covers config resolution against a given environment file, database.init_db against a scratch path, and request-builder shape
- [ ] The host tier makes exactly one live Anthropic round trip and asserts both that stop_reason is end_turn and that usage fields are populated
- [ ] The host tier connects the gateway and fails loudly when the privileged message_content intent was not actually granted
- [ ] The host tier resolves MOD_LOG_CHANNEL in every guild the bot is in and names any guild where it does not resolve
- [ ] The host tier reports whether DASHBOARD_TOKEN is set, since a blank one silently prevents the dashboard from starting
- [ ] No check swallows an exception into a pass; a test proves a raising check reports failure
- [ ] The offline suite exercises the host tier through injected boundaries and never contacts a real service (INVARIANT-06)

### Phase 4: Honest health and authenticated stats

**Goal**: Replace the unconditional ok from /health with a check that can actually fail (database reachable, gateway connected, age of the last classification), and add an aggregates-only /stats behind the existing bearer dependency — never beside the unauthenticated /health. Close the ops trap where start_dashboard silently declines to start because DASHBOARD_TOKEN is blank in the shipped .env.example.
**Depends on**: 2, 3.

| Task | Description | Effort |
|------|-------------|--------|
| 4.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] /health can fail: a test drives it to a failing status with an unreachable database
- [ ] /health reports gateway connectivity and the age of the last classification
- [ ] /stats sits behind the existing bearer dependency and returns 401 without it
- [ ] /stats returns aggregates only, and a test asserts no row content reaches the response body (INVARIANT-07)
- [ ] A blank DASHBOARD_TOKEN produces a loud startup warning rather than a silent decision not to start
- [ ] Full suite green

### Phase 5: Release cleanups

**Goal**: Shrink the surface before the durable queue and the UI touch it: drop the OPENAI_API_KEY fallback branch from config.resolve_model_key and the openai pin from requirements, remove the dead channels.is_exempt, and retire the legacy rules-table mirror in rules.set_scope_rules and rules.snapshot along with its one-shot backfill — after confirming nothing else reads that table. Version bump.
**Depends on**: 4.

| Task | Description | Effort |
|------|-------------|--------|
| 5.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] The OPENAI_API_KEY fallback branch is gone from config and the openai pin is gone from requirements
- [ ] channels.is_exempt and its tests are removed
- [ ] The legacy rules-table mirror and its one-shot backfill are removed, after a grep proves nothing else reads that table
- [ ] A fresh venv built from requirements-dev.txt alone runs the full suite green and pip check clean
- [ ] pyproject version, the package version, and the top CHANGELOG entry agree

### Phase 6: Durable queue: write-through persistence

**Goal**: Implement the write-through half of D3: capture the deploy host's sqlite version as a source-of-truth value first (L-07), add the queue table to database.SCHEMA with WAL and a busy timeout using only syntax that version supports, write a row at enqueue and delete it on successful flush, and settle the open question of whether enqueue must become async to close the write-through window. In-memory buckets remain the read path so the existing batcher tests keep their meaning.
**Depends on**: 5.

| Task | Description | Effort |
|------|-------------|--------|
| 6.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] The deploy host's sqlite3 version is captured as a source-of-truth value before any SQL is written, and no syntax newer than that version is used (L-07)
- [ ] The queue table is added through database.SCHEMA and its migration path, with WAL and a busy timeout configured
- [ ] A row is written at enqueue and deleted on successful flush; tests assert both transitions
- [ ] The enqueue sync-versus-async question (O-02) is answered in the phase summary with the residual durability window stated plainly
- [ ] depth() and bucket selection still read the in-memory structure, and the pre-existing batcher tests pass unchanged
- [ ] A concurrent-writer test proves the busy timeout prevents a database-is-locked failure under simultaneous bucket flushes

### Phase 7: Durable queue: replay, idempotency, and retention

**Goal**: Replay surviving rows into buckets at startup before accepting new enqueues, with an idempotency key so a bucket that crashed after the classifier call but before the actions were applied cannot double-punish. Reconcile replay with the existing shutdown drain and its unreviewed notice so the two mechanisms tell one story rather than double-processing. Discharge the retention obligation: raw message content is now on disk for the first time, so it gets a purge policy and the same file-permission treatment as warnings and appeals.
**Depends on**: 6.

| Task | Description | Effort |
|------|-------------|--------|
| 7.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] Rows surviving a restart are replayed into buckets before any new enqueue is accepted; a test inserts rows directly and asserts a fresh Batcher reflects them in depth()
- [ ] A bucket that crashed after the classifier call but before actions were applied does not double-punish on replay; a test proves the idempotency key holds
- [ ] Replay and the existing shutdown drain do not both process the same bucket, and the unreviewed notice is not posted twice across a restart
- [ ] Queue rows carry a purge policy and it is exercised by a test
- [ ] The queue file's permissions and retention are documented alongside warnings and appeals in SECURITY.md
- [ ] A dequeue failure still produces a mod-log notice rather than leaving a row queued forever (INVARIANT-03)

### Phase 8: UI read model

**Goal**: Extend the existing FastAPI app rather than standing up a second server: read-only routes over rules.snapshot and compose_rules, the batch settings view, pending actions, appeals, and queue depth. Depth is the one genuine seam gap — Batcher.depth lives on the running bot instance, not in database, so create_app and the dashboard_starter wiring must take the bot instance. Depth now reads durable state, so this view is written once against its final semantics.
**Depends on**: 7.

| Task | Description | Effort |
|------|-------------|--------|
| 8.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] create_app and the dashboard_starter wiring take the bot instance, so queue depth is served from the live batcher rather than a stale copy
- [ ] Read routes exist for the composed rules of a scope, batch settings, pending actions, appeals, and queue depth
- [ ] Every read route requires authentication; a test asserts 401 without it
- [ ] Routes are driven through the existing TestClient pattern, with no gateway and no live server
- [ ] Only one uvicorn server is started, and the on_ready regression guard still holds
- [ ] Full suite green

### Phase 9: Moderator identity and delegated authorship

**Goal**: Implement D-015: Discord OAuth2 sign-in, per-guild authorisation resolved from Discord permissions and role IDs rather than name strings, cookie sessions with SameSite=Strict, and CSRF tokens on mutating forms. Settle delegated scope authorship — which roles may edit which scopes — which the scoped-rules gameplan deferred to exactly this point. DASHBOARD_TOKEN is demoted to a machine-read credential and rejected on any mutating route.
**Depends on**: 8.

| Task | Description | Effort |
|------|-------------|--------|
| 9.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] Discord OAuth2 sign-in resolves a moderator to a Discord user id, with the client secret read only from the environment (INVARIANT-01)
- [ ] Authorisation is resolved per guild from Discord permissions and role IDs, never from role-name strings (INVARIANT-05)
- [ ] A moderator can do through the UI exactly what they can do in Discord and no more; a test proves a non-admin is refused an admin-only scope edit
- [ ] Delegated scope authorship is decided and recorded as a decision, closing the deferral carried from the scoped-rules gameplan
- [ ] Sessions are cookie-based with SameSite=Strict and mutating requests carry a CSRF token; tests cover a missing and a forged token
- [ ] DASHBOARD_TOKEN is rejected on every mutating route; a test asserts it cannot stand in for a moderator identity

### Phase 10: UI write model

**Goal**: Wire the write model behind the authorisation of Phase 9: set_scope_rules, clear_scope_rules, set_batch_interval, pending action approve and deny, and appeal resolution — each recording the acting moderator's Discord user id per INVARIANT-09, and each subject to the same human-gate guarantees the slash commands honour. The browser must not become a second path that can apply a held action without the gate.
**Depends on**: 9.

| Task | Description | Effort |
|------|-------------|--------|
| 10.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] Rules can be set and cleared per scope, and the batch interval set, from the browser, each recording the acting moderator's Discord user id (INVARIANT-09)
- [ ] Pending actions can be approved or denied and appeals resolved, with the same human-gate semantics the slash commands honour
- [ ] A test proves the browser cannot apply a held kick or ban without passing the gate
- [ ] Every write is authorised through Phase 9's per-guild resolution, and a test proves an unauthorised moderator is refused
- [ ] The audit trail records a real moderator id and never a shared credential; a test asserts the recorded id is a Discord user id
- [ ] Full suite green

### Phase 11: Release readiness

**Goal**: Truth up every document against what actually shipped, add the selfcheck step and the database backup note to the deployment runbook, write the reverse-proxy and TLS guidance the UI now requires (the loopback-only posture no longer covers it), revisit TimeoutStopSec against the durable shutdown drain, bump the version consistently across pyproject and the CHANGELOG, and run the clean-environment verification in a fresh venv.
**Depends on**: 10.

| Task | Description | Effort |
|------|-------------|--------|
| 11.1 | _(describe)_ | _(est)_ |

**Exit criteria**:
- [ ] README, ARCHITECTURE, SECURITY, DEPLOYMENT and TESTING claim only what shipped and was verified
- [ ] The deployment runbook has a numbered selfcheck step replacing the instruction to eyeball journalctl, and a database backup step before restart
- [ ] DEPLOYMENT.md's flat prohibition on moving off loopback is replaced with a reverse-proxy and TLS procedure for the UI
- [ ] TimeoutStopSec is revisited against the durable shutdown drain and either raised or justified as sufficient
- [ ] pyproject version, package version and the top CHANGELOG entry agree
- [ ] A fresh venv built from requirements-dev.txt alone runs the full suite green with pip check clean
- [ ] Every unmeasured cost claim is tagged as unmeasured, and any figure now measured cites its measurement
