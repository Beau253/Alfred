# Alfred/core/ai_handler.py

import logging
import google.generativeai as genai
from itertools import cycle
import asyncio
from collections import deque
from .config import settings
from .database import ConversationHistory, AsyncSessionLocal
from sqlalchemy import select, desc

# Set up a logger for this module
logger = logging.getLogger(__name__)

CONVERSATION_CACHE = {}
CACHE_MAX_SIZE = 100  # Max number of conversations to cache
CACHE_HISTORY_LENGTH = 20 # Max number of messages per conversation in cache

class AIHandler:
    """
    Manages all interactions with the AI model (Google Gemini).
    
    This class handles API key configuration, key rotation (pooling),
    and provides a simple interface for other parts of the application
    to get responses from the AI.
    """
    def __init__(self):
        self.models = {}
        self._key_cycler = None
        self.bot_user_id = None # Will be set by the bot on startup

        if not settings.GEMINI_API_KEYS:
            logger.warning("No Gemini API keys found. AIHandler will be disabled.")
            return

        self._keys = list(settings.GEMINI_API_KEYS)
        self._key_cycler = cycle(self._keys)
        self.configure_next_key()
    
    def configure_next_key(self) -> bool: 
        """Configures genai with the next available key from the pool."""
        if not self._key_cycler:
            return False
        
        try:
            next_key = next(self._key_cycler)
            genai.configure(api_key=next_key)
            logger.info(f"AI Handler configured with a new API key.")
            return True
        except Exception as e:
            logger.error(f"Failed to configure Gemini with an API key: {e}")
            return False

    def set_bot_user_id(self, bot_id: int):
        """A method to allow the bot to set its own ID after it has logged in."""
        self.bot_user_id = bot_id
        logger.info(f"AIHandler initialized with Bot User ID: {self.bot_user_id}")

    def _get_next_key(self) -> str | None:
        """Rotates to the next API key in the pool."""
        if not self._key_cycler:
            return None
        return next(self._key_cycler)

    def get_model(self, model_name: str = "gemini-1.5-flash-latest") -> genai.GenerativeModel | None:
        """
        Gets a cached instance of a generative model.
        
        Using a cached instance is more efficient than creating a new one for every request.
        """
        if not self._key_cycler:
            logger.error("Cannot get AI model because AIHandler is not configured.")
            return None

        if model_name not in self.models:
            logger.info(f"Creating a new instance for model: {model_name}")
            self.models[model_name] = genai.GenerativeModel(model_name)
        
        return self.models[model_name]

    async def _get_history(self, channel_id: int) -> deque:
        """
        Gets conversation history, prioritizing cache then falling back to DB.
        """
        # 1. Check cache first
        if channel_id in CONVERSATION_CACHE:
            logger.debug(f"Cache hit for channel {channel_id}.")
            return CONVERSATION_CACHE[channel_id]

        # 2. If cache miss, query database
        logger.info(f"Cache miss for channel {channel_id}. Querying database.")
        history_deque = deque(maxlen=CACHE_HISTORY_LENGTH)
        
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(ConversationHistory)
                    .where(ConversationHistory.channel_id == channel_id)
                    .order_by(desc(ConversationHistory.timestamp))
                    .limit(CACHE_HISTORY_LENGTH)
                )
                result = await session.execute(stmt)
                # The results are newest-first, so we reverse them to be chronological
                db_records = reversed(result.scalars().all())
                
                for record in db_records:
                    history_deque.append({'role': record.role, 'parts': [record.content]})
            
            # 3. Populate cache
            if len(CONVERSATION_CACHE) > CACHE_MAX_SIZE:
                 CONVERSATION_CACHE.popitem(last=False) # Evict oldest if cache is full

            CONVERSATION_CACHE[channel_id] = history_deque
            logger.info(f"Cached conversation history for channel {channel_id}.")
        except Exception as e:
            logger.error(f"Failed to retrieve history for channel {channel_id}: {e}", exc_info=True)
            
        return history_deque

    async def _save_history(self, guild_id: int, channel_id: int, user_id: int, prompt: str, response: str):
        """
        Saves the new prompt and response to both the cache and the database.
        """
        # 1. Update cache
        if channel_id not in CONVERSATION_CACHE:
            CONVERSATION_CACHE[channel_id] = deque(maxlen=CACHE_HISTORY_LENGTH)
        
        CONVERSATION_CACHE[channel_id].append({'role': 'user', 'parts': [prompt]})
        CONVERSATION_CACHE[channel_id].append({'role': 'model', 'parts': [response]})

        # 2. Save to database
        try:
            async with AsyncSessionLocal() as session:
                user_message = ConversationHistory(
                    guild_id=guild_id, channel_id=channel_id, user_id=user_id,
                    role='user', content=prompt
                )
                model_message = ConversationHistory(
                    guild_id=guild_id, channel_id=channel_id, user_id=self.bot_user_id, # Assumes we have bot's ID
                    role='model', content=response
                )
                session.add_all([user_message, model_message])
                await session.commit()
            logger.debug(f"Saved conversation history to DB for channel {channel_id}.")
        except Exception as e:
            logger.error(f"Failed to save history for channel {channel_id}: {e}", exc_info=True)


    async def get_chat_response(
        self, 
        guild_id: int,
        channel_id: int, 
        user_id: int, 
        prompt: str,
        system_instruction: str = "You are Alfred, a helpful and concise AI assistant."
    ) -> str:
        """
        Gets a contextual response from the AI, including conversation history
        and implementing rate-limit protection.
        """
        if not self._key_cycler or not self.bot_user_id:
            return "I am currently unable to connect to my AI core."

        model = self.get_model()
        if not model:
            return "I could not initialize my AI model. Please check my configuration."

        # 1. Get conversation history
        history = await self._get_history(channel_id)
        # Convert deque to a list for the API
        history_list = list(history)

        # 2. Prepend the system instruction (if history is empty)
        if not history_list:
            history_list.insert(0, {'role': 'model', 'parts': ["Understood."]})
            history_list.insert(0, {'role': 'user', 'parts': [system_instruction]})

        # 3. Rate Limit & Retry Logic
        max_retries = len(self._keys)
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending prompt to Gemini (Attempt {attempt + 1}/{max_retries})...")
                
                chat_session = model.start_chat(history=history_list)
                response = await chat_session.send_message_async(prompt)
                
                logger.info("Successfully received response from Gemini.")
                
                # 4. Save history
                await self._save_history(guild_id, channel_id, user_id, prompt, response.text)
                
                return response.text

            except Exception as e:
                logger.warning(f"Gemini API error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    logger.info("Switching to next API key and retrying...")
                    self.configure_next_key()
                    await asyncio.sleep(1) 
                else:
                    logger.error("All Gemini API keys failed. Aborting request.")
                    return "My AI core is currently experiencing high traffic. Please try again in a moment."
        
        return "An unexpected error occurred after multiple retries."

# Create a single, global instance of the AIHandler that the rest of the app can import.
ai_handler = AIHandler()