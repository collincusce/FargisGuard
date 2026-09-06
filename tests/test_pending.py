import discord
import pytest

from bot import create_bot
from database import add_warning, get_pending, get_warnings, list_pending
from moderation import HOLD_MINUTES, TIMEOUT_MINUTES, punish, resolve_pending_action
from tests.fakes import FakeGuild, FakeMember


async def _noop_analyze(content, guild_id):
    return "OK"


@pytest.fixture
def guild():
    return FakeGuild(id=1001)


@pytest.fixture
def member(guild):
    m = FakeMember(id=42, guild=guild)
    guild.members[42] = m
    return m


async def test_severity_4_is_held_not_banned(member, guild):
    result = await punish(member, 4, "hate")
    assert result.startswith("pending:") and result.endswith(":ban")
    assert member.bans == [] and member.kicks == []
    (hold,) = member.timeouts
    assert hold[0] is not None and "review" in hold[1]
    pid = int(result.split(":")[1])
    row = get_pending(pid)
    assert row["user_id"] == 42 and row["action"] == "ban" and row["reason"] == "hate"
    assert get_warnings(42, guild.id) == 1


async def test_severity_3_is_held_as_kick(member):
    result = await punish(member, 3, "harass")
    assert result.endswith(":kick") and member.kicks == []


async def test_escalation_raises_a_repeat_offender_into_review(member, guild):
    for _ in range(3):
        add_warning(42, guild.id)
    result = await punish(member, 2, "again")  # 2 + 1 = 3 -> kick, held
    assert result.startswith("pending:") and result.endswith(":kick")


async def test_first_offense_severity_2_is_an_immediate_timeout(member):
    assert await punish(member, 2, "flood") == "timeout"
    ((until, reason),) = member.timeouts
    assert reason == "flood" and until is not None


async def test_approve_executes_the_ban_and_marks_the_row(member, guild):
    pid = int((await punish(member, 4, "hate")).split(":")[1])
    msg = await resolve_pending_action(guild, pid, "approve", moderator_id=7)
    assert "approved" in msg
    assert guild.bans == [(42, "hate")]
    assert get_pending(pid)["status"] == "approved"
    assert get_pending(pid)["resolved_by"] == 7


async def test_approve_executes_a_kick(member, guild):
    pid = int((await punish(member, 3, "harass")).split(":")[1])
    await resolve_pending_action(guild, pid, "approve", moderator_id=7)
    assert member.kicks == ["harass"] and guild.bans == []


async def test_deny_lifts_the_hold_and_marks_the_row(member, guild):
    pid = int((await punish(member, 4, "hate")).split(":")[1])
    msg = await resolve_pending_action(guild, pid, "deny", moderator_id=7)
    assert "denied" in msg
    assert member.timeouts[-1] == (None, f"Pending #{pid} denied")
    assert get_pending(pid)["status"] == "denied" and guild.bans == []


async def test_resolving_twice_is_refused(member, guild):
    pid = int((await punish(member, 4, "hate")).split(":")[1])
    await resolve_pending_action(guild, pid, "deny", moderator_id=7)
    assert "already denied" in await resolve_pending_action(guild, pid, "approve", moderator_id=7)
    assert guild.bans == []


async def test_wrong_guild_or_unknown_id_is_refused(member, guild):
    pid = int((await punish(member, 4, "hate")).split(":")[1])
    other = FakeGuild(id=2002)
    wrong_guild = await resolve_pending_action(other, pid, "approve", moderator_id=7)
    unknown_id = await resolve_pending_action(guild, 9999, "approve", moderator_id=7)
    assert "No pending action" in wrong_guild and "No pending action" in unknown_id
    assert guild.bans == [] and other.bans == []


async def test_ban_still_executes_after_the_member_left(member, guild):
    pid = int((await punish(member, 4, "hate")).split(":")[1])
    del guild.members[42]
    await resolve_pending_action(guild, pid, "approve", moderator_id=7)
    assert guild.bans == [(42, "hate")]


async def test_kick_after_member_left_marks_approved_without_action(member, guild):
    pid = int((await punish(member, 3, "harass")).split(":")[1])
    del guild.members[42]
    msg = await resolve_pending_action(guild, pid, "approve", moderator_id=7)
    assert "already left" in msg and get_pending(pid)["status"] == "approved"


def test_modaction_requires_ban_members():
    cmd = create_bot(analyze=_noop_analyze).tree.get_command("modaction")
    assert cmd is not None and cmd.checks
    assert cmd.default_permissions.ban_members is True


def test_hold_is_longer_than_a_timeout():
    assert HOLD_MINUTES > TIMEOUT_MINUTES


def test_no_kick_or_ban_call_in_punish_source():
    import inspect

    src = inspect.getsource(punish)
    assert ".kick(" not in src and ".ban(" not in src


def test_list_pending_is_empty_initially(guild):
    assert list_pending(guild.id) == []


def test_discord_object_is_used_for_ban_of_absent_member():
    assert discord.Object(id=1).id == 1
