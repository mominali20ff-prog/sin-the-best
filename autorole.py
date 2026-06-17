import datetime
import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import success_embed, error_embed, info_embed


class TicketReasonModal(discord.ui.Modal, title="Open a Ticket"):
    reason = discord.ui.TextInput(
        label="What do you need help with?",
        style=discord.TextStyle.paragraph,
        placeholder="Briefly describe your issue...",
        max_length=500,
        required=True,
    )

    def __init__(self, cog: "Tickets"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.open_ticket(interaction, self.reason.value)


class TicketCloseView(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn", emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket(interaction)


class Tickets(commands.Cog):
    """Support ticket system. Use /ticket to open one; staff close it with the button."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ticket", description="Open a private support ticket.")
    async def ticket(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_settings(interaction.guild.id)
        if not settings.get("ticket_category_id"):
            await interaction.response.send_message(
                embed=error_embed("Tickets are not configured yet. Ask an admin to run `/settings ticketcategory` first."),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(TicketReasonModal(self))

    async def open_ticket(self, interaction: discord.Interaction, reason: str):
        guild = interaction.guild
        settings = await self.bot.db.get_settings(guild.id)
        category = guild.get_channel(settings.get("ticket_category_id"))
        support_role = guild.get_role(settings.get("ticket_support_role_id")) if settings.get("ticket_support_role_id") else None

        ticket_number = await self.bot.db.increment_ticket_counter(guild.id)
        channel_name = f"ticket-{ticket_number:04d}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            channel = await guild.create_text_channel(
                channel_name,
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                topic=f"Ticket opened by {interaction.user} | Reason: {reason}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to create channels."), ephemeral=True)
            return

        await self.bot.db.create_ticket(channel.id, guild.id, interaction.user.id, datetime.datetime.now(datetime.timezone.utc).isoformat())

        embed = info_embed(
            f"Hello {interaction.user.mention}! Support will be with you shortly.\n\n**Reason:** {reason}",
            title=f"🎫 Ticket #{ticket_number:04d}",
        )
        ping = support_role.mention if support_role else ""
        await channel.send(content=ping, embed=embed, view=TicketCloseView(self))
        await interaction.response.send_message(embed=success_embed(f"Your ticket has been created: {channel.mention}"), ephemeral=True)

    async def close_ticket(self, interaction: discord.Interaction):
        ticket = await self.bot.db.get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(embed=error_embed("This is not a ticket channel."), ephemeral=True)
            return
        await interaction.response.send_message(embed=info_embed("This ticket will be closed in 5 seconds..."))
        await self.bot.db.close_ticket(interaction.channel.id)

        settings = await self.bot.db.get_settings(interaction.guild.id)
        log_channel_id = settings.get("ticket_log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                opener = interaction.guild.get_member(ticket["user_id"])
                embed = info_embed(
                    f"Channel: #{interaction.channel.name}\nOpened by: {opener.mention if opener else ticket['user_id']}\nClosed by: {interaction.user.mention}",
                    title="🎫 Ticket Closed",
                )
                try:
                    await log_channel.send(embed=embed)
                except discord.HTTPException:
                    pass

        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        # Re-register the persistent close button so it still works after a restart.
        self.bot.add_view(TicketCloseView(self))


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
