# FargisGuard — Security

## Auth model

- **Discord side.** The bot acts with its own bot token. Administrative slash
  commands must be gated with `discord.app_commands` permission checks *and*
  `default_permissions` (the `discord.ext.commands` decorators do nothing on
  app commands — H-02).
- **Dashboard.** Loopback-only by default; remote access requires a bearer
  token supplied via `DASHBOARD_TOKEN` and should sit behind a reverse proxy.

## Threat model (what we defend against)

1. **Prompt injection** — message content or guild rules steering the
   classifier. Mitigation: the model's verdict is advisory (INVARIANT-02);
   severity ≥ 3 requires a human; rules are passed as delimited data, never
   as system-prompt instructions.
2. **Privilege escalation via string matching** — a role named "Moderator" or
   a channel named "nsfw". Mitigation: INVARIANT-05.
3. **Fail-open outages** — an API error must not let content through
   unreviewed. Mitigation: INVARIANT-03.
4. **Data exposure** — warnings and appeals are personal data. Mitigation:
   dashboard auth and loopback binding.

## Secrets policy

INVARIANT-01: nothing secret in the tree. `.env` locally, systemd
`EnvironmentFile` in production. `*.pem`, `*.key`, `.env*` are gitignored.
A key found in history is treated as compromised and rotated at the provider,
not merely deleted (H-01).
