# FargisGuard Hardening — Phase Status Tracker

> Living document. Updated after each phase completes.
> Last updated: 2026-09-06

## Phase Status

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap: dev tooling and secrets hygiene | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Verdict parsing and punishment correctness | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-1-HANDOFF.md |
| 2 | Gateway access control and channel checks | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-2-HANDOFF.md |
| 3 | Async, fail-closed AI path | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-3-HANDOFF.md |
| 4 | Human-in-the-loop for high severity and warning escalation | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-4-HANDOFF.md |
| 5 | Dashboard and database safety | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-5-HANDOFF.md |
| 6 | Appeals workflow | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-6-HANDOFF.md |
| 7 | Docs truth-up and deploy hygiene | ⬜ NOT STARTED | — | — | handoffs/PHASE-7-HANDOFF.md |

## Outputs Registry

### Phase 0 Outputs

```
baseline_tests: 7 passed (tests/test_config.py)
key_removed_from_tree: FargisGuard.pem deleted from HEAD; still present in history at 55ceedd until O-02
dev_tooling: pyproject.toml ([tool.pytest.ini_options] pythonpath=['.'], asyncio_mode=auto; [tool.ruff] E,F,W,I,B,UP, line 100), requirements-dev.txt, .env.example, tests/conftest.py
config_api: config.ConfigError, config.require_env(name, env=None), config.optional_env(name, default, env=None); DISCORD_TOKEN and OPENAI_API_KEY validated at import
```

### Phase 1 Outputs

```
tests: 48 passed (test_config, test_config_ids, test_verdict, test_moderation)
verdict_api: verdict.Verdict(severity:int, reason:str) frozen; verdict.parse_verdict(text) -> Verdict | None; strict single-line VIOLATION|1..4|reason, reason may contain pipes
moderation_api: moderation.ACTIONS={1:warn,2:timeout,3:kick,4:ban}; moderation.is_immune(member, immune_role_ids); async moderation.punish(member, severity, reason, *, immune_role_ids=()) -> warn|timeout|kick|ban|immune|none; TIMEOUT_MINUTES=15
config_immune_role_ids: config.IMMUNE_ROLE_IDS: frozenset[int] from IMMUNE_ROLE_IDS env (config.parse_id_list); IMMUNE_ROLES removed
test_fakes: tests/fakes.py: FakeMember (records sent/timeouts/kicks/bans, dms_closed), FakeRole, FakeGuild, FakePermissions, forbidden()
```

### Phase 2 Outputs

```
tests: 67 passed (adds test_channels, test_bot_wiring, test_pipeline)
bot_api: bot.create_bot(*, analyze, punisher, mod_log_channel, immune_role_ids, intents) -> FargisGuard(commands.Bot); bot.make_intents() = guilds+members+messages+message_content; bot.register_commands(bot); bot.mod_log_poster(name); bot.main() under __main__; setup_hook syncs the tree; command_prefix=when_mentioned (no prefix commands)
pipeline_api: pipeline.Deps(analyze, punish, log, immune_role_ids); async pipeline.handle_message(message, deps) -> ignored|exempt|clean|<action>; pipeline.violation_notice(message, action, reason)
channels_api: channels.is_exempt(channel) -> bool via channel.is_nsfw(); config.NSFW_CHANNEL_NAME removed
requirements: httpx<0.28 pinned (H-13); Phase 3 bumps openai and drops the pin
```

### Phase 3 Outputs

```
tests: 91 passed (adds test_ai_engine; test_pipeline fail-closed cases)
ai_engine_api: ai_engine.SYSTEM_PROMPT (static), CLEAN_SENTINEL='OK', MODEL='gpt-4o-mini', REQUEST_TIMEOUT=15.0, MAX_CONTENT_CHARS=2000; build_messages(rules, content) pure; neutralize_tags(text); get_client() lazy AsyncOpenAI; async classify(rules, content, *, client=None, model=MODEL) -> raw reply; async analyze_message(content, guild_id, *, client=None, rules_loader=get_rules)
pipeline_outcomes: handle_message returns ignored|exempt|skipped|clean|unparseable|error|<action>; should_analyze(content) pure; error_notice/unparseable_notice/violation_notice builders; _log_safely never raises
requirements: openai==2.54.0 (was 1.10.0); httpx pin removed; verified AsyncOpenAI constructs on httpx 0.28.1
```

### Phase 4 Outputs

```
tests: 127 passed (adds test_escalation, test_database, test_pending; test_moderation updated for holds)
database_api: database.connect(path=None) contextmanager (sqlite3.Row, commit/rollback, lazy init_db per path); init_db(path); db_path() from DB_PATH (default moderation.db); now_iso(); add_warning/get_warnings/forgive; add_pending/get_pending/list_pending/resolve_pending; MIGRATIONS add appeals.created_at/resolved_by/resolved_at to old files; no module-level conn/cursor
moderation_api: punish -> warn|timeout|pending:<id>:<kick|ban>|immune|none (severity raised by escalation.effective_severity from prior warnings; kick/ban never executed here, member held with a 60-minute timeout); async resolve_pending_action(guild, pending_id, approve|deny, *, moderator_id) -> message; HOLD_MINUTES=60
escalation_api: escalation.effective_severity(model_severity, prior_warnings): +1 at >=3 priors, +2 at >=6, capped at 4, never lower
commands: /modaction pending_id decision(approve|deny) — app_commands.checks.has_permissions(ban_members) + default_permissions(ban_members); mod-log notice names the id and both commands
```

