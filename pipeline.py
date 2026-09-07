"""The per-message moderation pipeline, with every side effect injected.

``handle_message`` is the one function ``on_message`` calls. Discord, the model,
and the database reach it only through ``Deps``, so the whole flow is driven
offline in tests (INVARIANT-04).

It fails closed (INVARIANT-03): an analyzer or punisher error, or a reply that
is neither the clean sentinel nor a valid verdict, is posted to mod-log for a
human instead of silently letting the message stand.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from channels import ScopeChain, resolve_scope
from composer import ResolvedRules, get_resolver
from moderation import record_history_only
from snapshots import MessageSnapshot, snapshot_of
from verdict import Clean, Outcome, Unparseable, Verdict

# analyze(content, guild_id, *, scope: ScopeChain) -> verdict.Outcome
Analyzer = Callable[..., Awaitable[Outcome]]
Punisher = Callable[..., Awaitable[str]]
Logger = Callable[[discord.Guild, str], Awaitable[None]]
IntervalLookup = Callable[[int], float]  # guild_id -> batch interval seconds; 0 = per message
RulesResolverFn = Callable[[ScopeChain], ResolvedRules]
Rechecker = Callable[..., Awaitable[Outcome]]  # (rules_text, content, *, ruleset_key) -> Outcome

RECHECK_AT = 3  # severity at which a second opinion is sought before a hold (D-011)

RAW_REPLY_PREVIEW = 300


def _default_resolve(scope: ScopeChain) -> ResolvedRules:
    return get_resolver().resolve(scope)


def no_batching(guild_id: int) -> float:
    return 0


@dataclass(frozen=True)
class Deps:
    analyze: Analyzer
    punish: Punisher
    log: Logger
    immune_role_ids: frozenset[int] = frozenset()
    # Batching (D-012). With no batcher, or an interval of 0 for the guild, a
    # message is classified on its own exactly as before.
    batcher: object | None = None  # batcher.Batcher; typed loosely to avoid an import cycle
    interval_for: IntervalLookup = no_batching
    resolve_rules: RulesResolverFn = _default_resolve
    clock: Callable[[], float] = time.time
    # Re-check tier (D-011): a severity >= RECHECK_AT verdict gets a second opinion
    # from the stronger model before anything is held. None disables it.
    recheck: Rechecker | None = None


def should_analyze(content: str | None) -> bool:
    """Pure: skip empty and whitespace-only messages (attachments, stickers)."""
    return bool(content and content.strip())


def _where(message: discord.Message) -> str:
    return f"User: {message.author.mention}\nChannel: {message.channel.mention}"


def _where_ids(author_id: int, channel_id: int) -> str:
    return f"User: <@{author_id}>\nChannel: <#{channel_id}>"


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


def unparseable_notice(message: discord.Message, problem: str) -> str:
    return (
        f"❓ **No usable classifier verdict — needs a human**\n{_where(message)}\n"
        f"Problem: {problem[:RAW_REPLY_PREVIEW]}\nMessage: {message.jump_url}"
    )


def snapshot_violation_notice(snap: MessageSnapshot, action: str, reason: str) -> str:
    return (
        f"🚨 **Violation Detected**\n{_where_ids(snap.author_id, snap.channel_id)}\n"
        f"Action: {describe_action(action)}\nReason: {reason}\nMessage: {snap.jump_url}"
    )


def snapshot_unparseable_notice(snap: MessageSnapshot, problem: str) -> str:
    return (
        f"❓ **No usable classifier verdict — needs a human**\n"
        f"{_where_ids(snap.author_id, snap.channel_id)}\n"
        f"Problem: {problem[:RAW_REPLY_PREVIEW]}\nMessage: {snap.jump_url}"
    )


def snapshot_error_notice(snap: MessageSnapshot, stage: str, exc: BaseException) -> str:
    return (
        f"⚠️ **Moderation {stage} failed — needs a human**\n"
        f"{_where_ids(snap.author_id, snap.channel_id)}\n"
        f"Error: {type(exc).__name__}: {exc}\nMessage: {snap.jump_url}"
    )


def reconcile(original: Verdict, second: Outcome | BaseException) -> Verdict:
    """Pure: fold the re-check into the verdict that will be acted on (D-011).

    A lower second-opinion severity wins; an equal or higher one changes nothing
    (the re-check never escalates). A clean second opinion does not clear the
    message — severity >= 3 is held for a human anyway, so both opinions go into
    the reason for the moderator. A failed or unparseable re-check keeps the
    original and says so. The original reason is always preserved.
    """
    if isinstance(second, Verdict):
        if second.severity < original.severity:
            return Verdict(
                second.severity,
                f"{second.reason} (re-check lowered from severity {original.severity}: "
                f"{original.reason})",
            )
        return Verdict(original.severity, f"{original.reason} (re-check agreed: {second.reason})")
    if isinstance(second, Clean):
        return Verdict(
            original.severity,
            f"{original.reason} (DISPUTED — re-check saw no violation; needs a human)",
        )
    if isinstance(second, Unparseable):
        detail = second.problem
    else:
        detail = f"{type(second).__name__}: {second}"
    return Verdict(original.severity, f"{original.reason} (re-check failed: {detail})")


async def with_recheck(
    deps: Deps, verdict: Verdict, rules_text: str | None, content: str, key: str
) -> Verdict:
    """Run the re-check when it applies; never raise (INVARIANT-03 keeps the original)."""
    if deps.recheck is None or verdict.severity < RECHECK_AT or rules_text is None:
        return verdict
    try:
        second = await deps.recheck(rules_text, content, ruleset_key=key)
    except Exception as exc:  # noqa: BLE001 — a failed second opinion keeps the first
        return reconcile(verdict, exc)
    return reconcile(verdict, second)


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

    # Batching (D-012): queue a snapshot under the frozen ruleset and return at once.
    if deps.batcher is not None:
        try:
            interval = deps.interval_for(message.guild.id)
            if interval > 0:
                resolved = deps.resolve_rules(scope)
                snap = snapshot_of(message, now=deps.clock())
                return deps.batcher.enqueue(snap, resolved, interval)
        except Exception as exc:  # noqa: BLE001 — a queueing failure is still fail-closed
            await _log_safely(deps, message.guild, error_notice(message, "queueing", exc))
            return "error"

    try:
        outcome = await deps.analyze(message.content, message.guild.id, scope=scope)
    except Exception as exc:  # noqa: BLE001 — any failure here must fail closed
        await _log_safely(deps, message.guild, error_notice(message, "analysis", exc))
        return "error"

    if isinstance(outcome, Clean):
        return "clean"
    if not isinstance(outcome, Verdict):
        problem = outcome.problem if isinstance(outcome, Unparseable) else repr(outcome)
        await _log_safely(deps, message.guild, unparseable_notice(message, problem))
        return "unparseable"
    verdict = outcome
    if deps.recheck is not None and verdict.severity >= RECHECK_AT:
        try:
            resolved = deps.resolve_rules(scope)
            rules_text, key = resolved.text, resolved.key
        except Exception as exc:  # noqa: BLE001 — cannot re-check without the rules; say so
            verdict = reconcile(verdict, exc)
        else:
            verdict = await with_recheck(deps, verdict, rules_text, message.content, key)

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


# --- applying a batch verdict from a snapshot (gameplan D1/D3) ---------------------


async def delete_by_id(guild: discord.Guild, channel_id: int, message_id: int) -> bool:
    """Delete without a live Message; a message already gone is a no-op, not an error."""
    lookup = getattr(guild, "get_channel_or_thread", None) or guild.get_channel
    channel = lookup(channel_id)
    if channel is None:
        return False
    try:
        await channel.get_partial_message(message_id).delete()
    except (discord.NotFound, discord.Forbidden):
        return False
    return True


async def apply_outcome(
    snap: MessageSnapshot,
    outcome: Outcome,
    guild: discord.Guild,
    deps: Deps,
    *,
    held: dict[int, int] | None = None,
    rules_text: str | None = None,
    ruleset_key: str = "batch",
) -> str:
    """Act on one message's outcome after its batch came back.

    Mirrors ``handle_message`` from the verdict onward, but from a snapshot: the
    author is re-resolved by id (gone → history recorded, nothing mutated), the
    delete tolerates the message having vanished, and a held-tier verdict for a
    member already held in this batch joins that pending action (``held``, D3).
    """
    if isinstance(outcome, Clean):
        return "clean"
    if not isinstance(outcome, Verdict):
        problem = outcome.problem if isinstance(outcome, Unparseable) else repr(outcome)
        await _log_safely(deps, guild, snapshot_unparseable_notice(snap, problem))
        return "unparseable"

    outcome = await with_recheck(deps, outcome, rules_text, snap.content, ruleset_key)

    member = guild.get_member(snap.author_id)
    if member is None:
        action = record_history_only(snap.author_id, guild.id)
        await delete_by_id(guild, snap.channel_id, snap.message_id)
        await _log_safely(
            deps,
            guild,
            snapshot_violation_notice(snap, "author left — warning recorded only", outcome.reason),
        )
        return action

    try:
        action = await deps.punish(
            member,
            outcome.severity,
            outcome.reason,
            immune_role_ids=deps.immune_role_ids,
            existing_pending_id=(held or {}).get(snap.author_id),
        )
    except Exception as exc:  # noqa: BLE001
        await _log_safely(deps, guild, snapshot_error_notice(snap, "punishment", exc))
        return "error"
    if held is not None and action.startswith("pending:"):
        held.setdefault(snap.author_id, int(action.split(":", 2)[1]))

    await delete_by_id(guild, snap.channel_id, snap.message_id)
    await _log_safely(deps, guild, snapshot_violation_notice(snap, action, outcome.reason))
    return action
