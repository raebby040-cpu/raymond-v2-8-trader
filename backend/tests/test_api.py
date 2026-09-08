"""Tests for API endpoints"""
import pytest
from datetime import datetime

class TestHealthEndpoint:
    """Test health check endpoint"""
    
    def test_health_check(self, client):
        """Test /health endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] in ["healthy", "ok"]
        assert "timestamp" in response.json()
    
    def test_live_trading_disabled_by_default(self, client):
        """Test live trading is disabled by default"""
        response = client.get("/health")
        
        assert response.json()["live_trading_enabled"] is False

class TestMarketDataEndpoints:
    """Test market data endpoints"""
    
    def test_get_current_price(self, client):
        """Test /api/market/price endpoint"""
        response = client.get("/api/market/price?symbol=XAUUSD")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "XAUUSD"
        assert "price" in data
        assert "bid" in data
        assert "ask" in data
    
    def test_get_candlesticks(self, client):
        """Test /api/market/candlesticks endpoint"""
        response = client.get("/api/market/candlesticks?symbol=XAUUSD&timeframe=H1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "XAUUSD"
        assert data["timeframe"] == "H1"
        assert "candlesticks" in data
    
    def test_get_indicators(self, client):
        """Test /api/market/indicators endpoint"""
        response = client.get("/api/market/indicators?symbol=XAUUSD")
        
        assert response.status_code == 200
        data = response.json()
        assert "indicators" in data
        assert "ema20" in data["indicators"]
        assert "ema50" in data["indicators"]
        assert "rsi" in data["indicators"]
        assert "atr" in data["indicators"]

class TestTradingEndpoints:
    """Test trading endpoints"""
    
    def test_place_order_paper_trading(self, client):
        """Test placing an order in paper trading mode"""
        order_data = {
            "symbol": "XAUUSD",
            "order_type": "market",
            "quantity": 0.5,
            "direction": "buy"
        }
        
        response = client.post("/api/trading/place-order", json=order_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "placed"
        assert data["execution_type"] == "paper"
    
    def test_get_positions(self, client):
        """Test /api/trading/positions endpoint"""
        response = client.get("/api/trading/positions")
        
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        assert "total_positions" in data
    
    def test_close_position(self, client):
        """Test closing a position"""
        response = client.post("/api/trading/close-position", json={"position_id": "POS-001"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "closed"

class TestStrategyEndpoints:
    """Test strategy endpoints"""
    
    def test_get_strategy_decision(self, client):
        """Test /api/strategy/decision endpoint"""
        response = client.get("/api/strategy/decision?symbol=XAUUSD")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "XAUUSD"
        assert "decision" in data
        assert "confidence" in data
        assert "recommended_entry" in data
    
    def test_run_backtest(self, client):
        """Test /api/strategy/backtest endpoint"""
        backtest_config = {
            "strategy_name": "EMA_Crossover",
            "symbol": "XAUUSD",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31"
        }
        
        response = client.post("/api/strategy/backtest", json=backtest_config)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "total_trades" in data
        assert "win_rate" in data

class TestJournalEndpoints:
    """Test journal endpoints"""
    
    def test_get_trade_journal(self, client):
        """Test /api/journal/trades endpoint"""
        response = client.get("/api/journal/trades?limit=50&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert "total" in data

class TestAdminEndpoints:
    """Test admin endpoints"""
    
    def test_admin_status(self, client):
        """Test /api/admin/status endpoint"""
        response = client.get("/api/admin/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "live_trading_enabled" in data
        assert "environment" in data
