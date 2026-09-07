# Changelog

Milestone-level history. Details live in `docs/HARDENING.md` (findings) and
`docs/gameplans/` (the work).

## Unreleased — Token architecture gameplan

- **Classifier moved to Anthropic** (D-011): `claude-haiku-4-5` classifies,
  `claude-sonnet-5` gives a second opinion on any severity-3/4 verdict before a
  member is held. `ANTHROPIC_API_KEY` replaces `OPENAI_API_KEY`; for one release
  the old key alone starts the bot with a warning and every message fails
  closed. The `openai` pin stays one release for rollback.
- **Batching** (D-012): `/batch set <seconds>` (Administrator, 0–300, default
  0 = off) sends messages that share a ruleset in one request; `/batch show`
  reports the interval and queue depth. Verdicts come back as structured JSON
  keyed by message id and fail closed per id (D-013). A stop drains the queue;
  `deploy/fargisguard.service` gains `TimeoutStopSec=40`.
- Prompt caching deliberately not used: the prefix is below Haiku 4.5's
  minimum cacheable size (D-014).

## Unreleased — Scoped moderation rules gameplan

- Rules can be authored per guild, category, channel, and thread (rules.py);
  legacy guild rules are migrated in place and mirrored for one release.
- Scope resolution runs inside the fail-closed boundary; a thread whose parent
  is gone is a mod-log error, never a silent guild-scope fallback (D-010).
- `/rules category|channel|thread <target> <text>`, `/rules clear`, and
  `/rules show` (Administrator): author rules per scope as plain sentences and
  see exactly what the classifier enforces in a channel, floor included.
- The classifier now enforces the composed scoped rules for the channel (and
  thread) a message was posted in; `LOG_LEVEL=DEBUG` logs the ruleset key and
  token usage per call.
- **Behaviour change:** NSFW-flagged channels are classified against their own
  rules instead of being skipped (D-007). A code-owned safety floor
  (`ai_engine.SAFETY_FLOOR`) applies in every channel and no rule text can
  relax it (D-008).

## 0.2.0 — 2026-09-06 — Hardening gameplan

The prototype's README promised human-supervised moderation, escalation, and
appeals; the code auto-banned on raw model output. This release makes the
README true.

### Security
- The committed EC2 private key is removed from the tree; `*.pem`, `*.key`,
  `.env.*` are gitignored. Rotation and history scrub are documented in
  `docs/DEPLOYMENT.md` (H-01 — owner action still required).
- `/setrules` now actually requires Administrator (the previous decorator was
  inert on app commands) (H-02).
- The model's verdict is advisory: strict parsing, rules passed as delimited
  data, and kick/ban require `/modaction` approval by a moderator (H-03).
- Dashboard binds loopback, requires a bearer token, and does not start
  without one (H-04).
- The moderation pipeline fails closed: errors and unparseable replies go to
  `#mod-logs` (H-05).
- NSFW exemption uses Discord's channel flag; immunity uses permissions/role
  IDs, never names (H-10).
- No more echoing model output into the channel (H-09).

### Fixed
- Severity-2 timeouts crashed on `discord.timedelta` (H-06).
- Slash commands were never synced; the dashboard restarted on every
  reconnect (H-11).
- `openai==1.10.0` and `fastapi==0.110.0` could not import against current
  httpx; both bumped (H-13).

### Added
- Warning escalation, pending-action review (`/modaction`), appeals
  resolution (`/appeals`, `/appeal_resolve`), `/pending` dashboard route.
- Async OpenAI client with timeout; per-call SQLite connections with
  `DB_PATH`; startup validation of required secrets.
- 148-test offline suite (pytest) and ruff; `requirements-dev.txt`.
- `deploy/fargisguard.service`, `docs/DEPLOYMENT.md`, Clauderizer memory
  under `docs/`.

## 0.1.0 — initial upload
