"""Runtime configuration.

Every secret comes from the environment (INVARIANT-01). Required variables
are validated at import so a misconfigured service fails at startup with the
variable's name instead of failing later inside a Discord or OpenAI call.
"""

import os
from collections.abc import Mapping

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """A required environment variable is missing or blank."""


def require_env(name: str, env: Mapping[str, str] | None = None) -> str:
    """Return the non-blank value of ``name`` or raise ``ConfigError`` naming it."""
    source = os.environ if env is None else env
    value = (source.get(name) or "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set; add it to .env (local) or the service EnvironmentFile (EC2)"
        )
    return value


def optional_env(name: str, default: str, env: Mapping[str, str] | None = None) -> str:
    """Return ``name`` from the environment, or ``default`` when unset or blank."""
    source = os.environ if env is None else env
    value = (source.get(name) or "").strip()
    return value or default


def parse_id_list(raw: str, *, name: str = "value") -> frozenset[int]:
    """Parse a comma-separated list of Discord snowflake IDs; blanks are ignored."""
    ids: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if not token.isdigit():
            raise ConfigError(f"{name} must be comma-separated integer IDs, got {token!r}")
        ids.add(int(token))
    return frozenset(ids)


load_dotenv()

DISCORD_TOKEN = require_env("DISCORD_TOKEN")
OPENAI_API_KEY = require_env("OPENAI_API_KEY")

MOD_LOG_CHANNEL = optional_env("MOD_LOG_CHANNEL", "mod-logs")
DASHBOARD_PORT = int(optional_env("DASHBOARD_PORT", "8000"))
# Loopback by default; put a reverse proxy in front for remote access (D3).
DASHBOARD_HOST = optional_env("DASHBOARD_HOST", "127.0.0.1")
# Empty means the dashboard is not started at all.
DASHBOARD_TOKEN = optional_env("DASHBOARD_TOKEN", "")

# Role IDs (not names) whose holders are never auto-moderated; administrators and
# anyone with manage_messages are immune regardless (INVARIANT-05).
IMMUNE_ROLE_IDS = parse_id_list(optional_env("IMMUNE_ROLE_IDS", ""), name="IMMUNE_ROLE_IDS")
