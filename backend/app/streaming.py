"""Real-time data streaming service"""
import logging
import asyncio
from typing import Dict, Callable, Optional
from datetime import datetime
from app.market_data import MarketDataManager, DataProvider, Timeframe
from app.indicators import IndicatorStream

logger = logging.getLogger(__name__)

# ==================== MARKET DATA STREAMING SERVICE ====================
class MarketDataStreamingService:
    """Service for streaming real-time market data"""
    
    def __init__(self, provider: DataProvider = DataProvider.MOCK, **kwargs):
        self.manager = MarketDataManager(provider, **kwargs)
        self.streams: Dict[str, IndicatorStream] = {}
        self.subscribers: Dict[str, list] = {}
        self.is_running = False
    
    async def start(self):
        """Start streaming service"""
        try:
            if await self.manager.connect():
                self.is_running = True
                logger.info("Market data streaming service started")
                return True
        except Exception as e:
            logger.error(f"Failed to start streaming service: {e}")
        
        return False
    
    async def stop(self):
        """Stop streaming service"""
        self.is_running = False
        await self.manager.disconnect()
        logger.info("Market data streaming service stopped")
    
    def create_stream(self, symbol: str) -> IndicatorStream:
        """Create indicator stream for symbol"""
        stream = IndicatorStream()
        self.streams[symbol] = stream
        logger.info(f"Created indicator stream for {symbol}")
        return stream
    
    def subscribe(self, symbol: str, callback: Callable):
        """Subscribe to market data updates"""
        if symbol not in self.subscribers:
            self.subscribers[symbol] = []
        
        self.subscribers[symbol].append(callback)
        logger.info(f"Subscriber added for {symbol}")
    
    async def publish(self, symbol: str, data: Dict):
        """Publish data to subscribers"""
        if symbol in self.subscribers:
            for callback in self.subscribers[symbol]:
                try:
                    await callback(data)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")
    
    async def stream_prices(self, symbol: str = "XAUUSD", interval: float = 1.0):
        """Stream real-time prices"""
        while self.is_running:
            try:
                price_data = await self.manager.get_current_price(symbol)
                
                if "error" not in price_data:
                    # Publish to subscribers
                    await self.publish(symbol, {
                        "type": "price",
                        "data": price_data
                    })
                
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error streaming prices: {e}")
                await asyncio.sleep(5)
    
    async def stream_candlesticks(self, symbol: str = "XAUUSD", 
                                   timeframe: Timeframe = Timeframe.H1, 
                                   interval: float = 60.0):
        """Stream candlestick updates"""
        while self.is_running:
            try:
                candlestick_data = await self.manager.get_candlesticks(symbol, timeframe, limit=100)
                
                if "error" not in candlestick_data:
                    # Publish to subscribers
                    await self.publish(symbol, {
                        "type": "candlestick",
                        "timeframe": timeframe.value,
                        "data": candlestick_data
                    })
                    
                    # Update indicator stream
                    if symbol not in self.streams:
                        self.create_stream(symbol)
                    
                    if candlestick_data["candlesticks"]:
                        latest_candle = candlestick_data["candlesticks"][-1]
                        self.streams[symbol].add_candle(
                            open_price=latest_candle["open"],
                            high=latest_candle["high"],
                            low=latest_candle["low"],
                            close=latest_candle["close"],
                            volume=latest_candle["volume"]
                        )
                
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error streaming candlesticks: {e}")
                await asyncio.sleep(5)
    
    async def stream_indicators(self, symbol: str = "XAUUSD", interval: float = 5.0):
        """Stream real-time indicator updates"""
        while self.is_running:
            try:
                if symbol in self.streams:
                    indicators = self.streams[symbol].get_current_indicators()
                    
                    # Publish to subscribers
                    await self.publish(symbol, {
                        "type": "indicators",
                        "data": {
                            "symbol": symbol,
                            "timestamp": datetime.utcnow().isoformat(),
                            "indicators": indicators
                        }
                    })
                
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error streaming indicators: {e}")
                await asyncio.sleep(5)
    
    def get_indicators(self, symbol: str) -> Optional[Dict]:
        """Get latest indicators for symbol"""
        if symbol in self.streams:
            return self.streams[symbol].get_current_indicators()
        return None

# ==================== GLOBAL STREAMING SERVICE INSTANCE ====================
_streaming_service: Optional[MarketDataStreamingService] = None

def get_streaming_service(provider: DataProvider = DataProvider.MOCK, **kwargs) -> MarketDataStreamingService:
    """Get or create global streaming service"""
    global _streaming_service
    
    if _streaming_service is None:
        _streaming_service = MarketDataStreamingService(provider, **kwargs)
    
    return _streaming_service
