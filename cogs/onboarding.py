# Alfred/cogs/onboarding.py

import logging
import discord

from discord.ext import commands
from discord import app_commands
import json
from pathlib import Path
from core.database import DatabaseManager, OnboardingStatus, GuildSettings
from core.ai_handler import AIHandler

logger = logging.getLogger(__name__)

async def is_setup_complete(interaction: discord.Interaction) -> bool:
    """A discord.py check that verifies if the essential settings for the guild are configured."""
    db_manager = interaction.client.db_manager
    async with db_manager.get_session() as session:
        settings = await session.get(GuildSettings, interaction.guild.id)
        if not settings or not settings.welcome_channel_id or not settings.language_channel_id:
            raise app_commands.CheckFailure(
                "An administrator must configure the welcome and language channels first.\n"
                "Please use `/setup welcome` and `/setup language`."
            )
    return True

BASE_DIR = Path(__file__).parent.parent

class Onboarding(commands.Cog):
    """A cog to handle the new member onboarding experience."""
    def __init__(self, bot: commands.Bot, db_manager: DatabaseManager, ai_handler: AIHandler):
        self.bot = bot
        self.db = db_manager
        self.ai = ai_handler
        self.greetings = self.load_greetings()

    def load_greetings(self) -> dict:
        greetings_path = BASE_DIR / "locale" / "greetings.json"
        try:
            with open(greetings_path, 'r', encoding='utf-8') as f:
                logger.info("Loading greetings from greetings.json...")
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load greetings.json: {e}. Falling back to default.")
            return {"en": "Excellent! Let me quickly show you how our translator works..."}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot: return
        logger.info(f"New member joined: {member.name} (ID: {member.id}) in guild {member.guild.id}")

        # Use the injected DatabaseManager to get a session
        async with self.db.get_session() as session:
            settings = await session.get(GuildSettings, member.guild.id)
            if not settings or not settings.welcome_channel_id or not settings.language_channel_id:
                logger.warning(f"Onboarding triggered in guild {member.guild.id}, but setup is incomplete. Aborting.")
                return

            existing_user = await session.get(OnboardingStatus, member.id)
            if not existing_user:
                new_status = OnboardingStatus(user_id=member.id, status="AWAITING_LANGUAGE")
                session.add(new_status)
                await session.commit()
                logger.info(f"Created new onboarding record for {member.name}.")
        
        welcome_channel = self.bot.get_channel(settings.welcome_channel_id)
        language_channel = self.bot.get_channel(settings.language_channel_id)
        
        if not welcome_channel or not language_channel:
            logger.error(f"Could not find a configured channel for guild {member.guild.id}. It may have been deleted.")
            return

        welcome_message = (
            f"Welcome to the server, {member.mention}! I'm Alfred, your personal guide.\n\n"
            f"To get started, let's head over to {language_channel.mention} so we can communicate effectively. 🇬🇧 🇪🇸 🇫🇷 🇩🇪"
        )
        await welcome_channel.send(welcome_message)
        logger.info(f"Sent public welcome message for {member.name}.")

    async def handle_language_set(self, user_id: int, language_code: str):
        member = None
        guild_settings = None
        
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member:
                async with self.db.get_session() as session:
                    guild_settings = await session.get(GuildSettings, guild.id)
                break

        if not member or not guild_settings or not guild_settings.language_channel_id:
            logger.error(f"Could not find member {user_id} or their guild's settings are incomplete.")
            return

        logger.info(f"Handling language set for User ID: {user_id} in guild {member.guild.id} with language '{language_code}'")
        
        async with self.db.get_session() as session:
            user_status = await session.get(OnboardingStatus, user_id)
            if not user_status:
                logger.warning(f"Received language set for user {user_id} but no record. Creating one.")
                user_status = OnboardingStatus(user_id=user_id, status="IN_PROGRESS")
                session.add(user_status)
            user_status.language_code = language_code
            user_status.status = "AWAITING_ROLE_GUIDE"
            await session.commit()
        
        greeting_text = self.greetings.get(language_code, self.greetings.get("en", "Welcome!"))
        tutorial_text = greeting_text + "\n\nWhen you're ready to continue, just say **'continue'**."

        try:
            await member.send(tutorial_text)
            logger.info(f"Sent first tutorial DM to {member.name}.")
        except Exception as e:
            logger.error(f"Failed to send DM to {member.name}: {e}", exc_info=True)
    
    @app_commands.command(name="ask-alfred", description="Ask Alfred a question about the server.")
    @app_commands.check(is_setup_complete)
    async def ask_alfred(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(ephemeral=True)
        try:
            thread = await interaction.channel.create_thread(
                name=f"❓ A question from {interaction.user.name}",
                type=discord.ChannelType.private_thread
            )
            await thread.add_user(interaction.user)

            initial_message = f"Hello {interaction.user.mention}, you asked: *'{question}'*\n\nI'll look into that for you now..."
            await thread.send(initial_message)
            
            system_prompt = (
                "You are Alfred, a helpful AI assistant for this Discord server. "
                "Your goal is to answer user questions concisely and accurately. "
                "If you don't know the answer, say so clearly and suggest they ask a human staff member."
            )
            
            ai_response = await self.ai.get_chat_response(
                guild_id=interaction.guild.id,
                channel_id=thread.id,
                user_id=interaction.user.id,
                prompt=question,
                system_instruction=system_prompt
            )

            await thread.send(ai_response)
            await interaction.followup.send(f"I've created a private thread for you to answer your question: {thread.mention}", ephemeral=True)

        except Exception as e:
            logger.error(f"Failed to create help thread for {interaction.user.name}: {e}", exc_info=True)
            await interaction.followup.send("I'm sorry, I was unable to create a help thread for you at this time.", ephemeral=True)