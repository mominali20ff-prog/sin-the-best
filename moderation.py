import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import success_embed, info_embed


class Settings(commands.Cog):
    """Core server configuration: log channel, mute role, ticket setup."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    settings_group = app_commands.Group(name="settings", description="Configure the bot for this server.")

    @settings_group.command(name="logchannel", description="Set the channel used for moderation/server logs and anti-nuke alerts.")
    @app_commands.checks.has_permissions(administrator=True)
    async def logchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.update_settings(interaction.guild.id, log_channel_id=channel.id)
        await interaction.response.send_message(embed=success_embed(f"Log channel set to {channel.mention}."))

    @settings_group.command(name="muterole", description="Set the role used by /mute and /unmute.")
    @app_commands.checks.has_permissions(administrator=True)
    async def muterole(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.db.update_settings(interaction.guild.id, mute_role_id=role.id)
        await interaction.response.send_message(embed=success_embed(f"Mute role set to {role.mention}. Remember it needs 'Send Messages' denied in your channel permissions."))

    @settings_group.command(name="ticketcategory", description="Set the category where new ticket channels are created.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticketcategory(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await self.bot.db.update_settings(interaction.guild.id, ticket_category_id=category.id)
        await interaction.response.send_message(embed=success_embed(f"Ticket category set to **{category.name}**."))

    @settings_group.command(name="ticketsupportrole", description="Set the role that can see and help with tickets.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticketsupportrole(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.db.update_settings(interaction.guild.id, ticket_support_role_id=role.id)
        await interaction.response.send_message(embed=success_embed(f"Ticket support role set to {role.mention}."))

    @settings_group.command(name="ticketlogchannel", description="Set the channel where closed-ticket summaries are logged.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticketlogchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.update_settings(interaction.guild.id, ticket_log_channel_id=channel.id)
        await interaction.response.send_message(embed=success_embed(f"Ticket log channel set to {channel.mention}."))

    @settings_group.command(name="view", description="View the current configuration for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_settings(self, interaction: discord.Interaction):
        s = await self.bot.db.get_settings(interaction.guild.id)
        guild = interaction.guild

        def fmt_channel(cid):
            ch = guild.get_channel(cid) if cid else None
            return ch.mention if ch else "Not set"

        def fmt_role(rid):
            r = guild.get_role(rid) if rid else None
            return r.mention if r else "Not set"

        embed = info_embed("", title=f"⚙️ Settings for {guild.name}")
        embed.add_field(name="Log Channel", value=fmt_channel(s["log_channel_id"]), inline=True)
        embed.add_field(name="Mute Role", value=fmt_role(s["mute_role_id"]), inline=True)
        embed.add_field(name="Join Role", value=fmt_role(s["autorole_id"]), inline=True)
        embed.add_field(name="Ticket Category", value=fmt_channel(s["ticket_category_id"]), inline=True)
        embed.add_field(name="Ticket Support Role", value=fmt_role(s["ticket_support_role_id"]), inline=True)
        embed.add_field(name="Ticket Log Channel", value=fmt_channel(s["ticket_log_channel_id"]), inline=True)
        embed.add_field(name="Application Panel Channel", value=fmt_channel(s["application_panel_channel_id"]), inline=True)
        embed.add_field(name="Application Review Channel", value=fmt_channel(s["application_log_channel_id"]), inline=True)
        embed.add_field(name="Application Accepted Role", value=fmt_role(s["application_accepted_role_id"]), inline=True)
        embed.add_field(name="Anti-Nuke", value="Enabled ✅" if s["antinuke_enabled"] else "Disabled ❌", inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
