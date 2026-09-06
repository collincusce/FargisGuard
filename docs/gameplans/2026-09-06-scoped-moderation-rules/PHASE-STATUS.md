# Scoped Moderation Rules — Phase Status Tracker

> Living document. Updated after each phase completes.
> Last updated: 2026-09-06

## Phase Status

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Scoped rules schema | ⬜ NOT STARTED | — | — | handoffs/PHASE-1-HANDOFF.md |
| 2 | Scope resolver | ⬜ NOT STARTED | — | — | handoffs/PHASE-2-HANDOFF.md |
| 3 | Safety floor and NSFW supersession | ⬜ NOT STARTED | — | — | handoffs/PHASE-3-HANDOFF.md |
| 4 | Composer and resolved-ruleset key | ⬜ NOT STARTED | — | — | handoffs/PHASE-4-HANDOFF.md |
| 5 | Authoring commands | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Wire-through and measurement | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |

## Outputs Registry

### Phase 0 Outputs

```
baseline_tests: 148 passed (pytest -q, Python 3.11.15, discord.py 2.3.2, openai 2.54.0)
o01_status: DEFERRED — operator has not yet supplied `journalctl -u fargisguard` output; live OpenAI project shows 0 requests / 30d. Phase 6 token-distribution criterion is blocked until resolved. Do not treat "token usage is high" as measured.
```

## Corrections Log

_(Every divergence from the gameplan, captured in real time, as C-NN entries.)_
