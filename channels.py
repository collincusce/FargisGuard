"""Channel-level moderation exemptions."""


def is_exempt(channel: object) -> bool:
    """True when Discord itself marks the channel NSFW (D-004, INVARIANT-05).

    Uses the channel's ``is_nsfw()`` flag — threads report their parent's —
    never the channel name. Objects without the method are never exempt.
    """
    probe = getattr(channel, "is_nsfw", None)
    return bool(probe and probe())
