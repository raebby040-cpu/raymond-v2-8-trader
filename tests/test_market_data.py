"""Production online market-data endpoint tests for RAYMOND v2.8."""

from fastapi.testclient import TestClient

from online_main import app


client = TestClient(app)


def test_online_status_is_read_only():
    response = client.get("/api/online/status")

    assert response.status_code == 200

    data = response.json()
    assert data["trading"]["live_trading_enabled"] is False
    assert data["trading"]["execution_authorized"] is False
    assert data["trading"]["broker_orders_allowed"] is False
    assert data["trading"]["read_only"] is True


def test_online_price_rejects_unsupported_symbol():
    response = client.get("/api/online/price?symbol=EURUSD")

    assert response.status_code == 400


def test_online_candlesticks_rejects_unsupported_symbol():
    response = client.get(
        "/api/online/candlesticks?symbol=EURUSD&timeframe=H1"
    )

    assert response.status_code == 400


def test_online_candlesticks_rejects_unsupported_timeframe():
    response = client.get(
        "/api/online/candlesticks?symbol=XAUUSD&timeframe=M2"
    )

    assert response.status_code == 400


def test_online_indicators_requires_valid_market_data():
    response = client.get(
        "/api/online/indicators?symbol=EURUSD&timeframe=H1"
    )

    assert response.status_code == 400


def test_online_analysis_is_read_only():
    response = client.get(
        "/api/online/analysis?symbol=EURUSD&timeframe=H1"
    )

    assert response.status_code == 400
