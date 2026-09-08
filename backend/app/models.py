"""SQLAlchemy database models for RAYMOND trading system"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.database import Base
import logging

logger = logging.getLogger(__name__)

# ==================== ENUMS ====================
class TradeStatus(str, PyEnum):
    """Trade status enumeration"""
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"

class OrderType(str, PyEnum):
    """Order type enumeration"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderDirection(str, PyEnum):
    """Order direction enumeration"""
    BUY = "buy"
    SELL = "sell"

class RiskLevel(str, PyEnum):
    """Risk level enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# ==================== MODELS ====================
class Trade(Base):
    """Trade record model"""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(String(50), unique=True, index=True, nullable=False)
    symbol = Column(String(20), index=True, nullable=False)  # XAUUSD, etc.
    direction = Column(Enum(OrderDirection), nullable=False)  # BUY/SELL
    order_type = Column(Enum(OrderType), nullable=False)
    
    # Price information
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    
    # Risk management
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    # Status
    status = Column(Enum(TradeStatus), default=TradeStatus.OPEN, index=True)
    
    # P&L
    pnl = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    
    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)
    
    # Metadata
    broker = Column(String(20), nullable=False)  # mt5, exness, paper
    strategy_decision = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relationships
    risk_events = relationship("RiskEvent", back_populates="trade")
    
    def calculate_pnl(self):
        """Calculate P&L if trade is closed"""
        if self.exit_price and self.entry_price:
            if self.direction == OrderDirection.BUY:
                self.pnl = (self.exit_price - self.entry_price) * self.quantity
            else:  # SELL
                self.pnl = (self.entry_price - self.exit_price) * self.quantity
            
            self.pnl_percent = (self.pnl / (self.entry_price * self.quantity)) * 100

class Position(Base):
    """Open position record"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(String(50), unique=True, index=True, nullable=False)
    trade_id = Column(String(50), nullable=False)  # Reference to Trade
    symbol = Column(String(20), index=True, nullable=False)
    direction = Column(Enum(OrderDirection), nullable=False)
    
    # Position details
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    
    # Risk
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    # Current metrics
    unrealized_pnl = Column(Float, default=0.0)
    unrealized_pnl_percent = Column(Float, default=0.0)
    
    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Metadata
    broker = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    
    def update_current_price(self, new_price: float):
        """Update current price and recalculate P&L"""
        self.current_price = new_price
        self.last_updated = datetime.utcnow()
        
        if self.direction == OrderDirection.BUY:
            self.unrealized_pnl = (new_price - self.entry_price) * self.quantity
        else:  # SELL
            self.unrealized_pnl = (self.entry_price - new_price) * self.quantity
        
        self.unrealized_pnl_percent = (self.unrealized_pnl / (self.entry_price * self.quantity)) * 100

class StrategyDecision(Base):
    """Strategy decision record for audit trail"""
    __tablename__ = "strategy_decisions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    symbol = Column(String(20), index=True, nullable=False)
    
    # Decision
    decision = Column(String(50), nullable=False)  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    confidence = Column(Float, nullable=False)
    
    # Price info
    current_price = Column(Float, nullable=False)
    bid = Column(Float, nullable=False)
    ask = Column(Float, nullable=False)
    
    # Recommendation
    suggested_entry = Column(Float, nullable=True)
    recommended_stop_loss = Column(Float, nullable=True)
    recommended_take_profit = Column(Float, nullable=True)
    risk_reward_ratio = Column(Float, nullable=True)
    
    # Indicators
    ema20 = Column(Float, nullable=True)
    ema50 = Column(Float, nullable=True)
    rsi = Column(Float, nullable=True)
    atr = Column(Float, nullable=True)
    momentum = Column(Float, nullable=True)
    
    # Risk assessment
    risk_level = Column(Enum(RiskLevel), nullable=True)
    
    # Metadata
    executed = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

class RiskEvent(Base):
    """Risk management events (alerts, stops, etc.)"""
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(String(50), ForeignKey("trades.trade_id"), index=True, nullable=True)
    position_id = Column(String(50), nullable=True)
    
    # Event info
    event_type = Column(String(50), nullable=False)  # stale_market, stop_loss_hit, tp_hit, etc.
    severity = Column(Enum(RiskLevel), nullable=False)
    
    # Details
    message = Column(Text, nullable=False)
    action_taken = Column(String(100), nullable=True)
    
    # Timestamps
    occurred_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # Metadata
    resolved = Column(Boolean, default=False)
    
    # Relationship
    trade = relationship("Trade", back_populates="risk_events")

class Journal(Base):
    """Trading journal for notes and analysis"""
    __tablename__ = "journal"

    id = Column(Integer, primary_key=True, index=True)
    journal_id = Column(String(50), unique=True, index=True, nullable=False)
    
    # Association
    trade_id = Column(String(50), nullable=True, index=True)
    
    # Content
    entry_date = Column(DateTime, default=datetime.utcnow, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    
    # Categories
    category = Column(String(50), nullable=True)  # trade_analysis, risk_review, market_review, etc.
    tags = Column(String(200), nullable=True)  # comma-separated tags
    
    # Metadata
    is_private = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Account(Base):
    """Account information and balance tracking"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(50), unique=True, index=True, nullable=False)
    
    # Account info
    broker = Column(String(20), nullable=False)
    account_type = Column(String(20), nullable=False)  # demo, live, paper
    currency = Column(String(10), default="USD")
    
    # Balance
    initial_balance = Column(Float, nullable=False)
    current_balance = Column(Float, nullable=False)
    equity = Column(Float, nullable=False)
    margin_used = Column(Float, default=0.0)
    margin_available = Column(Float, nullable=False)
    
    # Performance
    total_pnl = Column(Float, default=0.0)
    total_pnl_percent = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    
    # Counters
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Status
    is_active = Column(Boolean, default=True, index=True)

class Backtest(Base):
    """Backtest result records"""
    __tablename__ = "backtests"

    id = Column(Integer, primary_key=True, index=True)
    backtest_id = Column(String(50), unique=True, index=True, nullable=False)
    
    # Config
    strategy_name = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    initial_balance = Column(Float, nullable=False)
    
    # Results
    final_balance = Column(Float, nullable=False)
    total_pnl = Column(Float, nullable=False)
    total_pnl_percent = Column(Float, nullable=False)
    
    # Statistics
    total_trades = Column(Integer, nullable=False)
    winning_trades = Column(Integer, nullable=False)
    losing_trades = Column(Integer, nullable=False)
    win_rate = Column(Float, nullable=False)
    
    # Risk metrics
    max_drawdown = Column(Float, nullable=False)
    sharpe_ratio = Column(Float, nullable=True)
    sortino_ratio = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Metadata
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    notes = Column(Text, nullable=True)
