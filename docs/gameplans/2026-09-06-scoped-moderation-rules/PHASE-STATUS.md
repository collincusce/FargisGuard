# Scoped Moderation Rules — Phase Status Tracker

> Living document. Updated after each phase completes.
> Last updated: 2026-09-06

## Phase Status

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Scoped rules schema | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-1-HANDOFF.md |
| 2 | Scope resolver | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-2-HANDOFF.md |
| 3 | Safety floor and NSFW supersession | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-3-HANDOFF.md |
| 4 | Composer and resolved-ruleset key | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-4-HANDOFF.md |
| 5 | Authoring commands | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-5-HANDOFF.md |
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

### Phase 2 Outputs

```
test_count_after_phase_2: 176 passed (163 + 8 resolver tests in test_channels.py + 5 pipeline boundary tests); ruff clean
analyzer_contract: Deps.analyze is now `async (content, guild_id, *, scope: channels.ScopeChain) -> str`; pipeline passes scope on every call; ai_engine.analyze_message accepts scope=None and ignores it until Phase 6. ScopeChain(guild_id, category_id|None, channel_id, in_thread) — channel_id is the PARENT for threads.
```

### Phase 3 Outputs

```
test_count_after_phase_3: 184 passed (176 + 8 floor tests); ruff clean
floor_location: ai_engine.SAFETY_FLOOR (code constant: CSAM, animal cruelty, credible violent threats → always severity 4); rendered by render_floor() as <floor>…</floor> inside the STATIC system turn after CLASSIFIER_INSTRUCTIONS; SYSTEM_PROMPT = instructions + floor region. User turn is <rules> + <message>, tags neutralized so </floor> cannot be forged. pipeline no longer returns "exempt"; channels.is_exempt kept but unused (drop with legacy rules table).
```

### Phase 4 Outputs

```
test_count_after_phase_4: 196 passed (184 + 12 in tests/test_composer.py); ruff clean
composer_api: composer.py: compose_rules(chain, fragments) -> ResolvedRules(text, key=sha256); scope_keys(chain); RulesResolver(snapshot=rules.snapshot, version=rules.get_rules_version).resolve(chain) memoised by (ScopeChain -> version); get_resolver() process-wide. rules.snapshot(guild_id) -> (version, fragments) in ONE connection, seeds DEFAULT_RULES on cold guild. Render labels: '## Server rules' / '## Category rules (...)' / '## Channel rules (...)' / '## Thread rules (...)'.
```

### Phase 5 Outputs

```
test_count_after_phase_5: 212 passed (196 + 16 in tests/test_rulecmds.py); ruff clean
rules_commands: /rules group (Administrator default perms + has_permissions check on each, guild_only): category <CategoryChannel> <text>; channel <Text|Forum|Voice> <text>; thread <Text|Forum> <text> (keyed by parent id); clear <category|channel|thread> <GuildChannel>; show <Text|Forum|Voice|Thread> [in_thread]. Handlers in rulecmds.py: set_reply / clear_reply / show_reply / chain_for. Per-scope text capped at 4000 chars; show truncates to fit 2000. FakeInteraction.permissions added so has_permissions predicates run offline.
```

## Corrections Log

_(Every divergence from the gameplan, captured in real time, as C-NN entries.)_
