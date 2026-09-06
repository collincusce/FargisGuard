# FargisGuard Hardening Gameplan

> Created: 2026-09-06
> Status: Executing
<!-- Optional, advisory-only (D-072) — declare to arm the wind-down advisory:
     "> Budget: N sessions" here, and/or "**Budget**: N sessions" inside a
     "### Phase N" block. Dormant by default; nothing blocks, ever. -->
> Kind: driven
> Procedure: docs/gameplans/GAMEPLAN-PROCEDURE.md

## Project Overview

FargisGuard shipped as a prototype whose README promised human-supervised AI
moderation, escalation, and appeals, while the code auto-banned on raw model
output, exposed its rules prompt to every guild member, crashed on timeouts,
and committed the EC2 private key. This gameplan closes every finding in
`docs/HARDENING.md` (H-01..H-12) without changing the product's shape: same
subsystems, same SQLite store, same single process — but with the model
demoted to an advisor, a moderator holding the kick/ban button, an offline
test suite covering each fix, and a README that claims only what exists.

Work is ordered by dependency, not narrative: tooling first (so every later
phase has a green pre-flight), then the pure verdict/punishment core, then the
gateway surface that calls it, then the async/fail-closed pipeline, then the
human gate that the pipeline hands off to, then storage/dashboard, appeals,
and docs last.

## Subsystems Touched

- `subsys.bot-gateway` — every phase from 2 on (importable factory, permission checks, pipeline orchestration, new commands)
- `subsys.ai-engine` — Phase 3 (async client, delimited prompt)
- `subsys.moderation` — Phases 1, 4 (parser consumer, explicit severity map, pending actions, escalation)
- `subsys.database` — Phases 4, 5, 6 (pending_actions table, per-call connections, appeal status columns)
- `subsys.dashboard` — Phase 5 (loopback + bearer token, single start)
- `subsys.appeals` — Phase 6 (dedupe, notify, resolve)
- `subsys.rules` — Phase 5 (connect() migration only)
- `ext.discord-api`, `ext.openai-api` — unchanged providers; call sites change

## Source-of-Truth Captures

Captured 2026-09-06 in the planning sandbox (not the EC2 host — its Python
version and installed packages were not observed).

| Value | Captured |
|---|---|
| Baseline test count | **0** (no `tests/` directory existed) |
| Python (sandbox) | 3.11.15 |
| discord.py | 2.3.2 (pinned in requirements.txt) |
| openai | 1.10.0 (pinned) |
| fastapi / uvicorn | 0.110.0 / 0.29.0 (pinned) |
| ruff (dev) | 0.16.6 |
| Repo | `collincusce/FargisGuard`, public, `fork: true`, push access confirmed via GitHub API |
| Branch | `claude/friends-project-analysis-p8bpa0` (no upstream yet) |
| Committed key | `FargisGuard.pem`: RSA 2048-bit, parses, public half derives cleanly; in commit `55ceedd` |
| `/setrules` checks | `bot.tree.get_command('setrules').checks == []`, `default_permissions is None` (verified on discord.py 2.3.2) |
| `discord.timedelta` | `hasattr(discord, 'timedelta') is False` (verified) |

## Amendments

_(None yet. Append A-NNN entries here once Phase 0 starts.)_

## Decisions

### D1 — Invalid verdicts are rejected, never clamped

**Context**: The model can emit VIOLATION|9|x, VIOLATION|abc|x, or a truncated line. Clamping 9 to 4 turns a hallucination into a ban.
**Decision**: parse_verdict returns None for anything that is not exactly VIOLATION|<int 1..4>|<non-empty reason>; a None verdict takes no action and is posted to mod-log as an unparseable reply.
**Consequences**: Some true violations with malformed replies are not auto-actioned; humans see them instead. INVARIANT-02 and INVARIANT-03 both satisfied.
**Status**: active (2026-09-06)

### D2 — Severity 3 and 4 become pending actions that a moderator approves

