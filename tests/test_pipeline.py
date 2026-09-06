from dataclasses import dataclass, field

import pytest

from channels import ScopeChain
from pipeline import Deps, describe_action, handle_message, should_analyze
from tests.fakes import FakeChannel, FakeGuild, FakeMember, FakeMessage, FakeThread


@dataclass
class Recorder:
    reply: str = "OK"
    analyzed: list[tuple[str, int]] = field(default_factory=list)
    scopes: list[ScopeChain] = field(default_factory=list)
    punished: list[tuple[int, int, str, frozenset]] = field(default_factory=list)
    logged: list[str] = field(default_factory=list)
    action: str = "warn"
    analyze_error: Exception | None = None
    punish_error: Exception | None = None

    def deps(self) -> Deps:
        async def analyze(content, guild_id, *, scope):
            self.analyzed.append((content, guild_id))
            self.scopes.append(scope)
            if self.analyze_error is not None:
                raise self.analyze_error
            return self.reply

        async def punish(member, severity, reason, *, immune_role_ids=()):
            self.punished.append((member.id, severity, reason, frozenset(immune_role_ids)))
            if self.punish_error is not None:
                raise self.punish_error
            return self.action

        async def log(guild, text):
            self.logged.append(text)

        return Deps(analyze=analyze, punish=punish, log=log, immune_role_ids=frozenset({9}))


@pytest.fixture
def rec():
    return Recorder()


async def test_bot_authors_are_ignored(rec):
    msg = FakeMessage(author=FakeMember(bot=True))
    assert await handle_message(msg, rec.deps()) == "ignored"
    assert rec.analyzed == []


async def test_dms_are_ignored(rec):
    msg = FakeMessage(guild=None)
    assert await handle_message(msg, rec.deps()) == "ignored"
    assert rec.analyzed == []


async def test_nsfw_flagged_channel_skips_analysis(rec):
    msg = FakeMessage(channel=FakeChannel(name="art", nsfw=True))
    assert await handle_message(msg, rec.deps()) == "exempt"
    assert rec.analyzed == []


async def test_channel_merely_named_nsfw_is_analyzed(rec):
    msg = FakeMessage(channel=FakeChannel(name="nsfw", nsfw=False))
    assert await handle_message(msg, rec.deps()) == "clean"
    assert len(rec.analyzed) == 1


async def test_clean_reply_takes_no_action(rec):
    msg = FakeMessage(content="gg", guild=FakeGuild(id=7))
    assert await handle_message(msg, rec.deps()) == "clean"
    assert rec.analyzed == [("gg", 7)]
    assert rec.punished == [] and rec.logged == [] and msg.deleted is False


async def test_violation_punishes_deletes_and_logs(rec):
    rec.reply = "VIOLATION|2|flooding"
    rec.action = "timeout"
    msg = FakeMessage(content="spam spam", author=FakeMember(id=42))
    assert await handle_message(msg, rec.deps()) == "timeout"
    assert rec.punished == [(42, 2, "flooding", frozenset({9}))]
    assert msg.deleted is True
    assert len(rec.logged) == 1
    assert "Action: timeout" in rec.logged[0] and "Reason: flooding" in rec.logged[0]


async def test_delete_forbidden_still_logs(rec):
    rec.reply = "VIOLATION|1|x"
    msg = FakeMessage(delete_forbidden=True)
    assert await handle_message(msg, rec.deps()) == "warn"
    assert msg.deleted is False and len(rec.logged) == 1


# --- Phase 3: fail-closed behavior (INVARIANT-03) -------------------------------


@pytest.mark.parametrize("content", ["", "   ", "\n\t", None])
def test_should_analyze_rejects_empty(content):
    assert should_analyze(content) is False


def test_should_analyze_accepts_text():
    assert should_analyze("hi") is True


async def test_empty_message_never_reaches_the_analyzer(rec):
    msg = FakeMessage(content="   ")
    assert await handle_message(msg, rec.deps()) == "skipped"
    assert rec.analyzed == []


async def test_analyzer_error_posts_to_mod_log_and_punishes_nobody(rec):
    rec.analyze_error = TimeoutError("openai timed out")
    msg = FakeMessage(content="hello")
    assert await handle_message(msg, rec.deps()) == "error"
    assert rec.punished == [] and msg.deleted is False
    assert len(rec.logged) == 1
    assert "analysis failed" in rec.logged[0] and "TimeoutError" in rec.logged[0]
    assert msg.jump_url in rec.logged[0]


