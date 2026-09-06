---
id: subsys.bot-gateway
type: subsystem
version: 1.1.0
status: active
depends_on:
  - subsys.pipeline@^0.3
  - subsys.ai-engine@^0.3
  - subsys.moderation@^0.3
  - subsys.rules@^0.4
  - subsys.appeals@^0.3
  - subsys.database@^0.3
  - subsys.dashboard@^0.2
  - subsys.channels@^0.2
last_verified: 2026-09-06
external_deps:
  - ext.discord-api
documented_in: docs/ARCHITECTURE.md#bot-gateway
key_files:
  - bot.py
  - config.py
  - rulecmds.py
  - tests/test_bot_wiring.py
  - tests/test_rulecmds.py
---

# Bot Gateway

`bot.py` + `config.py`. `create_bot()` builds the client with narrowed
intents and injected `Deps`; `on_message` delegates to
`pipeline.handle_message`; `setup_hook` syncs the command tree and starts the
dashboard once.

## Slash commands

`/appeal`, `/appeals`, `/appeal_resolve`, `/modaction`, `/setrules`, and the
`/rules` group — `category`, `channel`, `thread`, `clear`, `show`. Every
moderator command carries an `app_commands.checks.has_permissions` check
*and* `default_permissions`; the `/rules` group is Administrator-only and
guild-only (gameplan D1). Targets are channel/category parameters, so Discord
renders a select and the handler only ever sees snowflake IDs.

Handlers with logic live in `rulecmds.py` (`set_reply`, `clear_reply`,
`show_reply`) and `appeals.py`, returning the ephemeral reply text so tests
drive them with `FakeInteraction`-shaped inputs.