**Context**: Kick and ban are irreversible from the member's side and the classifier is prompt-injectable (H-03).
**Decision**: on_message never calls kick or ban. Severity>=3 deletes the message, applies a timeout hold, stores a pending_actions row, and posts to mod-log; /modaction <id> approve|deny (requires ban_members) executes or lifts it.
**Consequences**: Adds a table, a command, and a moderator step; delivers the human oversight the README already promised.
**Status**: active (2026-09-06)

### D3 — Dashboard requires DASHBOARD_TOKEN and binds loopback by default

**Context**: H-04: 0.0.0.0 with no auth exposes personal data.
**Decision**: DASHBOARD_HOST defaults to 127.0.0.1; every route requires Authorization: Bearer <DASHBOARD_TOKEN>; if the token is unset the dashboard is not started at all and a warning is logged.
**Consequences**: Remote access needs a reverse proxy or an explicit host override; fail-closed by construction.
**Status**: active (2026-09-06)

### D4 — Per-call SQLite connections with DB_PATH from the environment

**Context**: H-08: a module-level cursor shared by the bot loop and the dashboard thread.
**Decision**: database.connect() is a context manager opening a fresh connection per call; DB_PATH env var (default moderation.db) so tests use a temp file.
**Consequences**: Slight per-call overhead, irrelevant at this scale; thread-safe and test-isolated.
**Status**: active (2026-09-06)

### D5 — bot.py becomes importable: create_bot() factory plus a __main__ guard

**Context**: bot.run() at module import makes the command tree untestable and any import connect to Discord.
**Decision**: All wiring lives in create_bot(); running is behind if __name__ == '__main__'. The message pipeline is a handle_message(message, deps) function with injected analyze/punish/log callables.
**Consequences**: Tests inspect the real command tree and drive the pipeline with fakes (INVARIANT-04).
**Status**: active (2026-09-06)

### D6 — Guild rules are passed as delimited data in the user turn; the system prompt is static

**Context**: H-03: rules text is interpolated into the system prompt, so /setrules is a system-prompt injection channel.
**Decision**: build_messages(rules, content) emits a fixed system prompt and one user turn containing <rules>...</rules> and <message>...</message>.
**Consequences**: Does not eliminate injection (nothing does) but removes the privileged channel; combined with D2 the blast radius is a timeout, not a ban.
**Status**: active (2026-09-06)

### D7 — The committed private key is removed from HEAD only; history scrub is the owner's call

**Context**: H-01. git filter-repo rewrites main and needs a force push to the fork; that is a destructive action on the owner's history.
**Decision**: Phase 0 deletes FargisGuard.pem from the tree and gitignores *.pem; rotation and history rewrite are tracked as open items for the owner.
**Consequences**: The key stays recoverable from history until the owner scrubs; rotation at AWS is what actually closes the exposure.
**Status**: active (2026-09-06)

## Open Items

**O-01.** _(phase 0)_ Rotate the EC2 keypair: create a new keypair, add its public key to ~/.ssh/authorized_keys on the instance, verify login, remove the old public key, delete the old keypair in the EC2 console. Cannot be done from the repo — owner action. (H-01)

**O-02.** _(phase 0)_ Scrub FargisGuard.pem from git history (git filter-repo --path FargisGuard.pem --invert-paths, then force-push main and the feature branch) — rewrites the fork's history, owner decision. Do it AFTER rotation. (H-01)

**O-03.** _(phase 2)_ Enable the Message Content and Server Members privileged intents for the bot in the Discord developer portal; without them the narrowed intents in Phase 2 will fail to connect. Deploy-time, owner action.

**O-04.** _(phase 7)_ Verify on the live EC2 host after deploy: systemd unit restarts cleanly, slash commands appear after tree.sync, dashboard answers only on loopback with the bearer token. Nothing in this gameplan can be verified against live Discord/OpenAI from the sandbox (INVARIANT-04).

## Phase Breakdown

### Phase 0: Bootstrap: dev tooling and secrets hygiene

**Goal**: Remove the committed private key from HEAD, make secrets hygiene structural (.gitignore, .env.example, fail-fast config), and stand up pytest + ruff with a first passing test so every later phase has a green pre-flight (H-01 tree half, D-005 fail-fast).
**Depends on**: nothing (first phase).

