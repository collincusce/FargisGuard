---
id: subsys.rules
type: subsystem
version: 0.3.0
status: active
depends_on:
  - subsys.database@^0.3
last_verified: 2026-09-06
documented_in: docs/ARCHITECTURE.md#rules
key_files:
  - rules.py
  - tests/test_rules.py
---

# Rules

The text the classifier is asked to enforce, authored per guild at four scopes
(D-009): `guild` (scope_id 0), `category`, `channel`, and `thread` — the last
keyed by the *parent channel's* id, because Discord has no nested threads.
Keys are snowflake IDs, never names (INVARIANT-05).

## API (`rules.py`)

- `get_rules(guild_id) -> str` / `set_rules(guild_id, content)` — the guild
  scope, unchanged signatures; `get_rules` seeds `DEFAULT_RULES` on a cold
  guild. These are what `ai_engine.analyze_message` and `/setrules` use.
- `get_scope_rules` / `set_scope_rules` / `clear_scope_rules` — one scope row.
  `validate_scope` rejects unknown kinds, non-int ids, a non-zero guild id, or
  a non-positive id for the other kinds.
- `list_scope_rules(guild_id)` — every fragment for a guild in a stable order;
  the composer (Phase 4) reads this once per uncached scope chain.
- `get_rules_version(guild_id)` — bumped by **every** write, including the
  default seeding and a delete of a missing row, so a memo keyed on it can
  never serve stale text.

## Compatibility bridge (D2)

Guild-scope writes are mirrored into the legacy `rules` table for one release,
so reverting to pre-scope code reads current text. Drop the mirror and the
table together in the release after this gameplan ships.

## Not here

Composition, the safety floor, and scope *resolution* from a Discord message
belong to later phases (composer, ai-engine, channels).
