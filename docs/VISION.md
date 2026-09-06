# FargisGuard — Vision

FargisGuard is an AI-assisted trust & safety bot for Discord communities. It
reads every message in a guild, asks a language model whether the message
breaks the guild's own written rules, and applies a graduated response —
warn, timeout, kick, ban — while logging every action to a moderator channel.

## What makes it different

- **Guild-authored rules.** Each server stores its own rules text; the model is
  judged against *those* rules, not a fixed global policy.
- **Graduated, reviewable enforcement.** Severity is a 1–4 ladder. Low
  severities act immediately and reversibly; high severities are meant to be
  human-approved (the code did not do this at onboarding — see `HARDENING.md`).
- **Isolated NSFW zone.** One designated channel is exempt from AI review and is
  moderated by humans only.
- **Appeals.** A punished user can file an appeal a moderator can act on.

## Scope boundaries

- Single-process bot on one host (EC2 + systemd). No multi-tenant SaaS, no
  horizontal scaling.
- SQLite is the only store.
- The model is a classifier, never a chat participant: FargisGuard does not
  answer questions or converse in-channel.

## Non-goals

- Replacing human moderators. The model proposes; humans hold the ban button.
- Image/attachment moderation (text only at present).
