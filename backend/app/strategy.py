"""
RAYMOND v2.8 - Strategy Engine
AI-driven trading strategy and decision layer with risk management
"""

import logging
from datetime import datetime
from typing import Dict, List
import numpy as np
from enum import Enum

logger = logging.getLogger(__name__)

# ==================== STRATEGY SIGNALS ====================
class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"

class StrategyDecision(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WEAK_BUY = "weak_buy"
    HOLD = "hold"
    WEAK_SELL = "weak_sell"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

# ==================== STRATEGY ENGINE ====================
class StrategyEngine:
    """Core strategy execution engine with multiple indicators"""
    
    def __init__(self):
        self.weights = {
            "ema_crossover": 0.30,
            "rsi": 0.25,
            "atr": 0.20,
            "momentum": 0.15,
            "volume": 0.10
        }
        self.min_confidence = 0.55
        logger.info("Strategy Engine initialized with weighted indicators")
    
    def analyze_ema_crossover(self, ema20: float, ema50: float, price: float) -> Dict:
        """EMA crossover strategy (Golden Cross / Death Cross)"""
        signal_strength = 0.0
        signal = SignalType.HOLD
        
        # Golden Cross: EMA20 > EMA50 (Bullish)
        if ema20 > ema50:
            crossover_strength = min(1.0, (ema20 - ema50) / ema50)
            signal_strength = 0.5 + (crossover_strength * 0.5)
            signal = SignalType.BUY
        
        # Death Cross: EMA20 < EMA50 (Bearish)
        elif ema20 < ema50:
            crossover_strength = min(1.0, (ema50 - ema20) / ema50)
            signal_strength = 0.5 + (crossover_strength * 0.5)
            signal = SignalType.SELL
        
        else:
            signal_strength = 0.3
            signal = SignalType.HOLD
        
        return {
            "signal": signal,
            "strength": signal_strength,
            "ema20": ema20,
            "ema50": ema50,
            "reason": f"EMA20({'>' if ema20 > ema50 else '<'})EMA50 - {abs(ema20-ema50):.2f} spread"
        }
    
    def analyze_rsi(self, rsi: float) -> Dict:
        """RSI overbought/oversold strategy"""
        signal = SignalType.HOLD
        signal_strength = 0.3
        
        # Oversold (RSI < 30) - Potential BUY
        if rsi < 30:
            signal_strength = 0.5 + ((30 - rsi) / 30) * 0.5
            signal = SignalType.BUY
            reason = f"RSI Oversold: {rsi:.2f}"
        
        # Overbought (RSI > 70) - Potential SELL
        elif rsi > 70:
            signal_strength = 0.5 + ((rsi - 70) / 30) * 0.5
            signal = SignalType.SELL
            reason = f"RSI Overbought: {rsi:.2f}"
        
        # Neutral zone
        else:
            signal_strength = 0.4
            signal = SignalType.HOLD
            reason = f"RSI Neutral: {rsi:.2f}"
        
        return {
            "signal": signal,
            "strength": signal_strength,
            "rsi": rsi,
            "reason": reason
        }
    
    def analyze_atr_volatility(self, atr: float, price: float, historical_atr: float = None) -> Dict:
        """ATR-based volatility analysis"""
        if historical_atr is None:
            historical_atr = atr
        
        atr_percent = (atr / price) * 100
        volatility_change = (atr / historical_atr) if historical_atr > 0 else 1.0
        
        signal = SignalType.HOLD
        signal_strength = 0.3
        
        # High volatility with uptrend = BUY opportunity
        if volatility_change > 1.2:
            signal = SignalType.BUY
            signal_strength = min(1.0, volatility_change * 0.4)
            reason = f"High Volatility ({atr_percent:.2f}%) - Breakout possible"
        
        # Low volatility = consolidation (HOLD)
        elif volatility_change < 0.8:
            signal = SignalType.HOLD
            signal_strength = 0.2
            reason = f"Low Volatility ({atr_percent:.2f}%) - Consolidation"
        
        return {
            "signal": signal,
            "strength": signal_strength,
            "atr": atr,
            "atr_percent": atr_percent,
            "reason": reason
        }
    
    def analyze_momentum(self, price_history: List[float]) -> Dict:
        """Momentum analysis based on price acceleration"""
        if len(price_history) < 10:
            return {
                "signal": SignalType.HOLD,
                "strength": 0.3,
                "momentum": 0.0,
                "reason": "Insufficient data"
            }
        
        # Calculate momentum (rate of change)
        recent_prices = price_history[-10:]
        momentum = ((recent_prices[-1] - recent_prices[0]) / recent_prices[0]) * 100
        
        signal = SignalType.HOLD
        signal_strength = 0.3
        
        if momentum > 1.0:  # Positive momentum
            signal = SignalType.BUY
            signal_strength = min(1.0, abs(momentum) / 5.0)
            reason = f"Positive Momentum: +{momentum:.2f}%"
        elif momentum < -1.0:  # Negative momentum
            signal = SignalType.SELL
            signal_strength = min(1.0, abs(momentum) / 5.0)
            reason = f"Negative Momentum: {momentum:.2f}%"
        else:
            reason = f"Neutral Momentum: {momentum:.2f}%"
        
        return {
            "signal": signal,
            "strength": signal_strength,
            "momentum": momentum,
            "reason": reason
        }

# ==================== AI DECISION LAYER ====================
class AIDecisionLayer:
    """AI-powered trading decision making with multi-signal analysis"""
    
    def __init__(self):
        self.strategy = StrategyEngine()
        self.decision_history: List[Dict] = []
        logger.info("AI Decision Layer initialized")
    
    def make_decision(self, market_data: Dict) -> Dict:
        """Make weighted trading decision based on multiple indicators"""
        indicators = market_data.get("indicators", {})
        price = market_data.get("current_price", 2050)
        price_history = market_data.get("price_history", [price])
        
        # Analyze each factor
        ema_analysis = self.strategy.analyze_ema_crossover(
            indicators.get("ema20", price),
            indicators.get("ema50", price),
            price
        )
        
        rsi_analysis = self.strategy.analyze_rsi(indicators.get("rsi", 50))
        atr_analysis = self.strategy.analyze_atr_volatility(indicators.get("atr", 5), price)
        momentum_analysis = self.strategy.analyze_momentum(price_history)
        
        # Calculate weighted score
        signals = [
            (ema_analysis["signal"], ema_analysis["strength"], self.strategy.weights["ema_crossover"]),
            (rsi_analysis["signal"], rsi_analysis["strength"], self.strategy.weights["rsi"]),
            (atr_analysis["signal"], atr_analysis["strength"], self.strategy.weights["atr"]),
            (momentum_analysis["signal"], momentum_analysis["strength"], self.strategy.weights["momentum"]),
        ]
        
        # Convert signals to numeric scores
        buy_score = sum(
            strength * weight 
            for signal, strength, weight in signals 
            if signal == SignalType.BUY
        )
        
        sell_score = sum(
            strength * weight 
            for signal, strength, weight in signals 
            if signal == SignalType.SELL
        )
        
        hold_score = sum(
            strength * weight 
            for signal, strength, weight in signals 
            if signal == SignalType.HOLD
        )
        
        # Normalize scores
        total_score = buy_score + sell_score + hold_score
        if total_score > 0:
            buy_score /= total_score
            sell_score /= total_score
            hold_score /= total_score
        
        # Determine final decision
        final_decision = self._score_to_decision(buy_score, sell_score)
        confidence = max(buy_score, sell_score, hold_score)
        
        decision = {
            "timestamp": datetime.utcnow().isoformat(),
            "final_decision": final_decision,
            "confidence": round(confidence, 3),
            "current_price": price,
            "bid": market_data.get("bid", price),
            "ask": market_data.get("ask", price),
            "analysis": {
                "ema_crossover": ema_analysis,
                "rsi": rsi_analysis,
                "atr_volatility": atr_analysis,
                "momentum": momentum_analysis
            },
            "scores": {
                "buy_score": round(buy_score, 3),
                "sell_score": round(sell_score, 3),
                "hold_score": round(hold_score, 3)
            },
            "recommendation": self._get_recommendation(final_decision, confidence, price, indicators),
            "risk_level": self._assess_risk(indicators.get("atr", 5), price)
        }
        
        self.decision_history.append(decision)
        logger.info(f"Decision made: {final_decision} (Confidence: {confidence:.1%})")
        
        return decision
    
    def _score_to_decision(self, buy_score: float, sell_score: float) -> StrategyDecision:
        """Convert scores to decision level"""
        if buy_score > 0.75:
            return StrategyDecision.STRONG_BUY
        elif buy_score > 0.60:
            return StrategyDecision.BUY
        elif buy_score > 0.50:
            return StrategyDecision.WEAK_BUY
        elif sell_score > 0.75:
            return StrategyDecision.STRONG_SELL
        elif sell_score > 0.60:
            return StrategyDecision.SELL
        elif sell_score > 0.50:
            return StrategyDecision.WEAK_SELL
        else:
            return StrategyDecision.HOLD
    
    def _get_recommendation(self, decision: StrategyDecision, confidence: float, price: float, indicators: Dict) -> Dict:
        """Get actionable trading recommendation"""
        atr = indicators.get("atr", 5)
        
        if decision in [StrategyDecision.STRONG_BUY, StrategyDecision.BUY]:
            return {
                "action": "BUY",
                "suggested_entry": round(price, 2),
                "stop_loss": round(price - (atr * 1.5), 2),
                "take_profit": round(price + (atr * 2.5), 2),
                "risk_reward_ratio": round((atr * 2.5) / (atr * 1.5), 2)
            }
        elif decision in [StrategyDecision.STRONG_SELL, StrategyDecision.SELL]:
            return {
                "action": "SELL",
                "suggested_entry": round(price, 2),
                "stop_loss": round(price + (atr * 1.5), 2),
                "take_profit": round(price - (atr * 2.5), 2),
                "risk_reward_ratio": round((atr * 2.5) / (atr * 1.5), 2)
            }
        else:
            return {
                "action": "HOLD/WAIT",
                "reason": "No clear signal - awaiting confirmation",
                "next_check_seconds": 300
            }
    
    def _assess_risk(self, atr: float, price: float) -> str:
        """Assess current market risk level"""
        atr_percent = (atr / price) * 100
        
        if atr_percent > 2.0:
            return "HIGH"
        elif atr_percent > 1.0:
            return "MEDIUM"
        else:
            return "LOW"
    
    def get_decision_history(self, limit: int = 10) -> List[Dict]:
        """Get recent decision history"""
        return self.decision_history[-limit:]
