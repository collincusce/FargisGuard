# FargisGuard — Testing

- **Runner:** `pytest` from the repo root (`pyproject.toml` sets
  `pythonpath=["."]`, `asyncio_mode=auto`). Lint: `ruff check .`
- **Discipline (INVARIANT-04):** the suite is fully offline. `tests/fakes.py`
  provides `FakeMember`, `FakeGuild`, `FakeChannel`, `FakeMessage`,
  `FakeInteraction` (drives real slash-command callbacks), `FakeAnthropic`
  (structured-output replies, stop reasons, usage), and partial-message
  deletes; `test_batcher.py` parks timers on futures it releases by hand.
  An autouse fixture points `DB_PATH` at a per-test temp file; an autouse
  fixture in `test_ai_engine.py` asserts no real Anthropic client is built
  (INVARIANT-06).
- **Import-time tests** load `config.py` as a fresh module object rather than
  reloading the shared one (reload mints new class objects and breaks other
  files' `except` clauses).
- **Baseline:** 0 tests at onboarding → 148 after hardening → 217 after
  scoped rules → **321** after the token-architecture gameplan (2026-09-07).
- **Coverage policy:** every code-fixable hardening finding has a regression
  test named for it; source-shape guards exist for the two things that must
  never come back (`.reply(` of model output; `.kick(`/`.ban(` inside
  `punish`).
- **Not covered:** anything requiring a live Discord gateway or Anthropic call;
  `uvicorn.Server.serve` on a real port.
