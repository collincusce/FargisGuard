# Changelog

Milestone-level history. Details live in `docs/HARDENING.md` (findings) and
`docs/gameplans/` (the work).

## Unreleased — Scoped moderation rules gameplan

- Rules can be authored per guild, category, channel, and thread (rules.py);
  legacy guild rules are migrated in place and mirrored for one release.
- Scope resolution runs inside the fail-closed boundary; a thread whose parent
  is gone is a mod-log error, never a silent guild-scope fallback (D-010).
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
