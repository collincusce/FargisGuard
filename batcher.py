"""Queue messages per (guild, ruleset key) and classify each bucket in one request.

The whole point of the token-architecture gameplan (D-012): the static prefix
and the composed rules are sent once per bucket instead of once per message.

A ``Bucket`` freezes the ``ResolvedRules`` it was opened with and holds
``MessageSnapshot`` values (gameplan D1). It flushes when its guild's interval
elapses since the first enqueue or when it reaches ``max_messages``, whichever
comes first. ``enqueue`` never awaits the network: flushes run as tasks. Every
time source is injected (``clock``, ``sleep``, ``spawn``) so the suite drives
timers offline (INVARIANT-06).

Fail-closed rules (INVARIANT-03): a classifier or transport failure posts ONE
consolidated mod-log notice for the whole bucket and punishes nobody; a
graceful shutdown flushes every bucket under a deadline and posts an
"unreviewed" notice for anything that did not finish (gameplan D2).
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from composer import ResolvedRules
from snapshots import MessageSnapshot
from verdict import ParsedBatch

log = logging.getLogger(__name__)

BATCH_MAX_MESSAGES = 25
SHUTDOWN_FLUSH_SECONDS = 20.0
LINKS_IN_NOTICE = 15

Classifier = Callable[..., Awaitable[ParsedBatch]]  # (rules_text, contents, *, ruleset_key)
Applier = Callable[..., Awaitable[str]]  # (snapshot, outcome, guild, *, held) -> action
GuildLookup = Callable[[int], object | None]
Logger = Callable[[object, str], Awaitable[None]]  # (guild, text)
BucketKey = tuple[int, str]


@dataclass
class Bucket:
    guild_id: int
    rules: ResolvedRules
    interval: float
    generation: int
    opened_at: float
    snapshots: list[MessageSnapshot] = field(default_factory=list)
    timer: asyncio.Task | None = None

    @property
    def key(self) -> BucketKey:
        return (self.guild_id, self.rules.key)


def links(snapshots: list[MessageSnapshot], limit: int = LINKS_IN_NOTICE) -> str:
    shown = "\n".join(s.jump_url for s in snapshots[:limit])
    extra = len(snapshots) - limit
    return shown + (f"\n…and {extra} more" if extra > 0 else "")


def batch_error_notice(bucket: Bucket, exc: BaseException) -> str:
    n = len(bucket.snapshots)
    return (
        f"⚠️ **Batch classification failed — {n} message(s) need a human**\n"
        f"Ruleset: `{bucket.rules.key[:12]}`\nError: {type(exc).__name__}: {exc}\n"
        f"{links(bucket.snapshots)}"
    )


def unreviewed_notice(bucket: Bucket, why: str) -> str:
    n = len(bucket.snapshots)
    return (
        f"⚠️ **{n} message(s) unreviewed — {why}**\n"
        f"Ruleset: `{bucket.rules.key[:12]}`\n{links(bucket.snapshots)}"
    )


class Batcher:
    def __init__(
        self,
        *,
        classify: Classifier,
        apply: Applier,
        guild_for: GuildLookup,
        log_to: Logger,
        max_messages: int = BATCH_MAX_MESSAGES,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        spawn: Callable[[Awaitable], asyncio.Task] = asyncio.create_task,
    ):
        self._classify = classify
        self._apply = apply
        self._guild_for = guild_for
        self._log_to = log_to
        self._max = max_messages
        self._clock = clock
        self._sleep = sleep
        self._spawn = spawn
        self._buckets: dict[BucketKey, Bucket] = {}
        self._inflight: dict[asyncio.Task, Bucket] = {}
        self._generation = 0

    # --- enqueue --------------------------------------------------------------------

    def enqueue(self, snapshot: MessageSnapshot, rules: ResolvedRules, interval: float) -> str:
        """Add a snapshot to its bucket; returns ``queued`` or ``queued-flush`` (size cap hit).

        Synchronous on purpose: no await between reading and mutating the bucket,
        so a concurrent flush cannot interleave (asyncio is cooperative).
        """
        key = (snapshot.guild_id, rules.key)
        bucket = self._buckets.get(key)
        if bucket is None:
            self._generation += 1
            bucket = Bucket(
                guild_id=snapshot.guild_id,
                rules=rules,
                interval=interval,
                generation=self._generation,
                opened_at=self._clock(),
            )
            self._buckets[key] = bucket
            bucket.timer = self._spawn(self._expire(key, bucket.generation, interval))
        bucket.snapshots.append(snapshot)
        if len(bucket.snapshots) >= self._max:
            self._start_flush(key)
            return "queued-flush"
        return "queued"

    def depth(self, guild_id: int | None = None) -> int:
        """Messages waiting (for one guild, or all)."""
        return sum(
            len(b.snapshots)
            for b in self._buckets.values()
            if guild_id is None or b.guild_id == guild_id
        )

    # --- flushing -------------------------------------------------------------------

    async def _expire(self, key: BucketKey, generation: int, interval: float) -> None:
        await self._sleep(interval)
        bucket = self._buckets.get(key)
        if bucket is not None and bucket.generation == generation:
            self._start_flush(key)

    def _start_flush(self, key: BucketKey) -> asyncio.Task | None:
        bucket = self._buckets.pop(key, None)  # swap-and-clear: the next enqueue opens a new one
        if bucket is None:
            return None
        if bucket.timer is not None and bucket.timer is not asyncio.current_task():
            bucket.timer.cancel()
        task = self._spawn(self._run(bucket))
        self._inflight[task] = bucket
        task.add_done_callback(lambda t: self._inflight.pop(t, None))
        return task

    def flush_now(self, guild_id: int | None = None) -> list[asyncio.Task]:
        """Flush every open bucket (for one guild, or all) without waiting for timers."""
        keys = [k for k, b in self._buckets.items() if guild_id is None or b.guild_id == guild_id]
        return [t for t in (self._start_flush(k) for k in keys) if t is not None]

    async def _run(self, bucket: Bucket) -> None:
        guild = self._guild_for(bucket.guild_id)
        if guild is None:
            log.warning(
                "batch for guild %s dropped: guild no longer available", bucket.guild_id
            )
            return
        ordered = sorted(bucket.snapshots, key=lambda s: s.message_id)  # D3: message order
        bucket.snapshots = ordered
        try:
            parsed = await self._classify(
                bucket.rules.text,
                [s.content for s in ordered],
                ruleset_key=bucket.rules.key,
            )
        except Exception as exc:  # noqa: BLE001 — one notice for the bucket, nobody punished
            await self._log_safely(guild, batch_error_notice(bucket, exc))
            return
        held: dict[int, int] = {}  # author_id -> pending id created in this batch (D3)
        for position, snapshot in enumerate(ordered, start=1):
            outcome = parsed.outcomes[position]
            try:
                await self._apply(snapshot, outcome, guild, held=held)
            except Exception as exc:  # noqa: BLE001 — one message's failure never aborts the rest
                log.exception("apply failed for message %s", snapshot.message_id)
                await self._log_safely(
                    guild,
                    f"⚠️ **Applying a verdict failed — needs a human**\n"
                    f"Error: {type(exc).__name__}: {exc}\nMessage: {snapshot.jump_url}",
                )
        if parsed.unexpected_ids:
            log.warning(
                "batch ruleset=%s: model returned %d unexpected id(s)",
                bucket.rules.key[:12],
                len(parsed.unexpected_ids),
            )

    async def _log_safely(self, guild, text: str) -> None:
        try:
            await self._log_to(guild, text)
        except Exception:  # noqa: BLE001 — logging must not turn a handled error into a crash
            log.exception("mod-log post failed")

    # --- shutdown (gameplan D2) ---------------------------------------------------------

    async def shutdown(self, deadline: float = SHUTDOWN_FLUSH_SECONDS) -> int:
        """Flush everything, wait up to ``deadline`` seconds, report what did not finish.

        Returns the number of messages posted as unreviewed.
        """
        self.flush_now()
        pending = set(self._inflight)
        if pending:
            _, still_running = await asyncio.wait(pending, timeout=deadline)
        else:
            still_running = set()
        unreviewed = 0
        stranded = [(task, self._inflight.get(task)) for task in still_running]
        for task, _ in stranded:
            task.cancel()
        if stranded:  # let the cancellations land so the done-callbacks clear _inflight
            await asyncio.gather(*(t for t, _ in stranded), return_exceptions=True)
        for _, bucket in stranded:
            if bucket is None:
                continue
            unreviewed += len(bucket.snapshots)
            guild = self._guild_for(bucket.guild_id)
            if guild is not None:
                why = "shutdown before the batch finished"
                await self._log_safely(guild, unreviewed_notice(bucket, why))
        return unreviewed
