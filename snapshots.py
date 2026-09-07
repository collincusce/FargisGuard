"""A frozen record of a message at the moment it was seen (gameplan D1).

The batcher queues these, not live ``discord.Message`` objects, so what gets
classified is exactly what was posted, and a flush never touches Discord to
re-read anything. Everything here is plain data — no methods that do I/O.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageSnapshot:
    message_id: int
    channel_id: int
    guild_id: int
    author_id: int
    content: str
    jump_url: str
    created_at: float  # seconds since the epoch, from the injected clock


def snapshot_of(message, *, now: float) -> MessageSnapshot:
    """Pure over the message's attributes; reads only ids, content, and jump_url."""
    return MessageSnapshot(
        message_id=message.id,
        channel_id=message.channel.id,
        guild_id=message.guild.id,
        author_id=message.author.id,
        content=message.content or "",
        jump_url=message.jump_url,
        created_at=now,
    )
