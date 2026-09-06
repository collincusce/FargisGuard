"""Apply a validated verdict to a guild member.

Severity is an explicit ladder (D-003); an unknown severity does nothing.
Immunity is decided by guild permissions or configured role IDs — never by a
role's name (INVARIANT-05).
"""

from collections.abc import Collection
from datetime import timedelta

import discord

from database import add_warning

TIMEOUT_MINUTES = 15

ACTIONS: dict[int, str] = {1: "warn", 2: "timeout", 3: "kick", 4: "ban"}


def is_immune(member: discord.Member, immune_role_ids: Collection[int]) -> bool:
    """True for administrators, anyone who can manage messages, or a configured role."""
    perms = member.guild_permissions
    if perms.administrator or perms.manage_messages:
        return True
    return any(role.id in immune_role_ids for role in member.roles)


async def punish(
    member: discord.Member,
    severity: int,
    reason: str,
    *,
    immune_role_ids: Collection[int] = (),
) -> str:
    """Carry out the action for ``severity`` and return its name.

    Returns ``"immune"`` when the member is exempt and ``"none"`` when the
    severity is not on the ladder; only ladder severities record a warning.
    """
    if is_immune(member, immune_role_ids):
        return "immune"

    action = ACTIONS.get(severity)
    if action is None:
        return "none"

    add_warning(member.id, member.guild.id)

    if action == "warn":
        try:
            await member.send(f"⚠️ Warning: {reason}")
        except discord.Forbidden:
            pass  # DMs closed; the warning is still on record and in mod-log
        return action

    if action == "timeout":
        until = discord.utils.utcnow() + timedelta(minutes=TIMEOUT_MINUTES)
        await member.timeout(until, reason=reason)
        return action

    if action == "kick":
        await member.kick(reason=reason)
        return action

    await member.ban(reason=reason)
    return action
