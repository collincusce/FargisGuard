---
id: subsys.bot-gateway
type: subsystem
version: 1.4.0
status: active
depends_on:
  - subsys.pipeline@^0.6
  - subsys.ai-engine@^0.6
  - subsys.moderation@^0.4
  - subsys.rules@^0.4
  - subsys.appeals@^0.3
  - subsys.database@^0.5
  - subsys.dashboard@^0.2
  - subsys.channels@^0.2
  - subsys.batcher@^0.2
last_verified: 2026-09-07
external_deps:
  - ext.discord-api
documented_in: docs/ARCHITECTURE.md#bot-gateway
key_files:
  - bot.py
  - config.py
  - rulecmds.py
  - tests/test_bot_wiring.py
  - tests/test_rulecmds.py
  - tests/test_batchsettings.py
---

# Bot Gateway

`bot.py` + `config.py`. `create_bot()` builds the client with narrowed
intents and injected `Deps`; `on_message` delegates to
`pipeline.handle_message`; `setup_hook` syncs the command tree and starts the
dashboard once.

## Slash commands

`/appeal`, `/appeals`, `/appeal_resolve`, `/modaction`, `/setrules`, and the
`/rules` group — `category`, `channel`, `thread`, `clear`, `show` — and the
`/batch` group — `set <seconds>`, `show` (queue depth + exposure note). Every
moderator command carries an `app_commands.checks.has_permissions` check
*and* `default_permissions`; the `/rules` and `/batch` groups are
Administrator-only and guild-only (scoped-rules D1, token-architecture D5). Targets are channel/category parameters, so Discord
renders a select and the handler only ever sees snowflake IDs.

Handlers with logic live in `rulecmds.py` (`set_reply`, `clear_reply`,
`show_reply`) and `appeals.py`, returning the ephemeral reply text so tests
drive them with `FakeInteraction`-shaped inputs.

`FargisGuard.__init__` builds the `Batcher` (classifier = `ai_engine.classify_batch`,
apply = `pipeline.apply_outcome`, guild lookup = `get_guild`) and `close()` drains
it under `SHUTDOWN_FLUSH_SECONDS` before the gateway closes (token-architecture D2).
`create_bot` wires `interval_for=batchsettings.get_batch_interval`.
