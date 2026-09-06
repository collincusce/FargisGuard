# FargisGuard — Testing

- **Runner:** `pytest -q` from the repo root (project venv). Lint: `ruff check .`.
- **Discipline:** every network boundary (Discord, OpenAI, SQLite file) is
  behind an injectable pure function so the suite runs fully offline
  (INVARIANT-04). Discord objects are replaced by small fakes; the OpenAI
  client by a stub returning canned verdict strings.
- **Baseline:** tracked by Clauderizer pre-flight (`.clauderizer/baseline.json`);
  at onboarding there were **0 tests**.
- **Coverage policy:** every hardening finding that is code-fixable gets a
  regression test named for it (see `HARDENING.md`).
