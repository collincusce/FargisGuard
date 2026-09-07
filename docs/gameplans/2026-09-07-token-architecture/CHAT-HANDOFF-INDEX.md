# Chat Handoff Index — token-architecture

> Last updated: 2026-09-07
> Status: Phase 1 of 7 in progress

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
| 1 | Batch verdict protocol | 🟡 IN PROGRESS | 2026-09-07 | — | handoffs/PHASE-1-HANDOFF.md |
| 2 | Anthropic engine | ⬜ NOT STARTED | — | — | handoffs/PHASE-2-HANDOFF.md |
| 3 | Batch queue | ⬜ NOT STARTED | — | — | handoffs/PHASE-3-HANDOFF.md |
| 4 | Batch settings and commands | ⬜ NOT STARTED | — | — | handoffs/PHASE-4-HANDOFF.md |
| 5 | Escalation re-check tier | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Release readiness | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |

**Status legend**: ⬜ NOT STARTED · 🟢 READY · 🟡 IN PROGRESS · ✅ COMPLETE · ⚠️ BLOCKED · 🔴 FAILED

## Per-Phase Completion Summaries

### Phase 0 — completed 2026-09-07

Planned from three lenses (batching failure modes, Anthropic API/caching/cost against the bundled reference, ops/config/testing). The decisive finding: prompt caching cannot fire on Haiku 4.5 — its minimum cacheable prefix is 4096 tokens against our ~350–1100 — so D-014 defers caching and batching carries the whole cost win (~65% by the lens estimate). Recorded D-011 (Anthropic Haiku 4.5 + Sonnet 5 re-check), D-012 (strict batching per (guild, key), interval 0 = per-message, hard cap), D-013 (structured per-id verdicts, supersedes D-001), INVARIANT-06 (provider-neutral offline tests), gameplan decisions D1–D5, and open items O-01..O-04 (durable queue, unconfirmed pricing, no live verification, carried baseline). Six phases laid out with machine-checkable criteria.

Fresh-venv proof: anthropic 1.4.0 installs beside openai 2.54.0 and fastapi 0.141.1 (httpx and httpx2 coexist), pip check clean, 217 passing. Plan committed as 718addd.

## Accumulated Lessons

_(Numbered sequentially across the whole gameplan. Categorized. Pruned of
obsolete items — mark with "(obsolete)" rather than deleting.)_

### Category: Process

_(none yet)_
