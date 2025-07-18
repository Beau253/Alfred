# Alfred/main.py

import logging
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve

# --- Basic Logging Setup ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler("alfred.log")
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# --- Application Imports ---
from core.bot import AlfredBot
from core.api_server import app as flask_app
from core.config import settings

# --- Asynchronous Runner ---
async def main():
    """The main asynchronous entry point for the application."""
    logger.info("Initializing Alfred...")

    # 1. Create the bot instance
    bot = AlfredBot()
    
    # 2. Configure Hypercorn to run our Flask app
    # Hypercorn is an ASGI server that can run Flask apps in an async context.
    config = Config()
    config.bind = [f"{settings.API_SERVER_HOST}:{settings.API_SERVER_PORT}"]
    
    # This is a special function to run a WSGI app (Flask) in an ASGI server (Hypercorn)
    shutdown_event = asyncio.Event()
    
    # Create tasks for both the bot and the API server
    # We pass the bot instance to the Flask app *before* starting the tasks
    flask_app.bot = bot

    api_task = asyncio.create_task(
        serve(flask_app, config, shutdown_trigger=lambda: shutdown_event.wait())
    )

    bot_task = asyncio.create_task(bot.start(settings.DISCORD_BOT_TOKEN))

    # Run both tasks concurrently. If one fails, the other will be cancelled.
    done, pending = await asyncio.wait(
        [bot_task, api_task], return_when=asyncio.FIRST_COMPLETED
    )
    
    logger.info("A core task has completed. Shutting down...")
    for task in pending:
        task.cancel()
    
    # Trigger the shutdown for the API server
    shutdown_trigger.set()
    await asyncio.gather(*pending, return_exceptions=True)
    
    # Gracefully close the bot
    if not bot.is_closed():
        await bot.close()


# --- Main Execution Block ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Exiting.")