| Task | Description | Effort |
|------|-------------|--------|
| 0.1 | `git rm FargisGuard.pem`; add `*.pem`, `*.key`, `.env.*` (keep `.env.example`) to `.gitignore` | S |
| 0.2 | `pyproject.toml` with `[tool.pytest.ini_options]` (testpaths, asyncio_mode) and `[tool.ruff]` (line length, excludes); `requirements-dev.txt` | S |
| 0.3 | `config.py`: pure `require_env(name, env)` raising `ConfigError` with the variable name; apply to DISCORD_TOKEN and OPENAI_API_KEY | S |
| 0.4 | `.env.example` enumerating every variable config.py reads, placeholder values only | S |
| 0.5 | `tests/test_config.py` covering require_env present/missing; run `pytest -q` and `ruff check .` green | S |

**Exit criteria**:
- [x] FargisGuard.pem is absent from the working tree and *.pem, *.key, .env.* are gitignored
- [x] .env.example lists every variable config.py reads, with no real values
- [x] config.py raises a clear error at import when DISCORD_TOKEN or OPENAI_API_KEY is missing (unit-tested via a pure require_env function)
- [x] pytest -q passes with at least one test and ruff check . is clean; baseline recorded by pre-flight
- [x] pyproject.toml carries pytest and ruff configuration; requirements-dev.txt pins pytest, pytest-asyncio, ruff

### Phase 1: Verdict parsing and punishment correctness

**Goal**: Turn the model's reply into a validated Verdict via a pure parser, fix the discord.timedelta crash, make the severity map explicit with no fallthrough, and base immunity on permissions/role IDs (H-03 parse half, H-05 partial, H-06, H-10 immunity).
**Depends on**: Phase 0.

| Task | Description | Effort |
|------|-------------|--------|
| 1.1 | `verdict.py`: frozen `Verdict(severity:int, reason:str)` and pure `parse_verdict(text) -> Verdict | None` (exact `VIOLATION|<1..4>|<reason>`, reason may contain pipes) | S |
| 1.2 | `moderation.py`: `from datetime import timedelta`; `ACTIONS: dict[int, str]` explicit map; unknown severity → `"none"`; DM `Forbidden` caught | S |
| 1.3 | `moderation.is_immune(member, immune_role_ids)`: `administrator` or `manage_messages` permission, or role id in `IMMUNE_ROLE_IDS` (config, comma-separated ints) | S |
| 1.4 | `tests/fakes.py` with `FakeMember`/`FakeRole`/`FakePermissions`; `tests/test_verdict.py`, `tests/test_moderation.py` covering the exit criteria table | M |

**Exit criteria**:
- [ ] verdict.parse_verdict returns None for every malformed input in the test table (missing fields, severity 0, 5, non-integer, empty reason, non-VIOLATION prefix) and a frozen Verdict for valid ones
- [ ] moderation uses datetime.timedelta; a test asserts member.timeout is awaited with a datetime for severity 2
- [ ] severity-to-action is an explicit mapping with no fallthrough branch; an unknown severity takes no action
- [ ] immunity is decided by guild permissions or IMMUNE_ROLE_IDS from config, never by role name; a test proves a role named Moderator is not immune
- [ ] a closed-DM member (send raises Forbidden) still returns warn without raising

### Phase 2: Gateway access control and channel checks

**Goal**: Make bot.py importable and testable, gate /setrules with real app-command permission checks, sync the command tree in setup_hook, use the channel NSFW flag for exemption, and remove the model-output echo (H-02, H-09, H-10 channel half, H-11 sync half).
**Depends on**: Phase 1.

| Task | Description | Effort |
|------|-------------|--------|
| 2.1 | `bot.py` → `create_bot(settings) -> commands.Bot` + `main()` under `__main__`; narrowed `Intents` (guilds, members, message_content) | M |
| 2.2 | `/setrules`: `@app_commands.checks.has_permissions(administrator=True)` + `@app_commands.default_permissions(administrator=True)` | S |
| 2.3 | `setup_hook`: `await tree.sync()`; remove dashboard start from `on_ready` (Phase 5 re-adds it correctly) | S |
| 2.4 | `channels.is_exempt(channel)` pure: `getattr(channel, 'is_nsfw', lambda: False)()`; drop `NSFW_CHANNEL_NAME`; delete the mention-echo branch | S |
| 2.5 | `tests/test_bot_wiring.py`: import safety, command checks, sync called, exemption table | M |

