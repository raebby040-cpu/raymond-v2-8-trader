"""Market data handlers for real-time XAUUSD data"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
from enum import Enum

logger = logging.getLogger(__name__)

# ==================== DATA PROVIDERS ====================
class DataProvider(str, Enum):
    """Available data providers"""
    MOCK = "mock"
    ALPHA_VANTAGE = "alpha_vantage"
    TWELVE_DATA = "twelve_data"
    ALPACA = "alpaca"
    POLYGON = "polygon"

class Timeframe(str, Enum):
    """Chart timeframes"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"

# ==================== CANDLESTICK MODEL ====================
class Candlestick:
    """OHLCV candlestick data"""
    
    def __init__(self, timestamp: datetime, open_price: float, high: float, 
                 low: float, close: float, volume: float):
        self.timestamp = timestamp
        self.open = open_price
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "time": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume
        }

# ==================== TICK DATA ====================
class Tick:
    """Real-time tick data (bid/ask)"""
    
    def __init__(self, timestamp: datetime, bid: float, ask: float, bid_volume: float = 0.0, ask_volume: float = 0.0):
        self.timestamp = timestamp
        self.bid = bid
        self.ask = ask
        self.bid_volume = bid_volume
        self.ask_volume = ask_volume
        self.mid_price = (bid + ask) / 2
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "mid_price": self.mid_price,
            "spread": self.ask - self.bid
        }

# ==================== BASE MARKET DATA PROVIDER ====================
class BaseMarketDataProvider:
    """Base class for market data providers"""
    
    def __init__(self, provider_type: DataProvider):
        self.provider_type = provider_type
        self.is_connected = False
        self.last_update = None
        logger.info(f"Initialized {provider_type.value} market data provider")
    
    async def connect(self) -> bool:
        """Connect to data provider"""
        raise NotImplementedError
    
    async def disconnect(self) -> bool:
        """Disconnect from data provider"""
        raise NotImplementedError
    
    async def get_current_tick(self, symbol: str) -> Optional[Tick]:
        """Get current bid/ask tick"""
        raise NotImplementedError
    
    async def get_candlesticks(self, symbol: str, timeframe: Timeframe, limit: int = 100) -> List[Candlestick]:
        """Get historical candlesticks"""
        raise NotImplementedError
    
    async def subscribe_ticks(self, symbol: str, callback):
        """Subscribe to real-time tick updates"""
        raise NotImplementedError

# ==================== MOCK DATA PROVIDER ====================
class MockMarketDataProvider(BaseMarketDataProvider):
    """Mock market data provider for testing"""
    
    def __init__(self):
        super().__init__(DataProvider.MOCK)
        self.current_price = 2050.45
        self.price_change = 0.0
    
    async def connect(self) -> bool:
        """Connect (mock)"""
        self.is_connected = True
        self.last_update = datetime.utcnow()
        logger.info("Mock market data provider connected")
        return True
    
    async def disconnect(self) -> bool:
        """Disconnect (mock)"""
        self.is_connected = False
        logger.info("Mock market data provider disconnected")
        return True
    
    async def get_current_tick(self, symbol: str = "XAUUSD") -> Tick:
        """Get mock current tick"""
        # Simulate slight price movement
        import random
        self.price_change = random.uniform(-0.5, 0.5)
        self.current_price += self.price_change
        
        spread = 0.10  # 0.1 pips
        bid = self.current_price - spread / 2
        ask = self.current_price + spread / 2
        
        return Tick(
            timestamp=datetime.utcnow(),
            bid=bid,
            ask=ask,
            bid_volume=1000000.0,
            ask_volume=1000000.0
        )
    
    async def get_candlesticks(self, symbol: str = "XAUUSD", timeframe: Timeframe = Timeframe.H1, 
                               limit: int = 100) -> List[Candlestick]:
        """Generate mock candlesticks"""
        candlesticks = []
        current_time = datetime.utcnow()
        current_price = 2048.00
        
        for i in range(limit, 0, -1):
            timestamp = current_time - timedelta(hours=i)
            
            # Random walk price movement
            import random
            change = random.uniform(-5, 5)
            open_price = current_price
            close_price = open_price + change
            high_price = max(open_price, close_price) + abs(random.uniform(0, 2))
            low_price = min(open_price, close_price) - abs(random.uniform(0, 2))
            volume = random.uniform(1000000, 5000000)
            
            candlesticks.append(Candlestick(
                timestamp=timestamp,
                open_price=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume
            ))
            
            current_price = close_price
        
        return candlesticks
    
    async def subscribe_ticks(self, symbol: str, callback):
        """Subscribe to mock tick updates"""
        logger.info(f"Subscribed to mock ticks for {symbol}")
        # In production, this would stream real data
        while self.is_connected:
            tick = await self.get_current_tick(symbol)
            await callback(tick)
            await asyncio.sleep(1)  # Update every second

