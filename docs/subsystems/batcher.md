---
id: subsys.batcher
type: subsystem
version: 0.2.0
status: active
depends_on:
  - subsys.rules@^0.4
  - subsys.verdict@^0.2
  - subsys.database@^0.5
last_verified: 2026-09-07
key_files:
  - batcher.py
  - batchsettings.py
  - snapshots.py
  - tests/test_batcher.py
  - tests/test_batchsettings.py
documented_in: docs/ARCHITECTURE.md#batcher
---

# Batcher

`batcher.py` — the token-architecture core (D-012). Messages are queued per
`(guild_id, ResolvedRules.key)` and classified in one request per bucket.

- `Bucket` freezes the `ResolvedRules` it was opened with and holds
  `MessageSnapshot` values (gameplan D1) — never live Discord objects.
- `Batcher.enqueue(snapshot, rules, interval)` is synchronous: no await
  between reading and mutating the bucket, so a flush cannot interleave. A new
  bucket starts a per-bucket timer (`spawn(sleep(interval))`); hitting
  `max_messages` (`BATCH_MAX_MESSAGES`, 25) flushes at once and cancels it.
- A flush is swap-and-clear: the bucket leaves the map, the next enqueue opens
  a new generation, so nothing is lost or classified twice.
- `_run` sorts snapshots by message id (D3), calls `classify(rules.text,
  contents, ruleset_key=)`, then `apply(snapshot, outcome, guild, held=)` per
  message; the `held` map lets a member's second held-tier verdict join the
  first pending action. One apply failure is posted and the rest continue. A
  classifier or transport failure posts ONE consolidated notice with the
  message links and punishes nobody (INVARIANT-03).
- `shutdown(deadline)` flushes every bucket, waits, cancels stragglers, and
  posts an "unreviewed — shutdown" notice per bucket that did not finish
  (gameplan D2). `FargisGuard.close()` calls it before the gateway closes.
- `clock`, `sleep`, `spawn` are injected; tests park timers on futures and
  release them explicitly (INVARIANT-06).

The queue is in-memory: a hard crash loses it (open item O-01 of the
token-architecture gameplan).

## Settings (`batchsettings.py`, gameplan D5)

`batch_settings(guild_id PK, interval_seconds)`; `get_batch_interval` returns 0
for an unknown guild and is read on every enqueue, so `/batch set` takes
effect on the next message with no restart. `set_batch_interval` clamps to
`0..BATCH_MAX_SECONDS` (300) and rejects non-integers before any write. The
`/batch set <seconds>` and `/batch show` replies come from `set_reply` /
`show_reply`; `show` includes the queue depth and the exposure-window sentence
from D-012.
