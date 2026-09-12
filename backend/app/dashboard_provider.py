from __future__ import annotations

from typing import Any

try:
    from .emergency_stop import EmergencyStopManager
    from .mt5_service import MT5Service, MT5ServiceError
except ImportError:
    from emergency_stop import EmergencyStopManager
    from mt5_service import MT5Service, MT5ServiceError


async def build_dashboard_state(
    *,
    mt5_service: MT5Service,
    safety_manager: EmergencyStopManager,
    symbol: str = "XAUUSD",
    live_trading_enabled: bool = False,
) -> dict[str, Any]:
    """
    Build a read-only dashboard snapshot.

    This function never places, modifies, or closes trades.
    """

    state: dict[str, Any] = {
        "market": None,
        "account": None,
        "positions": [],
        "connection": {
            "status": "disconnected",
            "healthy": False,
        },
        "emergency_stop": {
            "active": safety_manager.status().emergency_stop_active,
            "trading_allowed": safety_manager.can_trade(),
            "reason": safety_manager.status().reason,
        },
        "live_trading_enabled": bool(live_trading_enabled),
    }

    try:
        heartbeat = await mt5_service.heartbeat()
        connected = bool(heartbeat.get("connected", False))

        state["connection"] = {
            "status": "connected" if connected else "disconnected",
            "healthy": connected,
            "account_login": heartbeat.get("account_login"),
            "server": heartbeat.get("server"),
            "trade_allowed": heartbeat.get("trade_allowed"),
            "tradeapi_disabled": heartbeat.get("tradeapi_disabled"),
            "last_error": heartbeat.get("last_error"),
        }

        if connected:
            safety_manager.record_heartbeat()

            account = await mt5_service.get_account_info()

            state["account"] = {
                "login": account.get("login"),
                "server": account.get("server"),
                "currency": account.get("currency"),
                "balance": account.get("balance"),
                "equity": account.get("equity"),
                "profit": account.get("profit"),
                "margin": account.get("margin"),
                "margin_free": account.get("margin_free"),
                "margin_level": account.get("margin_level"),
            }

            tick = await mt5_service.get_symbol_tick(symbol)

            state["market"] = {
                "symbol": tick.get("symbol", symbol),
                "bid": tick.get("bid"),
                "ask": tick.get("ask"),
                "last": tick.get("last"),
                "spread": tick.get("spread"),
                "time": tick.get("time"),
                "time_msc": tick.get("time_msc"),
            }

            positions = await mt5_service.get_positions()

            state["positions"] = [
                {
                    "ticket": position.get("ticket"),
                    "symbol": position.get("symbol"),
                    "type": position.get("type"),
                    "volume": position.get("volume"),
                    "price_open": position.get("price_open"),
                    "price_current": position.get(
                        "price_current"
                    ),
                    "stop_loss": position.get("sl"),
                    "take_profit": position.get("tp"),
                    "profit": position.get("profit"),
                }
                for position in positions
            ]

        else:
            safety_manager.mark_connection_lost()

    except MT5ServiceError as exc:
        safety_manager.mark_connection_lost()

        state["connection"] = {
            "status": "error",
            "healthy": False,
            "last_error": str(exc),
        }

    except Exception as exc:
        safety_manager.mark_connection_lost()

        state["connection"] = {
            "status": "error",
            "healthy": False,
            "last_error": str(exc),
        }

    safety_status = safety_manager.status()

    state["emergency_stop"] = {
        "active": safety_status.emergency_stop_active,
        "trading_allowed": safety_status.trading_allowed,
        "connection_healthy": safety_status.connection_healthy,
        "connection_stale": safety_status.connection_stale,
        "reason": safety_status.reason,
        "last_heartbeat": safety_status.last_heartbeat,
    }

    return state
