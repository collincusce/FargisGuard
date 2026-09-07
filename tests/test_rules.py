"""Scoped rules storage (gameplan D-009 / D2): scopes, version counter, migration."""

import sqlite3

import pytest

import rules
from database import connect
from rules import (
    CATEGORY,
    CHANNEL,
    DEFAULT_RULES,
    GUILD,
    GUILD_SCOPE_ID,
    THREAD,
    clear_scope_rules,
    get_rules,
    get_rules_version,
    get_scope_rules,
    list_scope_rules,
    set_rules,
    set_scope_rules,
    validate_scope,
)

G = 4242


def _legacy_db(path, rows):
    raw = sqlite3.connect(path)
    raw.executescript("CREATE TABLE rules (guild_id INTEGER PRIMARY KEY, content TEXT NOT NULL);")
    raw.executemany("INSERT INTO rules VALUES (?, ?)", rows)
    raw.commit()
    raw.close()


# --- validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    "kind, scope_id",
    [("nope", 1), (GUILD, 5), (CHANNEL, 0), (CATEGORY, -1), (THREAD, "7"), (CHANNEL, True)],
)
def test_validate_scope_rejects_malformed_keys(kind, scope_id):
    with pytest.raises(ValueError):
        validate_scope(kind, scope_id)


def test_validate_scope_accepts_each_kind():
    validate_scope(GUILD, GUILD_SCOPE_ID)
    for kind in (CATEGORY, CHANNEL, THREAD):
        validate_scope(kind, 123456789012345678)


# --- guild-only compatibility ---------------------------------------------------


def test_get_rules_seeds_default_on_a_cold_guild_and_bumps_version():
    assert get_rules_version(G) == 0
    assert get_rules(G) == DEFAULT_RULES
    assert get_rules_version(G) == 1
    assert get_rules(G) == DEFAULT_RULES  # a read is not a write
    assert get_rules_version(G) == 1


def test_set_rules_is_the_guild_scope_and_mirrors_the_legacy_table():
    set_rules(G, "be kind")
    assert get_rules(G) == "be kind"
    assert get_scope_rules(G, GUILD, GUILD_SCOPE_ID) == "be kind"
    with connect() as conn:
        row = conn.execute("SELECT content FROM rules WHERE guild_id=?", (G,)).fetchone()
    assert row["content"] == "be kind"


# --- scoped writes --------------------------------------------------------------


def test_every_write_path_bumps_the_version():
    v0 = get_rules_version(G)
    v1 = set_scope_rules(G, CHANNEL, 10, "videos only")
    v2 = set_scope_rules(G, CHANNEL, 10, "videos only")  # same text still counts as a write
    assert clear_scope_rules(G, CHANNEL, 10) is True
    v3 = get_rules_version(G)
    assert clear_scope_rules(G, CHANNEL, 10) is False  # nothing to delete...
    v4 = get_rules_version(G)  # ...but the version still moves, keeping memos honest
    assert (v0, v1, v2, v3, v4) == (0, 1, 2, 3, 4)


def test_scopes_are_independent_and_listed_stably():
    set_scope_rules(G, GUILD, GUILD_SCOPE_ID, "g")
    set_scope_rules(G, CATEGORY, 2, "cat")
    set_scope_rules(G, CHANNEL, 3, "chan")
    set_scope_rules(G, THREAD, 3, "thr")
    set_scope_rules(G + 1, CHANNEL, 3, "other guild")
    assert get_scope_rules(G, CHANNEL, 3) == "chan"
    assert get_scope_rules(G, THREAD, 3) == "thr"
    assert get_scope_rules(G, CHANNEL, 999) is None
    assert [(r["scope_kind"], r["scope_id"], r["content"]) for r in list_scope_rules(G)] == [
        (CATEGORY, 2, "cat"),
        (CHANNEL, 3, "chan"),
        (GUILD, 0, "g"),
        (THREAD, 3, "thr"),
    ]


def test_versions_are_per_guild():
    set_scope_rules(G, CHANNEL, 1, "x")
    assert get_rules_version(G + 1) == 0


# --- migration ------------------------------------------------------------------


def test_legacy_rules_rows_are_backfilled_as_guild_scope(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    _legacy_db(old, [(1, "one"), (2, "two")])
    monkeypatch.setenv("DB_PATH", str(old))

    assert get_scope_rules(1, GUILD, GUILD_SCOPE_ID) == "one"
    assert get_scope_rules(2, GUILD, GUILD_SCOPE_ID) == "two"
    assert get_rules(1) == "one"  # no re-seeding over migrated text
    with connect() as conn:
        legacy = conn.execute("SELECT guild_id, content FROM rules ORDER BY guild_id").fetchall()
        applied = conn.execute("SELECT name FROM schema_migrations").fetchall()
    assert [tuple(r) for r in legacy] == [(1, "one"), (2, "two")]  # untouched
    assert [r["name"] for r in applied] == ["2026-09-06-backfill-scoped-rules"]


def test_backfill_runs_once_and_never_overwrites_newer_scoped_text(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    _legacy_db(old, [(1, "legacy")])
    monkeypatch.setenv("DB_PATH", str(old))
    set_scope_rules(1, GUILD, GUILD_SCOPE_ID, "edited after migration")

    # A fresh process re-running init_db must not resurrect the legacy text.
    import database

    database._initialized.discard(str(old))
    database.init_db(str(old))
    assert get_scope_rules(1, GUILD, GUILD_SCOPE_ID) == "edited after migration"


def test_default_rules_are_unchanged_by_the_refactor():
    assert rules.DEFAULT_RULES.startswith("1. No harassment")
