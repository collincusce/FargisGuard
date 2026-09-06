# Scoped Moderation Rules Gameplan

> Created: 2026-09-06
> Status: Executing
<!-- Optional, advisory-only (D-072) — declare to arm the wind-down advisory:
     "> Budget: N sessions" here, and/or "**Budget**: N sessions" inside a
     "### Phase N" block. Dormant by default; nothing blocks, ever. -->
> Kind: driven
> Procedure: docs/gameplans/GAMEPLAN-PROCEDURE.md

## Project Overview

Replace the single per-guild rules row with rules authored as plain sentences at
four scopes — guild default, channel category, channel, and the channel's
threads — composed into one injected prompt block per message. A moderator
types what a channel allows ("nudity is fine here, but never minors or animal
harm"; "video posts only, replies are plain text") instead of ticking boxes.

The composed text gets a stable identity (sha256 of its bytes) so that the
token-architecture gameplan that follows can batch messages sharing one ruleset
into one request and place the rules in a cacheable prefix. Along the way the
NSFW bypass (D-004) becomes a permissive scope with a hard, operator-owned
safety floor that no scope text can relax (D-007, D-008).

Scope model (so later phases do not re-derive it): Discord has no nested threads
(discord.py 2.3.2, verified from source), so thread scope is binary — in the
channel, or in one of its threads. Scopes are keyed by snowflake IDs, never
names (INVARIANT-05). Composition order is fixed: guild → category → channel →
thread; the floor is rendered separately and always present. The resolved
ruleset key is the content hash, not the scope tuple, so channels that inherit
identical text share one key. Resolution fails closed (D-010).

## Subsystems Touched

- subsys.rules — scoped table, composer, resolved-ruleset key (major)
- subsys.database — migration primitive, backfill, version counter
- subsys.channels — is_exempt retired from the pipeline; scope resolver lives here or beside it
- subsys.pipeline — resolver inside the fail-closed boundary; scope passed to analyze
- subsys.ai-engine — floor region in build_messages; analyze accepts scope
- subsys.bot-gateway — scope authoring slash commands
- docs: SECURITY.md threat model, DEPLOYMENT.md backup + NSFW release note

## Source-of-Truth Captures

- Baseline test suite: **148 passed** (`python -m pytest -p no:warnings`, 2026-09-06)
- Python 3.11.15; discord.py 2.3.2; openai 2.54.0; fastapi 0.141.1 (requirements.txt)
- discord.py 2.3.2 `Thread.category` raises `discord.ClientException("Parent channel not found")` when the parent is uncached (installed source, discord/threads.py)
- discord.py 2.3.2 has no nested threads: `Thread.parent` is `TextChannel | ForumChannel | None`
- Live OpenAI project "FargisGuard" dashboard, 30-day window ending 2026-09-06: 0 requests, 0 tokens, $0.00 spend (user screenshot) — see O-01
- Production call sites of the rules API: `ai_engine.py:77` (get_rules via rules_loader default), `bot.py:118` (set_rules from /setrules)
- Deploy: systemd unit `fargisguard`, `git pull` + `pip install` + `systemctl restart`, no backup step (docs/DEPLOYMENT.md:40-46)

## Amendments

_(None yet. Append A-NNN entries here once Phase 0 starts.)_

## Decisions

### D1 — Rule authorship at every scope is Administrator-gated in this gameplan; delegation is deferred to the UI gameplan

**Context**: /setrules (bot.py:113-119) is Administrator-only. If narrower scopes were writable under manage_channels, a single-channel mod could relax guild-wide moderation semantics for their channel — privilege escalation by proxy that INVARIANT-05 does not cover, since it concerns authorship rather than exemption. With the safety floor outside authored text, the residual risk is intentional delegation, which is a product choice, not a bug.
**Decision**: All scope-authoring commands added here require Administrator. Targets are chosen via Discord channel/category selects (IDs), never typed names. A delegation model (which roles may edit which scopes) is designed alongside the moderator UI, where it has a surface.
**Consequences**: Smaller permission surface now; one open item carried to the UI gameplan.
**Evidence**: bot.py:113-119, security lens findings #3 #6
**Status**: active (2026-09-06)

### D2 — Additive schema migration with backfill and one-release dual-read; the runbook gains a pre-restart DB backup

**Context**: database.MIGRATIONS (database.py:56-60) only supports ADD COLUMN. The move to a scoped table needs a new table with a composite key and a row copy; executescript offers no transactional DDL rollback, and the deploy runbook (docs/DEPLOYMENT.md:40-46) has no backup step. Existing guilds must keep working with zero moderator action on day one.
**Decision**: Add a one-shot-script migration primitive alongside _ensure_column. Create scoped_rules, backfill every rules row as a guild-scope row, and leave rules in place readable for one release so a bad migration is recoverable by code revert alone. get_rules keeps seeding DEFAULT_RULES when no scope has any row. DEPLOYMENT.md gains a `cp moderation.db moderation.db.bak-$(date +%F)` line before restart for this release.
**Consequences**: Dropping the legacy rules table is a follow-up after one production release. A second process running init_db concurrently is out of scope (single systemd unit) but noted for any future separate migration step.
**Evidence**: database.py:56-100, rules.py:13-30, docs/DEPLOYMENT.md:40-49, migration lens findings #1 #6
**Status**: active (2026-09-06)

### D3 — Forum posts resolve as threads of the forum channel

**Context**: A post in a Discord ForumChannel arrives as a discord.Thread whose parent_id is the forum. ForumChannel carries category_id like any guild channel. Giving forums their own scope kind would add a fifth scope and a fifth authoring command for no expressive gain: "the forum's rules" and "rules for posts in the forum" are the channel and thread scopes of the forum id.
**Decision**: resolve_scope treats a forum post exactly like a text-channel thread: channel_id = forum id, category_id = the forum's category, in_thread = True. Threads are recognised by the presence of parent_id (only discord.Thread has it in discord.py 2.3.2), and the parent is fetched by id via guild.get_channel, never via Thread.parent / Thread.category, which raise on an uncached parent.
**Consequences**: Moderators set forum rules with the channel-scope command on the forum and per-post rules with the thread-scope command. If Discord later nests threads, parent_id resolution needs revisiting; not before.
**Evidence**: discord.py 2.3.2 threads.py; tests/test_channels.py::test_forum_post_is_a_thread_of_the_forum_channel
**Status**: active (2026-09-06)

## Open Items

**O-01.** _(phase Bootstrap)_ Live deployment shows 0 OpenAI requests / 0 tokens over 30 days on the FargisGuard project. Token baseline measurement (Phase 0 and Phase 6) is blocked until the bot is confirmed running and its key is confirmed to belong to the project being watched. First diagnostic: `sudo journalctl -u fargisguard -n 50 --no-pager`.

**O-02.** Does the safety floor need an independent classification pass that ignores all scoped rules (a stronger-than-prompt guarantee), or is a structurally separate prompt region sufficient? Doubles calls if yes. Decide in the token-architecture gameplan once batching cost is known.

**O-03.** _(phase Scope resolver)_ Forum channels: a post in a ForumChannel is a Thread whose parent is the forum. Decide whether forum posts resolve as thread-scope of the forum, or whether ForumChannel gets its own scope kind. Resolver must have an explicit case either way (fail-closed decision). _(resolved 2026-09-06: D3: forum posts are threads of the forum channel (channel scope = forum id, in_thread=True); tested in tests/test_channels.py)_

**O-04.** Delegated rule authorship (which roles may edit which scopes) is deferred to the moderator-UI gameplan. Until then every scope is Administrator-only.

## Phase Breakdown

### Phase 0: Bootstrap

**Goal**: Land the plan and its captures, add the runbook backup step, and get a diagnosis on the silent live deployment so later phases start from a known state.
**Depends on**: nothing (first phase).

| Task | Description | Effort |
|------|-------------|--------|
| 0.1 | Commit the gameplan, decisions D-007..D-010, D1, D2, open items | 0.5h |
| 0.2 | Add the pre-restart `cp moderation.db moderation.db.bak-$(date +%F)` line to docs/DEPLOYMENT.md | 0.5h |
| 0.3 | O-01: read `journalctl -u fargisguard` output from the operator; record whether the unit is running, crashed at import, or keyed to another project | 0.5h |
| 0.4 | Write the Phase 1 handoff | 0.5h |

**Exit criteria**:
- [x] Baseline recorded in the phase handoff: 148 tests passing on Python 3.11.15 with discord.py 2.3.2, openai 2.54.0
- [x] docs/DEPLOYMENT.md contains a pre-restart `cp` backup line for moderation.db in the deploy sequence
- [x] O-01 has a recorded diagnosis (journalctl output summarised) or is explicitly deferred with the token-baseline criterion of Phase 6 marked blocked
- [x] A written scope-model note in the gameplan states the four scopes, the binary channel/thread rule, and the content-hash key, so later phases do not re-derive it
- [x] Working tree clean; the plan commit is on claude/moderation-bot-optimization-qpmfn2

### Phase 1: Scoped rules schema

**Goal**: Add the scoped_rules table (guild_id, scope_kind, scope_id, content, version) and a one-shot-script migration primitive in database.py; backfill every existing rules row as a guild-scope row; keep the legacy rules table readable for one release; rules.get_rules(guild_id) survives as a guild-only wrapper that still seeds DEFAULT_RULES; add a per-guild version counter bumped on every write.
**Depends on**: Bootstrap.

| Task | Description | Effort |
|------|-------------|--------|
| 1.1 | Add a one-shot-script migration primitive to database.py beside _ensure_column, idempotent, run inside init_db | 1h |
| 1.2 | Create scoped_rules(guild_id, scope_kind, scope_id, content) with a unique key, plus a per-guild rules_version counter | 1h |
| 1.3 | Backfill: copy every legacy rules row as a guild-scope row; leave the legacy table readable (D2) | 1h |
| 1.4 | rules.get_rules stays guild-only and still seeds DEFAULT_RULES; add get/set/clear at scope; every write bumps the version | 2h |
| 1.5 | Migration test on a temp DB seeded with a legacy row; version-bump tests | 1h |

**Exit criteria**:
- [x] database.py has a one-shot-script migration primitive alongside _ensure_column, applied idempotently inside init_db
- [x] scoped_rules table exists with a unique key on (guild_id, scope_kind, scope_id) and a per-guild rules version counter
- [x] A test opens a temp DB containing a legacy rules row, runs init_db, and asserts an identical guild-scope row exists in scoped_rules and the legacy row is untouched
- [x] rules.get_rules(guild_id) returns the guild-scope text and still seeds DEFAULT_RULES on a cold guild; the existing test_ai_engine loader test passes unchanged
- [x] Every write path (set, clear, default seeding) bumps the guild's version counter, proven by a test
- [x] Test count >= 148 and the full suite is green

### Phase 2: Scope resolver

**Goal**: A pure resolve_scope(message) → ScopeChain(guild_id, category_id | None, channel_id, in_thread: bool) that reads only Discord IDs, treats absence (no category) as normal, and raises on dangling references (thread parent not found, ClientException from Thread.category). Runs inside the pipeline's fail-closed try; the channel probe moves inside the same boundary (fixes the pre-existing INVARIANT-03 gap at pipeline.py:94). Add FakeCategory and FakeThread to tests/fakes.py. Settle O-03 (forum posts).
**Depends on**: Scoped rules schema.

| Task | Description | Effort |
|------|-------------|--------|
| 2.1 | resolve_scope(message) → ScopeChain from IDs only; absence is normal, dangling references raise (D-010) | 2h |
| 2.2 | Decide and test forum-post resolution (O-03) | 1h |
| 2.3 | FakeCategory, FakeThread, FakeChannel.category_id in tests/fakes.py | 1h |
| 2.4 | Move the channel probe + resolver inside the pipeline's fail-closed try; regression test for a raising probe | 1h |

**Exit criteria**:
- [x] A pure resolve_scope(message) exists that touches only .guild.id, .channel.id, .channel.category_id / .parent_id and never a name attribute
- [x] Tests cover: plain channel with category, channel with no category, thread of a text channel, thread whose parent lookup returns None (raises), Thread.category raising ClientException (raises), DM (never reached)
- [x] tests/fakes.py provides FakeCategory and FakeThread; FakeChannel gains category_id defaulting to None
- [x] pipeline.handle_message performs the channel probe and scope resolution inside the fail-closed try; a test proves a raising probe posts error_notice instead of escaping
- [x] O-03 (forum posts) is resolved with a recorded decision and a test
- [x] Full suite green

### Phase 3: Safety floor and NSFW supersession

**Goal**: Implement D-008: an operator-controlled floor (code/config, never a DB row) rendered in its own tagged prompt region separate from <rules>, always appended, with a system-prompt sentence telling the model the floor is non-negotiable. Implement D-007: retire channels.is_exempt from the pipeline so NSFW-flagged channels are classified against their resolved scope rules. Update docs/SECURITY.md threat model and the deploy note that NSFW channels are now classified. Tests prove no combination of scope text removes the floor from build_messages output.
**Depends on**: Scope resolver.

| Task | Description | Effort |
|------|-------------|--------|
| 3.1 | SAFETY_FLOOR in code/config; build_messages renders it in its own tagged region; SYSTEM_PROMPT names it non-negotiable (D-008) | 2h |
| 3.2 | Adversarial test: every scope filled with 'ignore the floor' text still yields the floor bytes in the payload | 1h |
| 3.3 | Retire channels.is_exempt from the pipeline; remove the 'exempt' return; update tests (D-007) | 1h |
| 3.4 | docs/SECURITY.md threat-model update; DEPLOYMENT.md release note that NSFW channels are now classified | 1h |

**Exit criteria**:
- [x] SAFETY_FLOOR text is defined in code or operator config and is not readable from or writable to any database table
- [x] build_messages renders the floor in its own tagged region distinct from <rules>, and SYSTEM_PROMPT states the floor overrides any rule text
- [x] A test asserts that for arbitrary scope text at every scope (including text that says to ignore the floor) the floor region is byte-for-byte present in the payload
- [x] channels.is_exempt is no longer called by pipeline.handle_message; the exempt return value is removed and its tests updated
- [x] docs/SECURITY.md threat model records that NSFW channels are now classified and injection there is in scope
- [x] docs/DEPLOYMENT.md release note tells operators that NSFW channels will be classified after this release
- [x] Full suite green

### Phase 4: Composer and resolved-ruleset key

**Goal**: compose_rules(chain) renders authored fragments in the fixed order guild → category → channel → thread with byte-stable whitespace, and returns ResolvedRules(text, key=sha256(text)). An in-process memo maps ScopeChain → ResolvedRules and is invalidated by the per-guild version counter (including the DEFAULT_RULES seeding insert). Property-style tests: same inputs → identical bytes; two channels that inherit the same text share one key; any write bumps the version and invalidates.
**Depends on**: Safety floor and NSFW supersession.

| Task | Description | Effort |
|------|-------------|--------|
| 4.1 | compose_rules(chain, fragments) → ResolvedRules(text, key) with fixed order and byte-stable joins (D-009) | 2h |
| 4.2 | In-process memo keyed by ScopeChain, invalidated by the guild version counter | 1h |
| 4.3 | Determinism, shared-key, invalidation, and single-connection tests | 2h |

**Exit criteria**:
- [x] compose_rules(chain, fragments) is pure and returns ResolvedRules(text, key) with key = sha256 of text
- [x] A test asserts identical inputs produce identical bytes across two calls and across fragment insertion order
- [x] A test asserts two channels with no channel-scope rows in the same category produce the same key
- [x] The in-process memo is keyed by ScopeChain and a test proves a rules write (any scope, including default seeding) invalidates it via the version counter
- [x] Resolution performs at most one SQLite connection per uncached ScopeChain, proven by a counting fake
- [x] Full suite green

### Phase 5: Authoring commands

**Goal**: Slash commands to set, show, and clear rules at each scope — targets chosen through Discord channel/category selects so only snowflake IDs reach the database (INVARIANT-05); thread scope is set on the parent channel. All Administrator-gated (D1). /showrules renders the effective composed text for a chosen channel so a moderator can see exactly what the classifier sees, floor included. Existing /setrules keeps guild-scope semantics unchanged.
**Depends on**: Composer and resolved-ruleset key.

| Task | Description | Effort |
|------|-------------|--------|
| 5.1 | /setrules-scope, /showrules, /clearrules-scope with channel/category select targets; Administrator-gated (D1) | 3h |
| 5.2 | /showrules renders the exact composed text incl. floor, for one chosen channel | 1h |
| 5.3 | FakeInteraction permission tests; existing /setrules tests unchanged | 1h |

**Exit criteria**:
- [ ] Slash commands exist to set, show, and clear rules at category, channel, and thread scope; targets are channel/category select options, not string names
- [ ] Every authoring command checks administrator permission before any database write, proven by a test using FakeInteraction
- [ ] /showrules <channel> renders the composed effective text including the floor region, so what a moderator sees equals what build_messages sends
- [ ] Existing /setrules behaviour and its tests are unchanged
- [ ] Full suite green

### Phase 6: Wire-through and measurement

**Goal**: pipeline.handle_message resolves the scope and passes it through Deps.analyze as additive optional kwargs; ai_engine.analyze_message composes via the memoised resolver; every classification logs the resolved-ruleset key, composed-rules token count, and message token count at debug level so the token-architecture gameplan starts from measured numbers. Update subsystem docs (rules, pipeline, ai-engine, channels), run the cascade, bump versions, and write the post-mortem inputs: distinct-ruleset cardinality per guild and the composed-rules token distribution (blocked on O-01 until the bot is confirmed running).
**Depends on**: Authoring commands.

| Task | Description | Effort |
|------|-------------|--------|
| 6.1 | pipeline passes ScopeChain to Deps.analyze as optional kwargs; ai_engine.analyze_message composes via the memo | 2h |
| 6.2 | Debug-level log per classification: ruleset key, composed-rules tokens, message tokens | 1h |
| 6.3 | Subsystem docs + version bumps; cz_cascade and resolve | 1h |
| 6.4 | Post-mortem inputs: ruleset cardinality and token distribution, or mark blocked on O-01 | 1h |

**Exit criteria**:
- [ ] pipeline.handle_message passes the resolved ScopeChain to Deps.analyze as additive optional kwargs; the Recorder helper in tests/test_pipeline.py is the only test change needed for the signature
- [ ] ai_engine.analyze_message composes through the memoised resolver and the guild-only rules_loader path still works for callers that pass no scope
- [ ] Each classification logs at debug level: resolved-ruleset key, composed-rules token count, message token count
- [ ] Subsystem docs for rules, pipeline, ai-engine, and channels are updated and versions bumped; cz_cascade run and resolved with no pending reports
- [ ] Post-mortem inputs recorded: distinct-ruleset cardinality per guild and composed-rules token distribution, or explicitly marked blocked on O-01
- [ ] Full suite green with test count recorded in the handoff
