---
id: subsys.moderation
type: subsystem
version: 0.4.0
status: active
depends_on:
  - subsys.database@^0.4
  - subsys.escalation@^0.1
last_verified: 2026-09-07
external_deps:
  - ext.discord-api
documented_in: docs/ARCHITECTURE.md#moderation
key_files:
  - moderation.py
  - tests/test_moderation.py
  - tests/test_pending.py
---

# Moderation

_(describe.)_

## Batch additions (token-architecture gameplan)

- `punish(..., existing_pending_id=)` — a held-tier verdict for a member who
  already has a pending action from the same batch appends to that action's
  reason (`database.append_pending_reason`) instead of opening a second hold
  (gameplan D3).
- `record_history_only(user_id, guild_id)` — the author left before the batch
  flushed: the warning goes on record, nothing is mutated on Discord.
