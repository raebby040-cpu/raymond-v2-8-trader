"""Tests for backtesting engine"""
import pytest
from datetime import datetime, timedelta
from app.backtest import (
    BacktestEngine, BacktestTrade, PriceBar, BacktestStatus, TimeframeType
)
from app.strategy import AIDecisionLayer


class TestPriceBar:
    """Test PriceBar class"""
    
    def test_price_bar_creation(self):
        """Test creating a price bar"""
        now = datetime.utcnow()
        bar = PriceBar(
            timestamp=now,
            open=2048.0,
            high=2051.0,
            low=2047.0,
            close=2050.0,
            volume=1000000
        )
        
        assert bar.open == 2048.0
        assert bar.close == 2050.0
        assert bar.volume == 1000000
    
    def test_price_bar_to_dict(self):
        """Test converting price bar to dictionary"""
        now = datetime.utcnow()
        bar = PriceBar(now, 2048.0, 2051.0, 2047.0, 2050.0, 1000000)
        bar_dict = bar.to_dict()
        
        assert bar_dict["open"] == 2048.0
        assert bar_dict["close"] == 2050.0
        assert "timestamp" in bar_dict


class TestBacktestTrade:
    """Test BacktestTrade class"""
    
    def test_backtest_trade_creation(self):
        """Test creating a backtest trade"""
        trade = BacktestTrade(
            trade_id="BT-000001",
            symbol="XAUUSD",
            direction="buy",
            entry_price=2050.0,
            quantity=0.5
        )
        
        assert trade.trade_id == "BT-000001"
        assert trade.direction == "buy"
        assert trade.status == "open"
    
    def test_backtest_trade_close_profit(self):
        """Test closing trade at profit"""
        trade = BacktestTrade(
            trade_id="BT-000001",
            symbol="XAUUSD",
            direction="buy",
            entry_price=2050.0,
            quantity=0.5
        )
        now = datetime.utcnow()
        trade.close(exit_price=2055.0, exit_time=now, reason="tp")
        
        assert trade.status == "closed"
        assert trade.pnl == 2.5  # 0.5 * (2055 - 2050)
        assert trade.pnl_percent > 0
    
    def test_backtest_trade_close_loss(self):
        """Test closing trade at loss"""
        trade = BacktestTrade(
            trade_id="BT-000001",
            symbol="XAUUSD",
            direction="buy",
            entry_price=2050.0,
            quantity=0.5
        )
        now = datetime.utcnow()
        trade.close(exit_price=2045.0, exit_time=now, reason="sl")
        
        assert trade.status == "closed"
        assert trade.pnl == -2.5
        assert trade.pnl_percent < 0


class TestBacktestEngine:
    """Test backtesting engine"""
    
    def test_backtest_engine_creation(self, backtest_engine):
        """Test creating backtest engine"""
        assert backtest_engine.symbol == "XAUUSD"
        assert backtest_engine.initial_balance == 10000.0
        assert backtest_engine.status == BacktestStatus.INITIALIZING
    
    def test_load_historical_data(self, backtest_engine, sample_price_bars):
        """Test loading historical data"""
        result = backtest_engine.load_historical_data(sample_price_bars)
        
        assert result["status"] == "loaded"
        assert result["bar_count"] == 100
        assert backtest_engine.start_date is not None
        assert backtest_engine.end_date is not None
    
    def test_calculate_ema(self):
        """Test EMA calculation"""
        prices = [2050.0 + (i * 0.5) for i in range(50)]
        ema = BacktestEngine._calculate_ema(prices, 20)
        
        assert len(ema) == 50
        assert ema[19] > 0  # First EMA value at index 19
        assert ema[-1] > 0  # Last EMA value
    
    def test_calculate_rsi(self):
        """Test RSI calculation"""
        prices = [2050.0 + (i * 0.5) for i in range(50)]
        rsi = BacktestEngine._calculate_rsi(prices, 14)
        
        assert len(rsi) == 50
        assert all(0 <= r <= 100 for r in rsi[14:])  # RSI should be between 0 and 100
    
    def test_calculate_atr(self, sample_price_bars):
        """Test ATR calculation"""
        atr = BacktestEngine._calculate_atr(sample_price_bars, 14)
        
        assert len(atr) == len(sample_price_bars)
        assert all(a >= 0 for a in atr)  # ATR should be non-negative
    
    def test_run_backtest(self, backtest_engine, sample_price_bars):
        """Test running a backtest"""
        backtest_engine.load_historical_data(sample_price_bars)
        
        # Simple strategy: buy on EMA crossover, sell when price drops 1%
        def simple_strategy(market_data):
            return {
                "recommendation": {
                    "action": "BUY" if market_data["indicators"]["ema20"] > market_data["indicators"]["ema50"] else "HOLD"
                }
            }
        
        report = backtest_engine.run_backtest(simple_strategy)
        
        assert report["status"] == BacktestStatus.COMPLETED.value
        assert report["total_trades"] >= 0
        assert report["winning_trades"] >= 0
        assert report["losing_trades"] >= 0
    
    def test_backtest_report_metrics(self, backtest_engine, sample_price_bars):
        """Test backtest report contains all metrics"""
        backtest_engine.load_historical_data(sample_price_bars)
        
        def dummy_strategy(market_data):
            return {"recommendation": {"action": "HOLD"}}
        
        report = backtest_engine.run_backtest(dummy_strategy)
        
        assert "initial_balance" in report
        assert "final_balance" in report
        assert "total_pnl" in report
        assert "win_rate" in report
        assert "max_drawdown" in report
        assert "trades" in report