### Phase 5 Outputs

```
tests: 139 passed (adds test_dashboard incl. a two-thread interleave test)
dashboard_api: dashboard.create_app(token) -> FastAPI (ValueError on empty token; /health open; /infractions /appeals /pending require Authorization: Bearer <token>, constant-time compare, 401 + WWW-Authenticate otherwise; rows are dicts); dashboard.start_dashboard(*, token, host, port, server_factory=_uvicorn_server) -> asyncio.Task | None (None + warning when token empty)
config: DASHBOARD_HOST default 127.0.0.1; DASHBOARD_TOKEN default '' (disabled); documented in .env.example with a token-generation one-liner
bot_wiring: FargisGuard(deps, *, intents, dashboard_starter); create_bot(..., dashboard_starter=None) defaults to functools.partial(start_dashboard, token/host/port from config); setup_hook syncs the tree then starts the dashboard once; on_ready only prints
requirements: fastapi 0.110.0 -> 0.141.1 (starlette 1.x) — the 0.110 TestClient passed app= to httpx, removed in 0.28
```

### Phase 6 Outputs

```
tests: 148 passed (adds test_appeals, driving the real command callbacks with FakeInteraction)
appeals_api: appeals.submit_appeal(user_id, guild_id, reason) -> id | None (None when one is pending); appeals.format_pending_appeals(guild_id); appeals.resolve_appeal_action(guild_id, appeal_id, approve|deny, *, moderator_id) -> message (approve calls database.forgive); database.has_pending_appeal/get_appeal/list_pending_appeals/resolve_appeal
commands: /appeal reason (everyone; ephemeral; posts a mod-log notice naming the id and both resolve commands); /appeals (manage_guild); /appeal_resolve appeal_id approve|deny (manage_guild). Full tree: appeal, appeal_resolve, appeals, modaction, setrules
```

## Corrections Log

### C-01 — Phase 0

**Phase**: 0
**What gameplan said**: Pre-flight's tests check blocks Phase 0 like every other phase.
**What was actually correct**: pytest -q exits 5 with zero tests collected, so the check fails on any repo that has no suite yet — which is exactly the state Phase 0 exists to fix.
**Why**: The baseline was 0 tests. Downgraded `tests` to advisory via preflight_advisory in .clauderizer/config.toml for Phase 0 only; it returns to blocking once the first test exists.
**Lesson**: A bootstrap phase on a test-less repo needs the tests pre-flight check downgraded to advisory for that one phase; restore it in the same phase's ending protocol.

### C-02 — Phase 1

**Phase**: 1
**What gameplan said**: Removing the mention-echo branch (H-09) is Phase 2 work.
**What was actually correct**: Deleted in Phase 1: once parse_verdict returned None for malformed VIOLATION lines, the else-branch would have echoed those lines to the channel when mentioned, which is worse than the original.
**Why**: Leaving a known-worse path in place to respect phase boundaries is the wrong trade; the Phase 2 exit criterion 'no code path replies with model output' is checked off there.

### C-03 — Phase 2

**Phase**: 2
**What gameplan said**: Phase 2 touches bot.py, channels, pipeline, and tests only.
**What was actually correct**: Phase 2 also pins httpx<0.28 in requirements.txt: without it `import bot` (and therefore every wiring test) fails on a clean install because openai 1.10.0 is incompatible with httpx 0.28+.
**Why**: Discovered the moment bot.py became importable in tests — the old module-level bot.run() had hidden that the pinned requirements no longer produce a bootable bot. Phase 3 replaces the openai pin and drops the httpx pin (H-13).
**Lesson**: Pinning only direct dependencies is not reproducibility: a pinned client library can be broken by an unpinned transitive one. Verify installs in a fresh venv, and prefer a full freeze/lock for deployables.

### C-04 — Phase 4

**Phase**: 4
**What gameplan said**: Per-call SQLite connections and DB_PATH (task 5.1) and the rules/appeals migration (5.2) belong to Phase 5.
**What was actually correct**: Done in Phase 4: pending_actions needed a table and its tests needed an isolated database file, and building that on the module-level cursor only to rewrite it a phase later was waste. dashboard.py is NOT migrated yet — it still imports the removed cursor and is broken until Phase 5, which keeps the dashboard half of 5.2 plus 5.3-5.5.
**Why**: Dependency order beat narrative order: the storage seam is a prerequisite of the human-gate work, not a sibling of it. Phase 5's first exit criterion is checked off here because it is met.
