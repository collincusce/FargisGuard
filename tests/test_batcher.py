"""Batch queue (gameplan D-012, D1, D2, D3): buckets, timers, flush, apply, shutdown."""

import asyncio

import pytest

import database
import pipeline
from batcher import Batcher, Bucket, batch_error_notice, unreviewed_notice
from composer import ResolvedRules
from pipeline import Deps, apply_outcome, handle_message
from snapshots import MessageSnapshot
from tests.fakes import FakeChannel, FakeGuild, FakeMember, FakeMessage, FakePermissions
from verdict import CLEAN, ParsedBatch, Unparseable, Verdict

G = 1001
RULES = ResolvedRules(text="## Server rules\n1. Be kind", key="a" * 64)
OTHER = ResolvedRules(text="## Server rules\n1. Be nice", key="b" * 64)


def snap(message_id, *, author=42, channel=500, content="hi"):
    return MessageSnapshot(
        message_id=message_id,
        channel_id=channel,
        guild_id=G,
        author_id=author,
        content=content,
        jump_url=f"https://discord.com/channels/{G}/{channel}/{message_id}",
        created_at=0.0,
    )


class FakeSleep:
    """Timers park on futures the test releases explicitly (INVARIANT-06: no wall clock)."""

    def __init__(self):
        self.waits: list[tuple[float, asyncio.Future]] = []

    async def __call__(self, seconds):
        fut = asyncio.get_running_loop().create_future()
        self.waits.append((seconds, fut))
        await fut

    def release_all(self):
        for _, fut in self.waits:
            if not fut.done():
                fut.set_result(None)


class Harness:
    def __init__(self, *, outcomes=None, classify_error=None, never_finish=False):
        self.calls: list[tuple[str, list[str], str]] = []
        self.applied: list[tuple[int, object, dict]] = []
        self.logged: list[str] = []
        self.sleep = FakeSleep()
        self.guild = FakeGuild(id=G)
        self.outcomes = outcomes
        self.classify_error = classify_error
        self.never_finish = never_finish
        self.batcher = Batcher(
            classify=self.classify,
            apply=self.apply,
            guild_for=lambda gid: self.guild if gid == G else None,
            log_to=self.log,
            max_messages=3,
            clock=lambda: 0.0,
            sleep=self.sleep,
        )

    async def classify(self, rules, contents, *, ruleset_key):
        self.calls.append((rules, list(contents), ruleset_key))
        if self.never_finish:
            await asyncio.get_running_loop().create_future()
        if self.classify_error is not None:
            raise self.classify_error
        ids = range(1, len(contents) + 1)
        outcomes = self.outcomes or {i: CLEAN for i in ids}
        return ParsedBatch({i: outcomes.get(i, CLEAN) for i in ids}, ())

    async def apply(self, snapshot, outcome, guild, *, held):
        self.applied.append((snapshot.message_id, outcome, dict(held)))
        if isinstance(outcome, Verdict) and outcome.severity >= 3:
            held.setdefault(snapshot.author_id, 100 + len(held))
        return "applied"

    async def log(self, guild, text):
        self.logged.append(text)


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


# --- enqueue and bucketing ------------------------------------------------------


async def test_enqueue_returns_at_once_and_freezes_rules_per_bucket():
    h = Harness()
    assert h.batcher.enqueue(snap(1), RULES, 30) == "queued"
    assert h.batcher.enqueue(snap(2), OTHER, 30) == "queued"
    assert h.calls == [] and h.batcher.depth(G) == 2
    (bucket_a, bucket_b) = h.batcher._buckets.values()
    assert bucket_a.rules is RULES and bucket_b.rules is OTHER
    await settle()  # timer tasks start on the next loop tick
    assert [seconds for seconds, _ in h.sleep.waits] == [30, 30]


