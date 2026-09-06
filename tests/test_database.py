import sqlite3

import database
from database import (
    add_pending,
    add_warning,
    connect,
    forgive,
    get_pending,
    get_warnings,
    list_pending,
    resolve_pending,
)


def test_no_module_level_connection_or_cursor():
    assert not hasattr(database, "cursor") and not hasattr(database, "conn")


def test_db_path_comes_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "x.db"))
    assert database.db_path().endswith("x.db")


def test_warning_roundtrip():
    assert get_warnings(1, 2) == 0
    assert add_warning(1, 2) == 1
    assert add_warning(1, 2) == 2
    assert get_warnings(1, 2) == 2
    forgive(1, 2)
    assert get_warnings(1, 2) == 0


def test_pending_lifecycle():
    pid = add_pending(guild_id=10, user_id=20, severity=4, action="ban", reason="hate")
    row = get_pending(pid)
    assert row["status"] == "pending" and row["action"] == "ban" and row["created_at"]
    assert [r["id"] for r in list_pending(10)] == [pid]
    assert list_pending(11) == []
    assert resolve_pending(pid, "approved", resolved_by=99) is True
    assert resolve_pending(pid, "denied", resolved_by=99) is False  # already resolved
    row = get_pending(pid)
    assert row["status"] == "approved" and row["resolved_by"] == 99 and row["resolved_at"]
    assert list_pending(10) == []


def test_rollback_on_error():
    try:
        with connect() as conn:
            conn.execute("INSERT INTO rules (guild_id, content) VALUES (1, 'x')")
            raise RuntimeError("abort")
    except RuntimeError:
        pass
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 0


def test_migration_adds_columns_to_an_old_appeals_table(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    raw = sqlite3.connect(old)
    raw.executescript(
        "CREATE TABLE appeals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
        "guild_id INTEGER, reason TEXT, status TEXT);"
        "INSERT INTO appeals (user_id, guild_id, reason, status) VALUES (1, 2, 'r', 'pending');"
    )
    raw.commit()
    raw.close()
    monkeypatch.setenv("DB_PATH", str(old))
    with connect() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(appeals)")}
        assert {"created_at", "resolved_by", "resolved_at"} <= cols
        assert conn.execute("SELECT COUNT(*) FROM appeals").fetchone()[0] == 1
