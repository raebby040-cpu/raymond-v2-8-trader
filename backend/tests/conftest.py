"""Test configuration and fixtures"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.main import app
from app.database import Base, get_db
from app.models import Trade, Position, StrategyDecision, RiskEvent, Journal, Account

# ==================== DATABASE SETUP ====================
@pytest.fixture(scope="function")
def test_db():
    """Create test database"""
    # Use in-memory SQLite for tests
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield TestingSessionLocal()
    
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()

# ==================== CLIENT SETUP ====================
@pytest.fixture(scope="function")
def client(test_db):
    """Create test client"""
    return TestClient(app)

# ==================== TRADE FIXTURES ====================
@pytest.fixture
def sample_trade_data():
    """Sample trade data for testing"""
    return {
        "symbol": "XAUUSD",
        "direction": "buy",
        "order_type": "market",
        "quantity": 0.5,
        "entry_price": 2050.00,
        "stop_loss": 2045.00,
        "take_profit": 2060.00,
        "broker": "mt5",
        "strategy_decision": "strong_buy",
        "confidence": 0.85,
        "notes": "Test trade"
    }

# ==================== POSITION FIXTURES ====================
@pytest.fixture
def sample_position_data():
    """Sample position data for testing"""
    return {
        "trade_id": "TRD-001",
        "symbol": "XAUUSD",
        "direction": "buy",
        "quantity": 0.5,
        "entry_price": 2050.00,
        "current_price": 2052.00,
        "stop_loss": 2045.00,
        "take_profit": 2060.00,
        "broker": "mt5"
    }

# ==================== STRATEGY DECISION FIXTURES ====================
@pytest.fixture
def sample_decision_data():
    """Sample strategy decision data for testing"""
    return {
        "symbol": "XAUUSD",
        "decision": "strong_buy",
        "confidence": 0.85,
        "current_price": 2050.45,
        "bid": 2050.40,
        "ask": 2050.50,
        "ema20": 2049.50,
        "ema50": 2047.00,
        "rsi": 65.5,
        "atr": 12.35,
        "risk_level": "medium"
    }

# ==================== JOURNAL FIXTURES ====================
@pytest.fixture
def sample_journal_data():
    """Sample journal data for testing"""
    return {
        "title": "Test Trade Analysis",
        "content": "This is a test journal entry",
        "category": "trade_analysis",
        "tags": "test,xauusd,analysis",
        "is_private": False
    }
