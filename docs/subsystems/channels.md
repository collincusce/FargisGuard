---
id: subsys.channels
type: subsystem
version: 0.2.0
status: active
last_verified: 2026-09-06
documented_in: docs/ARCHITECTURE.md#channels
key_files:
  - channels.py
  - tests/test_channels.py
---

# Channels

Where a message lives, read from Discord IDs and flags only (INVARIANT-05).

- `is_exempt(channel)` — the NSFW flag via `is_nsfw()`; threads report their
  parent's. Retired from the pipeline in Phase 3 (D-007), kept for one release.
- `ScopeChain(guild_id, category_id | None, channel_id, in_thread)` — frozen and
  hashable; the composer memoises on it. For a thread, `channel_id` is the
  **parent** channel, so thread scope keys on the channel that owns the threads.
- `resolve_scope(message)` — pure. A thread is recognised by `parent_id`
  (only `discord.Thread` has it in 2.3.2); its parent is fetched with
  `guild.get_channel(parent_id)`, never `Thread.parent`/`.category`, which raise
  on an uncached parent. `None` category is normal; a `None` parent is a
  dangling reference and raises `ScopeError` (D-010). Forum posts are threads of
  the forum channel (D3).

The pipeline calls `is_exempt` and `resolve_scope` inside its fail-closed
boundary, so any exception here becomes a mod-log notice, not a crash and not a
silent guild-scope fallback.
