# Hardening

**Append-only** persistent risk tracker. NEVER delete entries — mark a risk
resolved with a date instead. This is a permanent audit trail. Numbered `H-NN`.

## Risks

### H-01 — RSA private key (FargisGuard.pem) committed to the repository

- **Severity**: critical
- **Status**: open (2026-09-06)
- **Affected**: FargisGuard.pem, EC2 instance
- **Invariant violated**: INVARIANT-01
- **Impact**: A valid 2048-bit RSA private key (verified parseable; format matches an EC2 keypair) is in commit 55ceedd. Anyone with repo/fork access can SSH to the EC2 host if the key is still authorized.
- **Root cause**: .gitignore did not cover *.pem; files were bulk-uploaded via the GitHub web UI.
- **Recommended fix**: Rotate the EC2 keypair FIRST (add new key to authorized_keys, verify, remove old), then remove the file from the tree, add *.pem to .gitignore, and scrub history with git filter-repo + force push (owner decision).

### H-02 — /setrules slash command has no effective authorization

- **Severity**: critical
- **Status**: resolved (2026-09-06)
- **Affected**: bot.py setrules_cmd
- **Invariant violated**: INVARIANT-05
- **Impact**: Any guild member can rewrite the moderation rules that are interpolated into the LLM system prompt.
- **Root cause**: @commands.has_permissions (discord.ext.commands) is applied to an app command; verified on discord.py 2.3.2 that the check lands on __commands_checks__ which app_commands.Command never reads (checks=[], default_permissions=None).
- **Reproduction**: Load the command object: bot.tree.get_command('setrules').checks == [].
- **Recommended fix**: Use @app_commands.checks.has_permissions(administrator=True) plus @app_commands.default_permissions(administrator=True); add a test asserting the check is registered.
- **Resolution**: Phase 2: /setrules uses @app_commands.checks.has_permissions(administrator=True) + @app_commands.default_permissions(administrator=True); test_setrules_has_a_real_app_command_permission_check asserts checks is non-empty and default_permissions.administrator is True.
### H-03 — Model verdict is sole authority for kick/ban and is prompt-injectable

- **Severity**: high
- **Status**: resolved (2026-09-06)
- **Affected**: ai_engine.py, bot.py on_message, moderation.py
- **Invariant violated**: INVARIANT-02
- **Impact**: Combined with the /setrules hole, any member can set rules to 'always answer VIOLATION|4|x' and every subsequent message bans its author. Independently, message content can steer the model to not flag violations.
- **Root cause**: Untrusted content (rules and message) is placed in the prompt and the raw reply is parsed as a command channel with no validation and no human gate.
- **Recommended fix**: Parse into a validated Verdict; require human approval for severity>=3; put rules in a delimited user turn; add a keyword/OpenAI-moderation floor.
- **Resolution**: Phase 4: the human gate is in. Parse half (Phase 1), prompt half (Phase 3), and now severity>=3 becomes a pending action approved via /modaction; test_no_kick_or_ban_call_in_punish_source guards the regression.
### H-04 — Dashboard binds 0.0.0.0 with no authentication

- **Severity**: high
- **Status**: resolved (2026-09-06)
- **Affected**: dashboard.py
- **Impact**: /infractions and /appeals expose every user's warning count and full appeal text to anyone who can reach port 8000.
- **Root cause**: uvicorn.run(host='0.0.0.0') with no auth dependency.
- **Recommended fix**: Bind 127.0.0.1 by default and require a bearer token from DASHBOARD_TOKEN; front with nginx if remote access is needed.
- **Resolution**: Phase 5: loopback default, DASHBOARD_TOKEN required (create_app refuses empty; start_dashboard skips with a warning), bearer auth on every data route with 401 tests.
### H-05 — All failures in the moderation path fail open and silent

- **Severity**: high
- **Status**: resolved (2026-09-06)
- **Affected**: bot.py on_message, moderation.py, ai_engine.py
- **Invariant violated**: INVARIANT-03
- **Impact**: Any exception (OpenAI 429, DM Forbidden, malformed verdict, timeout AttributeError) kills on_message before the message is deleted or logged — the violating message stays up and nobody is told.
- **Root cause**: No try/except around the AI call, the punishment, or the parse.
- **Recommended fix**: Wrap the pipeline; on error post to mod-log for human review (fail closed).
- **Resolution**: Phase 3: pipeline.handle_message wraps analysis and punishment; failures and unparseable replies post to mod-log with the jump URL and take no action (tests: analyzer error, punisher error, unparseable table, logger failure).
### H-06 — discord.timedelta does not exist — severity-2 timeouts crash

- **Severity**: medium
- **Status**: resolved (2026-09-06)
- **Affected**: moderation.py punish
- **Impact**: Every severity-2 verdict raises AttributeError; timeouts have never worked.
- **Root cause**: discord.py does not re-export timedelta; verified hasattr(discord,'timedelta') is False on 2.3.2.
- **Recommended fix**: from datetime import timedelta; cover with a unit test using a fake Member.
- **Resolution**: Phase 1: moderation.py imports datetime.timedelta; test_severity_2_times_out_with_a_real_datetime asserts a tz-aware datetime reaches member.timeout.
### H-07 — Synchronous OpenAI client blocks the event loop on every message

