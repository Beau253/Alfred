# core/database.py

import logging
from sqlalchemy import (
    create_engine,
    Column,
    BigInteger,
    String,
    Boolean,
    Text,
    DateTime
)

from sqlalchemy.sql import func 
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import relationship 

from .config import settings  # Import our centralized settings

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- Database Engine Setup ---
# We create both a synchronous and an asynchronous engine.
# The bot will primarily use the async engine for non-blocking database calls.
# The Flask API server, being synchronous, will use the sync engine.

try:
    # Asynchronous engine for discord.py cogs
    async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
    
    # Synchronous engine for the Flask API server
    sync_engine = create_engine(settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql"), echo=False)
    
    # Sessionmakers are factories for creating new database sessions.
    AsyncSessionLocal = sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )
    SyncSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=sync_engine
    )
    
    logger.info("Database engines created successfully.")
except Exception as e:
    logger.critical(f"Failed to create database engines: {e}", exc_info=True)
    raise

# --- ORM Model Definition ---
# Base class for our declarative models
Base = declarative_base()

class OnboardingStatus(Base):
    """
    Represents the state of a new member's onboarding journey.
    """
    __tablename__ = "onboarding_status"

    # The user's unique Discord ID. This is the primary key.
    user_id = Column(BigInteger, primary_key=True)

    # The 2-letter ISO code for the user's chosen language (e.g., 'en', 'es').
    language_code = Column(String(5), nullable=True)

    # A simple state machine to track progress.
    # e.g., 'AWAITING_LANGUAGE', 'IN_PROGRESS', 'COMPLETED'
    status = Column(String(50), default="AWAITING_LANGUAGE", nullable=False)

    # A flag to indicate if the onboarding process is fully complete.
    is_complete = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return (
            f"<OnboardingStatus(user_id={self.user_id}, "
            f"status='{self.status}', is_complete={self.is_complete})>"
        )

class ConversationHistory(Base):
    """
    Stores the history of conversations between users and Alfred.
    """
    __tablename__ = "conversation_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    channel_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    
    # 'user' for the human, 'model' for the AI's response
    role = Column(String(10), nullable=False) 
    
    content = Column(Text, nullable=False)
    
    # This stores the timestamp in UTC.
    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self):
        return (
            f"<ConversationHistory(user_id={self.user_id}, role='{self.role}', "
            f"timestamp='{self.timestamp}')>"
        )

class GuildSettings(Base):
    """
    Stores server-specific settings for Alfred.
    """
    __tablename__ = "guild_settings"

    # The server's unique Discord ID.
    guild_id = Column(BigInteger, primary_key=True)

    # The ID of the channel where public welcome messages are sent.
    welcome_channel_id = Column(BigInteger, nullable=True)
    
    # The ID of the channel where users set their language.
    language_channel_id = Column(BigInteger, nullable=True)

    # The ID of the role that has staff/support permissions.
    support_role_id = Column(BigInteger, nullable=True)

    def __repr__(self):
        return f"<GuildSettings(guild_id={self.guild_id})>"

async def create_all_tables():
    """
    An asynchronous function to create all defined tables in the database.
    This should be called once when the bot starts up.
    """
    logger.info("Initializing database tables...")
    async with async_engine.begin() as conn:
        # This command connects to the DB and creates tables if they don't exist.
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")