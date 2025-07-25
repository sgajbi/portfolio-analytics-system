import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
from .database_models import Base

def get_database_url():
    """
    Determines the correct database URL based on the environment.
    - For local development, it uses HOST_DATABASE_URL from the .env file.
    - For Docker, it constructs the URL from individual POSTGRES_* vars.
    """
    url = os.getenv("HOST_DATABASE_URL")
    if url:
        return url
    
    return f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Database setup
SQLALCHEMY_DATABASE_URL = get_database_url()
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session():
    """
    Dependency to get a SQLAlchemy database session.
    Yields a session that is automatically closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()