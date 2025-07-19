# core/bot.py

import logging
import discord
from discord.ext import commands
import os
from pathlib import Path
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
from .api_server import app as flask_app
from .database import DatabaseManager
from .ai_handler import AIHandler
from .config import settings
from cogs.onboarding import Onboarding
from cogs.setup import Setup

logger = logging.getLogger(__name__)
COGS_DIR = Path(__file__).parent.parent / "cogs"
DEBUG_GUILDS = [1219455776096256060]

class AlfredBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        logger.info("AlfredBot class is initializing.")
        
        self.db_manager = DatabaseManager()
        self.ai_handler = AIHandler(self.db_manager)
        self.is_setup_complete = False
        flask_app.bot = self

        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        # For commands.Bot, the command prefix is a required argument, even if you don't use it.
        super().__init__(
            command_prefix="!", # Can be any character
            intents=intents,
            **kwargs
        )

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
        """The guaranteed async setup hook from discord.py"""
        logger.info("--- [SETUP HOOK] Starting setup ---")

        logger.info("[SETUP HOOK] Step 1: Starting API Server in background...")
        self.api_task = self.loop.create_task(self.start_api_server())
        
        logger.info("[SETUP HOOK] Step 2: Initializing Database Manager...")
        await self.db_manager.initialize()
        logger.info("[SETUP HOOK] ✅ Database Manager Initialized.")

        logger.info("[SETUP HOOK] Step 3: Loading Cogs...")
        try:
            await self.add_cog(Onboarding(self, self.db_manager, self.ai_handler))
            logger.info("  -> ✅ Successfully loaded cog: Onboarding")
            await self.add_cog(Setup(self, self.db_manager))
            logger.info("  -> ✅ Successfully loaded cog: Setup")
            logger.info(f"[SETUP HOOK] ✅ Cog loading complete.")
        except Exception as e:
            logger.error(f"  -> ❌ Failed to manually load cogs", exc_info=True)
        
        logger.info("[SETUP HOOK] Step 4: Forcibly syncing command tree to debug guild...")
        try:
            guild_obj = discord.Object(id=DEBUG_GUILDS[0])
            # The tree is now at self.tree
            self.tree.copy_global_to(guild=guild_obj)
            synced_commands = await self.tree.sync(guild=guild_obj)
            
            logger.info(f"[SETUP HOOK] ✅ COMMANDS SYNCED: {len(synced_commands)} commands registered to guild {DEBUG_GUILDS[0]}.")
            for command in synced_commands:
                    logger.info(f"    -> Synced command: '{command.name}'")

        except Exception as e:
            logger.critical(f"[SETUP HOOK] ❌ FAILED TO SYNC COMMANDS: {e}", exc_info=True)
        
        logger.info("--- [SETUP HOOK] Finished ---")

    async def on_ready(self) -> None:
        """Called when the bot is fully connected and ready."""
        self.ai_handler.set_bot_user_id(self.user.id)
        
        logger.info("="*50)
        logger.info(f"Alfred is online. Logged in as {self.user.name} (ID: {self.user.id})")
        logger.info("="*50)

    async def close(self):
        """Custom close method to gracefully shut down services."""
        logger.info("Closing bot and services...")
        if hasattr(self, 'api_task') and not self.api_task.done():
            self.api_task.cancel()
        if self.db_manager and self.db_manager.is_initialized:
            await self.db_manager.close()
        await super().close()