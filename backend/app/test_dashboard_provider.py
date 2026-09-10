from unittest.mock import AsyncMock

import pytest

from app.dashboard_provider import build_dashboard_state
from app.emergency_stop import EmergencyStopManager


@pytest.mark.asyncio
async def test_dashboard_provider_returns_connected_state():
    mt5_service = AsyncMock()

    mt5_service.heartbeat.return_value = {
        "connected": True,
        "account_login": 123456,
        "server": "TestServer",
        "trade_allowed": True,
        "tradeapi_disabled": False,
        "last_error": None,
    }

    mt5_service.get_account_info.return_value = {
        "login": 123456,
        "server": "TestServer",
        "currency": "USD",
        "balance": 10000.0,
        "equity": 10100.0,
        "profit": 100.0,
        "margin": 500.0,
        "margin_free": 9600.0,
        "margin_level": 2020.0,
    }

    mt5_service.get_symbol_tick.return_value = {
        "symbol": "XAUUSD",
        "bid": 2300.0,
        "ask": 2300.5,
        "last": 2300.25,
        "spread": 0.5,
        "time": 1234567890,
        "time_msc": 1234567890000,
    }

    mt5_service.get_positions.return_value = []

    safety_manager = EmergencyStopManager()

    state = await build_dashboard_state(
        mt5_service=mt5_service,
        safety_manager=safety_manager,
    )

    assert state["connection"]["status"] == "connected"
    assert state["connection"]["healthy"] is True

    assert state["account"]["login"] == 123456
    assert state["account"]["equity"] == 10100.0

    assert state["market"]["symbol"] == "XAUUSD"
    assert state["market"]["bid"] == 2300.0
    assert state["market"]["ask"] == 2300.5

    assert state["positions"] == []
    assert state["live_trading_enabled"] is False

    assert state["emergency_stop"]["connection_healthy"] is True
    assert state["emergency_stop"]["trading_allowed"] is True


@pytest.mark.asyncio
async def test_dashboard_provider_returns_positions():
    mt5_service = AsyncMock()

    mt5_service.heartbeat.return_value = {
        "connected": True,
        "account_login": 123456,
        "server": "TestServer",
        "trade_allowed": True,
        "tradeapi_disabled": False,
        "last_error": None,
    }

    mt5_service.get_account_info.return_value = {
        "login": 123456,
        "server": "TestServer",
        "currency": "USD",
        "balance": 10000.0,
        "equity": 10000.0,
        "profit": 0.0,
        "margin": 0.0,
        "margin_free": 10000.0,
        "margin_level": 0.0,
    }

    mt5_service.get_symbol_tick.return_value = {
        "symbol": "XAUUSD",
        "bid": 2300.0,
        "ask": 2300.5,
        "last": 2300.25,
        "spread": 0.5,
        "time": 1234567890,
        "time_msc": 1234567890000,
    }

    mt5_service.get_positions.return_value = [
        {
            "ticket": 1001,
            "symbol": "XAUUSD",
            "type": 0,
            "volume": 0.10,
            "price_open": 2295.0,
            "price_current": 2300.0,
            "sl": 2285.0,
            "tp": 2315.0,
            "profit": 50.0,
        }
    ]

    safety_manager = EmergencyStopManager()

    state = await build_dashboard_state(
        mt5_service=mt5_service,
        safety_manager=safety_manager,
    )

    assert len(state["positions"]) == 1
    assert state["positions"][0]["ticket"] == 1001
    assert state["positions"][0]["symbol"] == "XAUUSD"
    assert state["positions"][0]["volume"] == 0.10
    assert state["positions"][0]["stop_loss"] == 2285.0
    assert state["positions"][0]["take_profit"] == 2315.0


@pytest.mark.asyncio
async def test_dashboard_provider_marks_connection_lost():
    mt5_service = AsyncMock()

    mt5_service.heartbeat.return_value = {
        "connected": False,
        "account_login": None,
        "server": None,
        "trade_allowed": False,
        "tradeapi_disabled": False,
        "last_error": "MT5 disconnected",
    }

    safety_manager = EmergencyStopManager()

    state = await build_dashboard_state(
        mt5_service=mt5_service,
        safety_manager=safety_manager,
    )

    assert state["connection"]["status"] == "disconnected"
    assert state["connection"]["healthy"] is False

    assert state["account"] is None
    assert state["market"] is None
    assert state["positions"] == []

    assert state["emergency_stop"]["connection_healthy"] is False
    assert state["emergency_stop"]["trading_allowed"] is False

    assert mt5_service.get_account_info.await_count == 0
    assert mt5_service.get_symbol_tick.await_count == 0
    assert mt5_service.get_positions.await_count == 0


@pytest.mark.asyncio
async def test_dashboard_provider_handles_mt5_error():
    mt5_service = AsyncMock()

    mt5_service.heartbeat.side_effect = RuntimeError(
        "MT5 unavailable"
    )

    safety_manager = EmergencyStopManager()

    state = await build_dashboard_state(
        mt5_service=mt5_service,
        safety_manager=safety_manager,
    )

    assert state["connection"]["status"] == "error"
    assert state["connection"]["healthy"] is False
    assert state["connection"]["last_error"] == "MT5 unavailable"

    assert state["account"] is None
    assert state["market"] is None
    assert state["positions"] == []

    assert state["emergency_stop"]["trading_allowed"] is False


@pytest.mark.asyncio
async def test_dashboard_provider_uses_custom_symbol():
    mt5_service = AsyncMock()

    mt5_service.heartbeat.return_value = {
        "connected": True,
        "account_login": 123456,
        "server": "TestServer",
        "trade_allowed": True,
        "tradeapi_disabled": False,
        "last_error": None,
    }

    mt5_service.get_account_info.return_value = {
        "login": 123456,
        "server": "TestServer",
        "currency": "USD",
        "balance": 10000.0,
        "equity": 10000.0,
        "profit": 0.0,
        "margin": 0.0,
        "margin_free": 10000.0,
        "margin_level": 0.0,
    }

    mt5_service.get_symbol_tick.return_value = {
        "symbol": "EURUSD",
        "bid": 1.1000,
        "ask": 1.1002,
        "last": 1.1001,
        "spread": 0.0002,
        "time": 1234567890,
        "time_msc": 1234567890000,
    }

    mt5_service.get_positions.return_value = []

    safety_manager = EmergencyStopManager()

    state = await build_dashboard_state(
        mt5_service=mt5_service,
        safety_manager=safety_manager,
        symbol="EURUSD",
    )

    assert state["market"]["symbol"] == "EURUSD"

    mt5_service.get_symbol_tick.assert_awaited_once_with(
        "EURUSD"
    )


@pytest.mark.asyncio
async def test_dashboard_provider_does_not_enable_live_trading():
    mt5_service = AsyncMock()

    mt5_service.heartbeat.return_value = {
        "connected": True,
    }

    mt5_service.get_account_info.return_value = {}
    mt5_service.get_symbol_tick.return_value = {}
    mt5_service.get_positions.return_value = []

    safety_manager = EmergencyStopManager()

    state = await build_dashboard_state(
        mt5_service=mt5_service,
        safety_manager=safety_manager,
        live_trading_enabled=False,
    )

    assert state["live_trading_enabled"] is False
