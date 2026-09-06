# FargisGuard — Architecture

One Python process, two concurrent surfaces (the Discord gateway loop and an
in-process FastAPI dashboard task), one SQLite file. Subsystem entities and
their dependency edges are tracked under `docs/subsystems/` and
`docs/datasources/`; this document is the prose view.

```
Discord gateway ─▶ bot-gateway (bot.py) ─▶ pipeline (pipeline.py)
                        │                    ├─ channels.is_exempt
                        │                    ├─ ai-engine (ai_engine.py) ─▶ OpenAI
                        │                    │      └─ rules (rules.py) ─▶ database
                        │                    ├─ verdict.parse_verdict
                        │                    └─ moderation (moderation.py) ─▶ database
                        │                           └─ escalation.effective_severity
                        ├─ appeals (appeals.py) ─────────────────────────▶ database
                        └─ dashboard (dashboard.py, uvicorn task) ───────▶ database
```

## Subsystems

### bot-gateway
`bot.py` + `config.py`. `create_bot()` builds a `FargisGuard` (a
`commands.Bot`) with narrowed intents and injected `Deps`; `main()` runs it.
`setup_hook` syncs the slash-command tree and starts the dashboard exactly once.
`on_message` delegates to `pipeline.handle_message`. Slash commands: `/appeal`,
`/appeals`, `/appeal_resolve`, `/modaction`, `/setrules` — moderator commands
carry `app_commands` permission checks *and* default permissions.

### pipeline
`pipeline.py`. The per-message flow with every side effect injected through
`Deps(analyze, punish, log, immune_role_ids)`: skip bots/DMs → skip NSFW
channels → skip empty content → classify → `OK` is clean → parse verdict →
punish → delete → log. Analyzer/punisher errors and unparseable replies are
posted to mod-log and take no action (INVARIANT-03).

### ai-engine
`ai_engine.py`. Lazy `AsyncOpenAI` (15 s timeout). Static system prompt; the
guild's rules and the message are `<rules>`/`<message>` data in the user turn
with closing tags neutralized. Reply is either `OK` or a verdict line.

### verdict
`verdict.py`. `parse_verdict(text) -> Verdict | None` — exact
`VIOLATION|1..4|reason`, nothing else; never clamps.

### escalation
`escalation.py`. `effective_severity(model_severity, prior_warnings)` — pure
ladder: +1 at 3 priors, +2 at 6, capped at 4.

### moderation
`moderation.py`. `punish()` applies warn (DM) and timeout immediately; kick and
ban become a 60-minute hold plus a `pending_actions` row for `/modaction`.
`resolve_pending_action()` executes or lifts. Immunity: administrator,
manage_messages, or `IMMUNE_ROLE_IDS`.

### rules
`rules.py`. Per-guild rules text with a default; read by ai-engine, written by
`/setrules`.

### appeals
`appeals.py`. One pending appeal per member per guild; `/appeal` notifies
mod-log; `/appeal_resolve approve` clears warnings via `database.forgive`.

### dashboard
`dashboard.py`. `create_app(token)` — refuses an empty token; bearer auth on
`/infractions`, `/appeals`, `/pending`; `/health` open. `start_dashboard()`
returns `None` without a token, else one asyncio task running `uvicorn.Server`.

### database
`database.py`. `connect()` context manager, one connection per call, `DB_PATH`
from the environment, lazy schema creation and column migrations. Tables:
`warnings`, `rules`, `appeals`, `pending_actions`.

## External services

- **Discord API** (`discord.py` 2.3.2) — gateway events, message deletion,
  member timeout/kick/ban, application commands. Requires the *Message
  Content* and *Server Members* privileged intents.
- **OpenAI API** (`openai` 2.x) — chat completions, `gpt-4o-mini`.

## Runtime

AWS EC2 under systemd with secrets in an `EnvironmentFile`
(`docs/DEPLOYMENT.md`). The dashboard is loopback-only by default.