**Exit criteria**:
- [ ] python -c 'import bot' completes without connecting; create_bot() returns the configured bot
- [ ] a test asserts bot.tree.get_command('setrules').checks is non-empty and default_permissions.administrator is True
- [ ] setup_hook awaits tree.sync (tested with a fake tree)
- [ ] NSFW exemption uses channel.is_nsfw(); a test shows a channel named nsfw without the flag is moderated and a flagged channel is exempt
- [ ] no code path replies with model output; intents are narrowed to guilds, members, message_content

### Phase 3: Async, fail-closed AI path

**Goal**: Switch to AsyncOpenAI with a timeout and injectable client, pass rules as delimited user-turn data, skip empty messages, and wrap the whole pipeline so any error posts to mod-log instead of letting the message stand (H-05, H-07, H-03 prompt half).
**Depends on**: Phase 2.

| Task | Description | Effort |
|------|-------------|--------|
| 3.1 | `ai_engine.py`: `AsyncOpenAI` built lazily; `analyze_message(content, rules, *, client, timeout=15.0) -> str`; `build_messages(rules, content)` with `<rules>`/`<message>` tags in the user turn | M |
| 3.2 | `pipeline.py`: `should_analyze(content)`; `async handle_message(msg, deps: Deps)` orchestrating exempt → analyze → parse → punish → log, with every step in try/except that routes to `deps.log_error` | M |
| 3.3 | `bot.py` `on_message` delegates to `handle_message` with real deps | S |
| 3.4 | `tests/test_ai_engine.py`, `tests/test_pipeline.py` with a `FakeClient` | M |

**Exit criteria**:
- [ ] ai_engine uses AsyncOpenAI, awaited, with a request timeout; the client is injectable and no test constructs a real one
- [ ] build_messages puts rules and content inside delimited tags in the user turn and the system prompt contains no guild-supplied text
- [ ] empty or whitespace-only messages never reach the analyzer (test)
- [ ] when the analyzer raises, handle_message posts to mod-log and punishes nobody (test); when the verdict is None it posts the raw reply to mod-log
- [ ] handle_message is driven end-to-end in tests with fake message, analyzer, punisher, and logger

### Phase 4: Human-in-the-loop for high severity and warning escalation

**Goal**: Replace automatic kick/ban with pending actions approved via /modaction, apply a timeout hold meanwhile, and make prior warning count raise effective severity through a pure escalation function (H-03 human gate, H-12 escalation).
**Depends on**: Phase 3.

| Task | Description | Effort |
|------|-------------|--------|
| 4.1 | `escalation.py`: `effective_severity(model_severity, prior_warnings)` — +1 at ≥3 priors, +2 at ≥6, capped at 4; documented in the docstring | S |
| 4.2 | `database.py`: `pending_actions(id, guild_id, user_id, severity, reason, status, created_at)`; `add_pending`, `get_pending`, `resolve_pending` | S |
| 4.3 | `moderation.py`: severity ≥3 → delete + timeout hold + `add_pending` + return `"pending:<id>"`; `execute_pending(member, row)` performs kick/ban | M |
| 4.4 | `/modaction id action` (`ban_members`) in `bot.py`; mod-log post on pending creation names the id | M |
| 4.5 | `tests/test_escalation.py`, `tests/test_pending.py` | M |

**Exit criteria**:
- [ ] a severity-4 verdict results in no kick/ban call, a pending_actions row, a timeout hold, and a mod-log post naming the pending id (test)
- [ ] /modaction approve executes the stored action and marks the row; deny lifts the timeout and marks the row (tests with fakes)
- [ ] escalation.effective_severity is pure and tested: prior warnings raise severity per the documented ladder, capped at 4
- [ ] /modaction requires ban_members via app_commands checks and default_permissions (test)

### Phase 5: Dashboard and database safety

