# FargisGuard — Security

## Auth model

- **Discord side.** The bot acts with its own token. Moderator commands are
  gated with `discord.app_commands.checks.has_permissions` *and*
  `default_permissions` (the `discord.ext.commands` decorators are inert on app
  commands — H-02): `/setrules` Administrator, `/modaction` Ban Members,
  `/appeals` and `/appeal_resolve` Manage Guild.
- **Dashboard.** Loopback by default; every data route requires
  `Authorization: Bearer <DASHBOARD_TOKEN>` (constant-time compare). Without a
  token the dashboard is not started. Remote access goes through a reverse
  proxy or SSH tunnel.

## Threat model

1. **Prompt injection** — message content or rules text steering the
   classifier. Mitigations: the verdict is advisory (INVARIANT-02); only an
   exact `VIOLATION|1..4|reason` is acted on; rules are delimited data in the
   user turn, not system-prompt text; severity ≥ 3 needs a human via
   `/modaction`. Worst case for a successful injection is a 60-minute timeout,
   not a ban. Since D-007, NSFW-flagged channels are classified too, so
   injection there is in scope — and it is the channel where a successful
   "relax the rules" injection matters most. That is why the safety floor
   (D-008) is a separate `<floor>` region in the static system turn, defined in
   code (`ai_engine.SAFETY_FLOOR`) rather than any table a command can write:
   scope text can add allowances, never remove the floor. Whether the floor
   also needs an independent classification pass is tracked as an open item.
2. **Rule-authorship privilege** — a narrower-scope rule relaxing a wider one.
   Every scope-authoring command is Administrator-only for now (gameplan D1);
   delegation is a product decision deferred to the moderator UI.
3. **Privilege escalation via string matching** — mitigated by INVARIANT-05:
   scopes are keyed by channel/category IDs; immunity uses permissions/role IDs.
4. **Fail-open outages** — an API error must not let content through
   unreviewed. Mitigation: INVARIANT-03; errors and unparseable replies are
   posted to mod-log with the message link.
5. **Data exposure** — warnings, appeals, and pending actions are personal
   data. Mitigation: dashboard auth + loopback; SQLite file lives in a
   directory only the service user can read.
6. **Free model access** — the bot never echoes model output (H-09).

## Secrets policy

INVARIANT-01: nothing secret in the tree. `.env` locally, systemd
`EnvironmentFile` in production. `*.pem`, `*.key`, `.env*` are gitignored;
`config.py` refuses to start without the required variables. A key found in
history is treated as compromised and rotated at the provider, not merely
deleted — runbook in `docs/DEPLOYMENT.md` (H-01).

## Dependency hygiene

`requirements.txt` pins direct dependencies only; two of them were broken by
an unpinned transitive (`httpx`) during the hardening gameplan (H-13). Verify
installs in a fresh venv, and consider a full `pip freeze` lock for the host.
