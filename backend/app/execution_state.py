"""
RAYMOND v2.8 - Persistent Execution State

Stores broker execution attempts and their verification state so
DEMO/LIVE idempotency and reconciliation survive process restarts.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Index

try:
    from .database import Base
except ImportError:
    from database import Base


class ExecutionRecord(Base):
    __tablename__ = "execution_records"

    id = Column(Integer, primary_key=True, index=True)

    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    execution_mode = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    timeframe = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)
    side = Column(String, nullable=False)
    volume = Column(Float, nullable=False)
    requested_price = Column(Float, nullable=True)
    executed_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    order_ticket = Column(Integer, nullable=True, index=True)
    deal_ticket = Column(Integer, nullable=True, index=True)
    position_ticket = Column(Integer, nullable=True, index=True)
    broker_retcode = Column(Integer, nullable=True)
    broker_comment = Column(String, nullable=True)
    verified = Column(Boolean, nullable=False, default=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


Index("ix_execution_records_mode_status", ExecutionRecord.execution_mode, ExecutionRecord.status)


__all__ = ["ExecutionRecord"]