**Goal**: Per-call SQLite connections with DB_PATH, loopback-bound dashboard requiring a bearer token, started exactly once as an asyncio task from setup_hook (H-04, H-08, H-11 dashboard half).
**Depends on**: Phase 4.

| Task | Description | Effort |
|------|-------------|--------|
| 5.1 | `database.py`: `DB_PATH` from env; `connect()` contextmanager; `init_db()`; migrate every helper; delete module-level `conn`/`cursor` | M |
| 5.2 | `rules.py`, `appeals.py`, `moderation.py`, `dashboard.py` → `connect()` | S |
| 5.3 | `dashboard.py`: `require_token` dependency, `DASHBOARD_HOST`/`DASHBOARD_TOKEN`, rows as dicts; `start_dashboard(loop) -> Task | None` using `uvicorn.Server` | M |
| 5.4 | `bot.py` `setup_hook` starts the dashboard once via `start_dashboard` | S |
| 5.5 | `tests/test_database.py` (two-thread interleave), `tests/test_dashboard.py` (401/200, host default, token-unset no-start) | M |

**Exit criteria**:
- [ ] database exposes a connect() context manager and no module-level connection or cursor; DB_PATH env var controls the file
- [ ] rules, appeals, moderation, and dashboard all use connect(); a two-thread test performs interleaved reads without error
- [ ] dashboard routes return 401 without a valid bearer token and JSON objects (not tuples) with it (TestClient tests)
- [ ] DASHBOARD_HOST defaults to 127.0.0.1; with DASHBOARD_TOKEN unset the dashboard is not started (test on the start helper)
- [ ] the dashboard is started once from setup_hook as an asyncio task using uvicorn.Server, not from on_ready

### Phase 6: Appeals workflow

**Goal**: Make appeals actionable: dedupe pending appeals, notify mod-log on submission, and add /appeals and /appeal_resolve so forgive() is reachable (H-12 appeals).
**Depends on**: Phase 5.

| Task | Description | Effort |
|------|-------------|--------|
| 6.1 | `database.py`: appeals gain `resolved_by`, `created_at`; `has_pending_appeal`, `list_pending_appeals`, `resolve_appeal` | S |
| 6.2 | `appeals.py`: `submit_appeal` rejects a duplicate pending; returns the new id | S |
| 6.3 | `bot.py`: `/appeal` notifies mod-log; `/appeals` and `/appeal_resolve id approve|deny` (`manage_guild`); approve → `forgive()` | M |
| 6.4 | `tests/test_appeals.py` | M |

**Exit criteria**:
- [ ] submitting a second appeal while one is pending is rejected (test)
- [ ] a new appeal posts a notice to mod-log (test)
- [ ] /appeals lists pending appeals and /appeal_resolve approve calls forgive() for that user and guild (tests); both require manage_guild
- [ ] appeal rows record status and resolved_by

### Phase 7: Docs truth-up and deploy hygiene

**Goal**: Rewrite the README to claim only what exists, document every environment variable, add a systemd unit example and the key-rotation runbook in DEPLOYMENT.md, and start CHANGELOG.md (H-12 README, H-01 runbook).
**Depends on**: Phase 6.

| Task | Description | Effort |
|------|-------------|--------|
| 7.1 | README rewrite: what it does (as built), setup, env var table, commands, deployment pointer, security notes | M |
| 7.2 | `docs/DEPLOYMENT.md`: systemd unit + `EnvironmentFile`, `deploy/fargisguard.service`, EC2 key-rotation runbook (O-01/O-02) | M |
| 7.3 | `CHANGELOG.md` initial entry; `docs/ARCHITECTURE.md`/`SECURITY.md`/`TESTING.md` refreshed to final state | S |
| 7.4 | Final `pytest -q` + `ruff check .` in a fresh venv; record counts | S |

**Exit criteria**:
- [ ] README features section lists only behavior that exists in code; every .env.example variable is documented
- [ ] docs/DEPLOYMENT.md contains the systemd unit, EnvironmentFile usage, and the EC2 key-rotation runbook
- [ ] CHANGELOG.md exists with an entry for this gameplan
- [ ] pytest -q and ruff check . are green on the final tree
