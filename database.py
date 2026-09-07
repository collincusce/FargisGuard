"""SQLite persistence: one short-lived connection per call (gameplan D4).

``DB_PATH`` (environment) selects the file; tests point it at a temp file. The
schema is applied lazily the first time a path is opened in this process, so
callers never need to remember an init step. There is deliberately no
module-level connection or cursor (H-08).

Three migration layers run in order inside ``init_db``: ``SCHEMA`` (idempotent
``CREATE TABLE IF NOT EXISTS``), ``MIGRATIONS`` (columns added after a table
shipped), and ``SCRIPTS`` (one-shot data moves, each recorded by name in
``schema_migrations`` so it runs exactly once per database file).
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

DEFAULT_DB_PATH = "moderation.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS warnings (
    user_id  INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    count    INTEGER NOT NULL,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS rules (
    guild_id INTEGER PRIMARY KEY,
    content  TEXT NOT NULL
);

-- Scoped rules (gameplan D-009). scope_id is 0 for the guild scope, otherwise the
-- Discord snowflake of the category or channel (thread scope is keyed by the
-- parent channel). The legacy ``rules`` table stays mirrored for one release (D2).
CREATE TABLE IF NOT EXISTS scoped_rules (
    guild_id   INTEGER NOT NULL,
    scope_kind TEXT    NOT NULL,
    scope_id   INTEGER NOT NULL,
    content    TEXT    NOT NULL,
    PRIMARY KEY (guild_id, scope_kind, scope_id)
);

-- Bumped on every rules write; the composer's memo is invalidated by it.
CREATE TABLE IF NOT EXISTS rules_version (
    guild_id INTEGER PRIMARY KEY,
    version  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    name       TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appeals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    guild_id    INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT,
    resolved_by INTEGER,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS pending_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    severity    INTEGER NOT NULL,
    action      TEXT NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    resolved_by INTEGER,
    resolved_at TEXT
);
"""

# Columns added after the original schema shipped; applied to pre-existing files.
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("appeals", "created_at", "TEXT"),
    ("appeals", "resolved_by", "INTEGER"),
    ("appeals", "resolved_at", "TEXT"),
)

# One-shot scripts, applied once per file in this order and recorded by name.
# Each must be safe against a partially-applied predecessor (hence OR IGNORE).
SCRIPTS: tuple[tuple[str, str], ...] = (
    (
        "2026-09-06-backfill-scoped-rules",
        "INSERT OR IGNORE INTO scoped_rules (guild_id, scope_kind, scope_id, content) "
        "SELECT guild_id, 'guild', 0, content FROM rules",
    ),
)

_initialized: set[str] = set()


def db_path() -> str:
    return os.environ.get("DB_PATH") or DEFAULT_DB_PATH


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> bool:
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in present:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    return True


def _apply_script(conn: sqlite3.Connection, name: str, sql: str) -> bool:
    """Run ``sql`` once per database file, keyed by ``name``. True if it ran now."""
    done = conn.execute("SELECT 1 FROM schema_migrations WHERE name=?", (name,)).fetchone()
    if done:
        return False
    conn.execute(sql)
    conn.execute(
        "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)", (name, now_iso())
    )
    return True


def init_db(path: str | None = None) -> None:
    """Create tables and apply column and script migrations. Idempotent."""
    target = path or db_path()
    conn = sqlite3.connect(target)
    try:
        conn.executescript(SCHEMA)
        for table, column, decl in MIGRATIONS:
            _ensure_column(conn, table, column, decl)
        for name, sql in SCRIPTS:
            _apply_script(conn, name, sql)
        conn.commit()
    finally:
        conn.close()
    _initialized.add(target)


@contextmanager
def connect(path: str | None = None) -> Iterator[sqlite3.Connection]:
    """A fresh connection with dict-like rows; commits on success, rolls back on error."""
    target = path or db_path()
    if target not in _initialized:
        init_db(target)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- warnings -------------------------------------------------------------------


def add_warning(user_id: int, guild_id: int) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT count FROM warnings WHERE user_id=? AND guild_id=?", (user_id, guild_id)
        ).fetchone()
        count = (row["count"] + 1) if row else 1
        conn.execute(
            "INSERT INTO warnings (user_id, guild_id, count) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET count=excluded.count",
            (user_id, guild_id, count),
        )
        return count


def get_warnings(user_id: int, guild_id: int) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT count FROM warnings WHERE user_id=? AND guild_id=?", (user_id, guild_id)
        ).fetchone()
        return row["count"] if row else 0


def forgive(user_id: int, guild_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM warnings WHERE user_id=? AND guild_id=?", (user_id, guild_id))


# --- pending actions (gameplan D2) ---------------------------------------------


def add_pending(guild_id: int, user_id: int, severity: int, action: str, reason: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO pending_actions (guild_id, user_id, severity, action, reason, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, severity, action, reason, now_iso()),
        )
        return int(cur.lastrowid)


def append_pending_reason(pending_id: int, extra: str) -> bool:
    """Add ``extra`` to a still-pending action's reason (same member, same batch — D3)."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE pending_actions SET reason = reason || ? WHERE id=? AND status='pending'",
            (extra, pending_id),
        )
        return cur.rowcount == 1


def get_pending(pending_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM pending_actions WHERE id=?", (pending_id,)).fetchone()
        return dict(row) if row else None


def list_pending(guild_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM pending_actions WHERE guild_id=? AND status='pending' ORDER BY id",
            (guild_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def resolve_pending(pending_id: int, status: str, resolved_by: int) -> bool:
    """Mark a pending row approved/denied. False if it was not pending."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE pending_actions SET status=?, resolved_by=?, resolved_at=? "
            "WHERE id=? AND status='pending'",
            (status, resolved_by, now_iso(), pending_id),
        )
        return cur.rowcount == 1


# --- appeals --------------------------------------------------------------------


def has_pending_appeal(user_id: int, guild_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM appeals WHERE user_id=? AND guild_id=? AND status='pending' LIMIT 1",
            (user_id, guild_id),
        ).fetchone()
        return row is not None


def get_appeal(appeal_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM appeals WHERE id=?", (appeal_id,)).fetchone()
        return dict(row) if row else None


def list_pending_appeals(guild_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM appeals WHERE guild_id=? AND status='pending' ORDER BY id", (guild_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def resolve_appeal(appeal_id: int, status: str, resolved_by: int) -> bool:
    """Mark an appeal approved/denied. False if it was not pending."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE appeals SET status=?, resolved_by=?, resolved_at=? "
            "WHERE id=? AND status='pending'",
            (status, resolved_by, now_iso(), appeal_id),
        )
        return cur.rowcount == 1
