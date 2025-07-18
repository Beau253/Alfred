# Alfred/cogs/onboarding.py

import logging
import discord
from discord.commands import slash_command
from discord.ext import commands
import json
from pathlib import Path
from core.database import AsyncSessionLocal, OnboardingStatus, GuildSettings # Import GuildSettings
from core.ai_handler import ai_handler

# Set up a logger for this module
logger = logging.getLogger(__name__)

async def is_setup_complete(ctx: discord.ApplicationContext) -> bool:
    """
    A discord.py check that verifies if the essential settings for the guild are configured.
    """
    async with AsyncSessionLocal() as session:
        settings = await session.get(GuildSettings, ctx.guild.id)
        if not settings or not settings.welcome_channel_id or not settings.language_channel_id:
            await ctx.respond(
                "❌ **Setup Incomplete!**\n"
                "An administrator must configure the welcome and language channels first.\n"
                "Please use `/setup channel welcome` and `/setup channel language`.",
                ephemeral=True
            )
            return False
    return True

BASE_DIR = Path(__file__).parent.parent

class Onboarding(commands.Cog):
    """
    A cog to handle the new member onboarding experience.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.greetings = self.load_greetings()

    def load_greetings(self) -> dict:
        """Loads the greeting messages from the JSON file."""
        greetings_path = BASE_DIR / "locale" / "greetings.json"
        try:
            with open(greetings_path, 'r', encoding='utf-8') as f:
                logger.info("Loading greetings from greetings.json...")
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load greetings.json: {e}. Falling back to default.")
            # Fallback in case the file is missing or corrupted
            return {
                "en": "Excellent! Let me quickly show you how our translator works..."
            }

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Triggered when a new member joins the server.
        """
        # Ignore bots
        if member.bot:
            return

        logger.info(f"New member joined: {member.name} (ID: {member.id})")

        # Create a database record for the new user
        async with AsyncSessionLocal() as session:
            settings = await session.get(GuildSettings, member.guild.id)
            if not settings or not settings.welcome_channel_id or not settings.language_channel_id:
                logger.warning(f"Onboarding triggered in guild {member.guild.id}, but setup is incomplete. Aborting.")
                return

            # Check if a user record already exists
            existing_user = await session.get(OnboardingStatus, member.id)
            if not existing_user:
                new_status = OnboardingStatus(user_id=member.id, status="AWAITING_LANGUAGE")
                session.add(new_status)
                await session.commit()
                logger.info(f"Created new onboarding record for {member.name}.")
        
        # Get channel objects using the IDs from the database
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
                async with AsyncSessionLocal() as session:
                    guild_settings = await session.get(GuildSettings, guild.id)
                break

        if not member or not guild_settings or not guild_settings.language_channel_id:
            logger.error(f"Could not find member {user_id} or their guild's settings are incomplete.")
            return

        logger.info(f"Handling language set for User ID: {user_id} with language '{language_code}'")
        
        async with AsyncSessionLocal() as session:
            user_status = await session.get(OnboardingStatus, user_id)
            if not user_status:
                logger.warning(f"Received language set for user {user_id} but no record. Creating one.")
                user_status = OnboardingStatus(user_id=user_id, status="IN_PROGRESS")
                session.add(user_status)
            
            user_status.language_code = language_code
            user_status.status = "AWAITING_ROLE_GUIDE"
            await session.commit()
            logger.info(f"Updated database for {user_id}.")

        greeting_text = self.greetings.get(language_code, self.greetings.get("en"))
        if not greeting_text:
             greeting_text = "Welcome! Let's get started."

        tutorial_text = greeting_text + "\n\nWhen you're ready to continue, just say **'continue'**."

        try:
            language_channel = self.bot.get_channel(guild_settings.language_channel_id)
            if not language_channel:
                logger.error(f"Language channel ID {guild_settings.language_channel_id} is set but channel was not found.")
                return

            await language_channel.send(tutorial_text, ephemeral=True)
            logger.info(f"Sent first ephemeral tutorial to {member.name}.")
        except Exception as e:
            logger.error(f"Failed to send ephemeral message to {member.name}: {e}", exc_info=True)


    @slash_command(name="ask-alfred", description="Ask Alfred a question about the server.")
    @commands.check(is_setup_complete)
    async def ask_alfred(self, ctx: discord.ApplicationContext, question: str):
        """A general help command that creates a private thread for Q&A."""
        
        await ctx.defer(ephemeral=True) # Acknowledge the command privately
        
        try:
            # Create a private thread for the conversation
            thread = await ctx.channel.create_thread(
                name=f"❓ A question from {ctx.author.name}",
                type=discord.ChannelType.private_thread
            )
            await thread.add_user(ctx.author)

            # Send an initial message to the thread
            initial_message = f"Hello {ctx.author.mention}, you asked: *'{question}'*\n\nI'll look into that for you now..."
            await thread.send(initial_message)
            
            system_prompt = (
                "You are Alfred, a helpful AI assistant for this Discord server. "
                "Your goal is to answer user questions concisely and accurately. "
                "If you don't know the answer, say so clearly and suggest they ask a human staff member."
            )
            
            # Call the AI handler to get a contextual response
            ai_response = await ai_handler.get_chat_response(
                guild_id=ctx.guild.id,
                channel_id=thread.id,  # Critically, we use the new thread's ID for context
                user_id=ctx.author.id,
                prompt=question,
                system_instruction=system_prompt
            )

            # Send the AI's response to the thread
            await thread.send(ai_response)

            # Let the user know where to find the thread
            await ctx.followup.send(f"I've created a private thread for you to answer your question: {thread.mention}", ephemeral=True)

        except Exception as e:
            logger.error(f"Failed to create help thread for {ctx.author.name}: {e}", exc_info=True)
            await ctx.followup.send("I'm sorry, I was unable to create a help thread for you at this time.", ephemeral=True)

# This function is required for the cog to be loaded by the bot.
def setup(bot: commands.Bot):
    bot.add_cog(Onboarding(bot))