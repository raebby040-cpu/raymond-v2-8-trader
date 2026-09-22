"""
RAYMOND v2.8 - Authoritative Database Configuration

Stage 20 PostgreSQL Persistence

This module is the SINGLE runtime database foundation for RAYMOND.

Rules:
- DATABASE_URL is authoritative.
- PostgreSQL uses SSL/TLS.
- SQLite remains available for local development/tests.
- All runtime SQLAlchemy sessions use this engine.
- No trading logic is contained here.
- No broker/live-trading functionality is contained here.
"""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# DATABASE URL
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Local development/test fallback only.
    DATABASE_URL = "sqlite:///./raymond.db"


# ============================================================
# SQLALCHEMY ENGINE CONFIGURATION
# ============================================================

_is_sqlite = DATABASE_URL.startswith("sqlite")
_is_postgresql = (
    DATABASE_URL.startswith("postgresql://")
    or DATABASE_URL.startswith("postgres://")
    or DATABASE_URL.startswith("postgresql+")
)


connect_args: dict = {}


# SQLite requires this when FastAPI uses the database from
# multiple request/worker threads.
if _is_sqlite:
    connect_args = {
        "check_same_thread": False,
    }


# PostgreSQL on Render requires SSL/TLS.
#
# The Render environment already supplies DATABASE_URL.
# We deliberately do NOT hard-code credentials here.
if _is_postgresql:
    connect_args = {
        "sslmode": os.getenv(
            "PGSSLMODE",
            "require",
        ),
    }


# ============================================================
# ENGINE
# ============================================================

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


# ============================================================
# SESSION FACTORY
# ============================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ============================================================
# DECLARATIVE BASE
# ============================================================

Base = declarative_base()


# ============================================================
# FASTAPI DATABASE DEPENDENCY
# ============================================================

def get_db() -> Generator:
    """
    Provide one SQLAlchemy session per request.

    The session is always closed when the request finishes.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db() -> None:
    """
    Create database tables that do not already exist.

    Existing tables are NOT destroyed.

    Existing production data is therefore preserved.
    """

    # Import models here so SQLAlchemy registers all model
    # classes against this exact Base before create_all().
    from . import models  # noqa: F401

    Base.metadata.create_all(
        bind=engine,
    )


__all__ = [
    "DATABASE_URL",
    "engine",
    "SessionLocal",
    "Base",
    "get_db",
    "init_db",
]
