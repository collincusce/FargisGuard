import importlib

import pytest

import config
from config import ConfigError, optional_env, require_env


def test_require_env_returns_stripped_value():
    assert require_env("X", {"X": "  abc  "}) == "abc"


@pytest.mark.parametrize("env", [{}, {"X": ""}, {"X": "   "}])
def test_require_env_missing_or_blank_raises_with_name(env):
    with pytest.raises(ConfigError) as exc:
        require_env("X", env)
    assert "X is not set" in str(exc.value)


def test_optional_env_default_when_unset_or_blank():
    assert optional_env("X", "dflt", {}) == "dflt"
    assert optional_env("X", "dflt", {"X": " "}) == "dflt"
    assert optional_env("X", "dflt", {"X": "v"}) == "v"


# importlib.reload re-executes the module and mints a fresh ConfigError class,
# so these two tests match on the RuntimeError base plus the variable name.
def test_import_fails_fast_without_discord_token(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_TOKEN"):
        importlib.reload(config)
    monkeypatch.setenv("DISCORD_TOKEN", "test-discord-token")
    importlib.reload(config)  # restore the module for the rest of the suite


def test_import_fails_fast_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        importlib.reload(config)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    importlib.reload(config)
