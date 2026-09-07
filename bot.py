"""Discord gateway: bot factory, slash commands, and the on_message entry point.

Importing this module never connects; ``main()`` does (D5).
"""

import asyncio
import dataclasses
import functools
import logging
from collections.abc import Callable

import discord
from discord import app_commands
from discord.ext import commands

import batchsettings
import config
import database
import rulecmds
from ai_engine import analyze_message, classify_batch
from appeals import format_pending_appeals, resolve_appeal_action, submit_appeal
from batcher import SHUTDOWN_FLUSH_SECONDS, Batcher
from dashboard import start_dashboard
from moderation import punish, resolve_pending_action
from pipeline import Deps, apply_outcome, handle_message
from rules import CATEGORY, CHANNEL, THREAD, set_rules


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
        classifier=classify_batch,
        intents: discord.Intents | None = None,
        dashboard_starter: DashboardStarter | None = None,
    ):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents or make_intents())
        self.batcher = Batcher(
            classify=classifier,
            apply=lambda snap, outcome, guild, *, held: apply_outcome(
                snap, outcome, guild, self.deps, held=held
            ),
            guild_for=self.get_guild,
            log_to=deps.log,
        )
        self.deps = dataclasses.replace(deps, batcher=self.batcher)
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

    async def close(self) -> None:
        """Flush queued batches before the gateway goes away (gameplan D2)."""
        try:
            unreviewed = await self.batcher.shutdown(deadline=SHUTDOWN_FLUSH_SECONDS)
            if unreviewed:
                logging.getLogger(__name__).warning(
                    "%d message(s) left unreviewed at shutdown", unreviewed
                )
        finally:
            await super().close()


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

    rules_group = app_commands.Group(
        name="rules",
        description="Rules for a category, channel, or a channel's threads",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )

    @rules_group.command(name="category", description="Set rules for every channel in a category")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(category="The category", rules="Rules text, on top of the server rules")
    async def rules_category(
        interaction: discord.Interaction, category: discord.CategoryChannel, rules: str
    ) -> None:
        reply = rulecmds.set_reply(interaction.guild_id, CATEGORY, category, rules)
        await interaction.response.send_message(reply, ephemeral=True)

    @rules_group.command(name="channel", description="Set rules for one channel")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(channel="The channel", rules="Rules text, on top of the wider scopes")
    async def rules_channel(
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.ForumChannel | discord.VoiceChannel,
        rules: str,
    ) -> None:
        reply = rulecmds.set_reply(interaction.guild_id, CHANNEL, channel, rules)
        await interaction.response.send_message(reply, ephemeral=True)

    @rules_group.command(name="thread", description="Set rules for the threads under a channel")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(channel="The parent channel", rules="Rules for replies in its threads")
    async def rules_thread(
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.ForumChannel,
        rules: str,
    ) -> None:
        reply = rulecmds.set_reply(interaction.guild_id, THREAD, channel, rules)
        await interaction.response.send_message(reply, ephemeral=True)

    @rules_group.command(name="clear", description="Remove the rules set at one scope")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(scope="Which scope to clear", target="The category or channel")
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="category", value=CATEGORY),
            app_commands.Choice(name="channel", value=CHANNEL),
            app_commands.Choice(name="thread", value=THREAD),
        ]
    )
    async def rules_clear(
        interaction: discord.Interaction, scope: str, target: discord.abc.GuildChannel
    ) -> None:
        reply = rulecmds.clear_reply(interaction.guild_id, scope, target)
        await interaction.response.send_message(reply, ephemeral=True)

    @rules_group.command(name="show", description="Show what the moderator AI enforces here")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(channel="A channel or thread", in_thread="Rules for its threads")
    async def rules_show(
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.ForumChannel | discord.VoiceChannel | discord.Thread,
        in_thread: bool = False,
    ) -> None:
        reply = rulecmds.show_reply(interaction.guild, channel, in_thread=in_thread)
        await interaction.response.send_message(reply, ephemeral=True)

    bot.tree.add_command(rules_group)

    batch_group = app_commands.Group(
        name="batch",
        description="How often queued messages are sent to the moderator AI",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )

    @batch_group.command(name="set", description="Review messages in batches every N seconds")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(seconds=f"1–{batchsettings.BATCH_MAX_SECONDS}; 0 reviews each message")
    async def batch_set(interaction: discord.Interaction, seconds: int) -> None:
        reply = batchsettings.set_reply(interaction.guild_id, seconds)
        await interaction.response.send_message(reply, ephemeral=True)

    @batch_group.command(name="show", description="Show the batch interval and queue depth")
    @app_commands.checks.has_permissions(administrator=True)
    async def batch_show(interaction: discord.Interaction) -> None:
        depth = bot.batcher.depth(interaction.guild_id)
        reply = batchsettings.show_reply(interaction.guild_id, depth)
        await interaction.response.send_message(reply, ephemeral=True)

    bot.tree.add_command(batch_group)

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
    classifier=classify_batch,
    punisher=punish,
    interval_for=batchsettings.get_batch_interval,
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
        interval_for=interval_for,
    )
    if dashboard_starter is None:
        dashboard_starter = functools.partial(
            start_dashboard,
            token=config.DASHBOARD_TOKEN,
            host=config.DASHBOARD_HOST,
            port=config.DASHBOARD_PORT,
        )
    return FargisGuard(
        deps, classifier=classifier, intents=intents, dashboard_starter=dashboard_starter
    )


def main() -> None:
    logging.basicConfig(
        level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    database.init_db()
    # log_handler=None: discord.py must not add a second handler beside the root one.
    create_bot().run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
