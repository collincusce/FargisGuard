# FargisGuard Hardening — Phase Status Tracker

> Living document. Updated after each phase completes.
> Last updated: 2026-09-06

## Phase Status

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap: dev tooling and secrets hygiene | ✅ COMPLETE | 2026-09-06 | 2026-09-06 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Verdict parsing and punishment correctness | ⬜ NOT STARTED | — | — | handoffs/PHASE-1-HANDOFF.md |
| 2 | Gateway access control and channel checks | ⬜ NOT STARTED | — | — | handoffs/PHASE-2-HANDOFF.md |
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

## Corrections Log

### C-01 — Phase 0

**Phase**: 0
**What gameplan said**: Pre-flight's tests check blocks Phase 0 like every other phase.
**What was actually correct**: pytest -q exits 5 with zero tests collected, so the check fails on any repo that has no suite yet — which is exactly the state Phase 0 exists to fix.
**Why**: The baseline was 0 tests. Downgraded `tests` to advisory via preflight_advisory in .clauderizer/config.toml for Phase 0 only; it returns to blocking once the first test exists.
**Lesson**: A bootstrap phase on a test-less repo needs the tests pre-flight check downgraded to advisory for that one phase; restore it in the same phase's ending protocol.