# ==================== ALPHA VANTAGE PROVIDER ====================
class AlphaVantageMarketDataProvider(BaseMarketDataProvider):
    """Alpha Vantage market data provider"""
    
    def __init__(self, api_key: str):
        super().__init__(DataProvider.ALPHA_VANTAGE)
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
    
    async def connect(self) -> bool:
        """Connect to Alpha Vantage"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.base_url,
                    params={"function": "CURRENCY_EXCHANGE_RATE", "from_currency": "XAU", "to_currency": "USD", "apikey": self.api_key},
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    self.is_connected = True
                    self.last_update = datetime.utcnow()
                    logger.info("Connected to Alpha Vantage")
                    return True
        except Exception as e:
            logger.error(f"Failed to connect to Alpha Vantage: {e}")
        
        return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Alpha Vantage"""
        self.is_connected = False
        return True
    
    async def get_current_tick(self, symbol: str = "XAUUSD") -> Optional[Tick]:
        """Get current tick from Alpha Vantage"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.base_url,
                    params={
                        "function": "CURRENCY_EXCHANGE_RATE",
                        "from_currency": "XAU",
                        "to_currency": "USD",
                        "apikey": self.api_key
                    },
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "Realtime Currency Exchange Rate" in data:
                        rate_data = data["Realtime Currency Exchange Rate"]
                        price = float(rate_data["5. Exchange Rate"])
                        
                        # Mock bid/ask spread
                        spread = 0.10
                        return Tick(
                            timestamp=datetime.utcnow(),
                            bid=price - spread/2,
                            ask=price + spread/2
                        )
        except Exception as e:
            logger.error(f"Failed to get tick from Alpha Vantage: {e}")
        
        return None
    
    async def get_candlesticks(self, symbol: str = "XAUUSD", timeframe: Timeframe = Timeframe.H1, 
                               limit: int = 100) -> List[Candlestick]:
        """Get candlesticks from Alpha Vantage"""
        try:
            import httpx
            
            # Map timeframe to Alpha Vantage function
            function_map = {
                Timeframe.M1: "FX_INTRADAY",
                Timeframe.M5: "FX_INTRADAY",
                Timeframe.M15: "FX_INTRADAY",
                Timeframe.M30: "FX_INTRADAY",
                Timeframe.H1: "FX_INTRADAY",
            }
            
            function = function_map.get(timeframe, "FX_DAILY")
            
            async with httpx.AsyncClient() as client:
                params = {
                    "function": function,
                    "from_symbol": "XAU",
                    "to_symbol": "USD",
                    "interval": timeframe.value if timeframe in function_map else "daily",
                    "outputsize": "full",
                    "apikey": self.api_key
                }
                
                response = await client.get(self.base_url, params=params, timeout=10.0)
                
                if response.status_code == 200:
                    data = response.json()
                    candlesticks = []
                    
                    # Parse response data
                    for key, value in data.items():
                        if key.startswith("Meta") or key == "Information":
                            continue
                        
                        try:
                            candlesticks.append(Candlestick(
                                timestamp=datetime.fromisoformat(key),
                                open_price=float(value.get("1. open", 0)),
                                high=float(value.get("2. high", 0)),
                                low=float(value.get("3. low", 0)),
                                close=float(value.get("4. close", 0)),
                                volume=float(value.get("5. volume", 0))
                            ))
                        except:
                            continue
                    
                    return sorted(candlesticks, key=lambda x: x.timestamp)[-limit:]
        except Exception as e:
            logger.error(f"Failed to get candlesticks from Alpha Vantage: {e}")
        
        return []
    
    async def subscribe_ticks(self, symbol: str, callback):
        """Subscribe to Alpha Vantage tick updates"""
        logger.info(f"Subscribed to Alpha Vantage ticks for {symbol}")
        while self.is_connected:
            tick = await self.get_current_tick(symbol)
            if tick:
                await callback(tick)
            await asyncio.sleep(5)  # API rate limit

# ==================== MARKET DATA MANAGER ====================
class MarketDataManager:
    """Central market data manager"""
    
    def __init__(self, provider_type: DataProvider = DataProvider.MOCK, **kwargs):
        self.provider_type = provider_type
        
        # Initialize appropriate provider
        if provider_type == DataProvider.MOCK:
            self.provider = MockMarketDataProvider()
        elif provider_type == DataProvider.ALPHA_VANTAGE:
            api_key = kwargs.get('api_key', '')
            self.provider = AlphaVantageMarketDataProvider(api_key)
        else:
            # Default to mock if provider not implemented
            logger.warning(f"Provider {provider_type} not implemented, using mock")
            self.provider = MockMarketDataProvider()
        
        self.current_ticks: Dict[str, Tick] = {}
        self.candlestick_cache: Dict[str, List[Candlestick]] = {}
    
    async def connect(self) -> bool:
        """Connect to data provider"""
        return await self.provider.connect()
    
    async def disconnect(self) -> bool:
        """Disconnect from data provider"""
        return await self.provider.disconnect()
    
    async def get_current_price(self, symbol: str = "XAUUSD") -> Dict:
        """Get current price with bid/ask"""
        tick = await self.provider.get_current_tick(symbol)
        if tick:
            self.current_ticks[symbol] = tick
            return {
                "symbol": symbol,
                "price": tick.mid_price,
                "bid": tick.bid,
                "ask": tick.ask,
                "spread": tick.ask - tick.bid,
                "timestamp": tick.timestamp.isoformat()
            }
        
        return {"error": "Failed to get price"}
    
    async def get_candlesticks(self, symbol: str = "XAUUSD", timeframe: Timeframe = Timeframe.H1, 
                               limit: int = 100) -> Dict:
        """Get candlesticks"""
        candlesticks = await self.provider.get_candlesticks(symbol, timeframe, limit)
        self.candlestick_cache[f"{symbol}_{timeframe.value}"] = candlesticks
        
        return {
            "symbol": symbol,
            "timeframe": timeframe.value,
            "candlesticks": [cs.to_dict() for cs in candlesticks],
            "total": len(candlesticks)
        }
    
    def get_cached_tick(self, symbol: str) -> Optional[Tick]:
        """Get cached tick data"""
        return self.current_ticks.get(symbol)
    
    def get_cached_candlesticks(self, symbol: str, timeframe: Timeframe) -> List[Candlestick]:
        """Get cached candlesticks"""
        return self.candlestick_cache.get(f"{symbol}_{timeframe.value}", [])
