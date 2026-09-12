import pytest

from app import main


class FakeDashboardManager:
    def __init__(self):
        self.connected_websocket = None
        self.disconnected_websocket = None
        self.state = None

    async def connect(self, websocket):
        self.connected_websocket = websocket

    async def stream(self, websocket, provider=None):
        assert websocket is self.connected_websocket
        assert provider is not None

        self.state = await provider()

    def disconnect(self, websocket):
        self.disconnected_websocket = websocket


class FakeWebSocket:
    pass


def test_dashboard_websocket_route_exists():
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
    manager = FakeDashboardManager()

    async def fake_provider(**kwargs):
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

    monkeypatch.setattr(
        main,
        "dashboard_ws_manager",
        manager,
    )

    await main.dashboard_websocket(websocket)

    assert manager.connected_websocket is websocket
    assert manager.disconnected_websocket is websocket
    assert manager.state is not None

    assert (
        manager.state["market"]["symbol"]
        == "XAUUSD"
    )

    assert (
        manager.state["account"]["equity"]
        == 10000.0
    )

    assert manager.state["positions"] == []

    assert (
        manager.state["live_trading_enabled"]
        is False
    )


@pytest.mark.asyncio
async def test_dashboard_websocket_preserves_safety_state(
    monkeypatch,
):
    websocket = FakeWebSocket()
    manager = FakeDashboardManager()

    async def fake_provider(**kwargs):
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
        main,
        "dashboard_ws_manager",
        manager,
    )

    await main.dashboard_websocket(websocket)

    assert manager.state is not None

    assert (
        manager.state["emergency_stop"]["active"]
        is True
    )

    assert (
        manager.state["emergency_stop"][
            "trading_allowed"
        ]
        is False
    )

    assert (
        manager.state["live_trading_enabled"]
        is False
    )


@pytest.mark.asyncio
async def test_dashboard_websocket_never_enables_live_trading(
    monkeypatch,
):
    websocket = FakeWebSocket()
    manager = FakeDashboardManager()

    async def fake_provider(**kwargs):
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

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    monkeypatch.setattr(
        main,
        "dashboard_ws_manager",
        manager,
    )

    await main.dashboard_websocket(websocket)

    assert manager.state is not None

    assert (
        manager.state["live_trading_enabled"]
        is False
    )


@pytest.mark.asyncio
async def test_dashboard_websocket_disconnects_safely(
    monkeypatch,
):
    websocket = FakeWebSocket()
    manager = FakeDashboardManager()

    async def fake_provider(**kwargs):
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

    monkeypatch.setattr(
        main,
        "build_dashboard_state",
        fake_provider,
    )

    monkeypatch.setattr(
        main,
        "dashboard_ws_manager",
        manager,
    )

    await main.dashboard_websocket(websocket)

    assert manager.connected_websocket is websocket
    assert manager.disconnected_websocket is websocket
