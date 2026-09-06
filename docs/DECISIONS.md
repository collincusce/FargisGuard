# Decisions

Project-wide architectural decision records (ADRs). Append-only. Numbered `D-NNN`.
Each entry carries a `**Status**` (`active` | `superseded` | `deprecated`). When a
decision supersedes another, the predecessor stays in the record — annotated in place
with a `**Superseded by**: D-NNN` back-ref and `**Status**: superseded` — so the
lifecycle is navigable and the current decision is the one that surfaces.

## Decisions

_(Add entries with `cz_add_decision`.)_

### D-001 — LLM classifier emits a pipe-delimited verdict per message

**Context**: Every non-bot guild message is sent to OpenAI chat completions with the guild's rules in the system prompt (ai_engine.py). The model is instructed to answer exactly VIOLATION|<severity 1-4>|<reason> on a violation.
**Decision**: Use gpt-4o-mini as the per-message moderation classifier with a text verdict protocol parsed by bot.py.
**Consequences**: Moderation quality and safety are bounded by prompt adherence; the verdict must be parsed defensively and must not be treated as sole authority for irreversible actions (see H-NN findings).
**Evidence**: ai_engine.py, bot.py
**Status**: active (2026-09-06)

### D-002 — SQLite single-file store for warnings, rules, and appeals

**Context**: The bot runs as one process on one EC2 host (README). database.py opens moderation.db with check_same_thread=False and creates three tables.
**Decision**: Persist all moderation state in a local SQLite file; *.db is gitignored.
**Consequences**: No external DB dependency; concurrency must be handled by the app (one process, but two threads: bot loop + dashboard).
**Evidence**: database.py, .gitignore, README.md
**Status**: active (2026-09-06)

### D-003 — Severity ladder maps 1..4 to warn, timeout, kick, ban

**Context**: moderation.py maps the model's severity integer to a Discord action and increments the user's warning count.
**Decision**: Severity 1=DM warning, 2=15-minute timeout, 3=kick, 4=ban; Admin/Moderator roles are immune.
**Consequences**: Severity 3 and 4 are irreversible from the user's side; who may trigger them and how they are reviewed is a security-critical question.
**Evidence**: moderation.py, config.py
**Status**: active (2026-09-06)

### D-004 — NSFW content is isolated to a dedicated channel that bypasses AI moderation

**Context**: README lists human-supervised NSFW isolation; bot.py skips AI analysis entirely for the channel named in NSFW_CHANNEL_NAME.
**Decision**: One designated NSFW channel is exempt from the AI pipeline and relies on human moderation.
**Consequences**: The exemption test must be robust (Discord's channel NSFW flag, not a name string) or it becomes a moderation bypass.
**Evidence**: bot.py, config.py, README.md
**Status**: active (2026-09-06)

### D-005 — Runtime secrets come from .env via python-dotenv

**Context**: config.py loads DISCORD_TOKEN and OPENAI_API_KEY from the environment; .env is gitignored; README says environment-based secrets.
**Decision**: All credentials are read from the environment at startup, never from source.
**Consequences**: config must fail fast when a required variable is absent; any credential found in the tree is a policy violation.
**Evidence**: config.py, .gitignore, README.md
**Status**: active (2026-09-06)

### D-006 — FastAPI moderation dashboard runs in-process beside the bot

**Context**: dashboard.py defines /infractions and /appeals; bot.py starts uvicorn in a thread from on_ready.
**Decision**: Serve the read-only dashboard from the same process on DASHBOARD_PORT.
**Consequences**: Shares the SQLite connection with the bot loop; must be started exactly once and must not be reachable unauthenticated from the internet.
**Evidence**: dashboard.py, bot.py, config.py
**Status**: active (2026-09-06)
