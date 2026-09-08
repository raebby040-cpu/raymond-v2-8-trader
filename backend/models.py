from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, JSON, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db import Base


class EmergencyStop(Base):
    __tablename__ = "emergency_stop"

    id = Column(Integer, primary_key=True, index=True)
    activated = Column(Boolean, default=False, nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text, nullable=True)
    activated_by = Column(String(200), nullable=True)


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=True)

    receipts = relationship("BrokerReceipt", back_populates="journal_entry")


class BrokerReceipt(Base):
    __tablename__ = "broker_receipts"

    id = Column(Integer, primary_key=True, index=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    broker_order_id = Column(String(200), nullable=True)
    status = Column(String(100), nullable=True)
    raw = Column(JSON, nullable=True)

    journal_entry = relationship("JournalEntry", back_populates="receipts")


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    instrument = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)  # buy/sell
    qty = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=True)
    status = Column(String(50), default="open", nullable=False)  # open/closed
    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
