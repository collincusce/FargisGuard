"""Sonnet 5 re-check tier before a hold (D-011, Phase 5)."""

import logging

import pytest

import ai_engine
from ai_engine import RECHECK_MODEL, build_request, recheck
from pipeline import RECHECK_AT, Deps, apply_outcome, handle_message, reconcile
from tests.fakes import (
    FakeAnthropic,
    FakeChannel,
    FakeGuild,
    FakeMember,
    FakeMessage,
    batch_reply,
    ok_entry,
    violation_entry,
)
from tests.test_batcher import snap
from verdict import CLEAN, Unparseable, Verdict

G = 1001


@pytest.fixture(autouse=True)
def no_real_client(monkeypatch):
    monkeypatch.setattr(ai_engine, "get_client", lambda: (_ for _ in ()).throw(AssertionError()))


# --- request shape ----------------------------------------------------------------


async def test_recheck_request_uses_sonnet_with_thinking_disabled_and_no_sampling():
    fake = FakeAnthropic(reply=batch_reply(violation_entry(1, 2, "mild")))
    outcome = await recheck("rules", "content", client=fake, ruleset_key="k")
    (call,) = fake.messages.calls
    assert call["model"] == RECHECK_MODEL == "claude-sonnet-5"
    assert call["thinking"] == {"type": "disabled"}
    for banned in ("temperature", "top_p", "top_k", "cache_control"):
        assert banned not in call
    expected = build_request("r", ["c"])["output_config"]["format"]["schema"]
    assert call["output_config"]["format"]["schema"] is expected
    assert outcome == Verdict(2, "mild")


async def test_recheck_logs_its_own_tier(caplog):
    fake = FakeAnthropic(reply=batch_reply(ok_entry(1)))
    with caplog.at_level(logging.DEBUG, logger="ai_engine"):
        await recheck("r", "c", client=fake)
    assert "tier=recheck" in caplog.text and "batch=1" in caplog.text


def test_haiku_request_carries_no_thinking_key():
    assert "thinking" not in build_request("r", ["c"])


# --- reconcile (pure) ---------------------------------------------------------------


def test_lower_second_opinion_wins_and_keeps_both_reasons():
    v = reconcile(Verdict(4, "threat"), Verdict(2, "heated"))
    assert v.severity == 2 and "heated" in v.reason and "lowered from severity 4" in v.reason
    assert "threat" in v.reason


def test_equal_or_higher_second_opinion_never_escalates():
    assert reconcile(Verdict(3, "a"), Verdict(3, "b")).severity == 3
    assert reconcile(Verdict(3, "a"), Verdict(4, "b")).severity == 3


def test_clean_second_opinion_is_disputed_not_silently_clean():
    v = reconcile(Verdict(4, "threat"), CLEAN)
    assert v.severity == 4 and "DISPUTED" in v.reason and "needs a human" in v.reason


def test_failed_or_unparseable_second_opinion_keeps_the_original():
    v = reconcile(Verdict(3, "a"), Unparseable("stop_reason=refusal"))
    assert v.severity == 3 and "re-check failed" in v.reason and "refusal" in v.reason
    v = reconcile(Verdict(3, "a"), RuntimeError("429"))
    assert v.severity == 3 and "RuntimeError: 429" in v.reason


# --- wiring: who gets re-checked --------------------------------------------------


class Recorder:
    def __init__(self, second=CLEAN, error=None):
        self.calls = []
        self.punished = []
        self.logged = []
        self.second = second
        self.error = error

    async def recheck(self, rules_text, content, *, ruleset_key):
        self.calls.append((rules_text, content, ruleset_key))
        if self.error:
            raise self.error
        return self.second

    async def punish(self, member, severity, reason, **_):
        self.punished.append((severity, reason))
        return "warn" if severity < 3 else "pending:1:ban"

    async def log(self, guild, text):
        self.logged.append(text)

    def deps(self, first):
        async def analyze(content, guild_id, *, scope):
            return first

        from composer import ResolvedRules

        return Deps(
            analyze=analyze,
            punish=self.punish,
            log=self.log,
            recheck=self.recheck,
            resolve_rules=lambda scope: ResolvedRules("RULES", "k" * 64),
        )


@pytest.mark.parametrize("severity", [1, 2])
async def test_low_severity_is_never_rechecked(severity):
    rec = Recorder()
    msg = FakeMessage(content="x", guild=FakeGuild(id=G))
    assert await handle_message(msg, rec.deps(Verdict(severity, "r"))) == "warn"
    assert rec.calls == [] and rec.punished == [(severity, "r")]


@pytest.mark.parametrize("severity", [3, 4])
async def test_high_severity_is_rechecked_before_punish(severity):
    rec = Recorder(second=Verdict(2, "milder"))
    msg = FakeMessage(content="x", guild=FakeGuild(id=G))
    assert await handle_message(msg, rec.deps(Verdict(severity, "r"))) == "warn"
    assert rec.calls == [("RULES", "x", "k" * 64)]
    assert rec.punished[0][0] == 2 and "milder" in rec.punished[0][1]


async def test_recheck_failure_keeps_the_original_and_still_holds():
    rec = Recorder(error=RuntimeError("timeout"))
    msg = FakeMessage(content="x", guild=FakeGuild(id=G))
    assert await handle_message(msg, rec.deps(Verdict(4, "threat"))) == "pending:1:ban"
    assert rec.punished[0][0] == 4 and "re-check failed" in rec.punished[0][1]


async def test_no_rechecker_means_no_recheck():
    rec = Recorder()
    deps = Deps(**{**rec.deps(Verdict(4, "r")).__dict__, "recheck": None})
    msg = FakeMessage(content="x", guild=FakeGuild(id=G))
    assert await handle_message(msg, deps) == "pending:1:ban"
    assert rec.calls == [] and rec.punished == [(4, "r")]


async def test_batch_path_rechecks_with_the_frozen_rules():
    rec = Recorder(second=CLEAN)
    guild = FakeGuild(id=G)
    guild.channels[500] = FakeChannel(id=500)
    guild.members[42] = FakeMember(id=42, guild=guild)
    deps = rec.deps(None)
    action = await apply_outcome(
        snap(1), Verdict(4, "threat"), guild, deps, rules_text="FROZEN", ruleset_key="key1"
    )
    assert action == "pending:1:ban"
    assert rec.calls == [("FROZEN", "hi", "key1")]
    assert "DISPUTED" in rec.punished[0][1] and "DISPUTED" in rec.logged[-1]


async def test_batch_path_without_rules_text_skips_the_recheck():
    rec = Recorder()
    guild = FakeGuild(id=G)
    guild.channels[500] = FakeChannel(id=500)
    guild.members[42] = FakeMember(id=42, guild=guild)
    await apply_outcome(snap(1), Verdict(4, "threat"), guild, rec.deps(None))
    assert rec.calls == []


def test_recheck_threshold_matches_the_held_tier():
    assert RECHECK_AT == 3 == ai_engine.RECHECK_AT


def test_create_bot_wires_the_rechecker():
    from tests.test_bot_wiring import _bot

    assert _bot().deps.recheck is recheck
