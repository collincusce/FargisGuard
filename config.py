"""Runtime configuration.

Every secret comes from the environment (INVARIANT-01). Required variables
are validated at import so a misconfigured service fails at startup with the
variable's name instead of failing later inside a Discord or model-provider call.
"""

import logging
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


def resolve_model_key(env: Mapping[str, str] | None = None) -> tuple[str, str | None]:
    """The Anthropic key, plus a warning when only the legacy OpenAI key is present.

    One-release bridge (gameplan D4): an EnvironmentFile that still carries
    OPENAI_API_KEY starts the service — so the operator sees the warning in
    journalctl instead of a crash loop — and classification fails closed until
    ANTHROPIC_API_KEY is added. With neither key, fail fast naming the new one.
    """
    anthropic_key = optional_env("ANTHROPIC_API_KEY", "", env)
    if anthropic_key:
        return anthropic_key, None
    if optional_env("OPENAI_API_KEY", "", env):
        return "", (
            "ANTHROPIC_API_KEY is not set but OPENAI_API_KEY is: the classifier moved to "
            "Anthropic (D-011). Every message will fail closed to mod-log until "
            "ANTHROPIC_API_KEY is added to the EnvironmentFile and the service restarted."
        )
    raise ConfigError(
        "ANTHROPIC_API_KEY is not set; add it to .env (local) or the service EnvironmentFile (EC2)"
    )


load_dotenv()

DISCORD_TOKEN = require_env("DISCORD_TOKEN")
ANTHROPIC_API_KEY, _model_key_warning = resolve_model_key()
if _model_key_warning:
    logging.getLogger(__name__).warning(_model_key_warning)

MOD_LOG_CHANNEL = optional_env("MOD_LOG_CHANNEL", "mod-logs")
DASHBOARD_PORT = int(optional_env("DASHBOARD_PORT", "8000"))
# Loopback by default; put a reverse proxy in front for remote access (D3).
DASHBOARD_HOST = optional_env("DASHBOARD_HOST", "127.0.0.1")
# Empty means the dashboard is not started at all.
DASHBOARD_TOKEN = optional_env("DASHBOARD_TOKEN", "")

# Python logging level name; DEBUG adds one line per classification with the
# ruleset key and token usage (the batching/caching baseline).
LOG_LEVEL = optional_env("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
    raise ConfigError(f"LOG_LEVEL must be a Python logging level name, got {LOG_LEVEL!r}")

# Role IDs (not names) whose holders are never auto-moderated; administrators and
# anyone with manage_messages are immune regardless (INVARIANT-05).
IMMUNE_ROLE_IDS = parse_id_list(optional_env("IMMUNE_ROLE_IDS", ""), name="IMMUNE_ROLE_IDS")
