"""Apply a validated verdict to a guild member.

Severity is an explicit ladder (D-003) raised by the member's warning history
(escalation). Severities 1-2 act immediately and reversibly. Severities 3-4 are
never executed on model output alone (INVARIANT-02, gameplan D2): the member is
placed on a timeout hold, a pending action is recorded, and a moderator with
ban_members approves or denies it via ``/modaction``.

Immunity is decided by guild permissions or configured role IDs — never by a
role's name (INVARIANT-05).
"""

from collections.abc import Collection
from datetime import timedelta

import discord

from database import add_pending, add_warning, get_pending, get_warnings, resolve_pending
from escalation import effective_severity

TIMEOUT_MINUTES = 15
HOLD_MINUTES = 60  # how long a member stays muted while a kick/ban awaits review

ACTIONS: dict[int, str] = {1: "warn", 2: "timeout", 3: "kick", 4: "ban"}
REVIEW_REQUIRED = frozenset({"kick", "ban"})


def is_immune(member: discord.Member, immune_role_ids: Collection[int]) -> bool:
    """True for administrators, anyone who can manage messages, or a configured role."""
    perms = member.guild_permissions
    if perms.administrator or perms.manage_messages:
        return True
    return any(role.id in immune_role_ids for role in member.roles)


def pending_label(pending_id: int, action: str) -> str:
    return f"pending:{pending_id}:{action}"


async def punish(
    member: discord.Member,
    severity: int,
    reason: str,
    *,
    immune_role_ids: Collection[int] = (),
) -> str:
    """Act on ``severity`` for ``member`` and return what happened.

    Returns ``warn`` / ``timeout`` for immediate actions, ``pending:<id>:<kick|ban>``
    when the action awaits a moderator, ``immune`` for exempt members, and
    ``none`` for a severity off the ladder (nothing recorded).
    """
    if is_immune(member, immune_role_ids):
        return "immune"
    if severity not in ACTIONS:
        return "none"

    priors = get_warnings(member.id, member.guild.id)
    action = ACTIONS[effective_severity(severity, priors)]
    add_warning(member.id, member.guild.id)

    if action == "warn":
        try:
            await member.send(f"⚠️ Warning: {reason}")
        except discord.Forbidden:
            pass  # DMs closed; the warning is still on record and in mod-log
        return action

    if action == "timeout":
        await member.timeout(_until(TIMEOUT_MINUTES), reason=reason)
        return action

    # kick / ban: hold and hand to a human
    await member.timeout(_until(HOLD_MINUTES), reason=f"Held for moderator review: {reason}")
    pending_id = add_pending(member.guild.id, member.id, severity, action, reason)
    return pending_label(pending_id, action)


def _until(minutes: int):
    return discord.utils.utcnow() + timedelta(minutes=minutes)


async def resolve_pending_action(
    guild: discord.Guild, pending_id: int, decision: str, *, moderator_id: int
) -> str:
    """Approve (execute) or deny (lift the hold) a pending kick/ban. Returns a message."""
    row = get_pending(pending_id)
    if row is None or row["guild_id"] != guild.id:
        return f"No pending action #{pending_id} in this server."
    if row["status"] != "pending":
        return f"#{pending_id} was already {row['status']}."
    if decision not in ("approve", "deny"):
        return "Decision must be approve or deny."

    member = guild.get_member(row["user_id"])
    if decision == "deny":
        if member is not None:
            await member.timeout(None, reason=f"Pending #{pending_id} denied")
        resolve_pending(pending_id, "denied", moderator_id)
        return f"❎ #{pending_id} denied; hold lifted."

    action = row["action"]
    if action == "ban":
        await guild.ban(discord.Object(id=row["user_id"]), reason=row["reason"])
    elif member is not None:
        await member.kick(reason=row["reason"])
    else:
        resolve_pending(pending_id, "approved", moderator_id)
        return f"✅ #{pending_id} approved, but the member already left; nothing to kick."
    resolve_pending(pending_id, "approved", moderator_id)
    return f"✅ #{pending_id} approved: {action} executed."
