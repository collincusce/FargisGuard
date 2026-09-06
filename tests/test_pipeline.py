from dataclasses import dataclass, field

import pytest

from pipeline import Deps, handle_message
from tests.fakes import FakeChannel, FakeGuild, FakeMember, FakeMessage


@dataclass
class Recorder:
    reply: str = "clean"
    analyzed: list[tuple[str, int]] = field(default_factory=list)
    punished: list[tuple[int, int, str, frozenset]] = field(default_factory=list)
    logged: list[str] = field(default_factory=list)
    action: str = "warn"

    def deps(self) -> Deps:
        async def analyze(content, guild_id):
            self.analyzed.append((content, guild_id))
            return self.reply

        async def punish(member, severity, reason, *, immune_role_ids=()):
            self.punished.append((member.id, severity, reason, frozenset(immune_role_ids)))
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