async def test_timer_flushes_the_bucket_with_its_frozen_text():
    h = Harness()
    h.batcher.enqueue(snap(1), RULES, 30)
    h.batcher.enqueue(snap(2), RULES, 30)
    await settle()
    h.sleep.release_all()
    await settle()
    assert h.calls == [(RULES.text, ["hi", "hi"], RULES.key)]
    assert h.batcher.depth() == 0
    assert [m for m, _, _ in h.applied] == [1, 2]


async def test_size_cap_flushes_immediately_and_cancels_the_timer():
    h = Harness()
    h.batcher.enqueue(snap(1), RULES, 30)
    h.batcher.enqueue(snap(2), RULES, 30)
    assert h.batcher.enqueue(snap(3), RULES, 30) == "queued-flush"
    await settle()
    assert len(h.calls) == 1 and h.calls[0][1] == ["hi", "hi", "hi"]
    assert h.sleep.waits == [] or h.sleep.waits[0][1].cancelled()  # timer cancelled
    h.sleep.release_all()  # even if it fired, nothing is flushed a second time
    await settle()
    assert len(h.calls) == 1


async def test_enqueue_during_an_in_flight_flush_lands_in_the_next_generation():
    h = Harness(never_finish=True)
    h.batcher.enqueue(snap(1), RULES, 30)
    await settle()
    h.sleep.release_all()
    await settle()  # first flush is now parked inside classify
    assert h.batcher.depth() == 0 and len(h.calls) == 1
    assert h.batcher.enqueue(snap(2), RULES, 30) == "queued"
    assert h.batcher.depth() == 1  # a new bucket, not the one in flight
    h.never_finish = False
    await settle()
    h.sleep.release_all()
    await settle()
    assert [c[1] for c in h.calls] == [["hi"], ["hi"]]  # each message classified exactly once
    tasks = list(h.batcher._inflight)
    for t in tasks:
        t.cancel()


async def test_verdicts_apply_in_ascending_message_id_and_share_held_state():
    h = Harness(outcomes={1: Verdict(4, "a"), 2: Verdict(4, "b"), 3: CLEAN})
    h.batcher.enqueue(snap(30, author=7), RULES, 30)
    h.batcher.enqueue(snap(10, author=7), RULES, 30)
    h.batcher.enqueue(snap(20, author=8), RULES, 30)  # third fills the bucket
    await settle()
    assert h.calls[0][1] == ["hi", "hi", "hi"]
    assert [m for m, _, _ in h.applied] == [10, 20, 30]  # not enqueue order
    # each apply sees the holds opened earlier in the same batch, in message order
    held_seen = {m: held for m, _, held in h.applied}
    assert held_seen[10] == {} and held_seen[20] == {7: 100}
    assert held_seen[30] == {7: 100, 8: 101}


async def test_classifier_failure_posts_one_notice_and_applies_nothing():
    h = Harness(classify_error=RuntimeError("429 rate limited"))
    for i in (1, 2, 3):
        h.batcher.enqueue(snap(i), RULES, 30)
    await settle()
    assert h.applied == []
    assert len(h.logged) == 1
    notice = h.logged[0]
    assert "3 message(s) need a human" in notice and "RuntimeError" in notice
    assert all(snap(i).jump_url in notice for i in (1, 2, 3))


async def test_one_failing_apply_does_not_abort_the_rest():
    h = Harness(outcomes={1: Verdict(2, "x"), 2: Verdict(2, "y"), 3: Verdict(2, "z")})

    async def flaky(snapshot, outcome, guild, *, held):
        if snapshot.message_id == 2:
            raise RuntimeError("discord 5xx")
        h.applied.append((snapshot.message_id, outcome, {}))
        return "applied"

    h.batcher._apply = flaky
    for i in (1, 2, 3):
        h.batcher.enqueue(snap(i), RULES, 30)
    await settle()
    assert [m for m, _, _ in h.applied] == [1, 3]
    assert len(h.logged) == 1 and "Applying a verdict failed" in h.logged[0]


