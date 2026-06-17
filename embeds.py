import discord
from discord.ext import commands

from utils.embeds import base_embed


class LoggingEvents(commands.Cog):
    """Sends server activity (joins/leaves, message edits/deletes, channel and
    role changes, bans) to the configured log channel as embeds."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        settings = await self.bot.db.get_settings(guild.id)
        channel_id = settings.get("log_channel_id")
        if not channel_id:
            return None
        return guild.get_channel(channel_id)

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        channel = await self.log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # ---------------------------------------------------------- members
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = base_embed(title="📥 Member Joined", description=f"{member.mention} ({member})", color=0x57F287)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, style="R"))
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = base_embed(title="📤 Member Left", description=f"{member.mention} ({member})", color=0xED4245)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User):
        embed = base_embed(title="🔨 Member Banned", description=f"{user.mention if hasattr(user, 'mention') else user} ({user})", color=0xED4245)
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.abc.User):
        embed = base_embed(title="🔓 Member Unbanned", description=f"{user}", color=0x57F287)
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            added = set(after.roles) - set(before.roles)
            removed = set(before.roles) - set(after.roles)
            if not added and not removed:
                return
            embed = base_embed(title="🛠️ Member Roles Updated", description=f"{after.mention}")
            if added:
                embed.add_field(name="Added", value=", ".join(r.mention for r in added), inline=False)
            if removed:
                embed.add_field(name="Removed", value=", ".join(r.mention for r in removed), inline=False)
            await self.send_log(after.guild, embed)

    # ---------------------------------------------------------- messages
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        embed = base_embed(title="🗑️ Message Deleted", color=0xED4245)
        embed.add_field(name="Author", value=str(message.author), inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        content = message.content or "*(no text content)*"
        embed.add_field(name="Content", value=content[:1000], inline=False)
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        embed = base_embed(title="✏️ Message Edited", color=0xFEE75C)
        embed.add_field(name="Author", value=str(before.author), inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=(before.content or "*(empty)*")[:512], inline=False)
        embed.add_field(name="After", value=(after.content or "*(empty)*")[:512], inline=False)
        await self.send_log(before.guild, embed)

    # ---------------------------------------------------------- channels & roles
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = base_embed(title="📁 Channel Created", description=f"{channel.mention if hasattr(channel, 'mention') else channel.name}", color=0x57F287)
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = base_embed(title="📁 Channel Deleted", description=f"#{channel.name}", color=0xED4245)
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = base_embed(title="🎭 Role Created", description=role.mention, color=0x57F287)
        await self.send_log(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = base_embed(title="🎭 Role Deleted", description=role.name, color=0xED4245)
        await self.send_log(role.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingEvents(bot))