- **Severity**: medium
- **Status**: resolved (2026-09-06)
- **Affected**: ai_engine.py
- **Impact**: The bot freezes for the full API round-trip per message; throughput collapses under any real load.
- **Root cause**: openai.OpenAI (sync) called inside async def.
- **Recommended fix**: Use AsyncOpenAI with a timeout; short-circuit trivial/short messages.
- **Resolution**: Phase 3: ai_engine uses AsyncOpenAI (lazy, timeout=15s) and awaits chat.completions.create; empty messages never reach the API.
### H-08 — Shared SQLite cursor across the bot loop and the dashboard thread

- **Severity**: medium
- **Status**: resolved (2026-09-06)
- **Affected**: database.py, dashboard.py, rules.py, appeals.py
- **Impact**: Interleaved execute/fetchall on one cursor from two threads can return another query's rows or raise.
- **Root cause**: Module-level connection and cursor with check_same_thread=False.
- **Recommended fix**: Open a connection per call via a context manager; no module-level cursor.
- **Resolution**: Phase 5: dashboard.py migrated to database.connect(); no module-level connection or cursor remains anywhere (test_no_module_level_connection_or_cursor; grep clean). Two-thread interleave test passes.
### H-09 — Mentioning the bot returns raw model output — a free GPT proxy

- **Severity**: medium
- **Status**: resolved (2026-09-06)
- **Affected**: bot.py on_message else-branch
- **Impact**: Any member can obtain arbitrary model output posted under the bot's name, billed to the owner; content-safety and cost exposure.
- **Root cause**: Non-violation replies are echoed verbatim when the bot is mentioned.
- **Recommended fix**: Remove the echo; the classifier's non-violation output is discarded.
- **Resolution**: Phase 1: the mention-echo branch in bot.on_message is deleted; no code path replies with model output.
### H-10 — NSFW exemption and moderator immunity are string-name checks

- **Severity**: medium
- **Status**: resolved (2026-09-06)
- **Affected**: bot.py, moderation.py, config.py
- **Invariant violated**: INVARIANT-05
- **Impact**: Any channel named 'nsfw' bypasses moderation entirely; any role named 'Moderator' grants immunity.
- **Root cause**: Comparison against channel.name / role.name strings.
- **Recommended fix**: Use channel.is_nsfw() and permission/role-ID based immunity from config.
- **Resolution**: Phase 2: channel exemption is channels.is_exempt(channel) via is_nsfw(); tests prove a channel named nsfw without the flag is moderated. Immunity half was resolved in Phase 1.
### H-11 — Slash commands are never synced; on_ready starts the dashboard on every reconnect

- **Severity**: medium
- **Status**: resolved (2026-09-06)
- **Affected**: bot.py
- **Impact**: /appeal and /setrules never appear in Discord; the appeals workflow is unreachable. A gateway reconnect spawns a second uvicorn on a busy port.
- **Root cause**: No bot.tree.sync(); dashboard started from on_ready instead of setup_hook.
- **Recommended fix**: Sync in setup_hook; start the dashboard once as an asyncio task via uvicorn.Server.
- **Resolution**: Phase 5: setup_hook syncs the tree and starts the dashboard exactly once via uvicorn.Server as an asyncio task; on_ready only prints (test_dashboard_is_not_started_from_on_ready).
### H-12 — README claims features the code does not implement

- **Severity**: low
- **Status**: partial (2026-09-06)
- **Affected**: README.md, database.py, appeals.py
- **Impact**: Warning escalation (count is written, never read), appeals workflow (write-only table, forgive() never called), and human oversight for high-risk actions do not exist; contributors and operators are misled.
- **Root cause**: Documentation written ahead of implementation.
- **Recommended fix**: Implement escalation and the appeal resolution path, then truth-up the README.
- **Resolution**: Phase 4: warning escalation exists (escalation.effective_severity) and human oversight for high-risk actions exists (/modaction). The appeals workflow (Phase 6) and README truth-up (Phase 7) remain.
### H-13 — Pinned openai 1.10.0 crashes at import against current httpx (unpinned transitive dependency)

- **Severity**: high
- **Status**: resolved (2026-09-06)
- **Affected**: requirements.txt, ai_engine.py
- **Impact**: A fresh `pip install -r requirements.txt` resolves httpx>=0.28, and openai 1.10.0 then raises TypeError: Client.__init__() got an unexpected keyword argument 'proxies' when ai_engine constructs the client at import. The bot cannot start on a clean machine; existing deploys survive only on a cached older httpx.
- **Root cause**: requirements.txt pins direct dependencies only; httpx removed the proxies kwarg in 0.28.0 (2024-11) and openai fixed its client in 1.55.3.
- **Reproduction**: python -m venv v && v/bin/pip install -r requirements.txt && DISCORD_TOKEN=x OPENAI_API_KEY=y v/bin/python -c 'import ai_engine'
- **Recommended fix**: Immediate: pin httpx<0.28. Proper: bump openai to a current 1.x, construct the client lazily, and pin transitive deps (pip freeze or a lock file).
- **Resolution**: Phase 5 addendum: the same httpx 0.28 break also hit fastapi 0.110's TestClient (httpx.Client(app=...)); fastapi bumped to 0.141.1. Two pinned libraries broken by one unpinned transitive — a lock file is the real fix (tracked for Phase 7 docs).
