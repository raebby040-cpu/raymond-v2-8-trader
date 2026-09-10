from __future__ import annotations

from typing import Any


class DashboardStateError(ValueError):
    """Raised when dashboard state is unsafe or malformed."""


def safe_dashboard_state() -> dict[str, Any]:
    """
    Return the safest possible dashboard state.

    This state contains no trading permission and no live-trading
    activation. It is used when dashboard data cannot be trusted.
    """

    return {
        "market": None,
        "account": None,
        "positions": [],
        "connection": {
            "status": "unknown",
            "healthy": False,
            "account_login": None,
            "server": None,
            "trade_allowed": False,
            "tradeapi_disabled": None,
            "last_error": None,
        },
        "emergency_stop": {
            "active": True,
            "trading_allowed": False,
            "connection_healthy": False,
            "connection_stale": True,
            "reason": "Dashboard safety state unavailable.",
            "last_heartbeat": None,
        },
        "live_trading_enabled": False,
    }


def normalize_dashboard_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize a dashboard snapshot into a stable read-only schema.

    Safety is fail-closed:
    unhealthy, stale, or emergency-stop states cannot expose
    trading permission.
    """

    if not isinstance(state, dict):
        raise DashboardStateError(
            "Dashboard state must be a dictionary."
        )

    positions = state.get("positions", [])

    if not isinstance(positions, list):
        raise DashboardStateError(
            "Dashboard positions must be a list."
        )

    connection = state.get("connection", {})

    if not isinstance(connection, dict):
        raise DashboardStateError(
            "Dashboard connection must be an object."
        )

    emergency_stop = state.get(
        "emergency_stop",
        {},
    )

    if not isinstance(emergency_stop, dict):
        raise DashboardStateError(
            "Dashboard emergency_stop must be an object."
        )

    normalized = {
        "market": state.get("market"),
        "account": state.get("account"),
        "positions": positions,
        "connection": {
            "status": connection.get(
                "status",
                "unknown",
            ),
            "healthy": bool(
                connection.get(
                    "healthy",
                    False,
                )
            ),
            "account_login": connection.get(
                "account_login"
            ),
            "server": connection.get(
                "server"
            ),
            "trade_allowed": connection.get(
                "trade_allowed"
            ),
            "tradeapi_disabled": connection.get(
                "tradeapi_disabled"
            ),
            "last_error": connection.get(
                "last_error"
            ),
        },
        "emergency_stop": {
            "active": bool(
                emergency_stop.get(
                    "active",
                    False,
                )
            ),
            "trading_allowed": bool(
                emergency_stop.get(
                    "trading_allowed",
                    False,
                )
            ),
            "connection_healthy": bool(
                emergency_stop.get(
                    "connection_healthy",
                    False,
                )
            ),
            "connection_stale": bool(
                emergency_stop.get(
                    "connection_stale",
                    False,
                )
            ),
            "reason": emergency_stop.get(
                "reason",
                "Dashboard safety state unavailable.",
            ),
            "last_heartbeat": emergency_stop.get(
                "last_heartbeat"
            ),
        },
        "live_trading_enabled": bool(
            state.get(
                "live_trading_enabled",
                False,
            )
        ),
    }

    connection_healthy = normalized[
        "connection"
    ]["healthy"]

    safety = normalized[
        "emergency_stop"
    ]

    if (
        not connection_healthy
        or safety["active"]
        or safety["connection_stale"]
    ):
        safety["trading_allowed"] = False

    if not safety["connection_healthy"]:
        safety["trading_allowed"] = False

    if safety["connection_stale"]:
        safety["trading_allowed"] = False

    if safety["active"]:
        safety["trading_allowed"] = False

    return normalized
