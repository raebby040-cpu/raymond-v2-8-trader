import pytest
from fastapi.testclient import TestClient
from backend.fastapi_app.main import app

client = TestClient(app)


def test_health_default_live_trading_false():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert data.get("live_trading_enabled") is False


def test_joke_endpoint_returns_joke():
    resp = client.get("/joke")
    assert resp.status_code == 200
    data = resp.json()
    assert "joke" in data
    assert isinstance(data["joke"], dict)
