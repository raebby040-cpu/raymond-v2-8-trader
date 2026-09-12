"""Tests for strategy engine and AI decision layer"""
import pytest
from app.strategy import StrategyEngine, AIDecisionLayer, SignalType, StrategyDecision


class TestStrategyEngine:
    """Test StrategyEngine signal analysis"""
    
    def test_ema_crossover_golden_cross(self, strategy_engine):
        """Test EMA golden cross (bullish) signal"""
        result = strategy_engine.analyze_ema_crossover(
            ema20=2051.0, ema50=2048.0, price=2050.0
        )
        assert result["signal"] == SignalType.BUY
        assert result["strength"] > 0.5
        assert "EMA20" in result["reason"]
    
    def test_ema_crossover_death_cross(self, strategy_engine):
        """Test EMA death cross (bearish) signal"""
        result = strategy_engine.analyze_ema_crossover(
            ema20=2047.0, ema50=2050.0, price=2048.0
        )
        assert result["signal"] == SignalType.SELL
        assert result["strength"] > 0.5
    
    def test_ema_crossover_neutral(self, strategy_engine):
        """Test EMA neutral signal"""
        result = strategy_engine.analyze_ema_crossover(
            ema20=2049.0, ema50=2049.0, price=2049.0
        )
        assert result["signal"] == SignalType.HOLD
        assert result["strength"] < 0.5
    
    def test_rsi_oversold(self, strategy_engine):
        """Test RSI oversold signal (buy)"""
        result = strategy_engine.analyze_rsi(rsi=25.0)
        assert result["signal"] == SignalType.BUY
        assert result["strength"] > 0.5
    
    def test_rsi_overbought(self, strategy_engine):
        """Test RSI overbought signal (sell)"""
        result = strategy_engine.analyze_rsi(rsi=75.0)
        assert result["signal"] == SignalType.SELL
        assert result["strength"] > 0.5
    
    def test_rsi_neutral(self, strategy_engine):
        """Test RSI neutral signal"""
        result = strategy_engine.analyze_rsi(rsi=50.0)
        assert result["signal"] == SignalType.HOLD
        assert result["strength"] < 0.5
    
    def test_atr_high_volatility(self, strategy_engine):
        """Test ATR high volatility signal"""
        result = strategy_engine.analyze_atr_volatility(
            atr=20.0, price=2050.0, historical_atr=15.0
        )
        assert result["signal"] == SignalType.BUY
        assert "Volatility" in result["reason"]
    
    def test_atr_low_volatility(self, strategy_engine):
        """Test ATR low volatility signal"""
        result = strategy_engine.analyze_atr_volatility(
            atr=5.0, price=2050.0, historical_atr=12.0
        )
        assert result["signal"] == SignalType.HOLD
        assert "Consolidation" in result["reason"]
    
    def test_momentum_positive(self, strategy_engine):
        """Test positive momentum signal"""
        price_history = [2040.0 + (i * 0.5) for i in range(10)]  # Uptrend
        result = strategy_engine.analyze_momentum(price_history)
        assert result["signal"] == SignalType.BUY
        assert result["momentum"] > 0
    
    def test_momentum_negative(self, strategy_engine):
        """Test negative momentum signal"""
        price_history = [2050.0 - (i * 0.5) for i in range(10)]  # Downtrend
        result = strategy_engine.analyze_momentum(price_history)
        assert result["signal"] == SignalType.SELL
        assert result["momentum"] < 0
    
    def test_momentum_insufficient_data(self, strategy_engine):
        """Test momentum with insufficient data"""
        result = strategy_engine.analyze_momentum([2050.0, 2051.0])
        assert result["signal"] == SignalType.HOLD
        assert result["momentum"] == 0.0


