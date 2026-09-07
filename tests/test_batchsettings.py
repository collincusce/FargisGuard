"""Per-guild batch interval (gameplan D5) and the /batch commands."""

import pytest
from discord import app_commands

import batchsettings
from batchsettings import (
    BATCH_MAX_SECONDS,
    clamp_interval,
    get_batch_interval,
    set_batch_interval,
    set_reply,
    show_reply,
)
from pipeline import Deps, handle_message
from tests.fakes import FakeGuild, FakeInteraction, FakeMember, FakeMessage, FakePermissions
from tests.test_bot_wiring import _bot
from verdict import CLEAN

G = 77


# --- storage -------------------------------------------------------------------


def test_unknown_guild_is_off():
    assert get_batch_interval(G) == 0


@pytest.mark.parametrize(
    "given, stored",
    [
        (0, 0),
        (-5, 0),
        (1, 1),
        (45, 45),
        (BATCH_MAX_SECONDS, BATCH_MAX_SECONDS),
        (10**6, BATCH_MAX_SECONDS),
    ],
)
def test_set_clamps_to_the_system_ceiling(given, stored):
    assert set_batch_interval(G, given) == stored
    assert get_batch_interval(G) == stored


@pytest.mark.parametrize("bad", ["30", 3.5, None, True])
def test_non_integers_are_rejected_before_any_write(bad):
    with pytest.raises(ValueError):
        clamp_interval(bad)
    assert "Not stored" in set_reply(G, bad)
    assert get_batch_interval(G) == 0


def test_settings_are_per_guild():
    set_batch_interval(G, 30)
    assert get_batch_interval(G + 1) == 0


# --- replies -------------------------------------------------------------------


def test_show_when_off_explains_how_to_turn_on():
    text = show_reply(G, depth=0)
    assert "off" in text and "/batch set" in text


def test_show_when_on_states_interval_depth_cap_and_exposure_window():
    set_batch_interval(G, 60)
    text = show_reply(G, depth=4)
    assert "**60s**" in text and "**4** message(s)" in text
    assert "batches of up to 60 seconds" in text and "may stay visible" in text


def test_set_reply_mentions_the_cap_when_clamped():
    text = set_reply(G, 9999)
    assert f"**{BATCH_MAX_SECONDS}s**" in text and "capped from 9999s" in text
    assert "may stay visible" in text
    assert "off" in set_reply(G, 0)


# --- the batcher reads the interval per enqueue (no restart) --------------------


class RecordingBatcher:
    def __init__(self):
        self.intervals = []

    def enqueue(self, snapshot, rules, interval):
        self.intervals.append(interval)
        return "queued"


async def test_interval_change_applies_to_the_next_message_without_restart():
    rb = RecordingBatcher()
    analyzed = []

    async def analyze(content, guild_id, *, scope):
        analyzed.append(content)
        return CLEAN

    async def punish(*a, **k):
        return "warn"

    async def log(*a):
        pass

    from composer import ResolvedRules

    deps = Deps(
        analyze=analyze,
        punish=punish,
        log=log,
        batcher=rb,
        interval_for=batchsettings.get_batch_interval,  # what create_bot wires
        resolve_rules=lambda scope: ResolvedRules("r", "k" * 64),
    )
    msg = FakeMessage(content="a", guild=FakeGuild(id=G))
    assert await handle_message(msg, deps) == "clean"  # off: per-message path
    set_batch_interval(G, 20)
    assert await handle_message(msg, deps) == "queued"
    set_batch_interval(G, 0)
    assert await handle_message(msg, deps) == "clean"
    assert rb.intervals == [20] and analyzed == ["a", "a"]


# --- commands ------------------------------------------------------------------


def _group():
    group = _bot().tree.get_command("batch")
    assert isinstance(group, app_commands.Group)
    return group


@pytest.mark.parametrize("name", ["set", "show"])
async def test_batch_subcommands_are_administrator_only(name):
    cmd = _group().get_command(name)
    assert cmd is not None and cmd.checks
    admin = FakeInteraction(user=FakeMember(guild_permissions=FakePermissions(administrator=True)))
    mod = FakeInteraction(user=FakeMember(guild_permissions=FakePermissions(manage_guild=True)))
    (check,) = cmd.checks
    assert check(admin) is True
    with pytest.raises(app_commands.MissingPermissions):
        check(mod)


def test_batch_group_defaults_and_parameter():
    group = _group()
    assert group.default_permissions.administrator is True and group.guild_only is True
    (param,) = group.get_command("set").parameters
    assert param.name == "seconds" and param.type.name == "integer"


def test_create_bot_wires_the_stored_interval():
    b = _bot()
    assert b.deps.interval_for is batchsettings.get_batch_interval
