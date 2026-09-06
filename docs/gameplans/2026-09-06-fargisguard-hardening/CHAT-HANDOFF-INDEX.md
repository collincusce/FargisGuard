# Chat Handoff Index — FargisGuard Hardening

> Last updated: 2026-09-06
> Status: Phase 1 of 8 in progress

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
| 0 | Bootstrap: dev tooling and secrets hygiene | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Verdict parsing and punishment correctness | 🟡 IN PROGRESS | 2026-09-06 | — | handoffs/PHASE-1-HANDOFF.md |
| 2 | Gateway access control and channel checks | ⬜ NOT STARTED | — | — | handoffs/PHASE-2-HANDOFF.md |
| 3 | Async, fail-closed AI path | ⬜ NOT STARTED | — | — | handoffs/PHASE-3-HANDOFF.md |
| 4 | Human-in-the-loop for high severity and warning escalation | ⬜ NOT STARTED | — | — | handoffs/PHASE-4-HANDOFF.md |
| 5 | Dashboard and database safety | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Appeals workflow | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |
| 7 | Docs truth-up and deploy hygiene | ⬜ NOT STARTED | — | — | handoffs/PHASE-7-HANDOFF.md |

**Status legend**: ⬜ NOT STARTED · 🟢 READY · 🟡 IN PROGRESS · ✅ COMPLETE · ⚠️ BLOCKED · 🔴 FAILED

## Per-Phase Completion Summaries

### Phase 0 — completed 2026-09-06

Removed FargisGuard.pem from HEAD and made secrets hygiene structural: *.pem, *.key, .env.* gitignored (with .env.example whitelisted), a documented .env.example, and config.py that fails at import naming the missing variable via a pure require_env. Stood up pytest (pythonpath=['.'] for the flat layout, asyncio_mode=auto) and ruff (E/F/W/I/B/UP), fixed the six pre-existing import-order findings with ruff --fix (imports only, no behavior change), and landed the first 7 tests. The tests pre-flight check was downgraded to advisory for this phase only (C-01) and is restored to blocking here.

What I did not check: the EC2 host itself (its Python version, whether the old key is still in authorized_keys, whether systemd passes the env the way .env does locally); the git history, which still contains the key (O-01, O-02 are owner actions); that load_dotenv does not shadow a systemd EnvironmentFile in production.

## Accumulated Lessons

_(Numbered sequentially across the whole gameplan. Categorized. Pruned of
obsolete items — mark with "(obsolete)" rather than deleting.)_

### Category: Process

**1.** A bootstrap phase on a test-less repo needs the tests pre-flight check downgraded to advisory for that one phase; restore it in the same phase's ending protocol.

### Category: Testing

**2.** Flat-layout Python repos (modules at the root) need pythonpath=['.'] in [tool.pytest.ini_options] or test modules cannot import them; and any test that importlib.reload()s a module must catch a base exception class, because reload mints new class objects that no longer match the names imported before the reload. *(evidence: Phase 0: ModuleNotFoundError on import config, then two reload tests failing on class identity)*
