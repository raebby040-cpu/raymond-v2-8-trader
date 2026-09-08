"""Technical indicator calculations"""
import logging
from typing import Dict, List, Optional
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)

# ==================== INDICATOR CALCULATOR ====================
class IndicatorCalculator:
    """Calculate technical indicators"""
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
        
        prices_array = np.array(prices[-period:])
        multiplier = 2.0 / (period + 1)
        ema = prices_array[0]
        
        for price in prices_array[1:]:
            ema = price * multiplier + ema * (1 - multiplier)
        
        return float(ema)
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        
        return float(np.mean(prices[-period:]))
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return None
        
        prices_array = np.array(prices)
        deltas = np.diff(prices_array)
        
        # Separate gains and losses
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = up / down if down != 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        # Calculate for remaining prices
        for i in range(period + 1, len(deltas)):
            delta = deltas[i]
            if delta > 0:
                up = (up * (period - 1) + delta) / period
            else:
                down = (down * (period - 1) - delta) / period
            
            rs = up / down if down != 0 else 100
            rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    @staticmethod
    def calculate_atr(high: List[float], low: List[float], close: List[float], 
                      period: int = 14) -> Optional[float]:
        """Calculate Average True Range"""
        if len(high) < period or len(low) < period or len(close) < period:
            return None
        
        tr_values = []
        
        for i in range(1, len(close)):
            high_low = high[i] - low[i]
            high_close = abs(high[i] - close[i-1])
            low_close = abs(low[i] - close[i-1])
            
            tr = max(high_low, high_close, low_close)
            tr_values.append(tr)
        
        atr = np.mean(tr_values[-period:]) if len(tr_values) >= period else np.mean(tr_values)
        return float(atr)
    
    @staticmethod
    def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, 
                       signal: int = 9) -> Optional[Dict]:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if len(prices) < slow:
            return None
        
        ema_fast = IndicatorCalculator.calculate_ema(prices, fast)
        ema_slow = IndicatorCalculator.calculate_ema(prices, slow)
        
        if ema_fast is None or ema_slow is None:
            return None
        
        macd_line = ema_fast - ema_slow
        
        # Calculate signal line (EMA of MACD)
        macd_values = []
        for i in range(slow, len(prices)):
            ema_f = IndicatorCalculator.calculate_ema(prices[:i+1], fast)
            ema_s = IndicatorCalculator.calculate_ema(prices[:i+1], slow)
            if ema_f and ema_s:
                macd_values.append(ema_f - ema_s)
        
        signal_line = IndicatorCalculator.calculate_ema(macd_values, signal) if macd_values else None
        histogram = macd_line - (signal_line or 0) if signal_line else None
        
        return {
            "macd": float(macd_line),
            "signal": float(signal_line) if signal_line else None,
            "histogram": float(histogram) if histogram else None
        }
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, 
                                   std_dev: float = 2.0) -> Optional[Dict]:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return None
        
        sma = IndicatorCalculator.calculate_sma(prices, period)
        if sma is None:
            return None
        
        prices_array = np.array(prices[-period:])
        std = float(np.std(prices_array)) * std_dev
        
        return {
            "middle_band": float(sma),
            "upper_band": float(sma + std),
            "lower_band": float(sma - std),
            "bandwidth": float(2 * std)
        }
    
    @staticmethod
    def calculate_stochastic(high: List[float], low: List[float], close: List[float], 
                            period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> Optional[Dict]:
        """Calculate Stochastic Oscillator"""
        if len(high) < period or len(low) < period or len(close) < period:
            return None
        
        highest_high = max(high[-period:])
        lowest_low = min(low[-period:])
        
        k_percent = 100 * (close[-1] - lowest_low) / (highest_high - lowest_low) if (highest_high - lowest_low) != 0 else 50
        
        return {
            "k_percent": float(k_percent),
            "d_percent": float(k_percent),  # Simplified
            "range": (float(lowest_low), float(highest_high))
        }

# ==================== REAL-TIME INDICATOR STREAM ====================
class IndicatorStream:
    """Real-time indicator calculation stream"""
    
    def __init__(self, max_buffer: int = 1000):
        self.prices = deque(maxlen=max_buffer)
        self.highs = deque(maxlen=max_buffer)
        self.lows = deque(maxlen=max_buffer)
        self.closes = deque(maxlen=max_buffer)
        self.volumes = deque(maxlen=max_buffer)
        self.calculator = IndicatorCalculator()
    
    def add_candle(self, open_price: float, high: float, low: float, close: float, volume: float):
        """Add a new candlestick and update indicators"""
        self.prices.append((open_price + high + low + close) / 4)  # Typical price
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        self.volumes.append(volume)
    
    def get_current_indicators(self) -> Dict:
        """Get all current indicators"""
        if len(self.prices) < 14:
            return {"error": "Insufficient data"}
        
        return {
            "ema20": self.calculator.calculate_ema(list(self.prices), 20),
            "ema50": self.calculator.calculate_ema(list(self.prices), 50),
            "sma20": self.calculator.calculate_sma(list(self.prices), 20),
            "sma50": self.calculator.calculate_sma(list(self.prices), 50),
            "rsi": self.calculator.calculate_rsi(list(self.closes), 14),
            "atr": self.calculator.calculate_atr(list(self.highs), list(self.lows), list(self.closes), 14),
            "macd": self.calculator.calculate_macd(list(self.closes)),
            "bollinger_bands": self.calculator.calculate_bollinger_bands(list(self.closes), 20),
            "stochastic": self.calculator.calculate_stochastic(list(self.highs), list(self.lows), list(self.closes), 14)
        }
