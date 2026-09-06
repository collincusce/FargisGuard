# Scoped Moderation Rules — Phase Status Tracker

> Living document. Updated after each phase completes.
> Last updated: 2026-09-06

## Phase Status

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Scoped rules schema | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-1-HANDOFF.md |
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

### Phase 1 Outputs

```
test_count_after_phase_1: 163 passed (148 baseline + 15 in tests/test_rules.py); ruff check clean
rules_api: rules.py: constants GUILD/CATEGORY/CHANNEL/THREAD, GUILD_SCOPE_ID=0; validate_scope, get_scope_rules, set_scope_rules (returns new version), clear_scope_rules (bool), list_scope_rules (ordered by kind,id), get_rules_version; get_rules/set_rules unchanged signatures, guild-scope, mirror to legacy `rules` table (D2)
migration_script: database.SCRIPTS entry "2026-09-06-backfill-scoped-rules" — INSERT OR IGNORE legacy rules rows into scoped_rules as (guild, 0); recorded in schema_migrations; thread scope_id = parent channel id; no RETURNING clause used (SQLite <3.35 safe)
```

## Corrections Log

_(Every divergence from the gameplan, captured in real time, as C-NN entries.)_
