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

### Category: Security

**L-04.** Rotating a leaked credential is not done until the OLD credential is proven REJECTED by the live system — issuing a new one is not enough. Bake the negative check (expect 'Permission denied') into the rotation runbook as a required step. *(from 2026-09-06-fargisguard-hardening #7, 2026-09-06)*
