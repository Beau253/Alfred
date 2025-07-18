# Alfred/main.py

import logging
import os
import time
from threading import Thread
import asyncio

# --- Basic Logging Setup ---
# This sets up logging to a file and to the console.
# It's good practice to have this in your main entry point.
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler("alfred.log")
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# --- Application Imports ---
# We import our custom components AFTER setting up logging.
from core.bot import AlfredBot
from core.api_server import app as flask_app
from core.config import settings

# --- Threading Functions ---
def run_api_server():
    """Runs the Flask web server in a production-ready way using Waitress."""
    from waitress import serve
    logger.info(f"Starting Flask API server on {settings.API_SERVER_HOST}:{settings.API_SERVER_PORT}")
    serve(flask_app, host=settings.API_SERVER_HOST, port=settings.API_SERVER_PORT)

def run_discord_bot():
    """Creates and runs the Discord bot instance."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logger.info("Starting Alfred Discord bot...")
    bot = AlfredBot()
    flask_app.bot = bot 
    bot.run(settings.DISCORD_BOT_TOKEN)


# --- Main Execution Block ---
if __name__ == "__main__":
    logger.info("Initializing Alfred...")

    # Create a thread for the API server
    api_thread = Thread(target=run_api_server)
    api_thread.daemon = True  # Allows the main program to exit even if this thread is running

    # Create a thread for the Discord bot
    bot_thread = Thread(target=run_discord_bot)
    bot_thread.daemon = True

    # Start both threads
    api_thread.start()
    bot_thread.start()
    logger.info("API Server and Discord Bot are running in separate threads.")

    # Keep the main thread alive to handle signals like Ctrl+C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Exiting.")
        # The daemon threads will be terminated automatically when the main script exits.
        os._exit(0)