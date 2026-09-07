"""/rules handlers and their permission gates (gameplan D1, Phase 5)."""

import discord
import pytest
from discord import app_commands

import rules
from ai_engine import render_floor
from channels import ScopeChain
from rulecmds import MAX_RULES_CHARS, chain_for, clear_reply, set_reply, show_reply
from rules import CATEGORY, CHANNEL, DEFAULT_RULES, THREAD
from tests.fakes import (
    FakeCategory,
    FakeChannel,
    FakeGuild,
    FakeInteraction,
    FakeMember,
    FakePermissions,
    FakeThread,
)
from tests.test_bot_wiring import _bot

G = 31


# --- handlers -------------------------------------------------------------------


def test_set_stores_at_the_target_id_and_reports_the_version():
    reply = set_reply(G, CHANNEL, FakeChannel(id=10), "  Videos only.  ")
    assert "updated" in reply and "<#10>" in reply and "version 1" in reply
    assert rules.get_scope_rules(G, CHANNEL, 10) == "Videos only."


def test_set_rejects_blank_and_oversized_text_without_writing():
    assert "Nothing stored" in set_reply(G, CATEGORY, FakeCategory(id=3), "   ")
    assert "Too long" in set_reply(G, CATEGORY, FakeCategory(id=3), "x" * (MAX_RULES_CHARS + 1))
    assert rules.get_scope_rules(G, CATEGORY, 3) is None
    assert rules.get_rules_version(G) == 0


def test_thread_scope_is_keyed_by_the_parent_channel():
    set_reply(G, THREAD, FakeChannel(id=10), "Plain text replies.")
    assert rules.get_scope_rules(G, THREAD, 10) == "Plain text replies."


def test_clear_reports_whether_anything_existed():
    set_reply(G, CHANNEL, FakeChannel(id=10), "x")
    assert "cleared" in clear_reply(G, CHANNEL, FakeChannel(id=10))
    assert "No rules were set" in clear_reply(G, CHANNEL, FakeChannel(id=10))
    assert "/setrules" in clear_reply(G, "guild", FakeChannel(id=10))


def test_chain_for_a_thread_object_and_for_the_in_thread_flag():
    parent = FakeChannel(id=10, category_id=3)
    guild = FakeGuild(id=G, channels={10: parent})
    assert chain_for(guild, FakeThread(id=70, parent_id=10)) == ScopeChain(G, 3, 10, True)
    assert chain_for(guild, parent, in_thread=True) == ScopeChain(G, 3, 10, True)
    assert chain_for(guild, parent) == ScopeChain(G, 3, 10, False)


def test_show_renders_floor_then_composed_text_and_the_key():
    set_reply(G, CHANNEL, FakeChannel(id=10), "Videos only.")
    set_reply(G, THREAD, FakeChannel(id=10), "Replies are text.")
    guild = FakeGuild(id=G)
    root = show_reply(guild, FakeChannel(id=10))
    assert render_floor() in root and DEFAULT_RULES.splitlines()[0] in root
    assert "Videos only." in root and "Replies are text." not in root
    assert "ruleset `" in root and "<#10>" in root
    threads = show_reply(guild, FakeChannel(id=10), in_thread=True)
    assert "Replies are text." in threads and "inside its threads" in threads


def test_show_matches_what_the_classifier_would_receive():
    from composer import compose_rules

    set_reply(G, CHANNEL, FakeChannel(id=10), "Videos only.")
    chain = ScopeChain(G, None, 10, False)
    _, fragments = rules.snapshot(G)
    expected = compose_rules(chain, fragments)
    reply = show_reply(FakeGuild(id=G), FakeChannel(id=10))
    assert expected.text in reply and expected.key[:12] in reply


def test_show_truncates_long_rules_inside_the_discord_limit():
    set_reply(G, CHANNEL, FakeChannel(id=10), "y" * MAX_RULES_CHARS)
    reply = show_reply(FakeGuild(id=G), FakeChannel(id=10))
    assert len(reply) <= 2000 and "truncated" in reply


# --- permission gates (D1): every authoring command is Administrator-only ---------


def _group():
    group = _bot().tree.get_command("rules")
    assert isinstance(group, app_commands.Group)
    return group


@pytest.mark.parametrize("name", ["category", "channel", "thread", "clear", "show"])
async def test_every_rules_subcommand_checks_administrator(name):
    cmd = _group().get_command(name)
    assert cmd is not None and cmd.checks, f"/rules {name} must carry a has_permissions check"
    admin = FakeInteraction(user=FakeMember(guild_permissions=FakePermissions(administrator=True)))
    mod = FakeInteraction(user=FakeMember(guild_permissions=FakePermissions(manage_messages=True)))
    (check,) = cmd.checks
    assert check(admin) is True
    with pytest.raises(app_commands.MissingPermissions):
        check(mod)


def test_rules_group_defaults_to_administrator_and_guild_only():
    group = _group()
    assert group.default_permissions is not None
    assert group.default_permissions.administrator is True
    assert group.guild_only is True


def test_targets_are_channel_selects_not_strings():
    group = _group()
    kinds = {
        name: {p.name: p.type for p in group.get_command(name).parameters}
        for name in ("category", "channel", "thread", "clear", "show")
    }
    channel_t = discord.AppCommandOptionType.channel
    assert kinds["category"]["category"] is channel_t
    assert kinds["channel"]["channel"] is channel_t
    assert kinds["thread"]["channel"] is channel_t
    assert kinds["clear"]["target"] is channel_t
    assert kinds["show"]["channel"] is channel_t


def test_setrules_is_unchanged():
    cmd = _bot().tree.get_command("setrules")
    assert cmd is not None and cmd.default_permissions.administrator is True
    names = [p.name for p in cmd.parameters]
    assert names == ["rules"]
