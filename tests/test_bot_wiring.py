from pathlib import Path

import discord
from discord.ext import commands

import bot as botmod
from bot import FargisGuard, create_bot, make_intents


async def _analyze(content, guild_id):
    return "clean"


async def _punish(member, severity, reason, *, immune_role_ids=()):
    return "warn"


def _bot() -> FargisGuard:
    return create_bot(analyze=_analyze, punisher=_punish, immune_role_ids=frozenset({1}))


def test_import_does_not_connect_and_factory_returns_a_bot():
    assert isinstance(_bot(), commands.Bot)


def test_intents_are_narrowed():
    i = make_intents()
    assert i.guilds and i.members and i.message_content and i.messages
    assert not i.presences and not i.voice_states


def test_setrules_has_a_real_app_command_permission_check():
    cmd = _bot().tree.get_command("setrules")
    assert cmd is not None
    assert cmd.checks, "app_commands check must be registered (H-02)"
    assert cmd.default_permissions is not None
    assert cmd.default_permissions.administrator is True


def test_appeal_command_is_registered_for_everyone():
    cmd = _bot().tree.get_command("appeal")
    assert cmd is not None and cmd.default_permissions is None


async def test_setup_hook_syncs_the_command_tree_and_starts_the_dashboard_once():
    started = []
    b = create_bot(
        analyze=_analyze, punisher=_punish, dashboard_starter=lambda: started.append(1) or None
    )
    calls = []

    async def fake_sync(*, guild=None):
        calls.append(guild)
        return []

    b.tree.sync = fake_sync
    await b.setup_hook()
    assert calls == [None]
    assert started == [1]


def test_dashboard_is_not_started_from_on_ready():
    import inspect

    assert "dashboard" not in inspect.getsource(FargisGuard.on_ready)


def test_no_code_path_replies_with_model_output():
    for name in ("bot.py", "pipeline.py"):
        src = Path(name).read_text()
        assert ".reply(" not in src, f"{name} must not echo model output (H-09)"


def test_prefix_commands_are_not_used():
    assert _bot().command_prefix is commands.when_mentioned


def test_module_has_main_guard():
    assert "if __name__ == \"__main__\":" in Path(botmod.__file__).read_text()


def test_intents_type():
    assert isinstance(make_intents(), discord.Intents)
