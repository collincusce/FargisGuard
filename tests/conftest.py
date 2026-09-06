"""Shared test setup.

The suite runs fully offline (INVARIANT-04). config.py validates required
secrets at import, so give it harmless placeholders before any module under
test imports it.
"""

import os

os.environ.setdefault("DISCORD_TOKEN", "test-discord-token")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")


import pytest  # noqa: E402 — after the env placeholders on purpose


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Every test gets a fresh SQLite file; nothing touches moderation.db (INVARIANT-04)."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
