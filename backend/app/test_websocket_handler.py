import asyncio
import json

import pytest

from app.websocket_handler import (
    DashboardWebSocketManager,
    WebSocketHandlerError,
    empty_dashboard_provider,
)


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages = []
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, message: str) -> None:
        if self.closed:
            raise RuntimeError("connection closed")

        self.messages.append(message)


@pytest.mark.asyncio
async def test_connect_accepts_and_registers_websocket():
    manager = DashboardWebSocketManager(
        heartbeat_interval_seconds=1
    )
    websocket = FakeWebSocket()

    await manager.connect(websocket)

    assert websocket.accepted is True
    assert manager.connection_count == 1


def test_disconnect_removes_websocket():
    manager = DashboardWebSocketManager(
        heartbeat_interval_seconds=1
    )
    websocket = FakeWebSocket()

    manager._connections.add(websocket)

    manager.disconnect(websocket)

    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_send_json_sends_serializable_payload():
    manager = DashboardWebSocketManager(
        heartbeat_interval_seconds=1
    )
    websocket = FakeWebSocket()

    await manager.send_json(
        websocket,
        {
            "type": "test",
            "value": 123,
        },
    )

    assert len(websocket.messages) == 1

    payload = json.loads(
        websocket.messages[0]
    )

    assert payload["type"] == "test"
    assert payload["value"] == 123


@pytest.mark.asyncio
async def test_heartbeat_message_contains_required_fields():
    manager = DashboardWebSocketManager(
        heartbeat_interval_seconds=1
    )

    message = await manager.heartbeat_message()

    assert message["type"] == "heartbeat"
    assert "timestamp" in message
    assert "connection_count" in message


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_connections():
    manager = DashboardWebSocketManager(
        heartbeat_interval_seconds=1
    )

    websocket_one = FakeWebSocket()
    websocket_two = FakeWebSocket()

    await manager.connect(websocket_one)
    await manager.connect(websocket_two)

    await manager.broadcast_json(
        {
            "type": "dashboard_state",
            "value": "ok",
        }
    )

    assert len(websocket_one.messages) == 1
    assert len(websocket_two.messages) == 1


@pytest.mark.asyncio
async def test_broken_connection_is_removed():
    manager = DashboardWebSocketManager(
        heartbeat_interval_seconds=1
    )

    healthy = FakeWebSocket()
    broken = FakeWebSocket()
    broken.closed = True

    await manager.connect(healthy)
    await manager.connect(broken)

    await manager.broadcast_json(
        {
            "type": "test",
        }
    )

    assert manager.connection_count == 1
    assert len(healthy.messages) == 1


@pytest.mark.asyncio
async def test_empty_dashboard_provider_is_read_only():
    state = await empty_dashboard_provider()

    assert state["market"] is None
    assert state["account"] is None
    assert state["positions"] == []
    assert state["live_trading_enabled"] is False


def test_invalid_heartbeat_interval_is_rejected():
    with pytest.raises(WebSocketHandlerError):
        DashboardWebSocketManager(
            heartbeat_interval_seconds=0
        )


@pytest.mark.asyncio
async def test_stream_sends_dashboard_state_and_heartbeat():
    manager = DashboardWebSocketManager(
        heartbeat_interval_seconds=0.01
    )

    websocket = FakeWebSocket()

    await manager.connect(websocket)

    async def provider():
        return {
            "market": {
                "symbol": "XAUUSD",
                "price": 2300.0,
            },
            "positions": [],
        }

    task = asyncio.create_task(
        manager.stream(
            websocket,
            provider,
        )
    )

    await asyncio.sleep(0.025)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(websocket.messages) >= 2

    message_types = [
        json.loads(message)["type"]
        for message in websocket.messages
    ]

    assert "dashboard_state" in message_types
    assert "heartbeat" in message_types

    assert manager.connection_count == 0
