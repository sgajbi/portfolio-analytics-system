# libs/portfolio-common/portfolio_common/db.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from .config import POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
from .db_base import Base

def get_database_url():
    """
    Determines the correct database URL, now with an asyncpg driver scheme.
    - For local development, it uses HOST_DATABASE_URL from the .env file.
    - For Docker, it constructs the URL from individual POSTGRES_* vars.
    """
    url = os.getenv("HOST_DATABASE_URL")
    if url:
        # Ensure the scheme is compatible with asyncpg
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://")
        return url
    
    return f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Async Database Setup
ASYNC_SQLALCHEMY_DATABASE_URL = get_database_url()

async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    echo=False, # Set to True for debugging DB queries
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

async def get_async_db_session() -> AsyncSession:
    """
    An async dependency that provides an SQLAlchemy AsyncSession.
    It ensures the session is always closed, even if errors occur.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()