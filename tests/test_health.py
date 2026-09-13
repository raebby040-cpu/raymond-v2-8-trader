"""Health endpoint tests for RAYMOND v2.8."""

from fastapi.testclient import TestClient

from online_main import app


client = TestClient(app)


def test_health_endpoint_returns_healthy():
    """The production health endpoint must report a healthy service."""
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "raymond-v2-8-trader"
    assert "timestamp" in data


def test_health_endpoint_confirms_live_trading_is_disabled():
    """Health status must confirm that live trading is disabled."""
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["live_trading_enabled"] is False


def test_health_endpoint_does_not_authorize_execution():
    """Health endpoint must never indicate broker execution authorization."""
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["live_trading_enabled"] is False
