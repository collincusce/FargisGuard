# FargisGuard — Architecture

One Python process, two concurrent surfaces (the Discord gateway loop and a
FastAPI dashboard), one SQLite file. Subsystem entities and their dependency
edges are tracked under `docs/subsystems/` and `docs/datasources/`; this document
is the prose view.

```
Discord gateway ──▶ bot-gateway (bot.py) ──▶ ai-engine (ai_engine.py) ──▶ OpenAI
                        │                          │
                        │                          └── rules (rules.py) ──▶ database
                        ├──▶ moderation (moderation.py) ──▶ database
                        ├──▶ appeals (appeals.py) ──────────▶ database
                        └──▶ dashboard (dashboard.py) ──────▶ database
```

## Subsystems

### bot-gateway
`bot.py` + `config.py`. Owns the `discord.py` client, the `on_message` pipeline
(skip bots/DMs → NSFW exemption → analyze → act → log) and the slash commands
`/appeal` and `/setrules`. Everything else is called from here.

### ai-engine
`ai_engine.py`. Builds the moderation prompt from the guild's rules and asks
OpenAI for a verdict. The verdict protocol is a text line
`VIOLATION|<severity>|<reason>`; parsing and validating it is the
security-critical seam (see INVARIANT-02).

### moderation
`moderation.py`. Maps a validated severity to a Discord action and records a
warning. Immunity for privileged members lives here.

### rules
`rules.py`. Per-guild rules text with a default; read by ai-engine, written by
`/setrules`.

### appeals
`appeals.py`. Appeal submission; resolution lands here as the workflow is built
out.

### dashboard
`dashboard.py`. FastAPI read-only views over warnings and appeals, served in
process by uvicorn.

### database
`database.py`. SQLite schema (`warnings`, `rules`, `appeals`) and the
warning-count helpers.

## External services

- **Discord API** (`discord.py` 2.3.2) — gateway events, message deletion,
  member timeout/kick/ban, application commands. Requires the *message content*
  privileged intent.
- **OpenAI API** (`openai` 1.10.0) — chat completions, `gpt-4o-mini`.

## Runtime

Hosted on AWS EC2 under systemd; secrets via environment. The dashboard must
never be reachable unauthenticated from the internet (H-04).
