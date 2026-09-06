"""The appeals workflow: one pending appeal per member, resolved by a moderator."""

from database import (
    connect,
    forgive,
    get_appeal,
    has_pending_appeal,
    list_pending_appeals,
    now_iso,
    resolve_appeal,
)


def submit_appeal(user_id: int, guild_id: int, reason: str) -> int | None:
    """Record an appeal and return its id, or None if one is already pending."""
    if has_pending_appeal(user_id, guild_id):
        return None
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO appeals (user_id, guild_id, reason, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (user_id, guild_id, reason, now_iso()),
        )
        return int(cur.lastrowid)


def format_pending_appeals(guild_id: int) -> str:
    rows = list_pending_appeals(guild_id)
    if not rows:
        return "No pending appeals."
    lines = [f"#{r['id']} — <@{r['user_id']}> ({r['created_at']}): {r['reason']}" for r in rows]
    return "**Pending appeals**\n" + "\n".join(lines)


def resolve_appeal_action(
    guild_id: int, appeal_id: int, decision: str, *, moderator_id: int
) -> str:
    """Approve (clears the member's warnings) or deny an appeal. Returns a message."""
    row = get_appeal(appeal_id)
    if row is None or row["guild_id"] != guild_id:
        return f"No appeal #{appeal_id} in this server."
    if row["status"] != "pending":
        return f"Appeal #{appeal_id} was already {row['status']}."
    if decision not in ("approve", "deny"):
        return "Decision must be approve or deny."
    if decision == "approve":
        forgive(row["user_id"], guild_id)
        resolve_appeal(appeal_id, "approved", moderator_id)
        return f"✅ Appeal #{appeal_id} approved; warnings for <@{row['user_id']}> cleared."
    resolve_appeal(appeal_id, "denied", moderator_id)
    return f"❎ Appeal #{appeal_id} denied."
