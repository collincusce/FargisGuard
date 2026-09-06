import pytest

from appeals import format_pending_appeals, resolve_appeal_action, submit_appeal
from bot import create_bot
from database import add_warning, get_appeal, get_warnings, list_pending_appeals
from tests.fakes import FakeGuild, FakeInteraction, FakeMember


async def _analyze(content, guild_id):
    return "OK"


@pytest.fixture
def bot():
    logged = []

    async def log(guild, text):
        logged.append(text)

    b = create_bot(analyze=_analyze, dashboard_starter=lambda: None)
    object.__setattr__(b.deps, "log", log)  # Deps is frozen; swap the logger for the test
    b.logged = logged
    return b


def _cmd(bot, name):
    return bot.tree.get_command(name).callback


def test_second_pending_appeal_is_rejected():
    assert submit_appeal(1, 2, "first") == 1
    assert submit_appeal(1, 2, "again") is None
    assert submit_appeal(1, 3, "other guild") == 2  # different guild is fine
    assert len(list_pending_appeals(2)) == 1


def test_approve_clears_warnings_and_records_the_moderator():
    add_warning(1, 2)
    add_warning(1, 2)
    aid = submit_appeal(1, 2, "sorry")
    msg = resolve_appeal_action(2, aid, "approve", moderator_id=9)
    assert "approved" in msg and get_warnings(1, 2) == 0
    row = get_appeal(aid)
    assert row["status"] == "approved" and row["resolved_by"] == 9 and row["resolved_at"]
    assert submit_appeal(1, 2, "can appeal again later") == aid + 1


def test_deny_keeps_warnings():
    add_warning(1, 2)
    aid = submit_appeal(1, 2, "sorry")
    assert "denied" in resolve_appeal_action(2, aid, "deny", moderator_id=9)
    assert get_warnings(1, 2) == 1 and get_appeal(aid)["status"] == "denied"


def test_resolving_twice_or_wrong_guild_is_refused():
    aid = submit_appeal(1, 2, "sorry")
    assert "No appeal" in resolve_appeal_action(3, aid, "approve", moderator_id=9)
    resolve_appeal_action(2, aid, "deny", moderator_id=9)
    assert "already denied" in resolve_appeal_action(2, aid, "approve", moderator_id=9)


def test_format_pending_appeals():
    assert format_pending_appeals(2) == "No pending appeals."
    submit_appeal(1, 2, "sorry")
    text = format_pending_appeals(2)
    assert "#1" in text and "<@1>" in text and "sorry" in text


async def test_appeal_command_notifies_mod_log(bot):
    guild = FakeGuild(id=2)
    ix = FakeInteraction(user=FakeMember(id=1), guild=guild)
    await _cmd(bot, "appeal")(ix, "please reconsider")
    assert ix.response.sent[0][1] is True  # ephemeral
    assert "#1" in ix.response.sent[0][0]
    assert len(bot.logged) == 1
    assert "Appeal #1" in bot.logged[0] and "<@1>" in bot.logged[0]
    assert "/appeal_resolve 1 approve" in bot.logged[0]


async def test_appeal_command_duplicate_does_not_notify_twice(bot):
    ix = FakeInteraction(user=FakeMember(id=1), guild=FakeGuild(id=2))
    await _cmd(bot, "appeal")(ix, "one")
    await _cmd(bot, "appeal")(ix, "two")
    assert "already have a pending appeal" in ix.response.sent[1][0]
    assert len(bot.logged) == 1


async def test_appeals_and_resolve_commands(bot):
    add_warning(1, 2)
    user_ix = FakeInteraction(user=FakeMember(id=1), guild=FakeGuild(id=2))
    await _cmd(bot, "appeal")(user_ix, "sorry")
    mod_ix = FakeInteraction(user=FakeMember(id=9), guild=FakeGuild(id=2))
    await _cmd(bot, "appeals")(mod_ix)
    assert "sorry" in mod_ix.response.sent[0][0]
    await _cmd(bot, "appeal_resolve")(mod_ix, 1, "approve")
    assert "approved" in mod_ix.response.sent[1][0]
    assert get_warnings(1, 2) == 0


def test_moderator_commands_require_manage_guild(bot):
    for name in ("appeals", "appeal_resolve"):
        cmd = bot.tree.get_command(name)
        assert cmd.checks and cmd.default_permissions.manage_guild is True
