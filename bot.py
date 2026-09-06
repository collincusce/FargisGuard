import asyncio

import discord
from discord.ext import commands

import dashboard
from ai_engine import analyze_message
from appeals import submit_appeal
from config import DISCORD_TOKEN, IMMUNE_ROLE_IDS, MOD_LOG_CHANNEL, NSFW_CHANNEL_NAME
from moderation import punish
from rules import set_rules
from verdict import parse_verdict

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Guardian online as {bot.user}")
    asyncio.create_task(asyncio.to_thread(dashboard.run))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # 🔞 NSFW CHANNEL — AI BYPASS
    if message.channel.name == NSFW_CHANNEL_NAME:
        await bot.process_commands(message)
        return

    # 🧠 AI MODERATION
    result = await analyze_message(message.content, message.guild.id)

    verdict = parse_verdict(result)
    if verdict is not None:
        action = await punish(
            message.author, verdict.severity, verdict.reason, immune_role_ids=IMMUNE_ROLE_IDS
        )
        reason = verdict.reason

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        log_channel = discord.utils.get(
            message.guild.text_channels, name=MOD_LOG_CHANNEL
        )

        if log_channel:
            await log_channel.send(
                f"🚨 **Violation Detected**\n"
                f"User: {message.author}\n"
                f"Channel: {message.channel.mention}\n"
                f"Action: {action}\n"
                f"Reason: {reason}"
            )

    await bot.process_commands(message)

# ───── SLASH COMMANDS ─────

@bot.tree.command(name="appeal")
async def appeal(interaction: discord.Interaction, reason: str):
    submit_appeal(interaction.user.id, interaction.guild.id, reason)
    await interaction.response.send_message("📨 Appeal submitted.")

@bot.tree.command(name="setrules")
@commands.has_permissions(administrator=True)
async def setrules_cmd(interaction: discord.Interaction, rules: str):
    set_rules(interaction.guild.id, rules)
    await interaction.response.send_message("📜 Rules updated.")

bot.run(DISCORD_TOKEN)
