"""
RAYMOND v2.8 - Database Models
Defines SQLAlchemy models for trading system persistence
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import enum
import os

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./raymond.db")

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==================== ENUMS ====================
class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PLACED = "placed"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class PositionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    CLOSING = "closing"

class TradeDirection(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"

# ==================== MODELS ====================
class Trade(Base):
    """Persistent trade journal entry"""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(String, unique=True, index=True)
    symbol = Column(String, default="XAUUSD")
    direction = Column(SQLEnum(TradeDirection), default=TradeDirection.BUY)
    
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float)
    
    pnl = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    
    status = Column(SQLEnum(PositionStatus), default=PositionStatus.OPEN)
    execution_type = Column(String, default="paper")  # "paper" or "live"
    
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    notes = Column(String, nullable=True)

class Order(Base):
    """Trading order record"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True)
    trade_id = Column(String, nullable=True)
    
    symbol = Column(String, default="XAUUSD")
    order_type = Column(SQLEnum(OrderType), default=OrderType.MARKET)
    direction = Column(SQLEnum(TradeDirection), default=TradeDirection.BUY)
    
    quantity = Column(Float)
    price = Column(Float, nullable=True)
    fill_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, default=0.0)
    
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    broker = Column(String)  # "mt5" or "exness"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    filled_at = Column(DateTime, nullable=True)
    
    commission = Column(Float, default=0.0)
    notes = Column(String, nullable=True)

class Position(Base):
    """Active trading position"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(String, unique=True, index=True)
    
    symbol = Column(String, default="XAUUSD")
    direction = Column(SQLEnum(TradeDirection), default=TradeDirection.BUY)
    quantity = Column(Float)
    
    entry_price = Column(Float)
    current_price = Column(Float)
    
    pnl = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    
    status = Column(SQLEnum(PositionStatus), default=PositionStatus.OPEN)
    
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    max_drawdown = Column(Float, default=0.0)
    max_profit = Column(Float, default=0.0)
    
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

class StrategyMetric(Base):
    """Strategy performance metrics"""
    __tablename__ = "strategy_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    symbol = Column(String, default="XAUUSD")
    
    # Technical indicators
    ema20 = Column(Float)
    ema50 = Column(Float)
    rsi = Column(Float)
    atr = Column(Float)
    
    # Market data
    current_price = Column(Float)
    bid = Column(Float)
    ask = Column(Float)
    
    # Decision
    ai_decision = Column(String)  # "buy", "sell", "hold"
    ai_confidence = Column(Float)
    reason = Column(String, nullable=True)

class BacktestResult(Base):
    """Backtest execution results"""
    __tablename__ = "backtest_results"
    
    id = Column(Integer, primary_key=True, index=True)
    backtest_id = Column(String, unique=True, index=True)
    
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    
    win_rate = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    
    initial_balance = Column(Float, default=10000.0)
    final_balance = Column(Float, default=10000.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)

# ==================== DATABASE INITIALIZATION ====================
def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize tables on import
create_tables()
