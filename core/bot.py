# core/bot.py

import logging
import discord
import os # <-- Added this import
from pathlib import Path
from .ai_handler import ai_handler
from .config import settings
from .database import create_all_tables

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Define the path to the 'cogs' directory
COGS_DIR = Path(__file__).parent.parent / "cogs"

DEBUG_GUILDS = [1219455776096256060]

class AlfredBot(discord.Bot):
    """
    The main class for the Alfred bot.
    
    This class subclasses discord.Bot and handles the setup,
    loading of extensions (cogs), and core event handling.
    """
    def __init__(self, *args, **kwargs):
        # Define the intents for the bot. Intents are like permissions for what
        # events your bot can receive from Discord.
        intents = discord.Intents.default()
        intents.members = True  # Required for on_member_join events
        intents.message_content = True  # Required for some command interactions

        super().__init__(
            *args, 
            intents=intents, 
            debug_guilds=DEBUG_GUILDS, 
            **kwargs
        )

        # Pass the intents to the parent class constructor
        super().__init__(*args, intents=intents, **kwargs)

        logger.info("AlfredBot class is initializing.")

    async def setup_hook(self) -> None:
        """
        This is a special discord.py method that is called after the bot
        has logged in but before it has fully connected to Discord's gateway.
        It's the perfect place for asynchronous setup tasks.
        """
        logger.info("Running setup_hook...")
        
        # 1. Initialize the database tables
        try:
            await create_all_tables()
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to initialize database: {e}", exc_info=True)
            await self.close()
            return

        # 2. Discover and load all cogs
        logger.info("Loading cogs...")
        for filename in os.listdir(COGS_DIR):
            if filename.endswith(".py") and not filename.startswith("_"):
                cog_name = f"cogs.{filename[:-3]}"
                try:
                    self.load_extension(cog_name)
                    logger.info(f"Successfully loaded cog: {cog_name}")
                except Exception as e:
                    logger.error(f"Failed to load cog: {cog_name}", exc_info=True)

        logger.info("setup_hook completed.")

    async def on_ready(self) -> None:
        """
        This event is called when the bot has successfully connected to Discord
        and is ready to start processing events.
        """
        ai_handler.set_bot_user_id(self.user.id)

        logger.info("Syncing application commands...")
        await self.sync_commands()
        logger.info("Application commands synced successfully.")
        
        logger.info(f"Logged in as {self.user.name} (ID: {self.user.id})")
        logger.info("Alfred is online and ready.")
        print("------")
        print(f"Alfred is now online and connected as {self.user.name}.")
        print("------")
        
    async def on_connect(self) -> None:
        """This event is called when the bot successfully connects to Discord."""
        logger.info("Bot has successfully connected to Discord.")

    async def on_disconnect(self) -> None:
        """This event is called when the bot loses its connection to Discord."""
        logger.warning("Bot has been disconnected from Discord.")