async def test_punisher_error_posts_to_mod_log(rec):
    rec.reply = "VIOLATION|2|flood"
    rec.punish_error = RuntimeError("discord 5xx")
    msg = FakeMessage(content="spam")
    assert await handle_message(msg, rec.deps()) == "error"
    assert msg.deleted is False
    assert len(rec.logged) == 1 and "punishment failed" in rec.logged[0]


async def test_ok_sentinel_is_clean_and_silent(rec):
    rec.reply = "OK"
    assert await handle_message(FakeMessage(content="gg"), rec.deps()) == "clean"
    assert rec.logged == []


@pytest.mark.parametrize("reply", ["Looks fine to me.", "VIOLATION|9|x", "ok", "VIOLATION|2"])
async def test_unparseable_reply_goes_to_a_human_with_the_raw_text(rec, reply):
    rec.reply = reply
    msg = FakeMessage(content="hmm")
    assert await handle_message(msg, rec.deps()) == "unparseable"
    assert rec.punished == [] and msg.deleted is False
    assert len(rec.logged) == 1
    assert reply in rec.logged[0] and "needs a human" in rec.logged[0]


async def test_logger_failure_does_not_escape(rec):
    rec.analyze_error = RuntimeError("boom")

    async def bad_log(guild, text):
        raise RuntimeError("mod-log channel gone")

    deps = Deps(analyze=rec.deps().analyze, punish=rec.deps().punish, log=bad_log)
    assert await handle_message(FakeMessage(content="x"), deps) == "error"


async def test_pending_action_notice_names_the_id_and_the_command(rec):
    rec.reply = "VIOLATION|4|hate"
    rec.action = "pending:12:ban"
    msg = FakeMessage(content="...")
    assert await handle_message(msg, rec.deps()) == "pending:12:ban"
    assert "/modaction 12 approve" in rec.logged[0] and "**ban**" in rec.logged[0]


def test_describe_action_passthrough():
    assert describe_action("timeout") == "timeout"


# --- Phase 2 (scoped rules): scope resolution inside the fail-closed boundary ----


async def test_resolved_scope_reaches_the_analyzer(rec):
    guild = FakeGuild(id=7)
    msg = FakeMessage(content="hi", guild=guild, channel=FakeChannel(id=55, category_id=9))
    assert await handle_message(msg, rec.deps()) == "clean"
    assert rec.scopes == [ScopeChain(guild_id=7, category_id=9, channel_id=55, in_thread=False)]


async def test_thread_message_resolves_to_its_parent_channel(rec):
    parent = FakeChannel(id=55, category_id=9)
    guild = FakeGuild(id=7, channels={55: parent})
    msg = FakeMessage(content="hi", guild=guild, channel=FakeThread(id=77, parent_id=55))
    assert await handle_message(msg, rec.deps()) == "clean"
    assert rec.scopes == [ScopeChain(guild_id=7, category_id=9, channel_id=55, in_thread=True)]


async def test_thread_with_a_vanished_parent_fails_closed(rec):
    guild = FakeGuild(id=7, channels={})
    msg = FakeMessage(content="hi", guild=guild, channel=FakeThread(id=77, parent_id=55))
    assert await handle_message(msg, rec.deps()) == "error"
    assert rec.analyzed == [] and msg.deleted is False
    assert len(rec.logged) == 1
    assert "scope resolution failed" in rec.logged[0] and "ScopeError" in rec.logged[0]


async def test_raising_channel_probe_fails_closed_instead_of_escaping(rec):
    class ExplodingChannel(FakeChannel):
        def is_nsfw(self) -> bool:
            raise RuntimeError("Parent channel not found")

    msg = FakeMessage(content="hi", channel=ExplodingChannel())
    assert await handle_message(msg, rec.deps()) == "error"
    assert rec.analyzed == [] and "RuntimeError" in rec.logged[0]


async def test_empty_message_is_skipped_before_any_channel_access(rec):
    class ExplodingChannel(FakeChannel):
        def is_nsfw(self) -> bool:
            raise RuntimeError("should not be reached")

    msg = FakeMessage(content="  ", channel=ExplodingChannel())
    assert await handle_message(msg, rec.deps()) == "skipped"
    assert rec.logged == []
