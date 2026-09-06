# Chat Handoff Index — FargisGuard Hardening

> Last updated: 2026-09-06
> Status: Phase 4 ready

## How This Works

This is the coordination point for sessions executing this gameplan. A fresh
session gets current state automatically from the Clauderizer SessionStart hook,
then calls `cz_next_phase_context` for the active phase. No manual reading order.

## Pre-Flight Verification

Run `cz_preflight` before any code. If any enabled check fails: STOP, report.

**Current baseline test count**: 0

## Ending Protocol

1. `cz_transition_phase` the finished phase to complete.
2. `cz_add_output` each concrete produced value; `cz_add_phase_summary` the recap;
   `cz_add_correction` / `cz_add_lesson` as earned.
3. `cz_transition_status` on touched entities (fires cascade); `cz_resolve_cascade`
   the verdicts.
4. `cz_write_handoff` for the next phase.
5. Run exit verification; report the test count.

## Phase Status Table

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap: dev tooling and secrets hygiene | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Verdict parsing and punishment correctness | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-1-HANDOFF.md |
| 2 | Gateway access control and channel checks | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-2-HANDOFF.md |
| 3 | Async, fail-closed AI path | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-3-HANDOFF.md |
| 4 | Human-in-the-loop for high severity and warning escalation | ⬜ NOT STARTED | — | — | handoffs/PHASE-4-HANDOFF.md |
| 5 | Dashboard and database safety | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Appeals workflow | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |
| 7 | Docs truth-up and deploy hygiene | ⬜ NOT STARTED | — | — | handoffs/PHASE-7-HANDOFF.md |

**Status legend**: ⬜ NOT STARTED · 🟢 READY · 🟡 IN PROGRESS · ✅ COMPLETE · ⚠️ BLOCKED · 🔴 FAILED

## Per-Phase Completion Summaries

### Phase 0 — completed 2026-09-06

Removed FargisGuard.pem from HEAD and made secrets hygiene structural: *.pem, *.key, .env.* gitignored (with .env.example whitelisted), a documented .env.example, and config.py that fails at import naming the missing variable via a pure require_env. Stood up pytest (pythonpath=['.'] for the flat layout, asyncio_mode=auto) and ruff (E/F/W/I/B/UP), fixed the six pre-existing import-order findings with ruff --fix (imports only, no behavior change), and landed the first 7 tests. The tests pre-flight check was downgraded to advisory for this phase only (C-01) and is restored to blocking here.

What I did not check: the EC2 host itself (its Python version, whether the old key is still in authorized_keys, whether systemd passes the env the way .env does locally); the git history, which still contains the key (O-01, O-02 are owner actions); that load_dotenv does not shadow a systemd EnvironmentFile in production.

### Phase 1 — completed 2026-09-06

The classifier's reply now goes through verdict.parse_verdict, a pure strict parser that returns a frozen Verdict only for an exact single-line VIOLATION|1..4|reason and None for everything else (17-row rejection table). moderation.punish uses datetime.timedelta (severity-2 timeouts had never worked), an explicit ACTIONS map with no fallthrough (unknown severity -> 'none', no warning recorded), swallows Forbidden on closed DMs, and decides immunity by administrator/manage_messages permission or IMMUNE_ROLE_IDS from config — a role merely named Moderator is proven not immune. bot.py's raw split/int parse is replaced by the parser and the mention-echo branch (H-09) is deleted a phase early. 48 tests, ruff clean.

What I did not check: bot.py end to end (it still runs bot.run at import; Phase 2 makes it importable and testable); how gpt-4o-mini actually formats replies in production (the strictness may route more replies to human review than expected — that is the intended failure direction); Discord's real timeout semantics beyond the call signature; kick/ban still fire automatically for severity 3-4 until Phase 4.

### Phase 2 — completed 2026-09-06

