# main.py

import os
import time
from threading import Thread

# 1. Import our application components
from core.bot import AlfredBot
from core.api_server import app as flask_app # Our Flask app object
from core.config import settings

# 2. Define the function that will run the Flask app
# For Render, we need a production-ready server. Waitress is a great, simple choice.
def run_api_server():
    from waitress import serve
    print("Starting Flask API server on port", settings.API_SERVER_PORT)
    serve(flask_app, host="0.0.0.0", port=settings.API_SERVER_PORT)

# 3. Define the function that will run the Discord bot
def run_discord_bot():
    print("Starting Alfred Discord bot...")
    bot = AlfredBot()
    bot.run(settings.DISCORD_BOT_TOKEN)

# 4. The main entry point to start and manage the threads
if __name__ == "__main__":
    # Create a thread for the API server
    api_thread = Thread(target=run_api_server)
    api_thread.daemon = True # This allows the main thread to exit even if this one is running

    # Create a thread for the Discord bot
    bot_thread = Thread(target=run_discord_bot)
    bot_thread.daemon = True

    print("Initializing services...")
    api_thread.start()
    bot_thread.start()
    print("Services are running in separate threads.")

    # Keep the main thread alive to listen for a shutdown signal (like Ctrl+C)
    # Without this, the script would start the threads and immediately exit.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutdown signal received. Exiting.")
        # The daemon threads will be terminated automatically when the main script exits.
        os._exit(0)