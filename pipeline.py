"""The per-message moderation pipeline, with every side effect injected.

``handle_message`` is the one function ``on_message`` calls. Discord, OpenAI,
and the database reach it only through ``Deps``, so the whole flow is driven
offline in tests (INVARIANT-04).

It fails closed (INVARIANT-03): an analyzer or punisher error, or a reply that
is neither the clean sentinel nor a valid verdict, is posted to mod-log for a
human instead of silently letting the message stand.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from ai_engine import CLEAN_SENTINEL
from channels import ScopeChain, resolve_scope
from verdict import parse_verdict

# analyze(content, guild_id, *, scope: ScopeChain) -> raw classifier reply
Analyzer = Callable[..., Awaitable[str]]
Punisher = Callable[..., Awaitable[str]]
Logger = Callable[[discord.Guild, str], Awaitable[None]]

RAW_REPLY_PREVIEW = 300


@dataclass(frozen=True)
class Deps:
    analyze: Analyzer
    punish: Punisher
    log: Logger
    immune_role_ids: frozenset[int] = frozenset()


def should_analyze(content: str | None) -> bool:
    """Pure: skip empty and whitespace-only messages (attachments, stickers)."""
    return bool(content and content.strip())


def _where(message: discord.Message) -> str:
    return f"User: {message.author}\nChannel: {message.channel.mention}"


def describe_action(action: str) -> str:
    """Pure: turn punish()'s return value into the mod-log wording."""
    if action.startswith("pending:"):
        _, pending_id, proposed = action.split(":", 2)
        return (
            f"held for review — proposed **{proposed}**. "
            f"Run `/modaction {pending_id} approve` or `/modaction {pending_id} deny`."
        )
    return action


def violation_notice(message: discord.Message, action: str, reason: str) -> str:
    return (
        f"🚨 **Violation Detected**\n{_where(message)}\n"
        f"Action: {describe_action(action)}\nReason: {reason}"
    )


def error_notice(message: discord.Message, stage: str, exc: BaseException) -> str:
    return (
        f"⚠️ **Moderation {stage} failed — needs a human**\n{_where(message)}\n"
        f"Error: {type(exc).__name__}: {exc}\nMessage: {message.jump_url}"
    )


def unparseable_notice(message: discord.Message, reply: str) -> str:
    return (
        f"❓ **Unparseable classifier reply — needs a human**\n{_where(message)}\n"
        f"Reply: {reply[:RAW_REPLY_PREVIEW]}\nMessage: {message.jump_url}"
    )


async def _log_safely(deps: Deps, guild: discord.Guild, text: str) -> None:
    """Logging must never turn a handled error into an unhandled one."""
    try:
        await deps.log(guild, text)
    except Exception:  # noqa: BLE001 — last resort; the caller already failed closed
        pass


async def handle_message(message: discord.Message, deps: Deps) -> str:
    """Run one message through the pipeline and return what happened.

    Return values: ``ignored`` (bot or DM), ``skipped`` (nothing to analyze),
    ``clean``, ``unparseable`` (posted for a human), ``error`` (posted for a
    human), or the action ``punish`` returned. NSFW-flagged channels are not
    exempt (D-007); their scope rules say what they allow, the floor says what
    nothing allows.
    """
    if message.author.bot or message.guild is None:
        return "ignored"
    if not should_analyze(message.content):
        return "skipped"

    # Reading the channel is a Discord-object access and can raise (a thread whose
    # parent left the cache, for one), so it lives inside the fail-closed boundary.
    try:
        scope: ScopeChain = resolve_scope(message)
    except Exception as exc:  # noqa: BLE001 — D-010: never fall back to guild scope silently
        await _log_safely(deps, message.guild, error_notice(message, "scope resolution", exc))
        return "error"

    try:
        reply = await deps.analyze(message.content, message.guild.id, scope=scope)
    except Exception as exc:  # noqa: BLE001 — any failure here must fail closed
        await _log_safely(deps, message.guild, error_notice(message, "analysis", exc))
        return "error"

    if reply.strip() == CLEAN_SENTINEL:
        return "clean"
    verdict = parse_verdict(reply)
    if verdict is None:
        await _log_safely(deps, message.guild, unparseable_notice(message, reply))
        return "unparseable"

    try:
        action = await deps.punish(
            message.author, verdict.severity, verdict.reason, immune_role_ids=deps.immune_role_ids
        )
    except Exception as exc:  # noqa: BLE001
        await _log_safely(deps, message.guild, error_notice(message, "punishment", exc))
        return "error"

    try:
        await message.delete()
    except discord.Forbidden:
        pass
    await _log_safely(deps, message.guild, violation_notice(message, action, verdict.reason))
    return action
