"""Production API tests for RAYMOND v2.8.

These tests target the current online production entrypoint and preserve the
paper-only / read-only safety contract. They intentionally do not place,
close, or modify real broker orders.
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from online_main import app
from app import online_market_api


client = TestClient(app)


def test_health_endpoint_is_healthy_and_live_trading_is_disabled():
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "raymond-v2-8-trader"
    assert "timestamp" in data
    assert data["live_trading_enabled"] is False


def test_online_status_is_read_only():
    response = client.get("/api/online/status")

    assert response.status_code == 200
    data = response.json()

    assert data["online"] is True
    assert data["market_feed"] is True
    assert data["paper_trading_enabled"] is True
    assert data["demo_trading_enabled"] is True

    assert data["live_trading_enabled"] is False
    assert data["execution_authorized"] is False
    assert data["broker_orders_allowed"] is False

    assert data["trading_permissions"]["market_read"] is True
    assert data["trading_permissions"]["analysis"] is True
    assert data["trading_permissions"]["paper"] is True
    assert data["trading_permissions"]["live"] is False


def test_online_candlesticks_rejects_unsupported_symbol():
    response = client.get(
        "/api/online/candlesticks"
        "?symbol=EURUSD&timeframe=H1&limit=60"
    )

    assert response.status_code == 400

    detail = response.json()["detail"]

    assert "supports XAUUSD only" in detail["error"]


def test_online_candlesticks_rejects_unsupported_timeframe():
    response = client.get(
        "/api/online/candlesticks"
        "?symbol=XAUUSD&timeframe=M2&limit=60"
    )

    assert response.status_code == 400

    detail = response.json()["detail"]

    assert detail["error"] == "Unsupported timeframe"


def test_online_price_is_read_only(monkeypatch):
    async def fake_fetch_chart(symbol, timeframe, limit):
        return {
            "symbol": "XAUUSD",
            "source_symbol": "XAUUSD=X",
            "timeframe": timeframe,
            "price": 5000.25,
            "candles": [],
            "source": "test feed",
            "source_type": "test",
            "timestamp": "2026-09-13T00:00:00+00:00",
            "market_timestamp": 1234567890,
            "live_trading_allowed": False,
        }

    monkeypatch.setattr(
        online_market_api,
        "_fetch_chart",
        fake_fetch_chart,
    )

    response = client.get("/api/online/price?symbol=XAUUSD")

    assert response.status_code == 200

    data = response.json()

    assert data["symbol"] == "XAUUSD"
    assert data["price"] == 5000.25
    assert data["live_trading_enabled"] is False
    assert data["source_type"] == "test"


def test_online_candlesticks_returns_read_only_market_data(monkeypatch):
    candles = [
        {
            "time": 1234560000 + index * 3600,
            "open": 5000.0 + index,
            "high": 5001.0 + index,
            "low": 4999.0 + index,
            "close": 5000.5 + index,
            "volume": 100.0,
        }
        for index in range(60)
    ]

    async def fake_fetch_chart(symbol, timeframe, limit):
        return {
            "symbol": "XAUUSD",
            "source_symbol": "XAUUSD=X",
            "timeframe": timeframe,
            "price": candles[-1]["close"],
            "candles": candles[-limit:],
            "source": "test feed",
            "source_type": "test",
            "timestamp": "2026-09-13T00:00:00+00:00",
            "market_timestamp": 1234567890,
            "live_trading_allowed": False,
        }

    monkeypatch.setattr(
        online_market_api,
        "_fetch_chart",
        fake_fetch_chart,
    )

    response = client.get(
        "/api/online/candlesticks"
        "?symbol=XAUUSD&timeframe=H1&limit=60"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["symbol"] == "XAUUSD"
    assert data["timeframe"] == "H1"
    assert len(data["candles"]) == 60
    assert data["live_trading_allowed"] is False


def test_online_analysis_returns_wait_when_ai_has_no_trade_signal(
    monkeypatch,
):
    candles = [
        {
            "time": 1234560000 + index * 900,
            "open": 5000.0,
            "high": 5001.0,
            "low": 4999.0,
            "close": 5000.0,
            "volume": 100.0,
        }
        for index in range(60)
    ]

    async def fake_fetch_chart(symbol, timeframe, limit):
        return {
            "symbol": "XAUUSD",
            "source_symbol": "XAUUSD=X",
            "timeframe": timeframe,
            "price": 5000.0,
            "candles": candles,
            "source": "test feed",
            "source_type": "test",
            "timestamp": "2026-09-13T00:00:00+00:00",
            "market_timestamp": 1234567890,
            "live_trading_allowed": False,
        }

    indicators = SimpleNamespace(
        symbol="XAUUSD",
        timeframe="M15",
        close=5000.0,
        ema20=5000.0,
        ema50=5000.0,
        rsi14=50.0,
        atr14=10.0,
        macd=0.0,
        macd_signal=0.0,
        macd_histogram=0.0,
        trend="sideways",
        score=50,
        signal="HOLD",
        candles_used=60,
    )

    decision = SimpleNamespace(
        direction=SimpleNamespace(value="WAIT"),
        confidence=0.0,
        technical_score=50,
        trend="sideways",
        signal="HOLD",
        reasoning="No validated setup.",
        execution_type="paper",
        read_only=True,
        broker_order_required=False,
        risk_engine_required=True,
        proposal=None,
    )

    monkeypatch.setattr(
        online_market_api,
        "_fetch_chart",
        fake_fetch_chart,
    )

    monkeypatch.setattr(
        online_market_api,
        "calculate_indicators",
        lambda **kwargs: indicators,
    )

    monkeypatch.setattr(
        online_market_api._ai,
        "evaluate",
        lambda context: decision,
    )

    monkeypatch.setattr(
        online_market_api,
        "indicator_result_to_dict",
        lambda value: {
            "signal": "HOLD",
            "score": 50,
        },
    )

    response = client.get(
        "/api/online/analysis"
        "?symbol=XAUUSD&timeframe=M15&limit=60"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["accepted"] is True

    assert data["decision"]["direction"] == "WAIT"
    assert data["decision"]["action"] == "HOLD/WAIT"
    assert data["decision"]["execution_type"] == "paper"
    assert data["decision"]["read_only"] is True
    assert data["decision"]["broker_order_required"] is False

    assert data["safety"]["live_trading_enabled"] is False
    assert data["safety"]["execution_authorized"] is False
    assert data["safety"]["broker_order_allowed"] is False
    assert data["safety"]["read_only"] is True
