# FargisGuard — Testing

- **Runner:** `pytest` from the repo root (`pyproject.toml` sets
  `pythonpath=["."]`, `asyncio_mode=auto`). Lint: `ruff check .`
- **Discipline (INVARIANT-04):** the suite is fully offline. `tests/fakes.py`
  provides `FakeMember`, `FakeGuild`, `FakeChannel`, `FakeMessage`,
  `FakeInteraction` (drives real slash-command callbacks), and `FakeOpenAI`.
  An autouse fixture points `DB_PATH` at a per-test temp file; an autouse
  fixture in `test_ai_engine.py` asserts no real OpenAI client is built.
- **Import-time tests** load `config.py` as a fresh module object rather than
  reloading the shared one (reload mints new class objects and breaks other
  files' `except` clauses).
- **Baseline:** 0 tests at onboarding → **148** at the end of the hardening
  gameplan (2026-09-06). Pre-flight (`.clauderizer/baseline.json`) tracks it.
- **Coverage policy:** every code-fixable hardening finding has a regression
  test named for it; source-shape guards exist for the two things that must
  never come back (`.reply(` of model output; `.kick(`/`.ban(` inside
  `punish`).
- **Not covered:** anything requiring a live Discord gateway or OpenAI call;
  `uvicorn.Server.serve` on a real port.
