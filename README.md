# FargisGuard

AI-assisted trust & safety bot for Discord communities. Every message in a
guild is classified against that guild's own written rules; low-severity
violations are handled immediately and reversibly, and high-severity ones are
**held for a human moderator** — the model never kicks or bans on its own.

## How moderation works

```
message ──▶ resolve scope ──▶ [batch per ruleset, if /batch set] ──▶ classifier (Claude Haiku 4.5)
                                                    │
                       reply "OK" ◀─────────────────┤──▶ VIOLATION|sev|reason
                       (silent)                     │         │
                       anything else ──▶ mod-log    │    escalate by prior warnings
                       ("needs a human")            │         │
                                                    │    1 warn (DM)      ─┐ immediate
                                                    │    2 timeout 15 min ─┘
                                                    │    3 kick ┐ held: 60-min timeout +
                                                    │    4 ban  ┘ pending action → /modaction
```

- **Guild-authored rules.** `/setrules` stores the rules text the classifier
  enforces. Rules are passed to the model as data, not as instructions.
- **Strict verdicts.** Only an exact `VIOLATION|<1-4>|<reason>` line is acted
  on. Anything else the model says is posted to `#mod-logs` for a human and
  nothing happens automatically.
- **Escalation.** Prior warnings raise the effective severity (+1 at 3, +2 at 6,
  capped at 4).
- **Human gate.** Severity 3–4 places the member on a 60-minute timeout and
  records a pending action; a moderator runs `/modaction <id> approve` or
  `deny`.
- **Fail closed.** If the model API or Discord errors mid-pipeline, the message and the
  error go to `#mod-logs`. No silent pass-through.
- **Scoped rules with a floor.** Rules can differ per category, channel, and
  thread; a channel Discord marks NSFW is classified against *its* rules like
  any other. A short operator-owned safety floor (`ai_engine.SAFETY_FLOOR`)
  applies everywhere and cannot be relaxed by any rule text.
- **Immunity.** Administrators, anyone with *Manage Messages*, and the role IDs
  in `IMMUNE_ROLE_IDS` are never auto-moderated.

## Slash commands

| Command | Who | What |
|---|---|---|
| `/appeal <reason>` | everyone | File an appeal (one pending per member). Posts a notice to `#mod-logs`. |
| `/appeals` | Manage Guild | List pending appeals. |
| `/appeal_resolve <id> approve\|deny` | Manage Guild | Approve clears the member's warnings; deny records the decision. |
| `/modaction <id> approve\|deny` | Ban Members | Execute or cancel a held kick/ban. Deny lifts the timeout. |
| `/setrules <text>` | Administrator | Replace the server-wide rules. |
| `/rules category <category> <text>` | Administrator | Rules for every channel in a category, on top of the server rules. |
| `/rules channel <channel> <text>` | Administrator | Rules for one channel, on top of the wider scopes. |
| `/rules thread <channel> <text>` | Administrator | Rules for replies inside that channel's threads. |
| `/rules clear category\|channel\|thread <target>` | Administrator | Remove one scope's rules. |
| `/rules show <channel> [in_thread]` | Administrator | The exact text the classifier enforces there, safety floor included. |
| `/batch set <seconds>` | Administrator | Review messages in batches every N seconds (1–300; 0 = each message on its own, the default). |
| `/batch show` | Administrator | Current interval, size cap, and how many messages are waiting. |

**Batching.** With `/batch set`, messages that share a ruleset are sent to the
classifier together, so the rules and instructions are paid for once per batch
instead of once per message. The trade-off is explicit: a message — even a
severe one — stays visible until its batch is checked. Any verdict of severity
3 or 4 gets a second opinion from a stronger model before the member is held.

Rules are plain sentences ("nudity is fine here, never minors or animal
harm"; "video posts only — replies are plain text"). Narrower scopes add to
wider ones; the safety floor sits above all of them.

Replies are ephemeral. Commands are synced globally on startup; allow up to an
hour for Discord to show them the first time.

## Setup

Requires Python 3.11+.

```bash
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in DISCORD_TOKEN and ANTHROPIC_API_KEY
python bot.py
```

In the [Discord developer portal](https://discord.com/developers/applications)
enable the **Message Content** and **Server Members** privileged intents. Invite
the bot with *Send Messages*, *Manage Messages*, *Moderate Members*, *Kick
Members*, and *Ban Members*, and create a text channel named `mod-logs` (or
whatever `MOD_LOG_CHANNEL` is set to).

### Environment variables

Secrets come only from the environment — `.env` locally, a systemd
`EnvironmentFile` in production. Nothing secret is ever committed.

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `DISCORD_TOKEN` | yes | — | Bot token. Startup fails with a clear error if missing. |
| `ANTHROPIC_API_KEY` | yes | — | Anthropic key for the classifier. (For one release, `OPENAI_API_KEY` alone starts the bot with a warning and every message fails closed.) |
| `DB_PATH` | no | `moderation.db` | SQLite file (created on first use). |
| `MOD_LOG_CHANNEL` | no | `mod-logs` | Text channel that receives notices. |
| `DASHBOARD_TOKEN` | no | *(empty)* | Bearer token for the dashboard. **Empty disables the dashboard.** |
| `DASHBOARD_HOST` | no | `127.0.0.1` | Dashboard bind address. Keep loopback; reverse-proxy for remote access. |
| `DASHBOARD_PORT` | no | `8000` | Dashboard port. |
| `IMMUNE_ROLE_IDS` | no | *(empty)* | Comma-separated role IDs that are never auto-moderated. |

## Dashboard

A read-only JSON API served in-process. It starts only when `DASHBOARD_TOKEN`
is set, listens on loopback by default, and requires the token on every data
route:

```bash
curl -H "Authorization: Bearer $DASHBOARD_TOKEN" http://127.0.0.1:8000/infractions
curl -H "Authorization: Bearer $DASHBOARD_TOKEN" http://127.0.0.1:8000/appeals
curl -H "Authorization: Bearer $DASHBOARD_TOKEN" http://127.0.0.1:8000/pending
curl http://127.0.0.1:8000/health          # no token needed
```

## Development

```bash
pip install -r requirements-dev.txt
pytest          # fully offline: Discord, the model API, and the DB file are faked/isolated
ruff check .
```

Project memory (decisions, invariants, the hardening log, and the gameplan
that produced this version) lives under `docs/` and is maintained with
[Clauderizer](https://github.com/collincusce/Clauderizer). Start with
`docs/ARCHITECTURE.md` and `docs/SECURITY.md`.

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the EC2 + systemd setup,
the `EnvironmentFile` layout, and the SSH key-rotation runbook.

## Stack

Python 3.11 · discord.py 2.3 · Anthropic (`claude-haiku-4-5`, `claude-sonnet-5` re-check) · FastAPI + uvicorn · SQLite
