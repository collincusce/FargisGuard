---
id: subsys.bot-gateway
type: subsystem
version: 0.1.1
status: active
depends_on:
  - subsys.ai-engine@^0.1
  - subsys.moderation@^0.1
  - subsys.rules@^0.1
  - subsys.appeals@^0.1
  - subsys.dashboard@^0.1
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
