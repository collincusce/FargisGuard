"""The per-message moderation pipeline, with every side effect injected.

``handle_message`` is the one function ``on_message`` calls. Discord, OpenAI,
and the database reach it only through ``Deps``, so the whole flow is driven
offline in tests (INVARIANT-04).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from channels import is_exempt
from verdict import parse_verdict

Analyzer = Callable[[str, int], Awaitable[str]]
Punisher = Callable[..., Awaitable[str]]
Logger = Callable[[discord.Guild, str], Awaitable[None]]


@dataclass(frozen=True)
class Deps:
    analyze: Analyzer
    punish: Punisher
    log: Logger
    immune_role_ids: frozenset[int] = frozenset()


def violation_notice(message: discord.Message, action: str, reason: str) -> str:
    return (
        "🚨 **Violation Detected**\n"
        f"User: {message.author}\n"
        f"Channel: {message.channel.mention}\n"
        f"Action: {action}\n"
        f"Reason: {reason}"
    )


async def handle_message(message: discord.Message, deps: Deps) -> str:
    """Run one message through the pipeline and return what happened.

    Return values: ``ignored`` (bot or DM), ``exempt`` (NSFW channel),
    ``clean`` (no verdict), or the action name ``punish`` returned.
    """
    if message.author.bot or message.guild is None:
        return "ignored"
    if is_exempt(message.channel):
        return "exempt"

    reply = await deps.analyze(message.content, message.guild.id)
    verdict = parse_verdict(reply)
    if verdict is None:
        return "clean"

    action = await deps.punish(
        message.author, verdict.severity, verdict.reason, immune_role_ids=deps.immune_role_ids
    )
    try:
        await message.delete()
    except discord.Forbidden:
        pass
    await deps.log(message.guild, violation_notice(message, action, verdict.reason))
    return action
