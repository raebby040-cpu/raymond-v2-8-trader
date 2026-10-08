"""
Raymond v2.8 - MT5 Bridge Status API
=====================================

Read-only API for the remote MT5 execution bridge.

This module:
- reports bridge configuration/availability
- verifies DEMO account connectivity
- verifies XAUUSD market data
- NEVER submits an order
- NEVER modifies a position
- NEVER closes a position
- NEVER enables live trading
"""

from __future__ import annotations

from fastapi import APIRouter

from .mt5_bridge_client import (
    MT5BridgeError,
    mt5_bridge_client,
)


router = APIRouter(
    prefix="/api/mt5-bridge",
    tags=["MT5 Bridge"],
)


@router.get("/health")
async def bridge_health() -> dict:
    """
    Read-only bridge health.

    This endpoint does not require the MT5 bridge to be available.
    """
    health = await mt5_bridge_client.health()

    return {
        "service": "raymond-v2-8",
        "component": "mt5_execution_bridge",
        "read_only": True,
        "live_trading_enabled": False,
        **health,
    }


@router.get("/status")
async def bridge_status() -> dict:
    """
    Read-only detailed bridge status.

    If the bridge is unavailable, the response remains fail-closed.
    """
    health = await mt5_bridge_client.health()

    if not health.get("available"):
        return {
            "status": "unavailable",
            "connected": False,
            "configured": health.get(
                "configured",
                False,
            ),
            "demo_only": True,
            "real_accounts_allowed": False,
            "live_trading_enabled": False,
            "read_only": True,
            "reason": health.get(
                "reason",
                "MT5 bridge unavailable",
            ),
        }

    try:
        status = await mt5_bridge_client.status()

    except MT5BridgeError as exc:
        return {
            "status": "error",
            "connected": False,
            "configured": True,
            "demo_only": True,
            "real_accounts_allowed": False,
            "live_trading_enabled": False,
            "read_only": True,
            "reason": str(exc),
        }

    account = status.get("account") or {}

    is_demo = account.get("is_demo") is True

    if not is_demo:
        return {
            "status": "unsafe_account",
            "connected": True,
            "configured": True,
            "demo_only": True,
            "real_accounts_allowed": False,
            "live_trading_enabled": False,
            "read_only": True,
            "reason": (
                "Connected MT5 account is not verified as DEMO."
            ),
        }

    return {
        "status": "connected",
        "connected": True,
        "configured": True,
        "demo_only": True,
        "real_accounts_allowed": False,
        "live_trading_enabled": False,
        "read_only": True,
        "account": account,
        "terminal": status.get("terminal"),
    }


@router.get("/verify-demo")
async def verify_demo(
    symbol: str = "XAUUSD",
) -> dict:
    """
    Perform a complete read-only DEMO verification.

    Checks:
    1. Bridge reachability
    2. MT5 connection
    3. DEMO account
    4. REAL-account blocking
    5. Symbol availability
    6. Current bid/ask

    No order is submitted.
    """
    result = await mt5_bridge_client.verify_demo_connection(
        symbol=symbol,
    )

    if result.get("verified") is True:
        return {
            "status": "verified",
            "verified": True,
            "demo_only": True,
            "real_accounts_allowed": False,
            "live_trading_enabled": False,
            "read_only": True,
            **result,
        }

    return {
        "status": "not_verified",
        "verified": False,
        "demo_only": True,
        "real_accounts_allowed": False,
        "live_trading_enabled": False,
        "read_only": True,
        **result,
    }


@router.get("/account")
async def bridge_account() -> dict:
    """
    Read-only MT5 account information.
    """
    try:
        account = await mt5_bridge_client.account()

        return {
            "available": True,
            "demo_only": True,
            "real_accounts_allowed": False,
            "live_trading_enabled": False,
            "read_only": True,
            "account": account,
        }

    except MT5BridgeError as exc:
        return {
            "available": False,
            "demo_only": True,
            "real_accounts_allowed": False,
            "live_trading_enabled": False,
            "read_only": True,
            "reason": str(exc),
        }


@router.get("/symbol/{symbol}")
async def bridge_symbol(
    symbol: str,
) -> dict:
    """
    Read-only broker symbol specification.
    """
    try:
        result = await mt5_bridge_client.symbol(symbol)

        return {
            "available": True,
            "read_only": True,
            "symbol": result,
        }

    except MT5BridgeError as exc:
        return {
            "available": False,
            "read_only": True,
            "symbol": symbol,
            "reason": str(exc),
        }


@router.get("/tick/{symbol}")
async def bridge_tick(
    symbol: str,
) -> dict:
    """
    Read-only current market tick.
    """
    try:
        result = await mt5_bridge_client.tick(symbol)

        return {
            "available": True,
            "read_only": True,
            "tick": result,
        }

    except MT5BridgeError as exc:
        return {
            "available": False,
            "read_only": True,
            "symbol": symbol,
            "reason": str(exc),
        }


@router.get("/positions")
async def bridge_positions() -> dict:
    """
    Read-only broker positions.
    """
    try:
        result = await mt5_bridge_client.positions()

        return {
            "available": True,
            "read_only": True,
            "positions": result,
        }

    except MT5BridgeError as exc:
        return {
            "available": False,
            "read_only": True,
            "positions": [],
            "reason": str(exc),
        }
