"""Tests for API endpoints"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints"""
    
    def test_health_check(self):
        """Test /health endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "live_trading_enabled" in data
    
    def test_root_endpoint(self):
        """Test / root endpoint"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "description" in data
        assert "endpoints" in data


class TestMarketDataEndpoints:
    """Test market data endpoints"""
    
    def test_get_current_price(self):
        """Test /api/market/price endpoint"""
        response = client.get("/api/market/price?symbol=XAUUSD")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "XAUUSD"
        assert "price" in data
        assert "bid" in data
        assert "ask" in data
        assert "timestamp" in data
    
    def test_get_candlesticks(self):
        """Test /api/market/candlesticks endpoint"""
        response = client.get("/api/market/candlesticks?symbol=XAUUSD&timeframe=H1&limit=10")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "XAUUSD"
        assert data["timeframe"] == "H1"
        assert "candlesticks" in data
        assert "total" in data
    
    def test_get_indicators(self):
        """Test /api/market/indicators endpoint"""
        response = client.get("/api/market/indicators?symbol=XAUUSD")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "XAUUSD"
        assert "indicators" in data
        assert "ema20" in data["indicators"]
        assert "ema50" in data["indicators"]
        assert "rsi" in data["indicators"]
        assert "atr" in data["indicators"]


class TestTradingEndpoints:
    """Test trading endpoints"""
    
    def test_place_order(self):
        """Test POST /api/trading/place-order endpoint"""
        order_data = {
            "symbol": "XAUUSD",
            "order_type": "market",
            "direction": "buy",
            "quantity": 0.5
        }
        response = client.post("/api/trading/place-order", json=order_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "order_id" in data
        assert data["status"] == "placed"
        assert data["symbol"] == "XAUUSD"
        assert data["execution_type"] in ["paper", "live"]
    
    def test_get_positions(self):
        """Test GET /api/trading/positions endpoint"""
        response = client.get("/api/trading/positions")
        
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        assert "total_positions" in data
    
    def test_close_position(self):
        """Test POST /api/trading/close-position endpoint"""
        response = client.post("/api/trading/close-position?position_id=POS-001")
        
        assert response.status_code == 200
        data = response.json()
        assert data["position_id"] == "POS-001"
        assert data["status"] == "closed"


class TestStrategyEndpoints:
    """Test strategy endpoints"""
    
    def test_get_strategy_decision(self):
        """Test GET /api/strategy/decision endpoint"""
        response = client.get("/api/strategy/decision?symbol=XAUUSD")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "XAUUSD"
        assert "decision" in data
        assert "confidence" in data
        assert "reason" in data
    
    def test_run_backtest(self):
        """Test POST /api/strategy/backtest endpoint"""
        backtest_config = {
            "symbol": "XAUUSD",
            "start_date": "2026-01-01",
            "end_date": "2026-09-01"
        }
        response = client.post("/api/strategy/backtest", json=backtest_config)
        
        assert response.status_code == 200
        data = response.json()
        assert "backtest_id" in data
        assert data["status"] == "completed"
        assert "total_trades" in data
        assert "win_rate" in data


class TestJournalEndpoints:
    """Test journal endpoints"""
    
    def test_get_trade_journal(self):
        """Test GET /api/journal/trades endpoint"""
        response = client.get("/api/journal/trades?limit=10&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data


class TestAdminEndpoints:
    """Test admin endpoints"""
    
    def test_admin_status(self):
        """Test GET /api/admin/status endpoint"""
        response = client.get("/api/admin/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "live_trading_enabled" in data
        assert "environment" in data
    
    def test_emergency_stop(self):
        """Test POST /api/admin/emergency-stop endpoint"""
        response = client.post("/api/admin/emergency-stop")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "emergency_stop_activated"
        assert data["all_positions_closed"] is True
        assert data["new_orders_blocked"] is True
