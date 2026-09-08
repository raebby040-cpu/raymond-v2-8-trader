"""Pydantic schemas for request/response validation"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from enum import Enum

# ==================== ENUMS ====================
class TradeStatusEnum(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"

class OrderTypeEnum(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderDirectionEnum(str, Enum):
    BUY = "buy"
    SELL = "sell"

class RiskLevelEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# ==================== TRADE SCHEMAS ====================
class TradeCreate(BaseModel):
    """Create trade request"""
    symbol: str
    direction: OrderDirectionEnum
    order_type: OrderTypeEnum
    quantity: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    broker: str
    strategy_decision: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None

class TradeUpdate(BaseModel):
    """Update trade request"""
    exit_price: Optional[float] = None
    status: Optional[TradeStatusEnum] = None
    notes: Optional[str] = None

class TradeResponse(BaseModel):
    """Trade response"""
    id: int
    trade_id: str
    symbol: str
    direction: str
    order_type: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    status: str
    pnl: Optional[float]
    pnl_percent: Optional[float]
    opened_at: datetime
    closed_at: Optional[datetime]
    broker: str
    
    class Config:
        from_attributes = True

# ==================== POSITION SCHEMAS ====================
class PositionCreate(BaseModel):
    """Create position request"""
    trade_id: str
    symbol: str
    direction: OrderDirectionEnum
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    broker: str

class PositionUpdate(BaseModel):
    """Update position request"""
    current_price: float

class PositionResponse(BaseModel):
    """Position response"""
    id: int
    position_id: str
    trade_id: str
    symbol: str
    direction: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    opened_at: datetime
    is_active: bool
    broker: str
    
    class Config:
        from_attributes = True

# ==================== STRATEGY DECISION SCHEMAS ====================
class StrategyDecisionCreate(BaseModel):
    """Create strategy decision request"""
    symbol: str
    decision: str
    confidence: float
    current_price: float
    bid: float
    ask: float
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    rsi: Optional[float] = None
    atr: Optional[float] = None
    momentum: Optional[float] = None
    risk_level: Optional[str] = None

class StrategyDecisionResponse(BaseModel):
    """Strategy decision response"""
    id: int
    timestamp: datetime
    symbol: str
    decision: str
    confidence: float
    current_price: float
    ema20: Optional[float]
    ema50: Optional[float]
    rsi: Optional[float]
    atr: Optional[float]
    risk_level: Optional[str]
    executed: bool
    
    class Config:
        from_attributes = True

# ==================== RISK EVENT SCHEMAS ====================
class RiskEventCreate(BaseModel):
    """Create risk event request"""
    trade_id: Optional[str] = None
    position_id: Optional[str] = None
    event_type: str
    severity: RiskLevelEnum
    message: str
    action_taken: Optional[str] = None

class RiskEventResponse(BaseModel):
    """Risk event response"""
    id: int
    trade_id: Optional[str]
    position_id: Optional[str]
    event_type: str
    severity: str
    message: str
    occurred_at: datetime
    resolved: bool
    
    class Config:
        from_attributes = True

# ==================== JOURNAL SCHEMAS ====================
class JournalCreate(BaseModel):
    """Create journal entry request"""
    trade_id: Optional[str] = None
    title: str
    content: str
    category: Optional[str] = None
    tags: Optional[str] = None
    is_private: bool = False

class JournalResponse(BaseModel):
    """Journal response"""
    id: int
    journal_id: str
    trade_id: Optional[str]
    title: str
    content: str
    category: Optional[str]
    entry_date: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True

# ==================== ACCOUNT SCHEMAS ====================
class AccountResponse(BaseModel):
    """Account response"""
    id: int
    account_id: str
    broker: str
    account_type: str
    currency: str
    current_balance: float
    equity: float
    total_pnl: float
    total_pnl_percent: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    is_active: bool
    
    class Config:
        from_attributes = True

# ==================== BACKTEST SCHEMAS ====================
class BacktestCreate(BaseModel):
    """Create backtest request"""
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_balance: float

class BacktestResponse(BaseModel):
    """Backtest response"""
    id: int
    backtest_id: str
    strategy_name: str
    symbol: str
    final_balance: float
    total_pnl: float
    total_pnl_percent: float
    total_trades: int
    winning_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True
