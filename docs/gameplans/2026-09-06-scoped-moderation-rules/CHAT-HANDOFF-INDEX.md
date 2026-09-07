# Chat Handoff Index — Scoped Moderation Rules

> Last updated: 2026-09-06
> Status: All 7 phases complete

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
| 0 | Bootstrap | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Scoped rules schema | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-1-HANDOFF.md |
| 2 | Scope resolver | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-2-HANDOFF.md |
| 3 | Safety floor and NSFW supersession | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-3-HANDOFF.md |
| 4 | Composer and resolved-ruleset key | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-4-HANDOFF.md |
| 5 | Authoring commands | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-5-HANDOFF.md |
| 6 | Wire-through and measurement | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-6-HANDOFF.md |

**Status legend**: ⬜ NOT STARTED · 🟢 READY · 🟡 IN PROGRESS · ✅ COMPLETE · ⚠️ BLOCKED · 🔴 FAILED

## Per-Phase Completion Summaries

### Phase 0 — completed 2026-09-06

Landed the plan (D-007..D-010 project ADRs, D1/D2 gameplan decisions, O-01..O-04), captured the baseline (148 tests, Python 3.11.15, discord.py 2.3.2, openai 2.54.0), and added the pre-restart SQLite backup line to docs/DEPLOYMENT.md with the reasoning (no transactional DDL rollback once migrations create or copy tables). Fixed the session environment so cz_preflight's bare `pytest` resolves the project's deps (lesson #1).

O-01 (the live deployment reporting 0 OpenAI requests over 30 days) is deferred, not resolved: the operator has not yet supplied journalctl output. Phase 6's token-distribution criterion is blocked on it; nothing in Phases 1–5 depends on it.

### Phase 1 — completed 2026-09-06

Scoped rules storage landed without touching any caller. database.py gained three tables (scoped_rules keyed on guild/kind/id, rules_version, schema_migrations) and a third migration layer — SCRIPTS, one-shot statements recorded by name so each runs once per file — whose first entry backfills every legacy rules row as a guild-scope row with INSERT OR IGNORE. rules.py now exposes get/set/clear/list at scope plus a per-guild version counter bumped by every write (including default seeding and no-op deletes), while get_rules/set_rules keep their signatures and mirror guild-scope writes into the legacy table for one release (D2). RETURNING was deliberately avoided so the deploy target's SQLite version cannot matter.

15 new tests in tests/test_rules.py cover validation, compatibility, per-guild versioning, the backfill, and that a re-run never resurrects legacy text. Suite: 163 passing, ruff clean. Cascades for database and rules resolved: every dependent verified no-change; the callers get their scope wiring in Phases 5 and 6.

### Phase 2 — completed 2026-09-06

channels.py gained ScopeChain (frozen, hashable), ScopeError, and a pure resolve_scope(message) that reads only IDs and flags. Threads are recognised by parent_id and their parent fetched via guild.get_channel — never Thread.parent/.category, which raise on an uncached parent. A None category is normal; a None parent raises (D-010). Forum posts resolve as threads of the forum channel (D3, closes O-03). The pipeline now runs the NSFW probe and resolve_scope inside a fail-closed try — closing the pre-existing gap where a raising channel access escaped INVARIANT-03 — and passes scope= to the analyzer on every call; ai_engine.analyze_message accepts it and ignores it until the composer lands. "skipped" now precedes the channel probe so an empty message never touches a Discord object.

tests/fakes.py gained FakeCategory, FakeThread (a distinct type with only parent_id/is_nsfw, mirroring what real threads safely expose), FakeChannel.category_id, and FakeGuild.get_channel. 13 new tests; suite 176 green, ruff clean.

### Phase 3 — completed 2026-09-06

The safety floor now exists and the NSFW bypass is gone. ai_engine.SAFETY_FLOOR is a code constant (CSAM, animal cruelty, credible violent threats — always severity 4), rendered by render_floor() as its own <floor> region inside the static system turn after the classifier instructions, which state that nothing in <rules> can permit what the floor forbids. It is therefore structurally separate from every mod-authored fragment, sits in the future cacheable prefix, and is unreachable from any table — a test asserts no schema or migration script mentions it. Five adversarial rule texts (including a forged </floor> and a rewritten copy of the floor) all leave exactly one floor region in the payload and no closing tag in the user turn. pipeline.handle_message no longer returns "exempt"; an NSFW-flagged channel resolves like any other (D-007). channels.is_exempt stays for one release, uncalled.

Docs truthed: README, ARCHITECTURE, SECURITY threat model (NSFW injection now in scope, new rule-authorship item), DEPLOYMENT release note for operators, CHANGELOG Unreleased section, ai-engine subsystem body. Suite 184 green, ruff clean.

### Phase 4 — completed 2026-09-06

composer.py turns a ScopeChain plus a guild's fragments into ResolvedRules(text, key). compose_rules is pure and byte-deterministic: fragments render widest-first under fixed labels, whitespace that carries no meaning is normalised, empty fragments are omitted, and key is sha256 of the text — so two channels that inherit the same rules share a key, which is exactly what batching and caching will group on. rules.snapshot(guild_id) is the composer's one read: version plus every fragment in a single connection, seeding DEFAULT_RULES on a cold guild inside that same connection. RulesResolver memoises ScopeChain → (version, ResolvedRules); a miss costs one connection, a hit one version probe, a stale entry both, and any write anywhere in the guild (including a no-op delete or the default seeding) invalidates. 12 new tests; suite 196 green, ruff clean.

Nothing consumes the resolver yet — Phase 6 wires ai_engine.analyze_message to it; Phase 5's /showrules renders the same compose_rules output so moderators see what the model sees.

### Phase 5 — completed 2026-09-06

Moderators can now author scoped rules from Discord. bot.py registers a /rules command group — category, channel, thread, clear, show — Administrator-only by both default permissions and a has_permissions check on every subcommand, guild-only, with targets as channel/category parameters so Discord renders a select and only snowflake IDs reach the database (D1, INVARIANT-05). Logic lives in rulecmds.py as reply-returning handlers: set_reply trims, bounds (4000 chars per scope), stores, and reports the new rules version; clear_reply says whether anything existed; show_reply resolves the same ScopeChain a message would (reusing channels.resolve_scope, with an in_thread flag or a Thread object), composes through compose_rules, and renders floor + text + key prefix inside Discord's 2000-char limit — a test asserts it equals what the classifier's payload would carry. /setrules is untouched.

FakeInteraction gained a permissions property so has_permissions predicates run offline; a parametrised test proves each subcommand rejects a Manage-Messages moderator and accepts an Administrator. 16 new tests; suite 212, ruff clean. README, ARCHITECTURE, CHANGELOG, bot-gateway subsystem body updated; bot-gateway 1.1.0.

### Phase 6 — completed 2026-09-06

The classifier now enforces scoped rules end to end. ai_engine.analyze_message resolves the pipeline's ScopeChain through composer.get_resolver() — memoised, invalidated by the guild's rules version — and passes the composed text as the <rules> block; callers with no scope still get the guild text through rules_loader. classify logs one DEBUG line per call with the ruleset key, rules and message sizes, and the API-reported prompt/completion tokens; config.LOG_LEVEL (validated) enables it and bot.main configures root logging with discord.py's own handler disabled to avoid duplicates. The criterion's "token count per component" is delivered as chars plus API totals — recorded as correction C-01 with the reasoning.

Docs truthed (ARCHITECTURE, DEPLOYMENT env note, CHANGELOG, ai-engine subsystem); ai-engine 0.4.0 pinned to rules ^0.4. Suite 217 green, ruff clean. Post-mortem inputs (ruleset cardinality, token distribution) remain blocked on O-01 — the deployment has to run with LOG_LEVEL=DEBUG before either number exists.

## Accumulated Lessons

_(Numbered sequentially across the whole gameplan. Categorized. Pruned of
obsolete items — mark with "(obsolete)" rather than deleting.)_

### Category: Process

**2.** When a measurement criterion names a unit the system does not natively produce, prefer the unit the system reports for free and record the substitution, rather than adding a dependency whose numbers will not survive the next migration. (promoted 2026-09-06: L-06)

### Category: Environment

**1.** cz_preflight runs bare `pytest -q`, and on this host a uv-tool pytest at /root/.local/bin shadows /usr/local/bin/pytest with a venv that lacks the project's deps, so preflight fails with ModuleNotFoundError while `python -m pytest` passes. Fix at session start: `uv pip install --python /root/.local/share/uv/tools/pytest/bin/python -r requirements.txt -r requirements-dev.txt`. Do not "fix" it by editing the host profile's test command. *(evidence: Phase 0 preflight, 2026-09-06; `which pytest` → /root/.local/bin/pytest)* (promoted 2026-09-06: L-05)

### Category: Design

**3.** Capture the deploy target's runtime versions (here sqlite3.sqlite_version — Amazon Linux 2 ships 3.7, RETURNING needs 3.35) in Source-of-Truth Captures before using any version-gated feature. The dev box's 3.45 hid the risk; it was caught on re-read, not by a test. *(evidence: Phase 1, rules._bump_version rewritten to avoid RETURNING)* (promoted 2026-09-06: L-07)
