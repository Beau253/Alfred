# Alfred/main.py

import logging
import asyncio

# --- Basic Logging Setup ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler("alfred.log")
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# --- Application Imports ---
from core.bot import AlfredBot
from core.config import settings

async def main():
    """The main asynchronous entry point for the application."""
    logger.info("Initializing Alfred...")
    bot = AlfredBot()
    try:
        await bot.start(settings.DISCORD_BOT_TOKEN)
    finally:
        if not bot.is_closed():
            await bot.close()

# --- Main Execution Block ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Exiting.")