# FargisGuard — Deployment

Single EC2 instance, systemd-managed, secrets in an `EnvironmentFile`. There is
no CI/CD pipeline; deploys are `git pull` + restart.

## Layout on the host

```
/opt/fargisguard/            # git checkout, owned by user fargisguard
/opt/fargisguard/venv/       # python -m venv venv && venv/bin/pip install -r requirements.txt
/opt/fargisguard/data/       # DB_PATH=/opt/fargisguard/data/moderation.db
/etc/fargisguard/env         # secrets; root:fargisguard, mode 0640
/etc/systemd/system/fargisguard.service   # copy of deploy/fargisguard.service
```

## First install

```bash
sudo useradd --system --home /opt/fargisguard --shell /usr/sbin/nologin fargisguard
sudo git clone https://github.com/<you>/FargisGuard /opt/fargisguard
sudo -u fargisguard python3 -m venv /opt/fargisguard/venv
sudo -u fargisguard /opt/fargisguard/venv/bin/pip install -r /opt/fargisguard/requirements.txt
sudo install -d -o fargisguard -g fargisguard /opt/fargisguard/data

sudo install -d -m 0750 -o root -g fargisguard /etc/fargisguard
sudo cp /opt/fargisguard/.env.example /etc/fargisguard/env
sudo chmod 0640 /etc/fargisguard/env && sudo chown root:fargisguard /etc/fargisguard/env
sudoedit /etc/fargisguard/env     # set DISCORD_TOKEN, ANTHROPIC_API_KEY, DB_PATH, DASHBOARD_TOKEN (LOG_LEVEL=DEBUG logs per-request token usage)

sudo cp /opt/fargisguard/deploy/fargisguard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fargisguard
sudo journalctl -u fargisguard -f
```

`config.py` fails at startup naming any missing required variable, so a bad
`EnvironmentFile` shows up in `journalctl` immediately rather than as a
mysterious API error later.

## Upgrading

> **Token-architecture release note (do these in order).**
> 1. **Tell your moderators** that they can turn on batching with
>    `/batch set <seconds>`; while it is on, a message — including a severe
>    one — stays visible until its batch is checked (at most 300 s, or 25
>    messages). Batching is **off** for every server until a moderator opts in.
> 2. **Before restarting**, add `ANTHROPIC_API_KEY=sk-ant-...` to
>    `/etc/fargisguard/env`. The classifier moved from OpenAI to Anthropic
>    (Haiku 4.5, with a Sonnet 5 second opinion before any kick/ban hold).
>    A file that still has only `OPENAI_API_KEY` starts the service with a
>    WARNING in `journalctl` and every message fails closed to `#mod-logs`
>    until the key is added; a file with neither key refuses to start.
>    `OPENAI_API_KEY` can be removed once the new key is in place.
> 3. `deploy/fargisguard.service` now sets `TimeoutStopSec=40` so a stop can
>    drain queued batches (20 s budget + one request timeout). Re-copy the
>    unit and `systemctl daemon-reload` before the restart.
> 4. After the restart, with `LOG_LEVEL=DEBUG`, confirm one real
>    classification in `journalctl`: a line
>    `classify tier=batch ruleset=… batch=1 stop=end_turn input_tokens=N …`
>    with numeric token fields. That is the first live proof the migration
>    works (nothing in this release was exercised against the live API).

> **Scoped-rules release note.** After this release, channels Discord marks
> NSFW are classified like every other channel (they were skipped before).
> Their guild rules apply until a moderator sets channel-scope rules for them;
> the safety floor in `ai_engine.SAFETY_FLOOR` applies everywhere and cannot be
> relaxed by any rule text. Tell your moderators before restarting.

```bash
cd /opt/fargisguard && sudo -u fargisguard git pull
sudoedit /etc/fargisguard/env                                  # add ANTHROPIC_API_KEY (token-architecture release)
sudo cp deploy/fargisguard.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo -u fargisguard venv/bin/pip install -r requirements.txt
sudo -u fargisguard cp "$DB_PATH" "$DB_PATH.bak-$(date +%F)"   # DB_PATH as set in /etc/fargisguard/env
sudo systemctl restart fargisguard
sudo journalctl -u fargisguard -n 50 --no-pager               # no ConfigError; a `classify tier=` line once traffic flows
```

Rollback: `git checkout <previous-tag>`, restore the `.bak` file, restart. The
`openai` pin is kept for one release so the previous tag still imports without
a `pip install` step.

Schema changes are applied automatically on first connection
(`database.MIGRATIONS`); the SQLite file is never dropped. Take the backup
anyway: `ADD COLUMN` migrations are safe to re-run, but a release that creates
or copies tables (the scoped-rules release and later) has no transactional
rollback in SQLite, and a backup file plus `git checkout <previous-tag>` is the
whole recovery plan.

## Dashboard access

The dashboard binds `127.0.0.1` and requires `DASHBOARD_TOKEN`. For remote
access put nginx (or an SSH tunnel) in front of it; never change
`DASHBOARD_HOST` to `0.0.0.0` on a public instance.

```bash
ssh -L 8000:127.0.0.1:8000 ec2-user@<host>
curl -H "Authorization: Bearer $DASHBOARD_TOKEN" http://127.0.0.1:8000/pending
```

## Runbook: rotate the instance SSH key (H-01)

An RSA private key was committed to this repository's history
(`FargisGuard.pem`, commit `55ceedd`). It was removed from the tree in the
hardening gameplan, but **removal from the tree does not revoke it** — anyone
who cloned or forked before then has it. Treat it as compromised.

Order matters: rotate first, clean history second.

1. **Create a new key pair** (locally, or in the EC2 console → Key Pairs):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/fargisguard-2026 -C fargisguard
   ```
2. **Install the new public key** on the instance using the *old* key one last
   time:
   ```bash
   ssh -i FargisGuard.pem ec2-user@<host> \
     "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys" < ~/.ssh/fargisguard-2026.pub
   ```
3. **Verify** the new key works in a *separate* terminal before continuing:
   ```bash
   ssh -i ~/.ssh/fargisguard-2026 ec2-user@<host> echo ok
   ```
4. **Remove the old public key** from `~/.ssh/authorized_keys` on the instance
   (it is the line whose comment matches the old key pair name), then confirm
   the old private key is rejected:
   ```bash
   ssh -i FargisGuard.pem ec2-user@<host> echo still-works   # must FAIL
   ```
5. **Delete the old key pair** in the EC2 console so it cannot be attached to
   new instances. Shred local copies: `shred -u FargisGuard.pem`.
6. **Scrub git history** (rewrites `main`; coordinate with anyone who has a
   clone — they must re-clone):
   ```bash
   pip install git-filter-repo
   git filter-repo --path FargisGuard.pem --invert-paths
   git push --force --all && git push --force --tags
   ```
   Then ask GitHub Support to purge cached views of the old commits if the
   repository is public.

## Discord developer portal checklist

- Privileged intents: **Message Content**, **Server Members** (both required).
- Bot permissions: Send Messages, Manage Messages, Moderate Members, Kick
  Members, Ban Members.
- A `#mod-logs` text channel the bot can post in.