async def test_bucket_for_a_vanished_guild_is_dropped_with_a_log_line(caplog):
    h = Harness()
    h.guild = None  # guild_for returns None now
    for i in (1, 2, 3):
        h.batcher.enqueue(snap(i), RULES, 30)
    await settle()
    assert h.calls == [] and "no longer available" in caplog.text


# --- shutdown (D2) -------------------------------------------------------------


async def test_shutdown_flushes_everything_and_reports_what_did_not_finish():
    h = Harness(never_finish=True)
    h.batcher.enqueue(snap(1), RULES, 30)
    h.batcher.enqueue(snap(2), OTHER, 30)
    unreviewed = await h.batcher.shutdown(deadline=0.01)
    assert unreviewed == 2
    assert len(h.logged) == 2 and all("unreviewed" in t and "shutdown" in t for t in h.logged)
    assert h.batcher.depth() == 0 and h.batcher._inflight == {}


async def test_shutdown_with_a_fast_classifier_reports_nothing():
    h = Harness()
    h.batcher.enqueue(snap(1), RULES, 30)
    assert await h.batcher.shutdown(deadline=1) == 0
    assert [m for m, _, _ in h.applied] == [1] and h.logged == []


def test_notice_link_lists_are_capped():
    bucket = Bucket(guild_id=G, rules=RULES, interval=1, generation=1, opened_at=0.0)
    bucket.snapshots = [snap(i) for i in range(1, 21)]
    text = batch_error_notice(bucket, RuntimeError("x"))
    assert text.count("https://") == 15 and "and 5 more" in text
    assert "20 message(s)" in unreviewed_notice(bucket, "why")


# --- pipeline: the enqueue branch and interval 0 -------------------------------


class RecordingBatcher:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, snapshot, rules, interval):
        self.enqueued.append((snapshot, rules, interval))
        return "queued"


def deps_with(batcher, interval, *, analyzed):
    async def analyze(content, guild_id, *, scope):
        analyzed.append(content)
        return CLEAN

    async def punish(member, severity, reason, **_):
        return "warn"

    async def log(guild, text):
        pass

    return Deps(
        analyze=analyze,
        punish=punish,
        log=log,
        batcher=batcher,
        interval_for=lambda g: interval,
        resolve_rules=lambda scope: RULES,
        clock=lambda: 123.0,
    )


async def test_interval_zero_keeps_the_per_message_path():
    rb, analyzed = RecordingBatcher(), []
    msg = FakeMessage(content="hello", guild=FakeGuild(id=G))
    assert await handle_message(msg, deps_with(rb, 0, analyzed=analyzed)) == "clean"
    assert analyzed == ["hello"] and rb.enqueued == []


async def test_positive_interval_enqueues_a_snapshot_under_the_frozen_rules():
    rb, analyzed = RecordingBatcher(), []
    channel = FakeChannel(id=55)
    msg = FakeMessage(content="hello", guild=FakeGuild(id=G), channel=channel)
    msg.id = 9000
    assert await handle_message(msg, deps_with(rb, 45, analyzed=analyzed)) == "queued"
    assert analyzed == []
    ((s, rules, interval),) = rb.enqueued
    assert rules is RULES and interval == 45
    assert (s.message_id, s.channel_id, s.guild_id, s.content, s.created_at) == (
        9000,
        55,
        G,
        "hello",
        123.0,
    )


async def test_queueing_failure_is_fail_closed():
    logged = []

    async def log(guild, text):
        logged.append(text)

    deps = deps_with(RecordingBatcher(), 45, analyzed=[])
    deps = Deps(**{**deps.__dict__, "log": log, "resolve_rules": lambda s: 1 / 0})
    assert await handle_message(FakeMessage(content="x", guild=FakeGuild(id=G)), deps) == "error"
    assert "queueing failed" in logged[0]


# --- apply_outcome from a snapshot ----------------------------------------------