bot.py is now a factory (create_bot -> FargisGuard subclass of commands.Bot) with main() behind a __main__ guard, so importing it connects to nothing and tests inspect the real command tree. /setrules carries app_commands.checks.has_permissions(administrator) AND default_permissions(administrator) — the test asserts both, closing H-02. setup_hook awaits tree.sync (H-11 sync half); intents are narrowed to guilds/members/messages/message_content (messages is required to receive on_message at all). Channel exemption moved to channels.is_exempt using Discord's NSFW flag (H-10 closed). The per-message flow lives in pipeline.handle_message with all side effects injected via Deps, driven end-to-end by fakes. Making bot importable exposed H-13: openai 1.10.0 cannot construct its client against httpx>=0.28, so requirements.txt pins httpx<0.28 for now. 67 tests, ruff clean.

What I did not check: the interaction-time behavior of the permission check against a live guild (only that it is registered on the command); tree.sync against Discord (global sync propagation and rate limits); whether messages=True alone delivers thread messages the way the old Intents.all() did; the EC2 host's installed httpx version.

### Phase 3 — completed 2026-09-06

ai_engine now builds an AsyncOpenAI client lazily (15s timeout) and awaits it, with the client injectable so no test constructs a real one (an autouse fixture asserts it). The system prompt is static; the guild's rules and the message travel as <rules>/<message> data in the user turn with closing tags neutralized, so /setrules is no longer a system-prompt channel (D6). A clean reply is the exact sentinel OK (D8). pipeline.handle_message fails closed: empty messages are skipped before any API call; analyzer and punisher exceptions post an error notice with the jump URL to mod-log and punish nobody; any reply that is neither OK nor a valid verdict is posted raw for a human; the logger itself can fail without escaping. openai bumped 1.10.0 -> 2.54.0 and the httpx pin dropped (H-13 closed). 91 tests, ruff clean.

What I did not check: whether gpt-4o-mini reliably answers the bare OK sentinel in production (if not, mod-log gets noisy — visible, not silent); any live OpenAI call at all (openai 2.x was verified only by constructing AsyncOpenAI and by the chat.completions call signature the fake records); token cost per message; the behavior of temperature=0 and max_tokens=60 on the real model.

## Accumulated Lessons

_(Numbered sequentially across the whole gameplan. Categorized. Pruned of
obsolete items — mark with "(obsolete)" rather than deleting.)_

### Category: Process

**1.** A bootstrap phase on a test-less repo needs the tests pre-flight check downgraded to advisory for that one phase; restore it in the same phase's ending protocol.

**4.** Pinning only direct dependencies is not reproducibility: a pinned client library can be broken by an unpinned transitive one. Verify installs in a fresh venv, and prefer a full freeze/lock for deployables.

### Category: Testing

**2.** Flat-layout Python repos (modules at the root) need pythonpath=['.'] in [tool.pytest.ini_options] or test modules cannot import them; and any test that importlib.reload()s a module must catch a base exception class, because reload mints new class objects that no longer match the names imported before the reload. *(evidence: Phase 0: ModuleNotFoundError on import config, then two reload tests failing on class identity)* (obsolete 2026-09-06: superseded by lesson #3: the fix is to never reload a shared module in tests, not to widen the except clause)

**3.** Never importlib.reload() a shared module in a test: it mints new class objects, so exceptions raised later no longer match the classes other test files imported (failures appear in unrelated files that run afterwards). To test import-time behavior, exec config.py into a fresh module object via importlib.util.spec_from_file_location under a different name and leave sys.modules alone. Flat-layout repos still need pythonpath=['.'] in pytest config. *(evidence: Phase 1: test_config_ids failed only because test_config reloaded config first)*

### Category: Design

**5.** An LLM-as-classifier protocol needs an explicit positive sentinel for the negative class (here: reply exactly OK). Without it, 'no verdict' and 'garbage reply' are indistinguishable, forcing a choice between failing open and flooding humans; with it, the fail-closed path is precise and prompt drift becomes visible noise instead of silent non-enforcement. *(evidence: Phase 3 D8; the original code treated every non-VIOLATION reply as clean and echoed it to the channel)*
