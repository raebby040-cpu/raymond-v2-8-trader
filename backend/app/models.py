
from datetime import datetime
import enum

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Enum as SQLEnum,
)

# Support package imports and the existing test setup.
try:
    from .database import Base, engine, SessionLocal, get_db
except ImportError:
    from database import Base, engine, SessionLocal, get_db


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


class Trade(Base):
    __tablename__ = "trades"

    # Nullable for compatibility with historical records.
    # Existing records must not automatically be assigned to a new user.
    owner_user_id = Column(String(36), nullable=True, index=True)

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(String, unique=True, index=True)
    symbol = Column(String, default="XAUUSD")
    direction = Column(
        SQLEnum(TradeDirection),
        default=TradeDirection.BUY,
    )
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float)
    pnl = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    status = Column(
        SQLEnum(PositionStatus),
        default=PositionStatus.OPEN,
    )
    execution_type = Column(String, default="paper")
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    notes = Column(String, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    # Nullable for existing historical records.
    owner_user_id = Column(String(36), nullable=True, index=True)

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True)
    trade_id = Column(String, nullable=True)
    symbol = Column(String, default="XAUUSD")
    order_type = Column(
        SQLEnum(OrderType),
        default=OrderType.MARKET,
    )
    direction = Column(
        SQLEnum(TradeDirection),
        default=TradeDirection.BUY,
    )
    quantity = Column(Float)
    price = Column(Float, nullable=True)
    fill_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, default=0.0)
    status = Column(
        SQLEnum(OrderStatus),
        default=OrderStatus.PENDING,
    )
    broker = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    filled_at = Column(DateTime, nullable=True)
    commission = Column(Float, default=0.0)
    notes = Column(String, nullable=True)


class Position(Base):
    """
    Persistent paper-position state.

    Existing quantity, stop-loss, take-profit, thesis,
    management, and partial-close fields are retained.
    Ownership is nullable for safe historical compatibility.
    """

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)

    position_id = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    # Do not automatically claim historical positions for a new user.
    owner_user_id = Column(
        String(36),
        nullable=True,
        index=True,
    )

    # Paper execution/order linkage.
    trade_id = Column(
        String,
        unique=True,
        index=True,
        nullable=True,
    )

    # Basic position.
    symbol = Column(
        String,
        default="XAUUSD",
        nullable=False,
    )
    direction = Column(
        SQLEnum(TradeDirection),
        default=TradeDirection.BUY,
        nullable=False,
    )
    quantity = Column(Float, nullable=False)

    # Original trade state.
    entry_price = Column(Float, nullable=False)
    original_quantity = Column(Float, nullable=True)
    initial_stop_loss = Column(Float, nullable=True)
    take_profit_1 = Column(Float, nullable=True)
    take_profit_2 = Column(Float, nullable=True)
    risk_1r = Column(Float, nullable=True)

    # Current position state.
    current_price = Column(Float, nullable=True)
    current_stop_loss = Column(Float, nullable=True)
    remaining_quantity = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    pnl = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)

    # Entry thesis.
    regime = Column(String, nullable=True)
    setup = Column(String, nullable=True)
    technical_score = Column(Float, nullable=True)
    confluence = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    trade_thesis = Column(String, nullable=True)

    # Management state.
    break_even_applied = Column(Integer, default=0, nullable=False)
    partial_close_applied = Column(Integer, default=0, nullable=False)

    # Exact partial-close accounting.
    partial_close_price = Column(Float, nullable=True)
    partial_close_quantity = Column(Float, nullable=True)
    partial_close_pnl = Column(Float, nullable=True)

    trailing_active = Column(Integer, default=0, nullable=False)
    management_status = Column(
        String,
        default="open",
        nullable=False,
    )
    last_management_action = Column(String, nullable=True)
    last_management_time = Column(DateTime, nullable=True)

    # Performance tracking.
    max_drawdown = Column(Float, default=0.0)
    max_profit = Column(Float, default=0.0)

    # Lifecycle.
    status = Column(
        SQLEnum(PositionStatus),
        default=PositionStatus.OPEN,
        nullable=False,
    )
    opened_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    closed_at = Column(DateTime, nullable=True)


class StrategyMetric(Base):
    __tablename__ = "strategy_metrics"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(
        DateTime,
        default=datetime.utcnow,
        index=True,
    )
    symbol = Column(String, default="XAUUSD")
    ema20 = Column(Float)
    ema50 = Column(Float)
    rsi = Column(Float)
    atr = Column(Float)
    current_price = Column(Float)
    bid = Column(Float)
    ask = Column(Float)
    ai_decision = Column(String)
    ai_confidence = Column(Float)
    reason = Column(String, nullable=True)


class BacktestResult(Base):
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


def create_tables():
    """
    Create missing tables.

    Existing tables require explicit additive migrations.
    This function does not migrate an existing table's columns.
    """
    Base.metadata.create_all(bind=engine)


create_tables()
