"""
RAYMOND v2.8 - Backtest Engine
Historical backtesting with realistic market simulation
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
from enum import Enum

logger = logging.getLogger(__name__)

# ==================== BACKTEST ENUMS ====================
class BacktestStatus(str, Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TimeframeType(str, Enum):
    M1 = "m1"
    M5 = "m5"
    M15 = "m15"
    H1 = "h1"
    D1 = "d1"

# ==================== PRICE BAR ====================
class PriceBar:
    """Single OHLCV price bar"""
    
    def __init__(self, timestamp: datetime, open: float, high: float, low: float, close: float, volume: int):
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.ema20 = close
        self.ema50 = close
        self.rsi = 50.0
        self.atr = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "ema20": self.ema20,
            "ema50": self.ema50,
            "rsi": self.rsi,
            "atr": self.atr
        }

# ==================== BACKTEST TRADE ====================
class BacktestTrade:
    """Trade executed during backtest"""
    
    def __init__(self, trade_id: str, symbol: str, direction: str, entry_price: float, quantity: float):
        self.trade_id = trade_id
        self.symbol = symbol
        self.direction = direction
        self.entry_price = entry_price
        self.quantity = quantity
        self.entry_time: Optional[datetime] = None
        self.exit_price: Optional[float] = None
        self.exit_time: Optional[datetime] = None
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.pnl = 0.0
        self.pnl_percent = 0.0
        self.bars_held = 0
        self.status = "open"
        self.reason_closed = ""
    
    def close(self, exit_price: float, exit_time: datetime, reason: str = ""):
        """Close trade"""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.reason_closed = reason
        
        if self.direction == "buy":
            self.pnl = (exit_price - self.entry_price) * self.quantity
        else:
            self.pnl = (self.entry_price - exit_price) * self.quantity
        
        self.pnl_percent = (self.pnl / (self.entry_price * self.quantity)) * 100
        self.status = "closed"
    
    def to_dict(self) -> Dict:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 2),
            "exit_price": round(self.exit_price, 2) if self.exit_price else None,
            "quantity": self.quantity,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "stop_loss": round(self.stop_loss, 2),
            "take_profit": round(self.take_profit, 2),
            "pnl": round(self.pnl, 2),
            "pnl_percent": round(self.pnl_percent, 2),
            "status": self.status,
            "reason_closed": self.reason_closed
        }

# ==================== BACKTEST ENGINE ====================
class BacktestEngine:
    """Core backtesting engine"""
    
    def __init__(self, symbol: str = "XAUUSD", initial_balance: float = 10000.0):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.equity = initial_balance
        self.status = BacktestStatus.INITIALIZING
        
        self.bars: List[PriceBar] = []
        self.trades: List[BacktestTrade] = []
        self.open_positions: Dict = {}
        self.closed_positions: List = []
        
        self.start_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None
        self.timeframe = TimeframeType.H1
        
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self.max_balance = initial_balance
        
        logger.info(f"Backtest Engine initialized: {symbol} - Balance: ${initial_balance}")
    
    def load_historical_data(self, bars: List[PriceBar]) -> Dict:
        """Load historical price data"""
        if not bars:
            return {"status": "error", "message": "No bars provided"}
        
        self.bars = bars
        self.start_date = bars[0].timestamp
        self.end_date = bars[-1].timestamp
        
        # Calculate indicators
        self._calculate_indicators()
        
        logger.info(f"Loaded {len(bars)} bars from {self.start_date} to {self.end_date}")
        
        return {
            "status": "loaded",
            "bar_count": len(bars),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat()
        }
    
    def _calculate_indicators(self):
        """Calculate EMA, RSI, ATR for all bars"""
        if len(self.bars) < 50:
            logger.warning("Insufficient bars for indicator calculation")
            return
        
        closes = [bar.close for bar in self.bars]
        
        # EMA20 and EMA50
        ema20 = self._calculate_ema(closes, 20)
        ema50 = self._calculate_ema(closes, 50)
        
        # RSI
        rsi = self._calculate_rsi(closes, 14)
        
        # ATR
        atr = self._calculate_atr(self.bars, 14)
        
        # Assign to bars
        for i, bar in enumerate(self.bars):
            if i >= 19:
                bar.ema20 = ema20[i]
            if i >= 49:
                bar.ema50 = ema50[i]
            if i >= 13:
                bar.rsi = rsi[i]
            if i >= 13:
                bar.atr = atr[i]
    
    @staticmethod
    def _calculate_ema(prices: List[float], period: int) -> List[float]:
        """Calculate EMA"""
        ema = [0.0] * len(prices)
        multiplier = 2.0 / (period + 1)
        
        ema[period - 1] = np.mean(prices[:period])
        
        for i in range(period, len(prices)):
            ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
        
        return ema
    
    @staticmethod
    def _calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
        """Calculate RSI"""
        rsi = [50.0] * len(prices)
        deltas = np.diff(prices)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        for i in range(period, len(prices)):
            if avg_loss == 0:
                rsi[i] = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100.0 - (100.0 / (1.0 + rs))
            
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        
        return rsi
    
    @staticmethod
    def _calculate_atr(bars: List[PriceBar], period: int = 14) -> List[float]:
        """Calculate ATR"""
        atr = [0.0] * len(bars)
        tr = []
        
        for i in range(len(bars)):
            if i == 0:
                tr.append(bars[i].high - bars[i].low)
            else:
                tr.append(max(
                    bars[i].high - bars[i].low,
                    abs(bars[i].high - bars[i - 1].close),
                    abs(bars[i].low - bars[i - 1].close)
                ))
            
            if i >= period - 1:
                atr[i] = np.mean(tr[max(0, i - period + 1):i + 1])
        
        return atr
    
    def run_backtest(self, strategy_func) -> Dict:
        """Run backtest with strategy"""
        self.status = BacktestStatus.RUNNING
        self.total_trades = 0
        
        try:
            for i, bar in enumerate(self.bars):
                # Skip bars without indicators
                if bar.ema20 == bar.close or bar.ema50 == bar.close:
                    continue
                
                # Get market data for strategy
                market_data = {
                    "current_price": bar.close,
                    "bid": bar.close - 0.5,  # Simulated bid/ask
                    "ask": bar.close + 0.5,
                    "indicators": {
                        "ema20": bar.ema20,
                        "ema50": bar.ema50,
                        "rsi": bar.rsi,
                        "atr": bar.atr
                    },
                    "price_history": [b.close for b in self.bars[max(0, i - 20):i + 1]],
                    "timestamp": bar.timestamp
                }
                
                # Run strategy
                decision = strategy_func(market_data)
                
                # Execute trades based on decision
                self._execute_decision(decision, bar)
                
                # Update positions
                self._update_positions(bar)
                
                # Update equity
                self.equity = self.current_balance + self._calculate_unrealized_pnl()
            
            self.status = BacktestStatus.COMPLETED
            return self._generate_report()
        
        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            self.status = BacktestStatus.FAILED
            return {"status": "failed", "error": str(e)}
    
    def _execute_decision(self, decision: Dict, bar: PriceBar):
        """Execute trades based on strategy decision"""
        action = decision.get("recommendation", {}).get("action", "HOLD")
        
        if action == "BUY" and len(self.open_positions) == 0:
            self._open_position("buy", bar, decision)
        elif action == "SELL" and len(self.open_positions) == 0:
            self._open_position("sell", bar, decision)
    
    def _open_position(self, direction: str, bar: PriceBar, decision: Dict):
        """Open a new position"""
        quantity = 0.1  # Fixed position size
        trade_id = f"BT-{self.total_trades + 1:06d}"
        
        rec = decision.get("recommendation", {})
        entry = rec.get("suggested_entry", bar.close)
        sl = rec.get("stop_loss", bar.close - bar.atr)
        tp = rec.get("take_profit", bar.close + bar.atr * 2)
        
        trade = BacktestTrade(trade_id, self.symbol, direction, entry, quantity)
        trade.entry_time = bar.timestamp
        trade.stop_loss = sl
        trade.take_profit = tp
        
        self.open_positions[trade_id] = trade
        self.total_trades += 1
        
        logger.info(f"Trade opened: {trade_id} - {direction} @ {entry}")
    
    def _update_positions(self, bar: PriceBar):
        """Update open positions with current bar"""
        closed_trades = []
        
        for trade_id, trade in self.open_positions.items():
            # Check stop loss
            if trade.direction == "buy" and bar.low <= trade.stop_loss:
                trade.close(trade.stop_loss, bar.timestamp, "stop_loss")
                closed_trades.append(trade_id)
            elif trade.direction == "sell" and bar.high >= trade.stop_loss:
                trade.close(trade.stop_loss, bar.timestamp, "stop_loss")
                closed_trades.append(trade_id)
            
            # Check take profit
            elif trade.direction == "buy" and bar.high >= trade.take_profit:
                trade.close(trade.take_profit, bar.timestamp, "take_profit")
                closed_trades.append(trade_id)
            elif trade.direction == "sell" and bar.low <= trade.take_profit:
                trade.close(trade.take_profit, bar.timestamp, "take_profit")
                closed_trades.append(trade_id)
        
        # Move closed trades
        for trade_id in closed_trades:
            trade = self.open_positions.pop(trade_id)
            self.closed_positions.append(trade)
            self.current_balance += trade.pnl
            self.total_pnl += trade.pnl
            
            if trade.pnl > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1
            
            logger.info(f"Trade closed: {trade_id} - P&L: ${trade.pnl:.2f}")
        
        # Update max drawdown
        if self.equity < self.max_balance:
            drawdown = self.max_balance - self.equity
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
        else:
            self.max_balance = self.equity
    
    def _calculate_unrealized_pnl(self) -> float:
        """Calculate unrealized P&L from open positions"""
        unrealized = 0.0
        for trade in self.open_positions.values():
            if trade.direction == "buy":
                unrealized += (self.bars[-1].close - trade.entry_price) * trade.quantity
            else:
                unrealized += (trade.entry_price - self.bars[-1].close) * trade.quantity
        return unrealized
    
    def _generate_report(self) -> Dict:
        """Generate backtest report"""
        total_trades = self.winning_trades + self.losing_trades
        win_rate = (self.winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "status": self.status.value,
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_balance": round(self.initial_balance, 2),
            "final_balance": round(self.current_balance, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_percent": round((self.total_pnl / self.initial_balance) * 100, 2),
            "total_trades": total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(win_rate, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_percent": round((self.max_drawdown / self.initial_balance) * 100, 2),
            "trades": [t.to_dict() for t in self.closed_positions]
        }

# ==================== BACKTEST RUNNER ====================
class BacktestRunner:
    """Run multiple backtests and compare results"""
    
    def __init__(self):
        self.results: List[Dict] = []
    
    def run_strategy_backtest(
        self,
        symbol: str,
        initial_balance: float,
        bars: List[PriceBar],
        strategy_func
    ) -> Dict:
        """Run single strategy backtest"""
        engine = BacktestEngine(symbol, initial_balance)
        engine.load_historical_data(bars)
        result = engine.run_backtest(strategy_func)
        self.results.append(result)
        return result
    
    def get_backtest_summary(self) -> Dict:
        """Get summary of all backtests"""
        if not self.results:
            return {"status": "no_results"}
        
        total_pnl = sum(r.get("total_pnl", 0) for r in self.results)
        avg_win_rate = np.mean([r.get("win_rate", 0) for r in self.results])
        max_dd = max(r.get("max_drawdown", 0) for r in self.results)
        
        return {
            "backtests_run": len(self.results),
            "total_pnl": round(total_pnl, 2),
            "average_win_rate": round(avg_win_rate, 2),
            "max_drawdown": round(max_dd, 2),
            "results": self.results
        }
