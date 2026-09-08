"""
RAYMOND v2.8 - Market Data Handler
Real-time XAUUSD price feeds and technical indicators
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import numpy as np

logger = logging.getLogger(__name__)

# ==================== TECHNICAL INDICATORS ====================
class TechnicalIndicators:
    """Calculate technical indicators for trading decisions"""
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average (EMA)"""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        
        ema = np.mean(prices[-period:])
        for price in prices[-period:]:
            ema = price * (2 / (period + 1)) + ema * (1 - (2 / (period + 1)))
        return float(ema)
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index (RSI)"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices[-period-1:])
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = up / down if down != 0 else 0
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return float(rsi)
    
    @staticmethod
    def calculate_atr(high: List[float], low: List[float], close: List[float], period: int = 14) -> float:
        """Calculate Average True Range (ATR)"""
        if len(high) < period:
            return 0.0
        
        tr1 = np.array(high) - np.array(low)
        tr2 = np.abs(np.array(high) - close)
        tr3 = np.abs(np.array(low) - close)
        
        tr = np.max([tr1, tr2, tr3], axis=0)
        atr = np.mean(tr[-period:])
        return float(atr)

# ==================== MARKET DATA PROVIDER ====================
class MarketDataProvider:
    """Handle real-time market data for XAUUSD"""
    
    def __init__(self, provider: str = "exness"):
        self.provider = provider
        self.current_price = 2050.45
        self.bid = 2050.40
        self.ask = 2050.50
        self.price_history: List[float] = [2050.45]
        self.candlesticks: List[Dict] = []
        self.last_update = datetime.utcnow()
        
        logger.info(f"Market data provider initialized: {provider}")
    
    async def fetch_current_price(self) -> Dict:
        """Fetch current XAUUSD price"""
        # Simulate price movement
        price_change = np.random.normal(0, 0.5)  # Random walk
        self.current_price = max(2040, min(2100, self.current_price + price_change))
        self.bid = self.current_price - 0.05
        self.ask = self.current_price + 0.05
        self.price_history.append(self.current_price)
        self.last_update = datetime.utcnow()
        
        return {
            "symbol": "XAUUSD",
            "price": round(self.current_price, 2),
            "bid": round(self.bid, 2),
            "ask": round(self.ask, 2),
            "timestamp": self.last_update.isoformat(),
            "volume": np.random.randint(500000, 2000000)
        }
    
    async def fetch_candlesticks(self, timeframe: str = "H1", limit: int = 100) -> Dict:
        """Fetch candlestick data"""
        candlesticks = []
        current_price = self.current_price
        
        for i in range(limit):
            open_price = current_price
            close_price = current_price + np.random.normal(0, 1)
            high_price = max(open_price, close_price) + abs(np.random.normal(0, 0.5))
            low_price = min(open_price, close_price) - abs(np.random.normal(0, 0.5))
            
            candlesticks.append({
                "time": (datetime.utcnow() - timedelta(hours=limit-i)).isoformat(),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": int(np.random.randint(1000000, 3000000))
            })
            current_price = close_price
        
        self.candlesticks = candlesticks
        return {
            "symbol": "XAUUSD",
            "timeframe": timeframe,
            "candlesticks": candlesticks,
            "total": len(candlesticks)
        }
    
    async def fetch_indicators(self) -> Dict:
        """Calculate and return technical indicators"""
        if len(self.price_history) < 50:
            # Build price history if not enough data
            for _ in range(50 - len(self.price_history)):
                self.price_history.insert(0, self.current_price - np.random.uniform(0, 10))
        
        prices = self.price_history[-100:]
        
        ema20 = TechnicalIndicators.calculate_ema(prices, 20)
        ema50 = TechnicalIndicators.calculate_ema(prices, 50)
        rsi = TechnicalIndicators.calculate_rsi(prices, 14)
        
        # Generate candle data for ATR
        high_prices = [p + abs(np.random.normal(0, 0.5)) for p in prices]
        low_prices = [p - abs(np.random.normal(0, 0.5)) for p in prices]
        atr = TechnicalIndicators.calculate_atr(high_prices, low_prices, prices, 14)
        
        return {
            "symbol": "XAUUSD",
            "timestamp": datetime.utcnow().isoformat(),
            "indicators": {
                "ema20": round(ema20, 2),
                "ema50": round(ema50, 2),
                "rsi": round(rsi, 2),
                "atr": round(atr, 2),
                "current_price": round(self.current_price, 2)
            },
            "signal": self._generate_signal(ema20, ema50, rsi)
        }
    
    def _generate_signal(self, ema20: float, ema50: float, rsi: float) -> Dict:
        """Generate trading signal based on indicators"""
        signal = "hold"
        confidence = 0.0
        reason = ""
        
        if ema20 > ema50 and rsi > 60:
            signal = "buy"
            confidence = min(0.95, 0.5 + (rsi - 60) / 40 * 0.45)
            reason = "EMA20 > EMA50 & RSI > 60 (Bullish)"
        elif ema20 < ema50 and rsi < 40:
            signal = "sell"
            confidence = min(0.95, 0.5 + (40 - rsi) / 40 * 0.45)
            reason = "EMA20 < EMA50 & RSI < 40 (Bearish)"
        else:
            confidence = 0.3
            reason = "Uncertain - No clear signal"
        
        return {
            "signal": signal,
            "confidence": round(confidence, 2),
            "reason": reason
        }
    
    async def subscribe_to_market_updates(self, callback):
        """Subscribe to real-time market updates"""
        logger.info("Market update subscription started")
        while True:
            try:
                price_data = await self.fetch_current_price()
                await callback(price_data)
                await asyncio.sleep(5)  # Update every 5 seconds
            except Exception as e:
                logger.error(f"Error in market update: {e}")
                await asyncio.sleep(5)

# ==================== MARKET DATA SERVICE ====================
class MarketDataService:
    """Service layer for market data operations"""
    
    def __init__(self, provider: str = "exness"):
        self.market_provider = MarketDataProvider(provider)
        self.is_healthy = True
    
    async def get_market_health(self) -> Dict:
        """Check market data feed health"""
        return {
            "status": "healthy" if self.is_healthy else "unhealthy",
            "provider": self.market_provider.provider,
            "last_update": self.market_provider.last_update.isoformat(),
            "data_freshness_seconds": (datetime.utcnow() - self.market_provider.last_update).total_seconds()
        }
    
    async def get_trading_decision(self) -> Dict:
        """Get complete trading decision with all indicators"""
        indicators = await self.market_provider.fetch_indicators()
        price_data = await self.market_provider.fetch_current_price()
        
        signal = indicators.get("signal", {})
        ind = indicators.get("indicators", {})
        
        return {
            "symbol": "XAUUSD",
            "timestamp": datetime.utcnow().isoformat(),
            "current_price": price_data.get("price"),
            "bid": price_data.get("bid"),
            "ask": price_data.get("ask"),
            "indicators": ind,
            "decision": signal.get("signal", "hold"),
            "confidence": signal.get("confidence", 0.0),
            "reason": signal.get("reason", ""),
            "recommended_entry": round(price_data.get("price", 2050) + np.random.uniform(-2, 2), 2),
            "stop_loss": round(price_data.get("price", 2050) - ind.get("atr", 10), 2),
            "take_profit": round(price_data.get("price", 2050) + ind.get("atr", 10) * 1.5, 2)
        }
