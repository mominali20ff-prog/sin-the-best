import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta

from utils.embeds import success_embed, error_embed, info_embed


def hierarchy_ok(interaction: discord.Interaction, target: discord.Member) -> bool:
    """Returns True if the command invoker is allowed to act on target."""
    guild = interaction.guild
    if target.id == guild.owner_id:
        return False
    if target.id == interaction.user.id:
        return False
    if isinstance(interaction.user, discord.Member) and interaction.user.id != guild.owner_id:
        if target.top_role >= interaction.user.top_role:
            return False
    return True


class Moderation(commands.Cog):
    """Ban, kick, mute, timeout, warn and other punishment commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_mute_role(self, guild: discord.Guild) -> discord.Role | None:
        settings = await self.bot.db.get_settings(guild.id)
        role_id = settings.get("mute_role_id")
        if not role_id:
            return None
        return guild.get_role(role_id)

    # ---------------------------------------------------------- ban / unban
    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="The member to ban", reason="Reason for the ban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not hierarchy_ok(interaction, member):
            await interaction.response.send_message(embed=error_embed("You cannot ban this member (role hierarchy)."), ephemeral=True)
            return
        try:
            await member.send(embed=info_embed(f"You were banned from **{interaction.guild.name}**.\nReason: {reason}"))
        except discord.HTTPException:
            pass
        try:
            await interaction.guild.ban(member, reason=f"{interaction.user}: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to ban this member."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed(f"**{member}** has been banned.\n**Reason:** {reason}", title="Member Banned"))

    @app_commands.command(name="unban", description="Unban a user by their ID.")
    @app_commands.describe(user_id="The user ID to unban", reason="Reason for the unban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=f"{interaction.user}: {reason}")
        except (ValueError, discord.NotFound):
            await interaction.response.send_message(embed=error_embed("That user is not banned or the ID is invalid."), ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to unban."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed(f"**{user}** has been unbanned.\n**Reason:** {reason}", title="Member Unbanned"))

    # ---------------------------------------------------------- kick
    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not hierarchy_ok(interaction, member):
            await interaction.response.send_message(embed=error_embed("You cannot kick this member (role hierarchy)."), ephemeral=True)
            return
        try:
            await member.send(embed=info_embed(f"You were kicked from **{interaction.guild.name}**.\nReason: {reason}"))
        except discord.HTTPException:
            pass
        try:
            await member.kick(reason=f"{interaction.user}: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to kick this member."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed(f"**{member}** has been kicked.\n**Reason:** {reason}", title="Member Kicked"))

    # ---------------------------------------------------------- timeout (native discord timeout)
    @app_commands.command(name="timeout", description="Timeout a member (Discord native, max 28 days).")
    @app_commands.describe(member="The member to timeout", minutes="Duration in minutes", reason="Reason for the timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
        if not hierarchy_ok(interaction, member):
            await interaction.response.send_message(embed=error_embed("You cannot timeout this member (role hierarchy)."), ephemeral=True)
            return
        if minutes <= 0 or minutes > 40320:
            await interaction.response.send_message(embed=error_embed("Duration must be between 1 minute and 28 days (40320 minutes)."), ephemeral=True)
            return
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        try:
            await member.timeout(until, reason=f"{interaction.user}: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to timeout this member."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed(f"**{member}** has been timed out for **{minutes} minute(s)**.\n**Reason:** {reason}", title="Member Timed Out"))

    @app_commands.command(name="untimeout", description="Remove a member's timeout.")
    @app_commands.describe(member="The member to remove timeout from")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await member.timeout(None, reason=f"Timeout removed by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to do that."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed(f"Timeout removed for **{member}**.", title="Timeout Removed"))

    # ---------------------------------------------------------- mute / unmute (role based, indefinite)
    @app_commands.command(name="mute", description="Indefinitely mute a member using the configured mute role.")
    @app_commands.describe(member="The member to mute", reason="Reason for the mute")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        role = await self.get_mute_role(interaction.guild)
        if role is None:
            await interaction.response.send_message(embed=error_embed("No mute role configured. Use `/settings muterole` first."), ephemeral=True)
            return
        if not hierarchy_ok(interaction, member):
            await interaction.response.send_message(embed=error_embed("You cannot mute this member (role hierarchy)."), ephemeral=True)
            return
        try:
            await member.add_roles(role, reason=f"{interaction.user}: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to add that role."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed(f"**{member}** has been muted.\n**Reason:** {reason}", title="Member Muted"))

    @app_commands.command(name="unmute", description="Remove the mute role from a member.")
    @app_commands.describe(member="The member to unmute")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        role = await self.get_mute_role(interaction.guild)
        if role is None:
            await interaction.response.send_message(embed=error_embed("No mute role configured. Use `/settings muterole` first."), ephemeral=True)
            return
        try:
            await member.remove_roles(role, reason=f"Unmuted by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to remove that role."), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed(f"**{member}** has been unmuted.", title="Member Unmuted"))

    # ---------------------------------------------------------- warn
    @app_commands.command(name="warn", description="Warn a member. Warnings are saved and viewable later.")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not hierarchy_ok(interaction, member):
            await interaction.response.send_message(embed=error_embed("You cannot warn this member (role hierarchy)."), ephemeral=True)
            return
        timestamp = datetime.now(timezone.utc).isoformat()
        await self.bot.db.add_warn(interaction.guild.id, member.id, interaction.user.id, reason, timestamp)
        try:
            await member.send(embed=info_embed(f"You were warned in **{interaction.guild.name}**.\nReason: {reason}"))
        except discord.HTTPException:
            pass
        await interaction.response.send_message(embed=success_embed(f"**{member}** has been warned.\n**Reason:** {reason}", title="Member Warned"))

    @app_commands.command(name="warnings", description="View a member's warning history.")
    @app_commands.describe(member="The member to check")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings_cmd(self, interaction: discord.Interaction, member: discord.Member):
        warns = await self.bot.db.get_warns(interaction.guild.id, member.id)
        if not warns:
            await interaction.response.send_message(embed=info_embed(f"**{member}** has no warnings."), ephemeral=True)
            return
        embed = info_embed("", title=f"Warnings for {member}")
        for w in warns[:25]:
            mod = interaction.guild.get_member(w["moderator_id"])
            embed.add_field(
                name=f"Warn #{w['id']} • {w['timestamp'][:19].replace('T', ' ')}",
                value=f"By: {mod.mention if mod else w['moderator_id']}\nReason: {w['reason']}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member.")
    @app_commands.describe(member="The member to clear warnings for")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        await self.bot.db.clear_warns(interaction.guild.id, member.id)
        await interaction.response.send_message(embed=success_embed(f"Cleared all warnings for **{member}**."))

    # ---------------------------------------------------------- purge / slowmode
    @app_commands.command(name="purge", description="Bulk delete messages in this channel.")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(embed=success_embed(f"Deleted **{len(deleted)}** messages."), ephemeral=True)

    @app_commands.command(name="slowmode", description="Set slowmode delay for this channel.")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to disable)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        await interaction.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await interaction.response.send_message(embed=success_embed("Slowmode disabled for this channel."))
        else:
            await interaction.response.send_message(embed=success_embed(f"Slowmode set to **{seconds}** second(s)."))

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(embed=error_embed("You don't have permission to use this command."), ephemeral=True)
        elif isinstance(error, app_commands.CommandInvokeError):
            await interaction.response.send_message(embed=error_embed(f"Something went wrong: {error.original}"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
