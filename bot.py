"""Discord gateway: bot factory, slash commands, and the on_message entry point.

Importing this module never connects; ``main()`` does (D5).
"""

import asyncio
import functools
from collections.abc import Callable

import discord
from discord import app_commands
from discord.ext import commands

import config
import database
from ai_engine import analyze_message
from appeals import format_pending_appeals, resolve_appeal_action, submit_appeal
from dashboard import start_dashboard
from moderation import punish, resolve_pending_action
from pipeline import Deps, handle_message
from rules import set_rules


def make_intents() -> discord.Intents:
    """Only what moderation needs; presences and the rest stay off."""
    return discord.Intents(guilds=True, members=True, messages=True, message_content=True)


def mod_log_poster(channel_name: str):
    async def post(guild: discord.Guild, text: str) -> None:
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if channel is not None:
            await channel.send(text)

    return post


DashboardStarter = Callable[[], "asyncio.Task | None"]


class FargisGuard(commands.Bot):
    def __init__(
        self,
        deps: Deps,
        *,
        intents: discord.Intents | None = None,
        dashboard_starter: DashboardStarter | None = None,
    ):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents or make_intents())
        self.deps = deps
        self.dashboard_starter = dashboard_starter
        self.dashboard_task: asyncio.Task | None = None
        register_commands(self)

    async def setup_hook(self) -> None:
        """Runs once, before the gateway connects — never on reconnect (H-11)."""
        await self.tree.sync()
        if self.dashboard_starter is not None:
            self.dashboard_task = self.dashboard_starter()

    async def on_ready(self) -> None:
        print(f"🤖 FargisGuard online as {self.user}")

    async def on_message(self, message: discord.Message) -> None:
        await handle_message(message, self.deps)


def register_commands(bot: commands.Bot) -> None:
    @bot.tree.command(name="appeal", description="Appeal a moderation action against you")
    @app_commands.describe(reason="Why the action should be reconsidered")
    async def appeal(interaction: discord.Interaction, reason: str) -> None:
        appeal_id = submit_appeal(interaction.user.id, interaction.guild_id, reason)
        if appeal_id is None:
            await interaction.response.send_message(
                "You already have a pending appeal; a moderator will review it.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"📨 Appeal #{appeal_id} submitted.", ephemeral=True
        )
        await bot.deps.log(
            interaction.guild,
            f"📨 **Appeal #{appeal_id}** from {interaction.user.mention}: {reason}\n"
            f"Run `/appeal_resolve {appeal_id} approve` or `/appeal_resolve {appeal_id} deny`.",
        )

    @bot.tree.command(name="appeals", description="List pending appeals")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def appeals(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            format_pending_appeals(interaction.guild_id), ephemeral=True
        )

    @bot.tree.command(name="appeal_resolve", description="Approve or deny an appeal")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(appeal_id="The #id from the mod-log notice", decision="approve or deny")
    @app_commands.choices(
        decision=[
            app_commands.Choice(name="approve", value="approve"),
            app_commands.Choice(name="deny", value="deny"),
        ]
    )
    async def appeal_resolve(
        interaction: discord.Interaction, appeal_id: int, decision: str
    ) -> None:
        result = resolve_appeal_action(
            interaction.guild_id, appeal_id, decision, moderator_id=interaction.user.id
        )
        await interaction.response.send_message(result, ephemeral=True)

    @bot.tree.command(name="setrules", description="Replace this server's moderation rules")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(rules="The full rules text the moderator AI will enforce")
    async def setrules(interaction: discord.Interaction, rules: str) -> None:
        set_rules(interaction.guild_id, rules)
        await interaction.response.send_message("📜 Rules updated.", ephemeral=True)

    @bot.tree.command(name="modaction", description="Approve or deny a pending kick/ban")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(pending_id="The #id from the mod-log notice", decision="approve or deny")
    @app_commands.choices(
        decision=[
            app_commands.Choice(name="approve", value="approve"),
            app_commands.Choice(name="deny", value="deny"),
        ]
    )
    async def modaction(interaction: discord.Interaction, pending_id: int, decision: str) -> None:
        result = await resolve_pending_action(
            interaction.guild, pending_id, decision, moderator_id=interaction.user.id
        )
        await interaction.response.send_message(result, ephemeral=True)

    @bot.tree.error
    async def on_command_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return
        raise error


def create_bot(
    *,
    analyze=analyze_message,
    punisher=punish,
    mod_log_channel: str = config.MOD_LOG_CHANNEL,
    immune_role_ids: frozenset[int] = config.IMMUNE_ROLE_IDS,
    intents: discord.Intents | None = None,
    dashboard_starter: DashboardStarter | None = None,
) -> FargisGuard:
    deps = Deps(
        analyze=analyze,
        punish=punisher,
        log=mod_log_poster(mod_log_channel),
        immune_role_ids=frozenset(immune_role_ids),
    )
    if dashboard_starter is None:
        dashboard_starter = functools.partial(
            start_dashboard,
            token=config.DASHBOARD_TOKEN,
            host=config.DASHBOARD_HOST,
            port=config.DASHBOARD_PORT,
        )
    return FargisGuard(deps, intents=intents, dashboard_starter=dashboard_starter)


def main() -> None:
    database.init_db()
    create_bot().run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
