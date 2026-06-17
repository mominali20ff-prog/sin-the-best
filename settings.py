import discord
from discord.ext import commands

from utils.embeds import info_embed
from config import PREFIX

CATEGORIES = {
    "Moderation": ["ban", "unban", "kick", "timeout", "untimeout", "mute", "unmute", "warn", "warnings", "clearwarnings", "purge", "slowmode"],
    "Tickets": ["ticket"],
    "Applications": ["application setchannel", "application setlogchannel", "application setrole", "application addquestion", "application removequestions", "application listquestions", "application panel"],
    "Auto-Roles": ["autorole setjoinrole", "autorole removejoinrole", "autorole selfrole_add", "autorole selfrole_remove", "autorole selfrole_list", "autorole selfrole_panel"],
    "Anti-Nuke": ["antinuke enable", "antinuke disable", "antinuke whitelist_add", "antinuke whitelist_remove", "antinuke whitelist_list"],
    "Settings": ["settings logchannel", "settings muterole", "settings ticketcategory", "settings ticketsupportrole", "settings ticketlogchannel", "settings view"],
}


class Help(commands.Cog):
    """The .help / /help command."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show all available commands.")
    async def help_command(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🤖 Bot Commands",
            description=f"Most commands are slash commands — type `/` to see them with autocomplete.\nPrefix commands also work with `{PREFIX}` (e.g. `{PREFIX}help`).",
            color=0x5865F2,
        )
        for category, cmds in CATEGORIES.items():
            value = "\n".join(f"`/{c}`" for c in cmds)
            embed.add_field(name=category, value=value, inline=False)
        embed.set_footer(text="Need help setting things up? Ask an admin to run /settings view")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
