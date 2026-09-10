import json

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


async def fake_stream(websocket, provider=None):
    assert provider is not None

    state = await provider()

    await websocket.send_text(
        json.dumps(
            {
                "type": "dashboard_state",
                "data": state,
            }
        )
    )

    await websocket.close()


def connected_state():
    return {
        "market": {
            "symbol": "XAUUSD",
            "bid": 2300.0,
            "ask": 2300.5,
        },
        "account": {
            "equity": 10000.0,
        },
        "positions": [],
        "connection": {
            "status": "connected",
            "healthy": True,
        },
        "emergency_stop": {
            "active": False,
            "trading_allowed": True,
        },
        "live_trading_enabled": False,
    }


def test_dashboard_websocket_route_exists():
    routes = [
        route.path
        for route in main.app.routes
        if hasattr(route, "path")
    ]

    assert "/ws/dashboard" in routes


def test_dashboard_websocket_returns_dashboard_state(
    client,
    monkeypatch,
):
    async def fake_provider():
        return connected_state()

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "stream",
        fake_stream,
    )

    with client.websocket_connect(
        "/ws/dashboard"
    ) as websocket:
        message = websocket.receive_json()

    assert message["type"] == "dashboard_state"
    assert (
        message["data"]["market"]["symbol"]
        == "XAUUSD"
    )
    assert (
        message["data"]["account"]["equity"]
        == 10000.0
    )
    assert message["data"]["positions"] == []


def test_dashboard_websocket_is_read_only(
    client,
    monkeypatch,
):
    async def fake_provider():
        return {
            "market": None,
            "account": None,
            "positions": [],
            "connection": {
                "status": "disconnected",
                "healthy": False,
            },
            "emergency_stop": {
                "active": True,
                "trading_allowed": False,
            },
            "live_trading_enabled": False,
        }

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "stream",
        fake_stream,
    )

    with client.websocket_connect(
        "/ws/dashboard"
    ) as websocket:
        message = websocket.receive_json()

    assert (
        message["data"]["live_trading_enabled"]
        is False
    )
    assert (
        message["data"]["emergency_stop"][
            "trading_allowed"
        ]
        is False
    )


def test_dashboard_websocket_never_enables_live_trading(
    client,
    monkeypatch,
):
    async def fake_provider():
        return connected_state()

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "stream",
        fake_stream,
    )

    with client.websocket_connect(
        "/ws/dashboard"
    ) as websocket:
        message = websocket.receive_json()

    assert (
        message["data"]["live_trading_enabled"]
        is False
    )


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
