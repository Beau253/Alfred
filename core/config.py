# core/config.py

import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
import logging

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Define the base directory of the project.
# Path(__file__) is the path to this file (config.py).
# .parent gives us the 'core' directory.
# .parent again gives us the root 'Alfred' directory.
BASE_DIR = Path(__file__).parent.parent

# Load the .env file from the base directory
load_dotenv(BASE_DIR / ".env")

@dataclass
class Settings:
    """
    A dataclass to hold all application settings, loaded from environment variables
    and JSON files. This provides type hinting and a single source of truth for config.
    """
    # --- Discord Settings ---
    DISCORD_BOT_TOKEN: str = field(init=False)

    # --- Database Settings ---
    DATABASE_URL: str = field(init=False)

    # --- API Server Settings ---
    API_SERVER_HOST: str = field(init=False)
    API_SERVER_PORT: int = field(init=False)

    # --- Integration Settings ---
    # A dictionary to hold allowed tokens, e.g., {"RELAY": "secret_token"}
    ALLOWED_INTEGRATION_TOKENS: dict[str, str] = field(default_factory=dict)
    
    # --- AI Settings ---
    GEMINI_API_KEYS: list[str] = field(default_factory=list)

    def __post_init__(self):
        """
        This method is called after the class is initialized.
        We use it to load values from the environment and files.
        """
        logger.info("Loading application settings...")

        # Load required settings from environment variables
        self.DISCORD_BOT_TOKEN = self._get_env_var("DISCORD_BOT_TOKEN")
        self.DATABASE_URL = self._get_env_var("DATABASE_URL")
        self.API_SERVER_HOST = self._get_env_var("API_SERVER_HOST", default="0.0.0.0")
        self.API_SERVER_PORT = int(self._get_env_var("API_SERVER_PORT", default="8080"))

        # Load and parse the integration tokens
        self._load_integration_tokens()

        # Load Gemini API keys from the credentials file
        self._load_gemini_keys()
        
        logger.info("Settings loaded successfully.")

    def _get_env_var(self, key: str, default: str | None = None) -> str:
        """Helper function to get an environment variable and raise an error if not found."""
        value = os.getenv(key, default)
        if value is None:
            raise ValueError(f"Error: Environment variable '{key}' not found and no default was set.")
        return value

    def _load_integration_tokens(self):
        """Parses the ALLOWED_INTEGRATION_TOKENS string into a dictionary."""
        tokens_str = self._get_env_var("ALLOWED_INTEGRATION_TOKENS", default="")
        if not tokens_str:
            logger.warning("No integration tokens found in environment variables.")
            return

        try:
            # Splits "RELAY:token1,BOT2:token2" into ["RELAY:token1", "BOT2:token2"]
            token_pairs = tokens_str.split(',')
            for pair in token_pairs:
                # Splits "RELAY:token1" into ["RELAY", "token1"]
                name, token = pair.split(':', 1)
                self.ALLOWED_INTEGRATION_TOKENS[name.strip()] = token.strip()
            logger.info(f"Loaded {len(self.ALLOWED_INTEGRATION_TOKENS)} integration token(s).")
        except ValueError as e:
            logger.error(f"Error parsing ALLOWED_INTEGRATION_TOKENS: {e}. Ensure format is 'Name:Token,Name2:Token2'")


    def _load_gemini_keys(self):
        """Loads Gemini API keys from the specified JSON file."""
        keys_path = BASE_DIR / "credentials" / "gemini_keys.json"
        if not keys_path.exists():
            logger.warning(f"Gemini keys file not found at {keys_path}. AI features will be disabled.")
            return

        try:
            with open(keys_path, 'r') as f:
                data = json.load(f)
                keys = data.get("keys")
                if isinstance(keys, list) and keys:
                    self.GEMINI_API_KEYS = keys
                    logger.info(f"Loaded {len(self.GEMINI_API_KEYS)} Gemini API key(s).")
                else:
                    logger.warning(f"No keys found or 'keys' is not a list in {keys_path}.")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error reading or parsing {keys_path}: {e}")

# Create a single, global instance of the Settings class that the rest of the app can import.
settings = Settings()