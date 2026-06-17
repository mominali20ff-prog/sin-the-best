import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import success_embed, error_embed, info_embed


def build_selfrole_view(self_roles: list[dict]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for entry in self_roles[:25]:
        view.add_item(
            discord.ui.Button(
                label=entry["label"] or "Role",
                emoji=entry["emoji"] or None,
                style=discord.ButtonStyle.secondary,
                custom_id=f"selfrole_{entry['role_id']}",
            )
        )
    return view


class AutoRole(commands.Cog):
    """Gives a default role to new members and lets members self-assign roles
    from a button panel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        settings = await self.bot.db.get_settings(member.guild.id)
        role_id = settings.get("autorole_id")
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Auto-role on join")
            except discord.Forbidden:
                pass

    @commands.Cog.listener("on_interaction")
    async def on_raw_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if not custom_id.startswith("selfrole_"):
            return
        role_id = int(custom_id.split("_", 1)[1])
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(embed=error_embed("That role no longer exists."), ephemeral=True)
            return
        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Self-role toggle")
                await interaction.response.send_message(embed=success_embed(f"Removed **{role.name}**."), ephemeral=True)
            else:
                await member.add_roles(role, reason="Self-role toggle")
                await interaction.response.send_message(embed=success_embed(f"Added **{role.name}**."), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("I don't have permission to manage that role."), ephemeral=True)

    # ------------------------------------------------------------ slash commands
    autorole_group = app_commands.Group(name="autorole", description="Configure join roles and self-assignable roles.")

    @autorole_group.command(name="setjoinrole", description="Set the role automatically given to new members.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setjoinrole(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.db.update_settings(interaction.guild.id, autorole_id=role.id)
        await interaction.response.send_message(embed=success_embed(f"New members will now automatically receive {role.mention}."))

    @autorole_group.command(name="removejoinrole", description="Disable the automatic join role.")
    @app_commands.checks.has_permissions(administrator=True)
    async def removejoinrole(self, interaction: discord.Interaction):
        await self.bot.db.update_settings(interaction.guild.id, autorole_id=None)
        await interaction.response.send_message(embed=success_embed("Automatic join role disabled."))

    @autorole_group.command(name="selfrole_add", description="Add a role to the self-assignable roles panel.")
    @app_commands.describe(role="The role members can self-assign", label="Button label", emoji="Optional emoji shown on the button")
    @app_commands.checks.has_permissions(administrator=True)
    async def selfrole_add(self, interaction: discord.Interaction, role: discord.Role, label: str, emoji: str = None):
        await self.bot.db.add_self_role(interaction.guild.id, role.id, label, emoji)
        await interaction.response.send_message(embed=success_embed(f"Added **{role.name}** to the self-roles panel."))

    @autorole_group.command(name="selfrole_remove", description="Remove a role from the self-assignable roles panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def selfrole_remove(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.db.remove_self_role(interaction.guild.id, role.id)
        await interaction.response.send_message(embed=success_embed(f"Removed **{role.name}** from the self-roles panel."))

    @autorole_group.command(name="selfrole_list", description="List configured self-assignable roles.")
    async def selfrole_list(self, interaction: discord.Interaction):
        roles = await self.bot.db.get_self_roles(interaction.guild.id)
        if not roles:
            await interaction.response.send_message(embed=info_embed("No self-assignable roles configured."), ephemeral=True)
            return
        text = "\n".join(f"<@&{r['role_id']}> — {r['label']}" for r in roles)
        await interaction.response.send_message(embed=info_embed(text, title="Self-Assignable Roles"), ephemeral=True)

    @autorole_group.command(name="selfrole_panel", description="Post the self-assignable roles button panel in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def selfrole_panel(self, interaction: discord.Interaction):
        roles = await self.bot.db.get_self_roles(interaction.guild.id)
        if not roles:
            await interaction.response.send_message(embed=error_embed("No self-assignable roles configured yet. Use `/autorole selfrole_add` first."), ephemeral=True)
            return
        embed = discord.Embed(
            title="🎭 Self-Assignable Roles",
            description="Click a button below to add or remove a role.",
            color=0x5865F2,
        )
        await interaction.channel.send(embed=embed, view=build_selfrole_view(roles))
        await interaction.response.send_message(embed=success_embed("Self-roles panel posted."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
