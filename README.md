import asyncio
import logging

import discord
from discord.ext import commands

from config import BOT_TOKEN, PREFIX
import database
from utils.embeds import error_embed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bot")

intents = discord.Intents.default()
intents.members = True          # Required for join events / auto-role / on_member_update. Enable in Dev Portal.
intents.message_content = True  # Required for "." prefix commands. Enable in Dev Portal.

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
bot.db = None  # set in setup_hook

INITIAL_COGS = [
    "cogs.moderation",
    "cogs.antinuke",
    "cogs.logging_events",
    "cogs.tickets",
    "cogs.applications",
    "cogs.autorole",
    "cogs.settings",
    "cogs.helpcog",
]


@bot.event
async def setup_hook():
    bot.db = await database.init_db()
    for ext in INITIAL_COGS:
        try:
            await bot.load_extension(ext)
            log.info(f"Loaded extension: {ext}")
        except Exception:
            log.exception(f"Failed to load extension: {ext}")
    synced = await bot.tree.sync()
    log.info(f"Synced {len(synced)} global slash commands")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    # Re-dispatch so individual cogs can also listen for "on_app_command_error" if they want to.
    bot.dispatch("app_command_error", interaction, error)
    from discord import app_commands
    if isinstance(error, (app_commands.MissingPermissions, app_commands.CommandInvokeError)):
        return  # handled by the cog listener
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=error_embed(f"An unexpected error occurred: {error}"), ephemeral=True)
    except discord.HTTPException:
        pass


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    log.exception("Prefix command error", exc_info=error)


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id}) — connected to {len(bot.guilds)} server(s)")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{PREFIX}help | /help"))


if __name__ == "__main__":
    asyncio.run(bot.start(BOT_TOKEN))
