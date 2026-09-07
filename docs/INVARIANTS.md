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

### INVARIANT-06 — Tests never contact Discord or any model provider (OpenAI, Anthropic, or a successor); every network boundary is behind a pure, injectable function so the suite runs offline. Generalises INVARIANT-04's provider wording.
**Introduced by**: 2026-09-07-token-architecture planning (D-011)

Tests never contact Discord or any model provider (OpenAI, Anthropic, or a successor); every network boundary is behind a pure, injectable function so the suite runs offline. Generalises INVARIANT-04's provider wording.

### INVARIANT-07 — No raw message content, appeal text, or rules text ever appears in a log record, a metric, or an HTTP response body outside the authenticated moderator UI: observability carries only IDs, content hashes, lengths, counts, durations, and enum states. Jump URLs are the sanctioned way to point a human at a message.
**Introduced by**: 2026-09-07-operational-truth-observability-durable-queue-moderator-ui

No raw message content, appeal text, or rules text ever appears in a log record, a metric, or an HTTP response body outside the authenticated moderator UI: observability carries only IDs, content hashes, lengths, counts, durations, and enum states. Jump URLs are the sanctioned way to point a human at a message.

### INVARIANT-08 — No path through the moderation pipeline returns without leaving a trace: every early return, skip, and swallowed exception emits a log record naming the reason. Silence is reserved for the case where nothing happened because nothing arrived.
**Introduced by**: 2026-09-07-operational-truth-observability-durable-queue-moderator-ui

No path through the moderation pipeline returns without leaving a trace: every early return, skip, and swallowed exception emits a log record naming the reason. Silence is reserved for the case where nothing happened because nothing arrived.

### INVARIANT-09 — Every state-mutating moderator action records a resolvable Discord user id for the moderator who took it, whether it originated from a slash command or the web UI. No shared or machine credential may stand in for a human identity in an audit field.
**Introduced by**: 2026-09-07-operational-truth-observability-durable-queue-moderator-ui

Every state-mutating moderator action records a resolvable Discord user id for the moderator who took it, whether it originated from a slash command or the web UI. No shared or machine credential may stand in for a human identity in an audit field.
