"""
RAYMOND v2.8 - MT5 Broker Adapter

STEP 17.2

Purpose:
- Provide a broker-neutral interface around MetaTrader 5.
- Separate broker/account connectivity from trading strategy logic.
- Read account, terminal, symbol, tick and position information.
- Prepare the architecture for real order execution in Step 17.3.

IMPORTANT SAFETY RULES:
- This module does NOT place live orders.
- This module does NOT modify broker positions.
- This module does NOT enable live trading.
- No order_send call is performed here.
- Live execution will only be introduced through the dedicated
  execution gateway after the safety gate and reconciliation layers
  are implemented.

Architecture:

    Raymond
       |
       v
    BrokerAdapter
       |
       +---- MT5BrokerAdapter
                    |
                    v
              MT5Service
                    |
                    v
              MetaTrader 5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

try:
    from .mt5_service import (
        MT5ConnectionConfig,
        MT5Service,
        MT5ServiceError,
    )
except ImportError:
    from mt5_service import (
        MT5ConnectionConfig,
        MT5Service,
        MT5ServiceError,
    )


# ============================================================
# BROKER ADAPTER ERROR
# ============================================================

class BrokerAdapterError(RuntimeError):
    """Raised when a broker adapter operation fails."""


# ============================================================
# BROKER CONNECTION DATA
# ============================================================

@dataclass
class BrokerConnection:
    """
    Non-secret broker connection metadata.

    The password is intentionally not stored here.

    Credentials should eventually be resolved from the secure
    credential layer before connecting.
    """

    broker: str
    platform: str
    server: str
    account_number: str


# ============================================================
# BROKER ADAPTER BASE
# ============================================================

class BrokerAdapter:
    """
    Broker-neutral interface.

    Future adapters can implement:
    - MT5
    - Native broker REST APIs
    - Native broker WebSocket APIs
    - Other supported execution providers

    Step 17.2 only implements the MT5 read/connect layer.
    """

    name = "unknown"
    platform = "unknown"

    async def connect(self) -> bool:
        raise NotImplementedError

    async def disconnect(self) -> bool:
        raise NotImplementedError

    async def heartbeat(self) -> dict:
        raise NotImplementedError

    async def account_info(self) -> dict:
        raise NotImplementedError

    async def terminal_info(self) -> dict:
        raise NotImplementedError

    async def symbol_specification(
        self,
        symbol: str,
    ) -> dict:
        raise NotImplementedError

    async def symbol_tick(
        self,
        symbol: str,
    ) -> dict:
        raise NotImplementedError

    async def positions(
        self,
        symbol: Optional[str] = None,
    ) -> list[dict]:
        raise NotImplementedError

    async def available_symbols(
        self,
        query: Optional[str] = None,
    ) -> list[dict]:
        raise NotImplementedError

    async def send_order(
        self,
        order_request: dict,
    ) -> dict:
        """
        Deliberately unavailable in Step 17.2.

        Real order execution belongs to Step 17.3 and must pass
        the live safety gate before being allowed.
        """

        raise BrokerAdapterError(
            "Live order execution is not implemented in "
            "Step 17.2. Use the Step 17.3 execution gateway."
        )


# ============================================================
# MT5 BROKER ADAPTER
# ============================================================

class MT5BrokerAdapter(BrokerAdapter):
    """
    MetaTrader 5 implementation of the broker adapter.

    This class wraps the existing MT5Service rather than
    duplicating MT5 connection logic.
    """

    name = "MetaTrader 5"
    platform = "MT5"

    def __init__(
        self,
        service: Optional[MT5Service] = None,
        connection: Optional[BrokerConnection] = None,
    ):
        self.service = service or MT5Service()
        self.connection = connection

    async def connect(self) -> bool:
        try:
            return await self.service.initialize()

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"MT5 connection failed: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerAdapterError(
                f"Unexpected MT5 connection error: {exc}"
            ) from exc

    async def disconnect(self) -> bool:
        try:
            return await self.service.shutdown()

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"MT5 disconnect failed: {exc}"
            ) from exc

        except Exception as exc:
            raise BrokerAdapterError(
                f"Unexpected MT5 disconnect error: {exc}"
            ) from exc

    async def heartbeat(self) -> dict:
        try:
            result = await self.service.heartbeat()

            return {
                "adapter": self.name,
                "platform": self.platform,
                **result,
            }

        except Exception as exc:
            return {
                "adapter": self.name,
                "platform": self.platform,
                "connected": False,
                "last_error": str(exc),
                "timestamp": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            }

    async def account_info(self) -> dict:
        try:
            return await self.service.get_account_info()

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"Unable to read MT5 account: {exc}"
            ) from exc

    async def terminal_info(self) -> dict:
        try:
            return await self.service.get_terminal_info()

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"Unable to read MT5 terminal: {exc}"
            ) from exc

    async def symbol_specification(
        self,
        symbol: str,
    ) -> dict:
        symbol = str(symbol or "").strip()

        if not symbol:
            raise BrokerAdapterError(
                "Symbol is required."
            )

        try:
            return await self.service.get_symbol_specification(
                symbol
            )

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"Unable to read specification for "
                f"{symbol}: {exc}"
            ) from exc

    async def symbol_tick(
        self,
        symbol: str,
    ) -> dict:
        symbol = str(symbol or "").strip()

        if not symbol:
            raise BrokerAdapterError(
                "Symbol is required."
            )

        try:
            return await self.service.get_symbol_tick(
                symbol
            )

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"Unable to read tick for "
                f"{symbol}: {exc}"
            ) from exc

    async def positions(
        self,
        symbol: Optional[str] = None,
    ) -> list[dict]:
        try:
            return await self.service.get_positions(
                symbol=symbol
            )

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"Unable to read MT5 positions: {exc}"
            ) from exc

    async def available_symbols(
        self,
        query: Optional[str] = None,
    ) -> list[dict]:
        try:
            return await self.service.get_symbols(
                query=query
            )

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"Unable to read MT5 symbols: {exc}"
            ) from exc

    async def find_gold_symbols(self) -> list[dict]:
        try:
            return await self.service.find_gold_symbols()

        except MT5ServiceError as exc:
            raise BrokerAdapterError(
                f"Unable to discover XAUUSD symbols: {exc}"
            ) from exc


# ============================================================
# DEFAULT ADAPTER
# ============================================================

mt5_broker_adapter = MT5BrokerAdapter()


# ============================================================
# SAFE SERIALIZATION
# ============================================================

def _safe_account_info(
    account: dict,
) -> dict:
    allowed = {
        "login",
        "server",
        "company",
        "currency",
        "trade_mode",
        "leverage",
        "trade_allowed",
        "trade_expert",
        "balance",
        "credit",
        "profit",
        "equity",
        "margin",
        "margin_free",
        "margin_level",
        "margin_so_call",
        "margin_so_so",
    }

    return {
        key: account.get(key)
        for key in allowed
        if key in account
    }


def _safe_terminal_info(
    terminal: dict,
) -> dict:
    allowed = {
        "connected",
        "trade_allowed",
        "tradeapi_disabled",
        "build",
        "company",
        "name",
        "language",
        "maxbars",
    }

    return {
        key: terminal.get(key)
        for key in allowed
        if key in terminal
    }


# ============================================================
# API ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/broker-adapter",
    tags=["Broker Adapter"],
)


# ============================================================
# ADAPTER STATUS
# ============================================================

@router.get("/status")
async def adapter_status():
    """
    Read-only adapter health.

    This endpoint never enables trading.
    """

    return {
        "status": "ok",
        "adapter": mt5_broker_adapter.name,
        "platform": mt5_broker_adapter.platform,
        "execution_enabled": False,
        "live_orders_enabled": False,
        "timestamp": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "heartbeat": (
            await mt5_broker_adapter.heartbeat()
        ),
    }


# ============================================================
# CONNECT
# ============================================================

@router.post("/connect")
async def connect_adapter():
    """
    Connect to the configured MT5 terminal.

    This is a connection operation only.

    It does NOT authorize trading.
    """

    try:
        connected = (
            await mt5_broker_adapter.connect()
        )

        return {
            "status": "connected"
            if connected
            else "connection_failed",
            "adapter": mt5_broker_adapter.name,
            "platform": mt5_broker_adapter.platform,
            "execution_enabled": False,
            "live_orders_enabled": False,
            "timestamp": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

    except BrokerAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# ============================================================
# DISCONNECT
# ============================================================

@router.post("/disconnect")
async def disconnect_adapter():
    """
    Disconnect MT5.

    This does not close broker positions.
    """

    try:
        disconnected = (
            await mt5_broker_adapter.disconnect()
        )

        return {
            "status": (
                "disconnected"
                if disconnected
                else "disconnect_failed"
            ),
            "adapter": mt5_broker_adapter.name,
            "platform": mt5_broker_adapter.platform,
            "timestamp": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

    except BrokerAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# ============================================================
# ACCOUNT
# ============================================================

@router.get("/account")
async def adapter_account():
    try:
        account = (
            await mt5_broker_adapter.account_info()
        )

        return {
            "status": "ok",
            "account": _safe_account_info(
                account
            ),
            "execution_enabled": False,
        }

    except BrokerAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# ============================================================
# TERMINAL
# ============================================================

@router.get("/terminal")
async def adapter_terminal():
    try:
        terminal = (
            await mt5_broker_adapter.terminal_info()
        )

        return {
            "status": "ok",
            "terminal": _safe_terminal_info(
                terminal
            ),
            "execution_enabled": False,
        }

    except BrokerAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# ============================================================
# SYMBOL SPECIFICATION
# ============================================================

@router.get("/symbol/{symbol}")
async def adapter_symbol(
    symbol: str,
):
    try:
        specification = (
            await mt5_broker_adapter.symbol_specification(
                symbol
            )
        )

        return {
            "status": "ok",
            "symbol": symbol,
            "specification": specification,
            "execution_enabled": False,
        }

    except BrokerAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# ============================================================
# SYMBOL TICK
# ============================================================

@router.get("/symbol/{symbol}/tick")
async def adapter_symbol_tick(
    symbol: str,
):
    try:
        tick = (
            await mt5_broker_adapter.symbol_tick(
                symbol
            )
        )

        return {
            "status": "ok",
            "symbol": symbol,
            "tick": tick,
            "execution_enabled": False,
        }

    except BrokerAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# ============================================================
# POSITIONS
# ============================================================

@router.get("/positions")
async def adapter_positions(
    symbol: Optional[str] = None,
):
    try:
        positions = (
            await mt5_broker_adapter.positions(
                symbol=symbol
            )
        )

        return {
            "status": "ok",
            "symbol": symbol,
            "positions": positions,
            "count": len(positions),
            "execution_enabled": False,
        }

    except BrokerAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# ============================================================
# GOLD SYMBOL DISCOVERY
# ============================================================

@router.get("/gold-symbols")
async def adapter_gold_symbols():
    try:
        symbols = (
            await mt5_broker_adapter.find_gold_symbols()
        )

        return {
            "status": "ok",
            "symbols": symbols,
            "execution_enabled": False,
        }

    except BrokerAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# ============================================================
# EXPLICIT EXECUTION BLOCK
# ============================================================

@router.post("/orders")
async def adapter_order_block():
    """
    Deliberate safety block.

    Step 17.2 must not place real orders.
    """

    raise HTTPException(
        status_code=403,
        detail={
            "error": "LIVE_EXECUTION_NOT_AVAILABLE",
            "message": (
                "Real broker order execution is deliberately "
                "disabled in Step 17.2. "
                "Execution will be introduced in Step 17.3 "
                "behind the Raymond live safety gate."
            ),
            "execution_enabled": False,
            "live_trading_enabled": False,
        },
          )
