"""
Database session and connection management
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./raymond.db"
)

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

def get_db():
    """Dependency for FastAPI to inject database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
