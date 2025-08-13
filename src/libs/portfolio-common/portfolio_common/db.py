# libs/portfolio-common/portfolio_common/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from .config import POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
from .db_base import Base


def get_sync_database_url():
    """
    Determines the synchronous database URL.
    Prioritizes DATABASE_URL for containerized environments.
    Falls back to HOST_DATABASE_URL for local development/testing.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url.replace("postgresql+asyncpg://", "postgresql://")

    url = os.getenv("HOST_DATABASE_URL")
    if url:
        return url.replace("postgresql+asyncpg://", "postgresql://")

    return f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

engine = create_engine(get_sync_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session():
    """
    A synchronous dependency to get a SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



def get_async_database_url():
    """
    Determines the correct async database URL, with an asyncpg driver scheme.
    """
    url = os.getenv("DATABASE_URL") or f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    if "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url

async_engine = create_async_engine(
    get_async_database_url(),
    pool_pre_ping=True,
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
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()