"""Production smoke tests for RAYMOND v2.8."""

from fastapi.testclient import TestClient

from online_main import app


client = TestClient(app)


def test_application_imports():
    """The production entrypoint must import successfully."""
    assert app is not None


def test_health_endpoint_is_available():
    """The production health endpoint must respond successfully."""
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "raymond-v2-8-trader"


def test_live_trading_is_disabled():
    """Smoke test must confirm that live trading remains disabled."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["live_trading_enabled"] is False


def test_health_does_not_authorize_broker_execution():
    """Health status must never authorize real broker execution."""
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["live_trading_enabled"] is False
