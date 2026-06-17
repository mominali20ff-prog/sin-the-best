import asyncio
import time
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import success_embed, error_embed, info_embed
from config import ANTINUKE_THRESHOLD, ANTINUKE_WINDOW_SECONDS, EXTRA_OWNER_IDS


class AntiNuke(commands.Cog):
    """Detects mass-destructive actions (mass channel/role deletes, mass bans/kicks)
    and responds by banning the offender (and whoever invited a malicious bot),
    restoring deleted channels/roles, and alerting the server owner."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> user_id -> action_type -> list[timestamps]
        self.actions = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        # guild_id -> user_id -> action_type -> list[restorable objects]
        self.pending_restore = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        # guild_id -> set of user_ids currently being punished (avoid double trigger)
        self.punishing = defaultdict(set)

    # ------------------------------------------------------------ helpers
    async def is_protected(self, guild: discord.Guild, user_id: int) -> bool:
        if user_id == self.bot.user.id:
            return True
        if user_id == guild.owner_id:
            return True
        if user_id in EXTRA_OWNER_IDS:
            return True
        if await self.bot.db.is_whitelisted(guild.id, user_id):
            return True
        return False

    async def antinuke_enabled(self, guild_id: int) -> bool:
        settings = await self.bot.db.get_settings(guild_id)
        return bool(settings.get("antinuke_enabled", 1))

    def record(self, guild_id: int, user_id: int, action: str, payload=None) -> int:
        now = time.time()
        window_start = now - ANTINUKE_WINDOW_SECONDS
        bucket = self.actions[guild_id][user_id][action]
        bucket.append(now)
        while bucket and bucket[0] < window_start:
            bucket.pop(0)
        if payload is not None:
            self.pending_restore[guild_id][user_id][action].append(payload)
        return len(bucket)

    def pop_restorables(self, guild_id: int, user_id: int, action: str) -> list:
        items = self.pending_restore[guild_id][user_id][action]
        self.pending_restore[guild_id][user_id][action] = []
        return items

    async def find_audit_executor(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int = None):
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                if target_id is None or (entry.target and entry.target.id == target_id):
                    # only trust very recent entries
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() < 15:
                        return entry.user
        except discord.Forbidden:
            return None
        return None

    async def find_bot_inviter(self, guild: discord.Guild, bot_user: discord.abc.User):
        try:
            async for entry in guild.audit_logs(limit=20, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == bot_user.id:
                    return entry.user
        except discord.Forbidden:
            return None
        return None

    # ------------------------------------------------------------ punishment + restore
    async def trigger(self, guild: discord.Guild, executor: discord.abc.User, reason: str,
                       restore_channels=None, restore_roles=None, restore_bans=None):
        if executor.id in self.punishing[guild.id]:
            return
        self.punishing[guild.id].add(executor.id)
        try:
            banned_users = []

            # ban the executor
            try:
                await guild.ban(discord.Object(id=executor.id), reason=f"Anti-Nuke: {reason}")
                banned_users.append(str(executor))
            except discord.HTTPException:
                pass

            # if the executor is a bot, also ban whoever invited it
            inviter = None
            if getattr(executor, "bot", False):
                inviter = await self.find_bot_inviter(guild, executor)
                if inviter:
                    try:
                        await guild.ban(discord.Object(id=inviter.id), reason=f"Anti-Nuke: invited malicious bot {executor}")
                        banned_users.append(f"{inviter} (invited the bot)")
                    except discord.HTTPException:
                        pass

            restored_summary = []

            # restore channels
            if restore_channels:
                for ch in restore_channels:
                    try:
                        await self.recreate_channel(guild, ch)
                        restored_summary.append(f"#{ch.name}")
                    except discord.HTTPException:
                        pass

            # restore roles
            if restore_roles:
                for role in restore_roles:
                    try:
                        await self.recreate_role(guild, role)
                        restored_summary.append(f"role '{role.name}'")
                    except discord.HTTPException:
                        pass

            # unban anyone caught in a mass-ban wave
            if restore_bans:
                for user in restore_bans:
                    try:
                        await guild.unban(user, reason="Anti-Nuke: reversing mass-ban")
                        restored_summary.append(f"unbanned {user}")
                    except discord.HTTPException:
                        pass

            embed = discord.Embed(
                title="🛡️ Anti-Nuke Triggered",
                description=f"**Reason:** {reason}",
                color=0xED4245,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Server", value=f"{guild.name} ({guild.id})", inline=False)
            embed.add_field(name="Banned", value="\n".join(banned_users) or "None", inline=False)
            if restored_summary:
                embed.add_field(name="Restored", value="\n".join(restored_summary[:15]), inline=False)

            if guild.owner:
                try:
                    await guild.owner.send(embed=embed)
                except discord.HTTPException:
                    pass

            settings = await self.bot.db.get_settings(guild.id)
            log_channel = guild.get_channel(settings.get("log_channel_id")) if settings.get("log_channel_id") else None
            if log_channel:
                try:
                    await log_channel.send(embed=embed)
                except discord.HTTPException:
                    pass
        finally:
            await asyncio.sleep(5)
            self.punishing[guild.id].discard(executor.id)

    async def recreate_channel(self, guild: discord.Guild, channel: discord.abc.GuildChannel):
        overwrites = channel.overwrites if hasattr(channel, "overwrites") else {}
        category = channel.category
        kwargs = {"overwrites": overwrites, "category": category, "position": channel.position}
        if isinstance(channel, discord.TextChannel):
            await guild.create_text_channel(channel.name, topic=channel.topic, nsfw=channel.nsfw,
                                             slowmode_delay=channel.slowmode_delay, **kwargs)
        elif isinstance(channel, discord.VoiceChannel):
            await guild.create_voice_channel(channel.name, bitrate=channel.bitrate, user_limit=channel.user_limit, **kwargs)
        elif isinstance(channel, discord.CategoryChannel):
            await guild.create_category(channel.name, overwrites=overwrites, position=channel.position)
        elif isinstance(channel, discord.ForumChannel):
            await guild.create_forum(channel.name, **kwargs)

    async def recreate_role(self, guild: discord.Guild, role: discord.Role):
        await guild.create_role(
            name=role.name, permissions=role.permissions, colour=role.colour,
            hoist=role.hoist, mentionable=role.mentionable,
        )

    # ------------------------------------------------------------ listeners
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        if not await self.antinuke_enabled(guild.id):
            return
        await asyncio.sleep(1.5)
        executor = await self.find_audit_executor(guild, discord.AuditLogAction.channel_delete, channel.id)
        if not executor or await self.is_protected(guild, executor.id):
            return
        count = self.record(guild.id, executor.id, "channel_delete", payload=channel)
        if count >= ANTINUKE_THRESHOLD:
            restorables = self.pop_restorables(guild.id, executor.id, "channel_delete")
            await self.trigger(guild, executor, "Mass channel deletion detected", restore_channels=restorables)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        if not await self.antinuke_enabled(guild.id):
            return
        await asyncio.sleep(1.5)
        executor = await self.find_audit_executor(guild, discord.AuditLogAction.role_delete, role.id)
        if not executor or await self.is_protected(guild, executor.id):
            return
        count = self.record(guild.id, executor.id, "role_delete", payload=role)
        if count >= ANTINUKE_THRESHOLD:
            restorables = self.pop_restorables(guild.id, executor.id, "role_delete")
            await self.trigger(guild, executor, "Mass role deletion detected", restore_roles=restorables)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User):
        if not await self.antinuke_enabled(guild.id):
            return
        await asyncio.sleep(1.5)
        executor = await self.find_audit_executor(guild, discord.AuditLogAction.ban, user.id)
        if not executor or await self.is_protected(guild, executor.id):
            return
        count = self.record(guild.id, executor.id, "ban", payload=user)
        if count >= ANTINUKE_THRESHOLD:
            restorables = self.pop_restorables(guild.id, executor.id, "ban")
            await self.trigger(guild, executor, "Mass ban detected", restore_bans=restorables)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if not await self.antinuke_enabled(guild.id):
            return
        await asyncio.sleep(1.5)
        executor = await self.find_audit_executor(guild, discord.AuditLogAction.kick, member.id)
        if not executor or await self.is_protected(guild, executor.id):
            return
        count = self.record(guild.id, executor.id, "kick")
        if count >= ANTINUKE_THRESHOLD:
            await self.trigger(guild, executor, "Mass kick detected")

    # ------------------------------------------------------------ slash commands
    antinuke_group = app_commands.Group(name="antinuke", description="Configure the anti-nuke system.")

    @antinuke_group.command(name="enable", description="Enable the anti-nuke system.")
    @app_commands.checks.has_permissions(administrator=True)
    async def enable(self, interaction: discord.Interaction):
        await self.bot.db.update_settings(interaction.guild.id, antinuke_enabled=1)
        await interaction.response.send_message(embed=success_embed("Anti-Nuke is now **enabled**."))

    @antinuke_group.command(name="disable", description="Disable the anti-nuke system.")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable(self, interaction: discord.Interaction):
        await self.bot.db.update_settings(interaction.guild.id, antinuke_enabled=0)
        await interaction.response.send_message(embed=success_embed("Anti-Nuke is now **disabled**."))

    @antinuke_group.command(name="whitelist_add", description="Exempt a trusted member from anti-nuke checks.")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_add(self, interaction: discord.Interaction, member: discord.Member):
        await self.bot.db.add_whitelist(interaction.guild.id, member.id)
        await interaction.response.send_message(embed=success_embed(f"**{member}** is now whitelisted from anti-nuke."))

    @antinuke_group.command(name="whitelist_remove", description="Remove a member from the anti-nuke whitelist.")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_remove(self, interaction: discord.Interaction, member: discord.Member):
        await self.bot.db.remove_whitelist(interaction.guild.id, member.id)
        await interaction.response.send_message(embed=success_embed(f"**{member}** has been removed from the anti-nuke whitelist."))

    @antinuke_group.command(name="whitelist_list", description="List members whitelisted from anti-nuke.")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_list(self, interaction: discord.Interaction):
        ids = await self.bot.db.get_whitelist(interaction.guild.id)
        if not ids:
            await interaction.response.send_message(embed=info_embed("No members are whitelisted."), ephemeral=True)
            return
        mentions = "\n".join(f"<@{uid}>" for uid in ids)
        await interaction.response.send_message(embed=info_embed(mentions, title="Anti-Nuke Whitelist"))


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
