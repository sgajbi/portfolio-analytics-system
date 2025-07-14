from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from common.config import POSTGRES_URL

# Database setup
SQLALCHEMY_DATABASE_URL = POSTGRES_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define Base here to be imported by all SQLAlchemy models
Base = declarative_base()

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