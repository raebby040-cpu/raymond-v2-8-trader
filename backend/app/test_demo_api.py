"""
RAYMOND v2.8 - Demo Trading API Tests

Step 10A:
- Tests demo API endpoints.
- Confirms paper-only behavior.
- Confirms journal integration.
- Confirms performance reporting.
- Confirms no live execution path exists.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.demo_api import demo_engine, router
from app.models import Base, get_db


@pytest.fixture
def test_app():
    """Create an isolated FastAPI application."""

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        session = SessionLocal()

        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    demo_engine.reset()

    yield app

    demo_engine.reset()


@pytest.fixture
def client(test_app):
    """Create a test client."""

    return TestClient(test_app)


def test_demo_status_is_paper_only(client):
    response = client.get("/status")

    assert response.status_code == 200

    data = response.json()

    assert data["mode"] == "demo"
    assert data["execution_type"] == "paper"
    assert data["live_trading_enabled"] is False
    assert data["real_orders_allowed"] is False


def test_open_demo_trade(client):
    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "buy",
            "entry_price": 2000.0,
            "quantity": 0.1,
            "stop_loss": 1990.0,
            "take_profit": 2020.0,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "opened"
    assert data["mode"] == "demo"
    assert data["execution_type"] == "paper"
    assert data["live_trading_enabled"] is False
    assert data["real_orders_allowed"] is False

    trade = data["trade"]

    assert trade["symbol"] == "XAUUSD"
    assert trade["direction"] == "buy"
    assert trade["entry_price"] == 2000.0
    assert trade["quantity"] == 0.1
    assert trade["status"] == "open"


def test_open_trade_is_written_to_journal(client):
    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "buy",
            "entry_price": 2000.0,
            "quantity": 0.1,
        },
    )

    assert response.status_code == 200

    trade_id = response.json()["trade"]["trade_id"]

    response = client.get("/trades")

    assert response.status_code == 200

    data = response.json()

    assert data["execution_type"] == "paper"
    assert data["count"] == 1
    assert data["trades"][0]["trade_id"] == trade_id


def test_close_demo_trade(client):
    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "buy",
            "entry_price": 2000.0,
            "quantity": 0.1,
        },
    )

    assert response.status_code == 200

    trade_id = response.json()["trade"]["trade_id"]

    response = client.post(
        f"/trades/{trade_id}/close",
        json={
            "exit_price": 2010.0,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "closed"
    assert data["trade"]["status"] == "closed"
    assert data["trade"]["exit_price"] == 2010.0
    assert data["trade"]["pnl"] == 1.0


def test_closed_trade_is_updated_in_journal(client):
    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "buy",
            "entry_price": 2000.0,
            "quantity": 0.1,
        },
    )

    assert response.status_code == 200

    trade_id = response.json()["trade"]["trade_id"]

    response = client.post(
        f"/trades/{trade_id}/close",
        json={
            "exit_price": 2010.0,
        },
    )

    assert response.status_code == 200

    response = client.get("/trades")

    assert response.status_code == 200

    data = response.json()

    assert data["count"] == 1
    assert data["trades"][0]["status"] == "closed"
    assert data["trades"][0]["exit_price"] == 2010.0
    assert data["trades"][0]["pnl"] == 1.0


def test_performance_endpoint(client):
    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "buy",
            "entry_price": 2000.0,
            "quantity": 0.1,
        },
    )

    assert response.status_code == 200

    trade_id = response.json()["trade"]["trade_id"]

    response = client.post(
        f"/trades/{trade_id}/close",
        json={
            "exit_price": 2010.0,
        },
    )

    assert response.status_code == 200

    response = client.get("/performance")

    assert response.status_code == 200

    data = response.json()

    assert data["mode"] == "demo"
    assert data["execution_type"] == "paper"
    assert data["live_trading_enabled"] is False

    performance = data["performance"]

    assert performance["total_trades"] == 1
    assert performance["winning_trades"] == 1
    assert performance["losing_trades"] == 0
    assert performance["total_pnl"] == 1.0
    assert performance["win_rate"] == 100.0


def test_demo_risk_limit_is_enforced(client):
    for index in range(3):
        response = client.post(
            "/trades",
            json={
                "symbol": "XAUUSD",
                "direction": "buy",
                "entry_price": 2000.0 + index,
                "quantity": 0.1,
            },
        )

        assert response.status_code == 200

    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "buy",
            "entry_price": 2100.0,
            "quantity": 0.1,
        },
    )

    assert response.status_code == 400

    data = response.json()

    assert "Demo trading risk limits" in data["detail"]["message"]


def test_invalid_direction_is_rejected(client):
    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "invalid",
            "entry_price": 2000.0,
            "quantity": 0.1,
        },
    )

    assert response.status_code == 400


def test_invalid_price_is_rejected(client):
    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "buy",
            "entry_price": -1.0,
            "quantity": 0.1,
        },
    )

    assert response.status_code == 422


def test_missing_trade_is_rejected(client):
    response = client.post(
        "/trades/missing-trade/close",
        json={
            "exit_price": 2000.0,
        },
    )

    assert response.status_code == 400


def test_reset_endpoint(client):
    response = client.post(
        "/trades",
        json={
            "symbol": "XAUUSD",
            "direction": "buy",
            "entry_price": 2000.0,
            "quantity": 0.1,
        },
    )

    assert response.status_code == 200

    response = client.post("/reset")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "reset"
    assert data["mode"] == "demo"
    assert data["execution_type"] == "paper"
    assert data["live_trading_enabled"] is False
    assert data["real_orders_allowed"] is False


def test_live_execution_is_never_enabled(client):
    response = client.get("/status")

    assert response.status_code == 200

    data = response.json()

    assert data["live_trading_enabled"] is False
    assert data["real_orders_allowed"] is False

    response = client.get("/performance")

    assert response.status_code == 200

    data = response.json()

    assert data["live_trading_enabled"] is False
    assert data["real_orders_allowed"] is False