class TestAIDecisionLayer:
    """Test AI decision layer"""
    
    def test_make_decision_strong_buy(self, ai_decision_layer):
        """Test strong buy decision"""
        market_data = {
            "current_price": 2050.0,
            "bid": 2049.95,
            "ask": 2050.05,
            "indicators": {
                "ema20": 2052.0,  # EMA above 50
                "ema50": 2048.0,  # Golden cross
                "rsi": 25.0,      # Oversold
                "atr": 18.0       # High volatility
            },
            "price_history": [2040.0 + (i * 0.5) for i in range(10)]  # Uptrend
        }
        decision = ai_decision_layer.make_decision(market_data)
        assert decision["final_decision"] in [StrategyDecision.STRONG_BUY, StrategyDecision.BUY]
        assert decision["confidence"] > 0.6
        assert decision["recommendation"]["action"] == "BUY"
    
    def test_make_decision_strong_sell(self, ai_decision_layer):
        """Test strong sell decision"""
        market_data = {
            "current_price": 2050.0,
            "bid": 2049.95,
            "ask": 2050.05,
            "indicators": {
                "ema20": 2048.0,  # EMA below 50
                "ema50": 2052.0,  # Death cross
                "rsi": 75.0,      # Overbought
                "atr": 18.0
            },
            "price_history": [2050.0 - (i * 0.5) for i in range(10)]  # Downtrend
        }
        decision = ai_decision_layer.make_decision(market_data)
        assert decision["final_decision"] in [StrategyDecision.STRONG_SELL, StrategyDecision.SELL]
        assert decision["recommendation"]["action"] == "SELL"
    
    def test_make_decision_hold(self, ai_decision_layer):
        """Test hold decision"""
        market_data = {
            "current_price": 2050.0,
            "bid": 2049.95,
            "ask": 2050.05,
            "indicators": {
                "ema20": 2050.0,  # Neutral
                "ema50": 2050.0,  # Neutral
                "rsi": 50.0,      # Neutral
                "atr": 10.0       # Low volatility
            },
            "price_history": [2050.0] * 10  # Flat
        }
        decision = ai_decision_layer.make_decision(market_data)
        assert decision["final_decision"] == StrategyDecision.HOLD
        assert decision["recommendation"]["action"] == "HOLD/WAIT"
    
    def test_decision_confidence_threshold(self, ai_decision_layer):
        """Test that confidence is normalized"""
        market_data = {
            "current_price": 2050.0,
            "bid": 2049.95,
            "ask": 2050.05,
            "indicators": {
                "ema20": 2051.0,
                "ema50": 2048.0,
                "rsi": 60.0,
                "atr": 12.0
            },
            "price_history": [2050.0 + (i * 0.1) for i in range(10)]
        }
        decision = ai_decision_layer.make_decision(market_data)
        assert 0.0 <= decision["confidence"] <= 1.0
    
    def test_recommendation_includes_levels(self, ai_decision_layer):
        """Test that recommendation includes SL and TP"""
        market_data = {
            "current_price": 2050.0,
            "bid": 2049.95,
            "ask": 2050.05,
            "indicators": {
                "ema20": 2052.0,
                "ema50": 2048.0,
                "rsi": 25.0,
                "atr": 10.0
            },
            "price_history": [2045.0 + (i * 0.5) for i in range(10)]
        }
        decision = ai_decision_layer.make_decision(market_data)
        rec = decision["recommendation"]
        if rec["action"] in ["BUY", "SELL"]:
            assert "suggested_entry" in rec
            assert "stop_loss" in rec
            assert "take_profit" in rec
            assert rec["stop_loss"] < rec["take_profit"]
    
    def test_decision_history_tracking(self, ai_decision_layer):
        """Test that decisions are tracked in history"""
        market_data = {
            "current_price": 2050.0,
            "bid": 2049.95,
            "ask": 2050.05,
            "indicators": {"ema20": 2051.0, "ema50": 2048.0, "rsi": 50.0, "atr": 10.0},
            "price_history": [2050.0] * 10
        }
        ai_decision_layer.make_decision(market_data)
        ai_decision_layer.make_decision(market_data)
        ai_decision_layer.make_decision(market_data)
        
        history = ai_decision_layer.get_decision_history(limit=10)
        assert len(history) == 3
