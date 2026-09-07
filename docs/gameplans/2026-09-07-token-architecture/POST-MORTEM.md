# Post-mortem — Token Architecture

> Gameplan: 2026-09-07-token-architecture · Closed: 2026-09-07 · 7/7 phases complete
> Suite: 217 → 321 tests, green in the working install and in a fresh venv built from
> `requirements.txt`; `pip check` clean; ruff clean.

## What shipped

- **Anthropic classifier** (`ai_engine.py`, D-011): one `messages.create` per
  batch on `claude-haiku-4-5` with structured output under `VERDICT_SCHEMA`;
  `claude-sonnet-5` re-checks any severity-3/4 verdict before a hold
  (thinking disabled, no sampling parameters). Errors are logged by class and
  re-raised into the fail-closed boundary; a non-`end_turn` stop fails every id.
- **Batch verdict protocol** (`verdict.py`, D-013, supersedes D-001): JSON keyed
  by batch-local id; missing, duplicated, or malformed ids fail closed one at a
  time; invented ids are reported and never applied.
- **Batch queue** (`batcher.py`, D-012, gameplan D1–D3): per-(guild, ruleset-key)
  buckets with frozen rules text and message snapshots; per-bucket timers or a
  25-message cap; swap-and-clear flushes; verdicts in message order with
  same-member hold collapse; one consolidated notice per failed bucket;
  `close()` drains under a deadline and posts "unreviewed" for what did not finish.
- **Per-guild interval** (`batchsettings.py`, gameplan D5): `/batch set` (0 = per
  message, the default and the rollback switch; clamped to 300 s) and
  `/batch show` with queue depth and the exposure-window sentence.
- **Config bridge** (gameplan D4): `ANTHROPIC_API_KEY` wins; a legacy
  `OPENAI_API_KEY` alone starts the service with a warning and fails closed;
  `openai` stays pinned one release for rollback.
- **Release kit**: ordered runbook, `TimeoutStopSec=40`, docs truthed,
  `ext.openai-api` retired, `INVARIANT-06` (provider-neutral offline tests).

## What worked

- **The planning fan-out killed a wrong premise before any code.** The brief
  asked to put the static prefix under prompt caching. The reference docs put
  Haiku 4.5's minimum cacheable prefix at 4096 tokens against our ~350–1100, so
  a breakpoint would have written nothing while paying the write premium.
  D-014 defers caching and names the threshold that brings it back. Batching
  alone carries the estimated ~65% saving.
- **Structured output replaced a fragile protocol.** Per-id JSON under a schema
  made INVARIANT-02 hold per message inside a batch, which the pipe-delimited
  line never could.
- **Injected time made the queue testable.** Timers park on futures the tests
  release by hand; the shutdown drain is proven with a classifier that never
  returns. No wall-clock waits in the suite.
- **The "0 = per message" default meant zero behaviour change on deploy** and
  all 262 pre-batching tests passed unchanged apart from stub signatures.

## What didn't, with root causes

- **A decision named a parameter the SDK does not have.** D-011 said
  "temperature 0 on Haiku"; anthropic 1.4.0's `create()` has no `temperature`
  at all. Caught by `inspect.signature` after the decision was written, not
  before (C-01, L-08). Root cause: I trusted the reference's description of
  the API surface over the pinned SDK's actual signature.
- **A fake lagged the real object.** `FakeMessage` had no `id`, so
  `snapshot_of` raised inside the queueing boundary and the pipeline correctly
  answered `error` — the test read it as a bug in the code. Root cause: the
  fake was extended feature by feature instead of mirroring the attributes the
  real `discord.Message` guarantees.
- **Timer tasks start on the next loop tick.** Three batcher tests released
  timers before the timer coroutine had registered its future. Root cause: a
  `create_task`ed coroutine has not run yet when `enqueue` returns — the tests
  needed a `settle()` before releasing. Obvious in hindsight; worth a line in
  the batcher doc, now present.
- **Still no measured baseline.** Every cost figure in this gameplan is an
  estimate from the reference's worked pricing example (O-02); the live
  deployment has shown zero API traffic (O-04). The measurement line exists;
  the operator's `journalctl` does not yet.

## Procedure improvements

- When a decision names a request parameter, run `inspect.signature` on the
  pinned SDK in the same step and cite it as evidence (L-08).
- Keep `tests/fakes.py` shaped after the real objects' guaranteed attributes,
  not after what the current tests happen to touch.
- Put a "measured / unmeasured" tag on every cost claim in a gameplan
  overview; unmeasured claims may not be quoted outside the gameplan.

## Audit findings (`cz_audit`) and how they were resolved

- *Uncommitted work* — committed per phase; the final promote/post-mortem
  commit closes the tree.
- *Version drift* — `pyproject` stays 0.2.0 and CHANGELOG carries two
  **Unreleased** sections deliberately: the version bump belongs to the deploy,
  which needs the O-04 diagnosis and the first live classification first.
- *Clean-environment verification* — affirmed: a third fresh venv built from
  `requirements.txt` + `requirements-dev.txt` alone, 321 passed, `pip check`
  clean.
- *Consumer re-audit* — every tracked dependent cascaded and resolved (14
  reports); untracked consumers updated: README, ARCHITECTURE, SECURITY (unchanged
  threat model still accurate), DEPLOYMENT, TESTING, CHANGELOG, `.env.example`,
  the systemd unit.
- *Claim honesty* — **nothing here has touched the live Anthropic API or a
  live Discord guild** (O-03). The request shape was verified against the
  installed SDK's signature and types; the response handling against the
  documented shapes. The runbook's step 4 is the first live proof.
- *Shipped-artifact reality* — every command, module, and setting named in the
  CHANGELOG exists and has tests.

## Open threads (carried forward)

- **O-01** — durable queue: a hard crash loses in-memory buckets. Design a
  SQLite-backed queue once batching has run in production.
- **O-02** — confirm pricing against the live pricing page before quoting cost.
- **O-03** — first live classification with `LOG_LEVEL=DEBUG` after deploy.
- **O-04** — the zero-traffic deployment (`journalctl -u fargisguard -n 50`).
- **Next release** — drop the `OPENAI_API_KEY` fallback, the `openai` pin, the
  legacy `rules` table mirror, and `channels.is_exempt`.
- **Caching** — revisit only when a measured prefix exceeds the minimum for the
  model reading it (D-014).

## Handoff to the moderator-UI gameplan

Read model: `rules.snapshot`, `compose_rules`, `rulecmds.show_reply`,
`batchsettings.show_reply`, `Batcher.depth`. Write model: `set_scope_rules`,
`clear_scope_rules`, `set_batch_interval`. Everything a moderator can do from
Discord today is a reply-returning function the UI can call the same way.
