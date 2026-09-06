---
id: subsys.bot-gateway
type: subsystem
version: 0.3.1
status: active
depends_on:
  - subsys.pipeline@^0.2
  - subsys.ai-engine@^0.2
  - subsys.moderation@^0.3
  - subsys.rules@^0.2
  - subsys.appeals@^0.2
  - subsys.database@^0.2
  - subsys.dashboard@^0.2
last_verified: 2026-09-06
external_deps:
  - ext.discord-api
documented_in: docs/ARCHITECTURE.md#bot-gateway
key_files:
  - bot.py
  - config.py
---

# Bot Gateway

_(describe.)_
