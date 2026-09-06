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
sudoedit /etc/fargisguard/env     # set DISCORD_TOKEN, OPENAI_API_KEY, DB_PATH, DASHBOARD_TOKEN

sudo cp /opt/fargisguard/deploy/fargisguard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fargisguard
sudo journalctl -u fargisguard -f
```

`config.py` fails at startup naming any missing required variable, so a bad
`EnvironmentFile` shows up in `journalctl` immediately rather than as a
mysterious API error later.

## Upgrading

```bash
cd /opt/fargisguard && sudo -u fargisguard git pull
sudo -u fargisguard venv/bin/pip install -r requirements.txt
sudo -u fargisguard cp "$DB_PATH" "$DB_PATH.bak-$(date +%F)"   # DB_PATH as set in /etc/fargisguard/env
sudo systemctl restart fargisguard
```

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
