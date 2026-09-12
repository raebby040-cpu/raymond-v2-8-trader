import pytest

from dashboard_schema import (
    DashboardStateError,
    normalize_dashboard_state,
    safe_dashboard_state,
)


def test_safe_dashboard_state_is_fail_closed():
    state = safe_dashboard_state()

    assert state["live_trading_enabled"] is False

    assert (
        state["connection"]["healthy"]
        is False
    )

    assert (
        state["emergency_stop"]["active"]
        is True
    )

    assert (
        state["emergency_stop"]["trading_allowed"]
        is False
    )


def test_normalize_connected_safe_state():
    state = normalize_dashboard_state(
        {
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
                "connection_healthy": True,
                "connection_stale": False,
                "reason": (
                    "Trading safety checks passed."
                ),
            },
            "live_trading_enabled": False,
        }
    )

    assert (
        state["market"]["symbol"]
        == "XAUUSD"
    )

    assert (
        state["emergency_stop"][
            "trading_allowed"
        ]
        is True
    )

    assert (
        state["live_trading_enabled"]
        is False
    )


def test_unhealthy_connection_forces_trading_block():
    state = normalize_dashboard_state(
        {
            "market": None,
            "account": None,
            "positions": [],
            "connection": {
                "status": "disconnected",
                "healthy": False,
            },
            "emergency_stop": {
                "active": False,
                "trading_allowed": True,
                "connection_healthy": False,
                "connection_stale": False,
            },
            "live_trading_enabled": False,
        }
    )

    assert (
        state["emergency_stop"][
            "trading_allowed"
        ]
        is False
    )


def test_stale_connection_forces_trading_block():
    state = normalize_dashboard_state(
        {
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
                "connection_healthy": True,
                "connection_stale": True,
            },
            "live_trading_enabled": False,
        }
    )

    assert (
        state["emergency_stop"][
            "trading_allowed"
        ]
        is False
    )


def test_emergency_stop_forces_trading_block():
    state = normalize_dashboard_state(
        {
            "market": None,
            "account": None,
            "positions": [],
            "connection": {
                "status": "connected",
                "healthy": True,
            },
            "emergency_stop": {
                "active": True,
                "trading_allowed": True,
                "connection_healthy": True,
                "connection_stale": False,
            },
            "live_trading_enabled": False,
        }
    )

    assert (
        state["emergency_stop"][
            "trading_allowed"
        ]
        is False
    )


def test_invalid_positions_are_rejected():
    with pytest.raises(
        DashboardStateError
    ):
        normalize_dashboard_state(
            {
                "positions": {},
            }
        )


def test_invalid_connection_is_rejected():
    with pytest.raises(
        DashboardStateError
    ):
        normalize_dashboard_state(
            {
                "connection": [],
            }
        )


def test_invalid_safety_state_is_rejected():
    with pytest.raises(
        DashboardStateError
    ):
        normalize_dashboard_state(
            {
                "emergency_stop": [],
            }
        )


def test_live_trading_defaults_to_false():
    state = normalize_dashboard_state(
        {
            "market": None,
            "account": None,
            "positions": [],
            "connection": {
                "healthy": False,
            },
            "emergency_stop": {
                "active": True,
            },
        }
    )

    assert (
        state["live_trading_enabled"]
        is False
    )
