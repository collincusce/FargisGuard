# Chat Handoff Index — Operational Truth: Observability, Durable Queue, Moderator UI

> Last updated: 2026-09-07
> Status: Phase 0 ready

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
| 0 | Bootstrap | ⬜ READY | — | — | handoffs/PHASE-0-HANDOFF.md |
| 1 | Structured logging and no silent returns | ⬜ NOT STARTED | — | — | handoffs/PHASE-1-HANDOFF.md |
| 2 | Token and cost metering | ⬜ NOT STARTED | — | — | handoffs/PHASE-2-HANDOFF.md |
| 3 | Two-tier selfcheck | ⬜ NOT STARTED | — | — | handoffs/PHASE-3-HANDOFF.md |
| 4 | Honest health and authenticated stats | ⬜ NOT STARTED | — | — | handoffs/PHASE-4-HANDOFF.md |
| 5 | Release cleanups | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Durable queue: write-through persistence | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |
| 7 | Durable queue: replay, idempotency, and retention | ⬜ NOT STARTED | — | — | handoffs/PHASE-7-HANDOFF.md |
| 8 | UI read model | ⬜ NOT STARTED | — | — | handoffs/PHASE-8-HANDOFF.md |
| 9 | Moderator identity and delegated authorship | ⬜ NOT STARTED | — | — | handoffs/PHASE-9-HANDOFF.md |
| 10 | UI write model | ⬜ NOT STARTED | — | — | handoffs/PHASE-10-HANDOFF.md |
| 11 | Release readiness | ⬜ NOT STARTED | — | — | handoffs/PHASE-11-HANDOFF.md |

**Status legend**: ⬜ NOT STARTED · 🟢 READY · 🟡 IN PROGRESS · ✅ COMPLETE · ⚠️ BLOCKED · 🔴 FAILED

## Per-Phase Completion Summaries

_(None yet.)_

## Accumulated Lessons

_(Numbered sequentially across the whole gameplan. Categorized. Pruned of
obsolete items — mark with "(obsolete)" rather than deleting.)_

### Category: Process

_(none yet)_
