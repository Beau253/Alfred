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
from contextlib import asynccontextmanager, contextmanager
from .config import settings  # Import our centralized settings

# Set up a logger for this module
logger = logging.getLogger(__name__)

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

class DatabaseManager:
    """
    Manages the database connection, sessions, and table creation.
    """
    def __init__(self):
        self.async_engine = None
        self.AsyncSessionLocal = None
        self.is_initialized = False

    async def initialize(self):
        """Initializes the database engine and creates all necessary tables."""
        if self.is_initialized:
            logger.warning("DatabaseManager is already initialized.")
            return

        try:
            self.async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
            self.AsyncSessionLocal = sessionmaker(
                bind=self.async_engine, class_=AsyncSession, expire_on_commit=False
            )
            
            # Create all tables defined by the Base class
            logger.info("Initializing database tables...")
            async with self.async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized successfully.")
            
            self.is_initialized = True

        except Exception as e:
            logger.critical(f"Failed to initialize DatabaseManager: {e}", exc_info=True)
            self.is_initialized = False
            raise

    @asynccontextmanager
    async def get_session(self) -> AsyncSession:
        """Provides a managed asynchronous session for database operations."""
        if not self.is_initialized or not self.AsyncSessionLocal:
            raise RuntimeError("DatabaseManager is not initialized. Cannot get session.")
        
        session: AsyncSession = self.AsyncSessionLocal()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            
    async def close(self):
        """Closes the database engine connection."""
        if self.async_engine:
            await self.async_engine.dispose()
            self.is_initialized = False
            logger.info("Database connection pool closed.")