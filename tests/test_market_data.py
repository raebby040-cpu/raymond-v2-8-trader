"""Tests for market data providers"""
import pytest
from app.market_data import (
    MockMarketDataProvider, MarketDataManager,
    DataProvider, Timeframe
)


@pytest.mark.asyncio
class TestMockMarketDataProvider:
    """Test mock market data provider"""
    
    async def test_connect(self, market_data_provider):
        """Test connecting to mock provider"""
        result = await market_data_provider.connect()
        assert result is True
        assert market_data_provider.is_connected is True
    
    async def test_disconnect(self, market_data_provider):
        """Test disconnecting from mock provider"""
        await market_data_provider.connect()
        result = await market_data_provider.disconnect()
        assert result is True
        assert market_data_provider.is_connected is False
    
    async def test_get_current_tick(self, market_data_provider):
        """Test getting current tick"""
        await market_data_provider.connect()
        tick = await market_data_provider.get_current_tick("XAUUSD")
        
        assert tick is not None
        assert tick.bid > 0
        assert tick.ask > tick.bid
        assert tick.mid_price == (tick.bid + tick.ask) / 2
    
    async def test_get_candlesticks(self, market_data_provider):
        """Test getting candlesticks"""
        await market_data_provider.connect()
        candlesticks = await market_data_provider.get_candlesticks(
            "XAUUSD", Timeframe.H1, limit=10
        )
        
        assert len(candlesticks) == 10
        assert all(cs.open > 0 for cs in candlesticks)
        assert all(cs.close > 0 for cs in candlesticks)


@pytest.mark.asyncio
class TestMarketDataManager:
    """Test market data manager"""
    
    async def test_market_data_manager_connect(self):
        """Test market data manager connection"""
        manager = MarketDataManager(DataProvider.MOCK)
        result = await manager.connect()
        assert result is True
    
    async def test_get_current_price(self):
        """Test getting current price"""
        manager = MarketDataManager(DataProvider.MOCK)
        await manager.connect()
        
        price_data = await manager.get_current_price("XAUUSD")
        
        assert "error" not in price_data
        assert price_data["symbol"] == "XAUUSD"
        assert "price" in price_data
        assert "bid" in price_data
        assert "ask" in price_data
        assert "spread" in price_data
    
    async def test_get_candlesticks(self):
        """Test getting candlesticks"""
        manager = MarketDataManager(DataProvider.MOCK)
        await manager.connect()
        
        cs_data = await manager.get_candlesticks(
            "XAUUSD", Timeframe.H1, limit=20
        )
        
        assert "error" not in cs_data
        assert cs_data["symbol"] == "XAUUSD"
        assert cs_data["timeframe"] == "H1"
        assert cs_data["total"] == 20
    
    async def test_get_cached_tick(self):
        """Test getting cached tick"""
        manager = MarketDataManager(DataProvider.MOCK)
        await manager.connect()
        await manager.get_current_price("XAUUSD")
        
        cached = manager.get_cached_tick("XAUUSD")
        assert cached is not None
        assert cached.bid > 0
    
    async def test_get_cached_candlesticks(self):
        """Test getting cached candlesticks"""
        manager = MarketDataManager(DataProvider.MOCK)
        await manager.connect()
        await manager.get_candlesticks("XAUUSD", Timeframe.H1)
        
        cached = manager.get_cached_candlesticks("XAUUSD", Timeframe.H1)
        assert len(cached) > 0
