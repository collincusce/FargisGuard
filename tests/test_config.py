import importlib.util
from pathlib import Path

import pytest

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


def _load_fresh_config():
    """Execute config.py as a brand-new module object.

    Leaves sys.modules['config'] untouched, so other tests keep the class
    identities they imported (a reload would mint new ones).
    """
    path = Path(__file__).resolve().parent.parent / "config.py"
    spec = importlib.util.spec_from_file_location("config_fresh", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_fails_fast_without_discord_token(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_TOKEN is not set"):
        _load_fresh_config()


def test_import_fails_fast_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        _load_fresh_config()


def test_import_succeeds_with_both_secrets(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "t")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    module = _load_fresh_config()
    assert module.DISCORD_TOKEN == "t" and module.OPENAI_API_KEY == "k"


def test_log_level_is_validated_and_uppercased():
    import logging

    import config

    assert config.LOG_LEVEL in logging.getLevelNamesMapping()
    assert config.LOG_LEVEL == config.LOG_LEVEL.upper()
