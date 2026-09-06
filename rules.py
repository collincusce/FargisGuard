"""Per-guild rules text the classifier enforces, authored at four scopes.

Scopes (gameplan D-009): ``guild`` (the default), ``category``, ``channel``,
and ``thread`` (all threads under a channel, keyed by that channel's id). Rows
are keyed by Discord snowflake IDs, never names (INVARIANT-05). Every write
bumps the guild's version counter so a composer memo can invalidate itself.

``get_rules``/``set_rules`` keep their guild-only signatures: they are what the
classifier and ``/setrules`` call today, and for one release ``set_rules`` also
mirrors into the legacy ``rules`` table so a code revert loses nothing (D2).
"""

from database import connect

GUILD = "guild"
CATEGORY = "category"
CHANNEL = "channel"
THREAD = "thread"
SCOPE_KINDS = frozenset({GUILD, CATEGORY, CHANNEL, THREAD})

GUILD_SCOPE_ID = 0  # scope_id for the guild scope; every other scope needs a real snowflake

DEFAULT_RULES = """
1. No harassment or hate speech
2. No spam or flooding
3. No NSFW content outside channels Discord marks NSFW
4. Follow Discord TOS
""".strip()


def validate_scope(scope_kind: str, scope_id: int) -> None:
    """Pure: raise ``ValueError`` unless (kind, id) is a well-formed scope key."""
    if scope_kind not in SCOPE_KINDS:
        raise ValueError(
            f"unknown scope kind {scope_kind!r}; expected one of {sorted(SCOPE_KINDS)}"
        )
    if not isinstance(scope_id, int) or isinstance(scope_id, bool):
        raise ValueError(f"scope_id must be an int, got {type(scope_id).__name__}")
    if scope_kind == GUILD and scope_id != GUILD_SCOPE_ID:
        raise ValueError(f"guild scope uses scope_id {GUILD_SCOPE_ID}, got {scope_id}")
    if scope_kind != GUILD and scope_id <= 0:
        raise ValueError(f"{scope_kind} scope needs a positive Discord id, got {scope_id}")


def _bump_version(conn, guild_id: int) -> int:
    # Two statements rather than RETURNING: the deploy target's SQLite may predate 3.35.
    conn.execute(
        "INSERT INTO rules_version (guild_id, version) VALUES (?, 1) "
        "ON CONFLICT(guild_id) DO UPDATE SET version=version+1",
        (guild_id,),
    )
    row = conn.execute("SELECT version FROM rules_version WHERE guild_id=?", (guild_id,)).fetchone()
    return int(row[0])


def get_rules_version(guild_id: int) -> int:
    """0 until the guild's first write."""
    with connect() as conn:
        row = conn.execute(
            "SELECT version FROM rules_version WHERE guild_id=?", (guild_id,)
        ).fetchone()
        return int(row["version"]) if row else 0


def get_scope_rules(guild_id: int, scope_kind: str, scope_id: int) -> str | None:
    validate_scope(scope_kind, scope_id)
    with connect() as conn:
        row = conn.execute(
            "SELECT content FROM scoped_rules WHERE guild_id=? AND scope_kind=? AND scope_id=?",
            (guild_id, scope_kind, scope_id),
        ).fetchone()
        return row["content"] if row else None


def set_scope_rules(guild_id: int, scope_kind: str, scope_id: int, content: str) -> int:
    """Upsert one scope's text and return the guild's new rules version."""
    validate_scope(scope_kind, scope_id)
    with connect() as conn:
        conn.execute(
            "INSERT INTO scoped_rules (guild_id, scope_kind, scope_id, content) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, scope_kind, scope_id) DO UPDATE SET content=excluded.content",
            (guild_id, scope_kind, scope_id, content),
        )
        if scope_kind == GUILD:
            # One-release mirror so a revert to the pre-scope code reads current text (D2).
            conn.execute(
                "INSERT INTO rules (guild_id, content) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET content=excluded.content",
                (guild_id, content),
            )
        return _bump_version(conn, guild_id)


def clear_scope_rules(guild_id: int, scope_kind: str, scope_id: int) -> bool:
    """Delete one scope's text. True if a row existed; the version bumps either way."""
    validate_scope(scope_kind, scope_id)
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM scoped_rules WHERE guild_id=? AND scope_kind=? AND scope_id=?",
            (guild_id, scope_kind, scope_id),
        )
        _bump_version(conn, guild_id)
        return cur.rowcount == 1


def list_scope_rules(guild_id: int) -> list[dict]:
    """Every authored fragment for a guild, in a stable order."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT scope_kind, scope_id, content FROM scoped_rules WHERE guild_id=? "
            "ORDER BY scope_kind, scope_id",
            (guild_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_rules(guild_id: int) -> str:
    """The guild-scope text, seeding ``DEFAULT_RULES`` on first sight of a guild."""
    existing = get_scope_rules(guild_id, GUILD, GUILD_SCOPE_ID)
    if existing is not None:
        return existing
    set_scope_rules(guild_id, GUILD, GUILD_SCOPE_ID, DEFAULT_RULES)
    return DEFAULT_RULES


def set_rules(guild_id: int, content: str) -> None:
    """Guild-scope write; what ``/setrules`` has always meant."""
    set_scope_rules(guild_id, GUILD, GUILD_SCOPE_ID, content)
