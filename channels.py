"""Where a message lives: NSFW exemption and the scope chain the rules resolve on.

Everything here reads Discord *IDs and flags*, never names (INVARIANT-05), and
touches no network — a fake with the same attributes drives it in tests
(INVARIANT-04).
"""

from dataclasses import dataclass


class ScopeError(RuntimeError):
    """The scope chain could not be resolved; the pipeline fails closed on it (D-010)."""


@dataclass(frozen=True)
class ScopeChain:
    """The scopes a message's rules are composed from (D-009).

    ``channel_id`` is the *parent* channel when the message is in a thread, so
    thread scope is keyed by the channel that owns the threads. ``category_id``
    is ``None`` for channels outside any category — that is normal, not an error.
    """

    guild_id: int
    category_id: int | None
    channel_id: int
    in_thread: bool


def is_exempt(channel: object) -> bool:
    """True when Discord itself marks the channel NSFW (D-004, INVARIANT-05).

    Uses the channel's ``is_nsfw()`` flag — threads report their parent's —
    never the channel name. Objects without the method are never exempt.
    """
    probe = getattr(channel, "is_nsfw", None)
    return bool(probe and probe())


def resolve_scope(message) -> ScopeChain:
    """Pure: the ScopeChain for a guild message.

    A thread is recognised by ``parent_id`` (discord.py 2.3.2: only ``Thread``
    carries it). Its parent is looked up by id through ``guild.get_channel``
    rather than ``Thread.category``/``Thread.parent``, which raise on an
    uncached parent. A parent that resolves to ``None`` is a dangling reference
    and raises ``ScopeError`` — never a silent fall-back to guild scope (D-010).
    Forum posts are threads whose parent is the forum, so they resolve to the
    forum's channel scope with ``in_thread=True`` (D3).
    """
    guild = message.guild
    if guild is None:
        raise ScopeError("message has no guild")
    channel = message.channel
    parent_id = getattr(channel, "parent_id", None)
    if parent_id is None:
        return ScopeChain(
            guild_id=guild.id,
            category_id=getattr(channel, "category_id", None),
            channel_id=channel.id,
            in_thread=False,
        )
    parent = guild.get_channel(parent_id)
    if parent is None:
        raise ScopeError(f"thread {channel.id} has no resolvable parent channel {parent_id}")
    return ScopeChain(
        guild_id=guild.id,
        category_id=getattr(parent, "category_id", None),
        channel_id=parent.id,
        in_thread=True,
    )
