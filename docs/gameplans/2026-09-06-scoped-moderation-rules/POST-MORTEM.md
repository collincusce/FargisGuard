# Post-mortem — Scoped Moderation Rules

> Gameplan: 2026-09-06-scoped-moderation-rules · Closed: 2026-09-06 · 7/7 phases complete
> Suite: 148 → 217 tests, green in the working install and in a fresh venv; ruff clean.

## What shipped

- **Scoped rules storage** (`rules.py`, `database.py`): guild / category /
  channel / thread scope keyed by snowflake IDs, a per-guild version counter
  bumped by every write, and a one-shot `SCRIPTS` migration layer whose first
  entry backfills legacy guild rules. `get_rules`/`set_rules` unchanged; guild
  writes mirrored to the legacy table for one release (D2).
- **Scope resolver** (`channels.py`): `resolve_scope(message)` from IDs only,
  fail-closed on dangling references (D-010); forum posts are threads of the
  forum (D3). The pipeline's channel access now sits inside the fail-closed
  boundary — a pre-existing INVARIANT-03 gap, closed.
- **Safety floor** (`ai_engine.SAFETY_FLOOR`, D-008): a code constant rendered
  as its own `<floor>` region in the static system turn; no table can reach it
  and no rule text can forge or remove it (adversarial tests).
- **NSFW channels are classified** (D-007 supersedes D-004) against their own
  scope rules plus the floor.
- **Composer** (`composer.py`): deterministic composition, sha256 ruleset key,
  memo invalidated by the version counter. One connection per uncached chain.
- **`/rules` command group**: category / channel / thread / clear / show,
  Administrator-only, targets via channel selects; `show` renders exactly what
  the classifier receives.
- **Measurement**: `LOG_LEVEL=DEBUG` logs ruleset key, part sizes, and API
  token usage per classification.

## What worked

- **The planning fan-out paid for itself twice.** One lens found that Discord
  has no nested threads (the "thread depth" scope collapsed to a boolean before
  it reached the schema); another found that D-004's NSFW bypass was
  structurally incompatible with "NSFW allows nudity but never CSAM" — the
  classifier has to *run* there, which is what made the floor a first-class
  decision instead of an afterthought.
- **Concrete captures made every phase a one-pass build.** Exact call sites,
  the ADD-COLUMN-only migration limit, and the "keep `get_rules`'s signature"
  constraint meant no caller changed until the phase that meant to change it.
  Five of six code phases were green on the first full run.
- **Reply-returning handlers** (`rulecmds.py`) kept the Discord surface thin
  and let `FakeInteraction` drive the permission predicates offline, so "every
  authoring command is Administrator-only" is a test, not a claim.

## What didn't, with root causes

- **The cost premise was never measured.** The gameplan was ordered "scoped
  rules first" to give the token-architecture work a stable batch key — but
  the live OpenAI project shows 0 requests in 30 days (O-01). Root cause: I
  ranked cost levers from the prompt's structure before asking for a baseline.
  The measurement line now exists; the numbers still do not.
- **A version-gated SQL feature nearly shipped.** `RETURNING` (SQLite ≥ 3.35)
  passed on the dev box's 3.45; Amazon Linux 2 ships 3.7. Caught on re-read,
  not by a test (L-07). Root cause: no capture of the deploy target's runtime
  versions.
- **The measurement criterion named a unit the system does not produce.**
  Per-component *token* counts need a tokenizer we are about to switch away
  from; delivered chars per part plus API-reported totals (C-01, L-06).
- **Preflight fought the environment.** A uv-tool `pytest` shadowed the real
  one; the fix is a session-start install, recorded as L-05.

## Procedure improvements

- Add the deploy target's `sqlite3.sqlite_version`, OS, and Python to
  Source-of-Truth Captures whenever a phase touches SQL or stdlib features.
- Before ranking cost levers, require a measured baseline or an explicit
  "unmeasured" flag in the gameplan overview.
- Check `cz_set_exit_criteria` takes the numeric phase id, not the name — the
  name form fails with "not found in Phase Breakdown".

## Audit findings (`cz_audit`) and how they were resolved

- *Uncommitted work* — committed per phase; tree clean at close.
- *Version drift* — `pyproject` stays 0.2.0 and CHANGELOG carries an
  **Unreleased** section on purpose: the bump belongs to the deploy, which
  needs the O-01 diagnosis first.
- *Clean-environment verification* — affirmed: fresh venv, 217 passed, ruff
  clean.
- *Consumer re-audit* — every tracked dependent cascaded and resolved;
  untracked consumers updated: README, ARCHITECTURE, SECURITY, DEPLOYMENT,
  CHANGELOG, `.env.example`.
- *Claim honesty* — the `/rules` group's parameter annotations were verified
  against discord.py 2.3.2 offline; the commands have **not** been exercised
  against a live Discord guild in this session. Sync globally and try `/rules
  show` on one channel before trusting the UX.

## Open threads (carried forward)

- **O-01** — live deployment shows zero API usage. First step:
  `sudo journalctl -u fargisguard -n 50 --no-pager`. Until resolved, the
  token-architecture gameplan has no measured baseline.
- **O-02** — whether the floor needs an independent classification pass.
  Decide in the token-architecture gameplan once batching cost is known.
- **O-04** — delegated rule authorship (which roles may edit which scopes).
  Belongs to the moderator-UI gameplan.
- **Follow-up release** — drop the legacy `rules` table mirror and
  `channels.is_exempt` once one production release has run on `scoped_rules`.

## Handoff to the next gameplans

- *Token architecture* (batching on a moderator-set interval, Anthropic
  migration, caching): group by `ResolvedRules.key`; the static system turn
  (instructions + floor) is the cacheable prefix; time-box flushes per key so
  per-channel customisation degrades to latency, not to one-call-per-message.
- *Moderator UI*: `rules.snapshot`, `compose_rules`, and `rulecmds.show_reply`
  are the read model; `set_scope_rules`/`clear_scope_rules` the write model.
