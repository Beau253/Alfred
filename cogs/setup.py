# Alfred/cogs/setup.py

import logging
import discord
from discord.commands import SlashCommandGroup, option
from discord.ext import commands

from core.database import DatabaseManager, GuildSettings

logger = logging.getLogger(__name__)

class Setup(commands.Cog):
    """
    A cog for server administrators to configure Alfred's settings.
    """
    def __init__(self, bot: commands.Bot, db_manager: DatabaseManager):
        self.bot = bot
        self.db = db_manager

    setup = SlashCommandGroup(
        "setup", 
        "Commands to configure Alfred for this server.",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    
    channel_group = setup.create_subgroup(
        "channel", "Set up specific channels for Alfred's features."
    )

    @channel_group.command(name="welcome", description="Set the channel for welcome messages.")
    @option("channel", discord.TextChannel, description="The channel to send welcome messages to.")
    async def set_welcome_channel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        """Sets the welcome message channel."""
        await self._update_setting(ctx, welcome_channel_id=channel.id)

    @channel_group.command(name="language", description="Set the channel where users select their language.")
    @option("channel", discord.TextChannel, description="The channel for language selection.")
    async def set_language_channel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        """Sets the language selection channel."""
        await self._update_setting(ctx, language_channel_id=channel.id)

    role_group = setup.create_subgroup(
        "role", "Set up specific roles for Alfred's features."
    )

    @role_group.command(name="support", description="Set the role for support staff.")
    @option("role", discord.Role, description="The role that identifies support staff.")
    async def set_support_role(self, ctx: discord.ApplicationContext, role: discord.Role):
        """Sets the support staff role."""
        await self._update_setting(ctx, support_role_id=role.id)
    
    async def _update_setting(self, ctx: discord.ApplicationContext, **kwargs):
        """A helper function to update settings in the database."""
        await ctx.defer(ephemeral=True)
        
        guild_id = ctx.guild.id
        setting_key = list(kwargs.keys())[0]
        setting_value = list(kwargs.values())[0]

        try:
            async with self.db.get_session() as session:
                guild_settings = await session.get(GuildSettings, guild_id)
                if not guild_settings:
                    guild_settings = GuildSettings(guild_id=guild_id)
                    session.add(guild_settings)
                
                setattr(guild_settings, setting_key, setting_value)
                await session.commit()
            
            logger.info(f"Updated setting '{setting_key}' for guild {guild_id}.")
            await ctx.followup.send(f"✅ Successfully updated the **{setting_key.replace('_', ' ')}** to point to `{setting_value}`.", ephemeral=True)

        except Exception as e:
            logger.error(f"Failed to update setting for guild {guild_id}: {e}", exc_info=True)
            await ctx.followup.send("❌ An error occurred while updating the setting. Please check the logs.", ephemeral=True)