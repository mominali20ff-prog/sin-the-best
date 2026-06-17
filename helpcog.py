import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import success_embed, error_embed, info_embed

MAX_QUESTIONS = 5


class ApplicationModal(discord.ui.Modal, title="Staff Application"):
    def __init__(self, cog: "Applications", questions: list[str]):
        super().__init__()
        self.cog = cog
        self.inputs = []
        for i, q in enumerate(questions[:MAX_QUESTIONS]):
            text_input = discord.ui.TextInput(
                label=q[:45],
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=500,
                custom_id=f"q_{i}",
            )
            self.inputs.append((q, text_input))
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        answers = [(q, ti.value) for q, ti in self.inputs]
        await self.cog.submit_application(interaction, answers)


class ApplyView(discord.ui.View):
    """Persistent view (static custom_id) shown on the public apply panel."""

    def __init__(self, cog: "Applications"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Apply Now", style=discord.ButtonStyle.success, custom_id="application_apply_btn", emoji="📝")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await self.cog.bot.db.get_settings(interaction.guild.id)
        questions = settings.get("application_questions") or []
        if not questions:
            await interaction.response.send_message(embed=error_embed("No application questions are configured yet."), ephemeral=True)
            return
        await interaction.response.send_modal(ApplicationModal(self.cog, questions))


def build_review_view(applicant_id: int) -> discord.ui.View:
    """Builds the Accept/Deny view for a single submission. The applicant id is
    encoded directly in the custom_id so a generic listener can handle clicks
    even after a bot restart, without needing per-message view re-registration."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Accept", style=discord.ButtonStyle.success, custom_id=f"appaccept_{applicant_id}"))
    view.add_item(discord.ui.Button(label="Deny", style=discord.ButtonStyle.danger, custom_id=f"appdeny_{applicant_id}"))
    return view


class Applications(commands.Cog):
    """Staff application system: post an apply panel, collect modal answers,
    and let staff Accept/Deny submissions from the review channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def submit_application(self, interaction: discord.Interaction, answers: list[tuple[str, str]]):
        settings = await self.bot.db.get_settings(interaction.guild.id)
        log_channel_id = settings.get("application_log_channel_id")
        log_channel = interaction.guild.get_channel(log_channel_id) if log_channel_id else None
        if not log_channel:
            await interaction.response.send_message(embed=error_embed("Applications are not fully configured (missing log channel)."), ephemeral=True)
            return

        embed = discord.Embed(title="📋 New Application", color=0x5865F2, timestamp=discord.utils.utcnow())
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        for q, a in answers:
            embed.add_field(name=q[:256], value=a[:1024] or "*(no answer)*", inline=False)
        embed.set_footer(text=f"Applicant ID: {interaction.user.id}")

        await log_channel.send(embed=embed, view=build_review_view(interaction.user.id))
        await interaction.response.send_message(embed=success_embed("Your application has been submitted. You'll be notified of the result."), ephemeral=True)

    async def resolve_application(self, interaction: discord.Interaction, applicant_id: int, accepted: bool):
        guild = interaction.guild
        applicant = guild.get_member(applicant_id)
        settings = await self.bot.db.get_settings(guild.id)

        if accepted and applicant:
            role_id = settings.get("application_accepted_role_id")
            role = guild.get_role(role_id) if role_id else None
            if role:
                try:
                    await applicant.add_roles(role, reason="Application accepted")
                except discord.Forbidden:
                    pass

        if applicant:
            try:
                if accepted:
                    await applicant.send(embed=success_embed(f"Your application in **{guild.name}** was accepted! 🎉"))
                else:
                    await applicant.send(embed=error_embed(f"Your application in **{guild.name}** was denied."))
            except discord.HTTPException:
                pass

        result_text = "✅ Accepted" if accepted else "❌ Denied"
        new_embed = interaction.message.embeds[0]
        new_embed.add_field(name="Result", value=f"{result_text} by {interaction.user.mention}", inline=False)
        new_embed.color = 0x57F287 if accepted else 0xED4245
        await interaction.response.edit_message(embed=new_embed, view=None)

    @commands.Cog.listener("on_interaction")
    async def on_raw_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if custom_id.startswith("appaccept_"):
            await self.resolve_application(interaction, int(custom_id.split("_", 1)[1]), accepted=True)
        elif custom_id.startswith("appdeny_"):
            await self.resolve_application(interaction, int(custom_id.split("_", 1)[1]), accepted=False)

    # ------------------------------------------------------------ slash commands
    application_group = app_commands.Group(name="application", description="Configure the staff application system.")

    @application_group.command(name="setchannel", description="Set the channel where the apply panel will be posted.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.update_settings(interaction.guild.id, application_panel_channel_id=channel.id)
        await interaction.response.send_message(embed=success_embed(f"Application panel channel set to {channel.mention}."))

    @application_group.command(name="setlogchannel", description="Set the channel where submitted applications are reviewed.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlogchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.update_settings(interaction.guild.id, application_log_channel_id=channel.id)
        await interaction.response.send_message(embed=success_embed(f"Application review channel set to {channel.mention}."))

    @application_group.command(name="setrole", description="Set the role given to accepted applicants.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setrole(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.db.update_settings(interaction.guild.id, application_accepted_role_id=role.id)
        await interaction.response.send_message(embed=success_embed(f"Accepted-applicant role set to {role.mention}."))

    @application_group.command(name="addquestion", description=f"Add an application question (max {MAX_QUESTIONS}).")
    @app_commands.checks.has_permissions(administrator=True)
    async def addquestion(self, interaction: discord.Interaction, question: str):
        settings = await self.bot.db.get_settings(interaction.guild.id)
        questions = settings.get("application_questions") or []
        if len(questions) >= MAX_QUESTIONS:
            await interaction.response.send_message(embed=error_embed(f"You can only have up to {MAX_QUESTIONS} questions."), ephemeral=True)
            return
        questions.append(question)
        await self.bot.db.update_settings(interaction.guild.id, application_questions=questions)
        await interaction.response.send_message(embed=success_embed(f"Added question ({len(questions)}/{MAX_QUESTIONS})."))

    @application_group.command(name="removequestions", description="Clear all configured application questions.")
    @app_commands.checks.has_permissions(administrator=True)
    async def removequestions(self, interaction: discord.Interaction):
        await self.bot.db.update_settings(interaction.guild.id, application_questions=[])
        await interaction.response.send_message(embed=success_embed("All application questions cleared."))

    @application_group.command(name="listquestions", description="List the current application questions.")
    async def listquestions(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_settings(interaction.guild.id)
        questions = settings.get("application_questions") or []
        if not questions:
            await interaction.response.send_message(embed=info_embed("No application questions configured."), ephemeral=True)
            return
        text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        await interaction.response.send_message(embed=info_embed(text, title="Application Questions"), ephemeral=True)

    @application_group.command(name="panel", description="Post the application panel in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📝 Staff Applications",
            description="Click the button below to start your application.",
            color=0x5865F2,
        )
        await interaction.channel.send(embed=embed, view=ApplyView(self))
        await interaction.response.send_message(embed=success_embed("Application panel posted."), ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(ApplyView(self))


async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))
