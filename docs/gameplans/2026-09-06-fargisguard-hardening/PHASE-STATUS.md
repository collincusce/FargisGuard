# FargisGuard Hardening — Phase Status Tracker

> Living document. Updated after each phase completes.
> Last updated: 2026-09-06

## Phase Status

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap: dev tooling and secrets hygiene | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Verdict parsing and punishment correctness | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-1-HANDOFF.md |
| 2 | Gateway access control and channel checks | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-2-HANDOFF.md |
| 3 | Async, fail-closed AI path | ⬜ NOT STARTED | — | — | handoffs/PHASE-3-HANDOFF.md |
| 4 | Human-in-the-loop for high severity and warning escalation | ⬜ NOT STARTED | — | — | handoffs/PHASE-4-HANDOFF.md |
| 5 | Dashboard and database safety | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Appeals workflow | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |
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
