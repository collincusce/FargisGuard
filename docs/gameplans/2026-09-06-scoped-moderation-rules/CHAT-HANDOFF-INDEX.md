# Chat Handoff Index — Scoped Moderation Rules

> Last updated: 2026-09-06
> Status: Phase 4 ready

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
| 4 | Composer and resolved-ruleset key | ⬜ NOT STARTED | — | — | handoffs/PHASE-4-HANDOFF.md |
| 5 | Authoring commands | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Wire-through and measurement | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |

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

## Accumulated Lessons

_(Numbered sequentially across the whole gameplan. Categorized. Pruned of
obsolete items — mark with "(obsolete)" rather than deleting.)_

### Category: Process

### Category: Environment

**1.** cz_preflight runs bare `pytest -q`, and on this host a uv-tool pytest at /root/.local/bin shadows /usr/local/bin/pytest with a venv that lacks the project's deps, so preflight fails with ModuleNotFoundError while `python -m pytest` passes. Fix at session start: `uv pip install --python /root/.local/share/uv/tools/pytest/bin/python -r requirements.txt -r requirements-dev.txt`. Do not "fix" it by editing the host profile's test command. *(evidence: Phase 0 preflight, 2026-09-06; `which pytest` → /root/.local/bin/pytest)*
