# core/bot.py

import logging
import discord
import os # <-- Added this import
from pathlib import Path
from discord.ext import commands
from .database import DatabaseManager
from .ai_handler import AIHandler

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Define the path to the 'cogs' directory
COGS_DIR = Path(__file__).parent.parent / "cogs"

DEBUG_GUILDS = [1219455776096256060]

class AlfredBot(commands.Bot):
    """
    The main class for the Alfred bot, using a dependency injection pattern.
    """
    def __init__(self, *args, **kwargs):
        # Define the intents for the bot.
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        # Pass the intents to the parent class constructor.
        # Note: We are no longer using debug_guilds here. Syncing is handled in setup_hook.
        super().__init__(*args, command_prefix="!", intents=intents, **kwargs)

        logger.info("AlfredBot class is initializing.")
        
        # Create instances of our manager classes. They are "owned" by the bot.
        self.db_manager = DatabaseManager()
        self.ai_handler = AIHandler(self.db_manager) # Pass the db_manager to the AI handler

    async def setup_hook(self) -> None:
        """
        This is the guaranteed entry point for all async setup.
        """
        logger.info("--- [SETUP HOOK] Starting guaranteed async setup ---")

        # Step 1: Initialize the Database Manager
        logger.info("[SETUP HOOK] Step 1: Initializing Database Manager...")
        try:
            await self.db_manager.initialize()
            logger.info("[SETUP HOOK] ✅ Database Manager Initialized.")
        except Exception as e:
            logger.critical(f"[SETUP HOOK] ❌ FAILED to initialize Database Manager: {e}", exc_info=True)
            await self.close() # Shut down if DB connection fails
            return

        # Step 2: Load all cogs from the /cogs directory
        logger.info("[SETUP HOOK] Step 2: Loading Cogs...")
        for filename in os.listdir(COGS_DIR):
            if filename.endswith(".py") and not filename.startswith("_"):
                cog_name = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(cog_name)
                    logger.info(f"  -> ✅ Successfully loaded cog: {cog_name}")
                except Exception as e:
                    logger.error(f"  -> ❌ Failed to load cog: {cog_name}", exc_info=True)
        logger.info("[SETUP HOOK] ✅ Cog loading complete.")
        
        # Step 3: Sync the command tree AFTER all cogs have been loaded
        logger.info("[SETUP HOOK] Step 3: Syncing command tree...")
        try:
            synced_commands = await self.tree.sync(guild=discord.Object(id=DEBUG_GUILDS[0]))
            logger.info(f"[SETUP HOOK] ✅ Command tree synced successfully. {len(synced_commands)} commands registered.")
        except Exception as e:
            logger.critical(f"[SETUP HOOK] ❌ FAILED TO SYNC COMMANDS: {e}", exc_info=True)

        logger.info("--- [SETUP HOOK] Finished ---")

    async def on_ready(self) -> None:
        """
        Called when the bot is fully connected and ready.
        """
        # Pass the bot's user ID to the AI handler now that we know it.
        self.ai_handler.set_bot_user_id(self.user.id)
        
        logger.info("="*50)
        logger.info(f"Alfred is online. Logged in as {self.user.name} (ID: {self.user.id})")
        logger.info("="*50)

    async def close(self):
        """Custom close method to gracefully shut down services."""
        logger.info("Closing bot and services...")
        if self.db_manager and self.db_manager.is_initialized:
            await self.db_manager.close()
        await super().close()