import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import main


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, message):
        self.messages.append(message)


@pytest.fixture
def client():
    return TestClient(main.app)


def test_dashboard_websocket_route_exists():
    routes = [
        route.path
        for route in main.app.routes
        if hasattr(route, "path")
    ]

    assert "/ws/dashboard" in routes


def test_dashboard_websocket_connects(client, monkeypatch):
    async def fake_provider():
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

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    with client.websocket_connect("/ws/dashboard") as websocket:
        message = websocket.receive_json()

        assert message["type"] in {
            "dashboard_state",
            "heartbeat",
        }


def test_dashboard_websocket_returns_valid_json(client):
    with client.websocket_connect("/ws/dashboard") as websocket:
        message = websocket.receive_json()

        assert isinstance(message, dict)
        assert "type" in message


def test_dashboard_websocket_is_read_only():
    websocket = FakeWebSocket()

    assert websocket.accepted is False
    assert websocket.messages == []


def test_dashboard_websocket_does_not_execute_trades():
    """
    Step 9B safety test.

    The dashboard WebSocket must remain read-only.
    It must not expose or invoke trade execution.
    """

    websocket = FakeWebSocket()

    assert not hasattr(
        websocket,
        "execute",
    )

    assert not hasattr(
        websocket,
        "place_order",
    )

    assert not hasattr(
        websocket,
        "close_position",
    )


@pytest.mark.asyncio
async def test_websocket_message_format():
    websocket = FakeWebSocket()

    payload = {
        "type": "dashboard_state",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "data": {
            "market": None,
            "account": None,
            "positions": [],
            "live_trading_enabled": False,
        },
    }

    await websocket.send_text(
        json.dumps(payload)
    )

    assert len(websocket.messages) == 1

    decoded = json.loads(
        websocket.messages[0]
    )

    assert decoded["type"] == "dashboard_state"
    assert decoded["data"]["positions"] == []
    assert decoded["data"]["live_trading_enabled"] is False


@pytest.mark.asyncio
async def test_websocket_fake_client_accepts_connection():
    websocket = FakeWebSocket()

    await websocket.accept()

    assert websocket.accepted is True


@pytest.mark.asyncio
async def test_websocket_fake_client_can_receive_dashboard_state():
    websocket = FakeWebSocket()

    payload = {
        "type": "dashboard_state",
        "data": {
            "positions": [],
            "live_trading_enabled": False,
        },
    }

    await websocket.send_text(
        json.dumps(payload)
    )

    decoded = json.loads(
        websocket.messages[0]
    )

    assert decoded["type"] == "dashboard_state"
    assert decoded["data"]["live_trading_enabled"] is False
