"""The per-guild batch interval: a moderator-set knob with a system ceiling (D-012, D5).

``0`` means every message is classified on its own — today's behaviour, the
default for a guild nobody has configured, and the per-guild rollback switch.
Anything else is clamped to ``1..BATCH_MAX_SECONDS`` so no guild can configure
an unbounded exposure window. The reply helpers return the ephemeral text the
``/batch`` commands send, so tests drive them without Discord.
"""

from batcher import BATCH_MAX_MESSAGES
from database import connect

BATCH_MAX_SECONDS = 300

EXPOSURE_NOTE = (
    "Messages are reviewed in batches of up to {seconds} seconds — a severe message "
    "may stay visible until its batch is checked. Set 0 to review each message on its own."
)


def clamp_interval(seconds: int) -> int:
    """Pure: 0 stays 0; anything else lands in 1..BATCH_MAX_SECONDS."""
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise ValueError(f"interval must be an integer number of seconds, got {seconds!r}")
    if seconds <= 0:
        return 0
    return min(seconds, BATCH_MAX_SECONDS)


def get_batch_interval(guild_id: int) -> int:
    """0 for a guild with no row. Read on every enqueue, so a change needs no restart."""
    with connect() as conn:
        row = conn.execute(
            "SELECT interval_seconds FROM batch_settings WHERE guild_id=?", (guild_id,)
        ).fetchone()
        return int(row["interval_seconds"]) if row else 0


def set_batch_interval(guild_id: int, seconds: int) -> int:
    """Store the clamped value and return it."""
    value = clamp_interval(seconds)
    with connect() as conn:
        conn.execute(
            "INSERT INTO batch_settings (guild_id, interval_seconds) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET interval_seconds=excluded.interval_seconds",
            (guild_id, value),
        )
    return value


def describe(interval: int, depth: int) -> str:
    if interval == 0:
        return (
            "⏱️ Batching is **off**: every message is classified on its own.\n"
            f"Turn it on with `/batch set <seconds>` (1–{BATCH_MAX_SECONDS})."
        )
    return (
        f"⏱️ Batch interval: **{interval}s** (max {BATCH_MAX_SECONDS}s); a batch also flushes "
        f"at {BATCH_MAX_MESSAGES} messages.\nWaiting right now: **{depth}** message(s).\n"
        + EXPOSURE_NOTE.format(seconds=interval)
    )


def set_reply(guild_id: int, seconds: int) -> str:
    try:
        value = set_batch_interval(guild_id, seconds)
    except ValueError as exc:
        return f"Not stored: {exc}"
    note = ""
    if seconds > BATCH_MAX_SECONDS:
        note = f" (capped from {seconds}s)"
    if value == 0:
        return "⏱️ Batching turned **off**; every message is classified on its own from now."
    return f"⏱️ Batch interval set to **{value}s**{note}.\n" + EXPOSURE_NOTE.format(seconds=value)


def show_reply(guild_id: int, depth: int) -> str:
    return describe(get_batch_interval(guild_id), depth)
