# Invariants

Rules that hold across all work. Append-only. Numbered `INVARIANT-NN`.

## Invariants

_(Add entries with `cz_add_invariant`.)_

### INVARIANT-01 — No credential, private key, or token is ever committed to the repository; runtime secrets come only from the environment (.env locally, systemd EnvironmentFile on EC2).
**Introduced by**: onboarding audit 2026-09-06

No credential, private key, or token is ever committed to the repository; runtime secrets come only from the environment (.env locally, systemd EnvironmentFile on EC2).

### INVARIANT-02 — Model output is advisory, never authority: a parsed verdict must be validated (integer severity in 1..4, non-empty reason) and an irreversible action (kick, ban) is never taken on model output alone.
**Introduced by**: onboarding audit 2026-09-06

Model output is advisory, never authority: a parsed verdict must be validated (integer severity in 1..4, non-empty reason) and an irreversible action (kick, ban) is never taken on model output alone.

### INVARIANT-03 — The moderation path fails closed: any error in AI analysis or punishment is logged to the mod-log channel for human review and never silently lets the message stand unreviewed.
**Introduced by**: onboarding audit 2026-09-06

The moderation path fails closed: any error in AI analysis or punishment is logged to the mod-log channel for human review and never silently lets the message stand unreviewed.

### INVARIANT-04 — Tests never contact Discord or OpenAI; every network boundary is behind a pure, injectable function so the suite runs offline.
**Introduced by**: onboarding audit 2026-09-06

Tests never contact Discord or OpenAI; every network boundary is behind a pure, injectable function so the suite runs offline.

### INVARIANT-05 — Privilege checks use Discord permissions or role IDs from config, never role-name strings; channel exemptions use the channel's NSFW flag, never its name.
**Introduced by**: onboarding audit 2026-09-06

Privilege checks use Discord permissions or role IDs from config, never role-name strings; channel exemptions use the channel's NSFW flag, never its name.
