import discord
from database import add_warning
from config import IMMUNE_ROLES

async def punish(member: discord.Member, severity: int, reason: str) -> str:
    if any(role.name in IMMUNE_ROLES for role in member.roles):
        return "immune"

    add_warning(member.id, member.guild.id)

    if severity == 1:
        await member.send(f"⚠️ Warning: {reason}")
        return "warn"

    if severity == 2:
        await member.timeout(
            discord.utils.utcnow() + discord.timedelta(minutes=15)
        )
        return "timeout"

    if severity == 3:
        await member.kick(reason=reason)
        return "kick"

    await member.ban(reason=reason)
    return "ban"
