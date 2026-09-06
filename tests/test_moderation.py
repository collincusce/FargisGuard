from datetime import datetime

import pytest

import moderation
from moderation import ACTIONS, is_immune, punish
from tests.fakes import FakeMember, FakePermissions, FakeRole


@pytest.fixture
def warnings(monkeypatch):
    """Record add_warning calls instead of touching SQLite."""
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(moderation, "add_warning", lambda uid, gid: calls.append((uid, gid)))
    return calls


async def test_severity_1_dms_a_warning(warnings):
    m = FakeMember()
    assert await punish(m, 1, "spam") == "warn"
    assert m.sent == ["⚠️ Warning: spam"]
    assert warnings == [(m.id, m.guild.id)]


async def test_severity_1_with_dms_closed_still_warns_without_raising(warnings):
    m = FakeMember(dms_closed=True)
    assert await punish(m, 1, "spam") == "warn"
    assert m.sent == []
    assert warnings == [(m.id, m.guild.id)]


async def test_severity_2_times_out_with_a_real_datetime(warnings):
    m = FakeMember()
    assert await punish(m, 2, "flood") == "timeout"
    ((until, reason),) = m.timeouts
    assert isinstance(until, datetime)
    assert until.tzinfo is not None
    assert reason == "flood"


async def test_severity_3_kicks(warnings):
    m = FakeMember()
    assert await punish(m, 3, "harassment") == "kick"
    assert m.kicks == ["harassment"]
    assert m.bans == []


async def test_severity_4_bans(warnings):
    m = FakeMember()
    assert await punish(m, 4, "hate") == "ban"
    assert m.bans == ["hate"]


@pytest.mark.parametrize("severity", [0, 5, 99, -1])
async def test_unknown_severity_takes_no_action_and_records_nothing(warnings, severity):
    m = FakeMember()
    assert await punish(m, severity, "x") == "none"
    assert not (m.sent or m.timeouts or m.kicks or m.bans)
    assert warnings == []


def test_action_map_is_explicit_and_complete():
    assert ACTIONS == {1: "warn", 2: "timeout", 3: "kick", 4: "ban"}


def test_administrator_is_immune():
    m = FakeMember(guild_permissions=FakePermissions(administrator=True))
    assert is_immune(m, ()) is True


def test_manage_messages_is_immune():
    m = FakeMember(guild_permissions=FakePermissions(manage_messages=True))
    assert is_immune(m, ()) is True


def test_configured_role_id_is_immune():
    m = FakeMember(roles=[FakeRole(id=555, name="whatever")])
    assert is_immune(m, {555}) is True


def test_role_named_moderator_is_not_immune_by_name():
    m = FakeMember(roles=[FakeRole(id=777, name="Moderator"), FakeRole(id=778, name="Admin")])
    assert is_immune(m, {555}) is False


async def test_immune_member_is_never_punished(warnings):
    m = FakeMember(guild_permissions=FakePermissions(administrator=True))
    assert await punish(m, 4, "x") == "immune"
    assert m.bans == [] and warnings == []
