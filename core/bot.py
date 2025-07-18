# core/bot.py

import logging
import discord
import os # <-- Added this import
from pathlib import Path
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
from .api_server import app as flask_app
from .database import DatabaseManager
from .ai_handler import AIHandler
from .config import settings


logger = logging.getLogger(__name__)
COGS_DIR = Path(__file__).parent.parent / "cogs"
DEBUG_GUILDS = [1219455776096256060]

class AlfredBot(discord.Bot):
    def __init__(self, *args, **kwargs):
        # Define the intents for the bot.
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(*args, intents=intents, debug_guilds=DEBUG_GUILDS, **kwargs)

        logger.info("AlfredBot class is initializing.")
        self.db_manager = DatabaseManager()
        self.ai_handler = AIHandler(self.db_manager) # Pass the db_manager to the AI handler

        flask_app.bot = self

    async def start_api_server(self):
        """A background task to run the Hypercorn web server."""
        try:
            config = Config()
            config.bind = [f"{settings.API_SERVER_HOST}:{settings.API_SERVER_PORT}"]
            await serve(flask_app, config)
        except asyncio.CancelledError:
            logger.info("API server task was cancelled.")
        except Exception as e:
            logger.critical(f"API server crashed with an exception: {e}", exc_info=True)

    async def setup_hook(self) -> None:
        """The guaranteed entry point for all async setup."""
        logger.info("--- [SETUP HOOK] Starting guaranteed async setup ---")

        # Step 1: Start the API server as a background task
        logger.info("[SETUP HOOK] Step 1: Starting API Server in background...")
        self.api_task = self.loop.create_task(self.start_api_server())
        
        # Step 2: Initialize the Database Manager
        logger.info("[SETUP HOOK] Step 2: Initializing Database Manager...")
        await self.db_manager.initialize()
        logger.info("[SETUP HOOK] ✅ Database Manager Initialized.")

        # Step 3: Load all cogs
        logger.info("[SETUP HOOK] Step 3: Loading Cogs...")
        cogs_loaded = 0
        for filename in os.listdir(COGS_DIR):
            if filename.endswith(".py") and not filename.startswith("_"):
                cog_name = f"cogs.{filename[:-3]}"
                try:
                    self.load_extension(f"cogs.{filename[:-3]}")
                    logger.info(f"  -> ✅ Successfully loaded cog: {cog_name}")
                    cogs_loaded += 1
                except Exception as e:
                    logger.error(f"  -> ❌ Failed to load cog: {cog_name}", exc_info=True)
        logger.info(f"[SETUP HOOK] ✅ Cog loading complete. {cogs_loaded} cogs loaded.")
        
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