@pytest.fixture
def world():
    guild = FakeGuild(id=G)
    channel = FakeChannel(id=500)
    guild.channels[500] = channel
    member = FakeMember(id=42, guild=guild)
    guild.members[42] = member
    logged, punished = [], []

    async def punish(m, severity, reason, *, immune_role_ids=(), existing_pending_id=None):
        punished.append((m.id, severity, existing_pending_id))
        pid = 7 if existing_pending_id is None else existing_pending_id
        return "warn" if severity < 3 else f"pending:{pid}:ban"

    async def log(g, text):
        logged.append(text)

    async def analyze(*a, **k):
        raise AssertionError("not used")

    deps = Deps(analyze=analyze, punish=punish, log=log)
    return guild, channel, member, deps, logged, punished


async def test_clean_outcome_does_nothing(world):
    guild, channel, member, deps, logged, punished = world
    assert await apply_outcome(snap(1), CLEAN, guild, deps) == "clean"
    assert punished == [] and channel.deleted == [] and logged == []


async def test_unparseable_outcome_goes_to_a_human(world):
    guild, channel, member, deps, logged, punished = world
    assert await apply_outcome(snap(1), Unparseable("missing"), guild, deps) == "unparseable"
    assert punished == [] and "needs a human" in logged[0] and "missing" in logged[0]


async def test_violation_punishes_deletes_by_id_and_logs(world):
    guild, channel, member, deps, logged, punished = world
    assert await apply_outcome(snap(1), Verdict(2, "flood"), guild, deps) == "warn"
    assert punished == [(42, 2, None)] and channel.deleted == [1]
    assert "Violation Detected" in logged[0] and "<@42>" in logged[0] and "flood" in logged[0]


async def test_already_deleted_message_is_a_no_op_not_an_error(world):
    guild, channel, member, deps, logged, punished = world
    channel.gone.add(1)
    assert await apply_outcome(snap(1), Verdict(2, "flood"), guild, deps) == "warn"
    assert channel.deleted == [] and len(logged) == 1


async def test_author_who_left_gets_history_only(world, monkeypatch):
    guild, channel, member, deps, logged, punished = world
    recorded = []
    monkeypatch.setattr(
        pipeline, "record_history_only", lambda u, g: recorded.append((u, g)) or "absent"
    )
    assert await apply_outcome(snap(1, author=999), Verdict(3, "threat"), guild, deps) == "absent"
    assert punished == [] and recorded == [(999, G)] and channel.deleted == [1]
    assert "author left" in logged[0]


async def test_held_tier_verdicts_for_one_member_collapse_within_a_batch(world):
    guild, channel, member, deps, logged, punished = world
    held = {}
    assert await apply_outcome(snap(1), Verdict(4, "a"), guild, deps, held=held) == "pending:7:ban"
    assert held == {42: 7}
    assert await apply_outcome(snap(2), Verdict(4, "b"), guild, deps, held=held) == "pending:7:ban"
    assert punished == [(42, 4, None), (42, 4, 7)]


async def test_punish_failure_is_fail_closed(world):
    guild, channel, member, deps, logged, punished = world

    async def boom(*a, **k):
        raise RuntimeError("discord 5xx")

    deps = Deps(**{**deps.__dict__, "punish": boom})
    assert await apply_outcome(snap(1), Verdict(2, "x"), guild, deps) == "error"
    assert channel.deleted == [] and "punishment failed" in logged[0]


# --- moderation: existing_pending_id joins the hold instead of opening another ----


async def test_punish_appends_to_an_existing_pending_action():
    guild = FakeGuild(id=G)
    m = FakeMember(id=42, guild=guild, guild_permissions=FakePermissions())
    first = await __import__("moderation").punish(m, 4, "first")
    pid = int(first.split(":")[1])
    second = await __import__("moderation").punish(m, 4, "second", existing_pending_id=pid)
    assert second == first
    assert len(m.timeouts) == 1  # one hold, not two
    row = database.get_pending(pid)
    assert row["reason"] == "first; also: second"
    assert len(database.list_pending(G)) == 1
