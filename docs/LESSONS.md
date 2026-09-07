# Distilled Lessons

> Project-level lessons promoted from gameplans (`cz_promote_lesson`).
> Every future handoff carries this list, so it must stay compact: obsolete
> entries that stop earning their place (`cz_obsolete_lesson` with the `L-NN`
> id). Entries are never deleted, only marked.

## Lessons

### Category: Testing

**L-01.** Never importlib.reload() a shared module in a test — reload mints new class objects, so exceptions raised afterward stop matching the classes other files imported (failures surface in unrelated files). Test import-time behavior by exec'ing the module into a fresh object via importlib.util. Flat-layout repos need pythonpath=['.'] in pytest config. *(from 2026-09-06-fargisguard-hardening #3, 2026-09-06)*

### Category: Dependencies

**L-02.** Pinning only direct dependencies is not reproducibility: a pinned library (openai, fastapi) can be broken at import by an unpinned transitive (httpx). Always verify installs in a fresh venv, and prefer a full freeze/lock for anything deployed. *(from 2026-09-06-fargisguard-hardening #4, 2026-09-06)*

### Category: Design

**L-03.** An LLM-as-classifier protocol needs an explicit positive sentinel for the negative class (here: reply exactly 'OK'). Without it, 'no verdict' and 'garbage reply' are indistinguishable, forcing a choice between failing open and flooding humans; with it, the fail-closed path is precise and prompt drift shows up as visible noise, not silent non-enforcement. *(from 2026-09-06-fargisguard-hardening #5, 2026-09-06)*

**L-07.** Capture the deploy target's runtime versions (here sqlite3.sqlite_version — Amazon Linux 2 ships 3.7, RETURNING needs 3.35) in Source-of-Truth Captures before using any version-gated feature. The dev box's 3.45 hid the risk; it was caught on re-read, not by a test. *(evidence: Phase 1, rules._bump_version rewritten to avoid RETURNING)* *(from 2026-09-06-scoped-moderation-rules #3, 2026-09-06)*

### Category: Security

**L-04.** Rotating a leaked credential is not done until the OLD credential is proven REJECTED by the live system — issuing a new one is not enough. Bake the negative check (expect 'Permission denied') into the rotation runbook as a required step. *(from 2026-09-06-fargisguard-hardening #7, 2026-09-06)*

### Category: Environment

**L-05.** cz_preflight runs bare `pytest -q`; on the remote host a uv-tool pytest in ~/.local/bin shadows /usr/local/bin/pytest with a venv lacking the project's deps, so preflight fails with ModuleNotFoundError while `python -m pytest` passes. At session start run `uv pip install --python /root/.local/share/uv/tools/pytest/bin/python -r requirements.txt -r requirements-dev.txt`; never "fix" it by changing the host profile's test command. *(from 2026-09-06-scoped-moderation-rules #1, 2026-09-06)*

### Category: Process

**L-06.** When a measurement criterion names a unit the system does not natively produce, prefer the unit the system reports for free and record the substitution, rather than adding a dependency whose numbers will not survive the next migration. *(from 2026-09-06-scoped-moderation-rules #2, 2026-09-06)*

**L-08.** Before recording a decision that names a request parameter, verify it against the installed SDK's signature (inspect.signature on the pinned version) — the reference docs describe the API surface, the SDK pin decides what is expressible. Here anthropic 1.4.0's messages.create had no temperature parameter at all, so D-011's "temperature 0" had to be corrected (C-01). *(from 2026-09-07-token-architecture #1, 2026-09-07)*
