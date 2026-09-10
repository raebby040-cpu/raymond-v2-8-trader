import pytest

import main


class FakeWebSocket:
    pass


@pytest.mark.asyncio
async def test_dashboard_websocket_route_exists():
    routes = [
        route.path
        for route in main.app.routes
        if hasattr(route, "path")
    ]

    assert "/ws/dashboard" in routes


@pytest.mark.asyncio
async def test_dashboard_websocket_streams_read_only_state(
    monkeypatch,
):
    websocket = FakeWebSocket()
    captured = {}

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

    async def fake_connect(received_websocket):
        captured["connected_websocket"] = received_websocket

    async def fake_stream(received_websocket, provider=None):
        assert received_websocket is websocket
        assert provider is not None

        captured["state"] = await provider()

    def fake_disconnect(received_websocket):
        captured["disconnected_websocket"] = received_websocket

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "connect",
        fake_connect,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "stream",
        fake_stream,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "disconnect",
        fake_disconnect,
    )

    await main.dashboard_websocket(websocket)

    assert captured["connected_websocket"] is websocket
    assert captured["disconnected_websocket"] is websocket

    assert (
        captured["state"]["market"]["symbol"]
        == "XAUUSD"
    )

    assert (
        captured["state"]["account"]["equity"]
        == 10000.0
    )

    assert captured["state"]["positions"] == []

    assert (
        captured["state"]["live_trading_enabled"]
        is False
    )


@pytest.mark.asyncio
async def test_dashboard_websocket_preserves_safety_state(
    monkeypatch,
):
    websocket = FakeWebSocket()
    captured = {}

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

    async def fake_connect(received_websocket):
        captured["connected"] = received_websocket

    async def fake_stream(received_websocket, provider=None):
        captured["state"] = await provider()

    def fake_disconnect(received_websocket):
        captured["disconnected"] = received_websocket

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "connect",
        fake_connect,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "stream",
        fake_stream,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "disconnect",
        fake_disconnect,
    )

    await main.dashboard_websocket(websocket)

    assert captured["connected"] is websocket
    assert captured["disconnected"] is websocket

    assert (
        captured["state"]["emergency_stop"]["active"]
        is True
    )

    assert (
        captured["state"]["emergency_stop"][
            "trading_allowed"
        ]
        is False
    )

    assert (
        captured["state"]["live_trading_enabled"]
        is False
    )


@pytest.mark.asyncio
async def test_dashboard_websocket_never_enables_live_trading(
    monkeypatch,
):
    websocket = FakeWebSocket()
    captured = {}

    async def fake_provider():
        return {
            "market": None,
            "account": None,
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

    async def fake_connect(received_websocket):
        captured["connected"] = received_websocket

    async def fake_stream(received_websocket, provider=None):
        captured["state"] = await provider()

    def fake_disconnect(received_websocket):
        captured["disconnected"] = received_websocket

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "connect",
        fake_connect,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "stream",
        fake_stream,
    )

    monkeypatch.setattr(
        main.dashboard_ws_manager,
        "disconnect",
        fake_disconnect,
    )

    await main.dashboard_websocket(websocket)

    assert captured["connected"] is websocket
    assert captured["disconnected"] is websocket

    assert (
        captured["state"]["live_trading_enabled"]
        is False
    )


@pytest.mark.asyncio
async def test_health_endpoint_is_available():
    response = await main.health_check()

    assert response["status"] == "healthy"

    assert (
        response["live_trading_enabled"]
        is False
    )
