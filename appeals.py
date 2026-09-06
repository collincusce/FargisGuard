"""Appeal submission. Resolution arrives in Phase 6."""

from database import connect, now_iso


def submit_appeal(user_id: int, guild_id: int, reason: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO appeals (user_id, guild_id, reason, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (user_id, guild_id, reason, now_iso()),
        )
        return int(cur.lastrowid)
