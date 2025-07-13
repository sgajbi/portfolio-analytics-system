
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from common.config import POSTGRES_URL
from common.database_models import Base, TransactionDB

# Database setup
SQLALCHEMY_DATABASE_URL = POSTGRES_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

