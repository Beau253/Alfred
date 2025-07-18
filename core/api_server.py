# Alfred/core/api_server.py

import logging
import asyncio
from flask import Flask, request, jsonify, current_app

from .config import settings

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Create the Flask application instance
app = Flask(__name__)

# --- Authentication Decorator ---
# This is a more robust way to handle authentication for our routes.
from functools import wraps

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            logger.warning("Auth error: Missing Authorization header.")
            return jsonify({"status": "error", "message": "Authorization header is missing."}), 401

        try:
            auth_type, provided_token = auth_header.split()
            if auth_type.lower() != 'bearer':
                raise ValueError("Invalid auth type")
        except ValueError:
            logger.warning("Auth error: Malformed Authorization header.")
            return jsonify({"status": "error", "message": "Malformed Authorization header. Expected 'Bearer <token>'."}), 400

        # Check the provided token against our list of allowed tokens
        if provided_token not in settings.ALLOWED_INTEGRATION_TOKENS.values():
            logger.warning(f"Auth error: Invalid token provided.")
            return jsonify({"status": "error", "message": "Invalid authentication token."}), 403
        
        # If we get here, authentication is successful
        return f(*args, **kwargs)
    return decorated_function


# --- API Routes ---

@app.route('/health', methods=['GET'])
def health_check():
    """A simple health check endpoint. Useful for diagnostics."""
    return jsonify({"status": "ok"}), 200


# In core/api_server.py

@app.route('/v1/onboarding/language_set', methods=['POST'])
@require_auth
def language_set_webhook():
    """
    Webhook endpoint to be called by the Relay (translator) bot.
    It receives a notification that a new user has set their language.
    """
    logger.info("Received request on /v1/onboarding/language_set")
    
    # --- ADD THIS LOGIC BACK IN ---
    data = request.get_json()
    if not data or 'user_id' not in data or 'language_code' not in data:
        logger.error("Webhook error: Invalid or missing JSON payload.")
        return jsonify({"status": "error", "message": "Invalid JSON payload. 'user_id' and 'language_code' are required."}), 400

    # We need to convert the user_id from a string (in JSON) to an integer
    try:
        user_id = int(data['user_id'])
        language_code = str(data['language_code'])
    except (ValueError, TypeError):
        logger.error("Webhook error: user_id or language_code have incorrect types.")
        return jsonify({"status": "error", "message": "Invalid data types for user_id or language_code."}), 400
    # --------------------------------

    # Your existing logic is perfect and starts here:
    try:
        # Get the running bot instance from the current app context
        bot = current_app.bot
        
        # Get the onboarding cog
        onboarding_cog = bot.get_cog('Onboarding')
        if not onboarding_cog:
            logger.error("CRITICAL: Onboarding cog not found.")
            return jsonify({"status": "error", "message": "Internal server error: Cog not loaded."}), 500

        # Schedule the asynchronous task to run on the bot's event loop
        # This is the thread-safe way to call an async function from a sync context
        asyncio.run_coroutine_threadsafe(
            onboarding_cog.handle_language_set(user_id, language_code),
            bot.loop
        )

        logger.info(f"Successfully scheduled language set task for User ID: {user_id}")
        return jsonify({
            "status": "success",
            "message": f"Language set notification queued for user {user_id}."
        }), 202 # 202 Accepted is a good status code for "I got it, and am processing it"
    
    except Exception as e:
        logger.critical(f"Error when trying to schedule language set task: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error while processing request."}), 500