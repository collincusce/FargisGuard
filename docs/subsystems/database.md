---
id: subsys.database
type: subsystem
version: 0.5.0
status: active
last_verified: 2026-09-07
documented_in: docs/ARCHITECTURE.md#database
key_files:
  - database.py
  - tests/test_database.py
---

# Database

SQLite, one short-lived connection per call (`connect()`), schema applied
lazily per path on first open. No module-level connection (H-08).

## Tables

`warnings`, `rules` (legacy guild text, mirrored for one release — D2),
`scoped_rules` (guild_id, scope_kind, scope_id, content; PK on all three),
`rules_version` (per-guild write counter), `appeals`, `pending_actions`
(`append_pending_reason` extends a still-pending row's reason — batch collapse, D3), and
`schema_migrations` (names of one-shot scripts already applied).

## Migration layers (`init_db`)

1. `SCHEMA` — `CREATE TABLE IF NOT EXISTS`, always safe.
2. `MIGRATIONS` — `(table, column, decl)` tuples; `_ensure_column` adds what
   is missing.
3. `SCRIPTS` — `(name, sql)` one-shot data moves recorded in
   `schema_migrations` so each runs exactly once per file. The first is the
   2026-09-06 backfill of `rules` rows into `scoped_rules` as guild scope
   (`INSERT OR IGNORE`, so a scoped edit made after migration is never
   overwritten by a re-run).

SQLite has no transactional DDL rollback across `executescript`; the deploy
runbook backs the file up before every restart for that reason.
