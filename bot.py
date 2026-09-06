"""Discord gateway: bot factory, slash commands, and the on_message entry point.

Importing this module never connects; ``main()`` does (D5).
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
from ai_engine import analyze_message
from appeals import submit_appeal
from moderation import punish
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


class FargisGuard(commands.Bot):
    def __init__(self, deps: Deps, *, intents: discord.Intents | None = None):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents or make_intents())
        self.deps = deps
        register_commands(self)

    async def setup_hook(self) -> None:
        await self.tree.sync()

    async def on_ready(self) -> None:
        print(f"🤖 FargisGuard online as {self.user}")

    async def on_message(self, message: discord.Message) -> None:
        await handle_message(message, self.deps)


def register_commands(bot: commands.Bot) -> None:
    @bot.tree.command(name="appeal", description="Appeal a moderation action against you")
    @app_commands.describe(reason="Why the action should be reconsidered")
    async def appeal(interaction: discord.Interaction, reason: str) -> None:
        submit_appeal(interaction.user.id, interaction.guild_id, reason)
        await interaction.response.send_message("📨 Appeal submitted.", ephemeral=True)

    @bot.tree.command(name="setrules", description="Replace this server's moderation rules")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(rules="The full rules text the moderator AI will enforce")
    async def setrules(interaction: discord.Interaction, rules: str) -> None:
        set_rules(interaction.guild_id, rules)
        await interaction.response.send_message("📜 Rules updated.", ephemeral=True)

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
) -> FargisGuard:
    deps = Deps(
        analyze=analyze,
        punish=punisher,
        log=mod_log_poster(mod_log_channel),
        immune_role_ids=frozenset(immune_role_ids),
    )
    return FargisGuard(deps, intents=intents)


def main() -> None:
    create_bot().run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
