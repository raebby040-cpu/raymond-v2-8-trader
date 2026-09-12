"""Tests for strategy engine"""
import pytest
from app.strategy import StrategyEngine, AIDecisionLayer, SignalType, StrategyDecision

class TestStrategyEngine:
    """Test strategy engine indicators"""
    
    def setup_method(self):
        """Setup for each test"""
        self.engine = StrategyEngine()
    
    def test_ema_crossover_bullish(self):
        """Test EMA crossover bullish signal"""
        result = self.engine.analyze_ema_crossover(ema20=2050.0, ema50=2048.0, price=2050.0)
        
        assert result["signal"] == SignalType.BUY
        assert result["strength"] > 0.5
        assert "spread" in result["reason"]
    
    def test_ema_crossover_bearish(self):
        """Test EMA crossover bearish signal"""
        result = self.engine.analyze_ema_crossover(ema20=2045.0, ema50=2048.0, price=2045.0)
        
        assert result["signal"] == SignalType.SELL
        assert result["strength"] > 0.5
    
    def test_ema_crossover_hold(self):
        """Test EMA crossover hold signal (equal)"""
        result = self.engine.analyze_ema_crossover(ema20=2048.0, ema50=2048.0, price=2048.0)
        
        assert result["signal"] == SignalType.HOLD
        assert result["strength"] <= 0.5
    
    def test_rsi_oversold(self):
        """Test RSI oversold signal"""
        result = self.engine.analyze_rsi(rsi=25.0)
        
        assert result["signal"] == SignalType.BUY
        assert "Oversold" in result["reason"]
    
    def test_rsi_overbought(self):
        """Test RSI overbought signal"""
        result = self.engine.analyze_rsi(rsi=75.0)
        
        assert result["signal"] == SignalType.SELL
        assert "Overbought" in result["reason"]
    
    def test_rsi_neutral(self):
        """Test RSI neutral signal"""
        result = self.engine.analyze_rsi(rsi=50.0)
        
        assert result["signal"] == SignalType.HOLD
        assert "Neutral" in result["reason"]
    
    def test_atr_high_volatility(self):
        """Test ATR high volatility signal"""
        result = self.engine.analyze_atr_volatility(atr=15.0, price=2050.0, historical_atr=10.0)
        
        assert result["signal"] == SignalType.BUY
        assert "High Volatility" in result["reason"]
    
    def test_atr_low_volatility(self):
        """Test ATR low volatility signal"""
        result = self.engine.analyze_atr_volatility(atr=5.0, price=2050.0, historical_atr=10.0)
        
        assert result["signal"] == SignalType.HOLD
        assert "Low Volatility" in result["reason"]
    
    def test_momentum_positive(self):
        """Test positive momentum signal"""
        price_history = [2040.0, 2041.0, 2042.0, 2043.0, 2044.0, 2045.0, 2046.0, 2047.0, 2048.0, 2050.0]
        result = self.engine.analyze_momentum(price_history)
        
        assert result["signal"] == SignalType.BUY
        assert "Positive Momentum" in result["reason"]
    
    def test_momentum_negative(self):
        """Test negative momentum signal"""
        price_history = [2050.0, 2049.0, 2048.0, 2047.0, 2046.0, 2045.0, 2044.0, 2043.0, 2042.0, 2040.0]
        result = self.engine.analyze_momentum(price_history)
        
        assert result["signal"] == SignalType.SELL
        assert "Negative Momentum" in result["reason"]
    
    def test_momentum_insufficient_data(self):
        """Test momentum with insufficient data"""
        price_history = [2050.0, 2051.0]
        result = self.engine.analyze_momentum(price_history)
        
        assert result["signal"] == SignalType.HOLD
        assert "Insufficient data" in result["reason"]

class TestAIDecisionLayer:
    """Test AI decision layer"""
    
    def setup_method(self):
        """Setup for each test"""
        self.ai = AIDecisionLayer()
    
    def test_strong_buy_decision(self):
        """Test strong buy decision"""
        market_data = {
            "indicators": {
                "ema20": 2051.0,
                "ema50": 2048.0,
                "rsi": 25.0,
                "atr": 15.0
            },
            "current_price": 2050.45,
            "price_history": [2040.0 + i*0.5 for i in range(10)],
            "bid": 2050.40,
            "ask": 2050.50
        }
        
        decision = self.ai.make_decision(market_data)
        
        assert decision["final_decision"] in [StrategyDecision.STRONG_BUY, StrategyDecision.BUY]
        assert decision["confidence"] > 0.55
        assert "recommendation" in decision
        assert "risk_level" in decision
    
    def test_hold_decision(self):
        """Test hold decision"""
        market_data = {
            "indicators": {
                "ema20": 2050.0,
                "ema50": 2050.0,
                "rsi": 50.0,
                "atr": 10.0
            },
            "current_price": 2050.00,
            "price_history": [2050.0] * 10,
            "bid": 2050.00,
            "ask": 2050.10
        }
        
        decision = self.ai.make_decision(market_data)
        
        assert decision["final_decision"] == StrategyDecision.HOLD
        assert decision["confidence"] <= 0.75
    
    def test_decision_history(self):
        """Test decision history tracking"""
        market_data = {
            "indicators": {"ema20": 2051.0, "ema50": 2048.0, "rsi": 65.5, "atr": 12.35},
            "current_price": 2050.45,
            "price_history": [2050.0] * 10,
            "bid": 2050.40,
            "ask": 2050.50
        }
        
        # Make multiple decisions
        for _ in range(5):
            self.ai.make_decision(market_data)
        
        history = self.ai.get_decision_history(limit=10)
        assert len(history) == 5
        assert all("timestamp" in decision for decision in history)
