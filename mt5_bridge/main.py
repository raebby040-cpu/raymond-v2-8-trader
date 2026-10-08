"""
Raymond v2.8 - MT5 Execution Bridge
====================================

Runs on the machine/VPS where the MetaTrader 5 terminal is installed.

IMPORTANT:
- DEMO accounts only.
- REAL accounts are rejected.
- This bridge does NOT enable Raymond live trading.
- Raymond's own risk engine, emergency stop, authorization and execution
  controls remain authoritative.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BRIDGE_API_KEY = os.getenv("MT5_BRIDGE_API_KEY", "").strip()

MT5_LOGIN = os.getenv("MT5_LOGIN", "").strip()
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "").strip()
MT5_TERMINAL_PATH = os.getenv("MT5_TERMINAL_PATH", "").strip()

MT5_TIMEOUT_MS = int(os.getenv("MT5_TIMEOUT_MS", "60000"))

# Hard safety lock.
# This bridge is DEMO ONLY until deliberately replaced by a separately
# audited live execution architecture.
ALLOW_REAL_ACCOUNT = False


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

_connected = False
_started_at = time.time()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class OrderRequest(BaseModel):
    symbol: str
    order_type: str = Field(pattern="^(BUY|SELL)$")
    volume: float = Field(gt=0)
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    deviation: int = Field(default=20, ge=0, le=1000)
    magic: int = Field(default=280001, ge=0)
    comment: str = Field(default="RAYMOND_DEMO", max_length=31)


class ModifyPositionRequest(BaseModel):
    ticket: int = Field(gt=0)
    stop_loss: float | None = None
    take_profit: float | None = None


class ClosePositionRequest(BaseModel):
    ticket: int = Field(gt=0)
    deviation: int = Field(default=20, ge=0, le=1000)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def require_api_key(
    x_mt5_bridge_key: str | None = Header(default=None),
) -> None:
    if not BRIDGE_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="MT5 bridge API key is not configured",
        )

    if x_mt5_bridge_key != BRIDGE_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid MT5 bridge API key",
        )


# ---------------------------------------------------------------------------
# MT5 helpers
# ---------------------------------------------------------------------------


def require_mt5() -> Any:
    if mt5 is None:
        raise HTTPException(
            status_code=503,
            detail="MetaTrader5 Python package is not installed",
        )

    return mt5


def initialize_mt5() -> None:
    global _connected

    mt5_module = require_mt5()

    kwargs: dict[str, Any] = {
        "timeout": MT5_TIMEOUT_MS,
    }

    if MT5_LOGIN:
        try:
            kwargs["login"] = int(MT5_LOGIN)
        except ValueError:
            raise HTTPException(
                status_code=500,
                detail="MT5_LOGIN must be numeric",
            )

    if MT5_PASSWORD:
        kwargs["password"] = MT5_PASSWORD

    if MT5_SERVER:
        kwargs["server"] = MT5_SERVER

    if MT5_TERMINAL_PATH:
        ok = mt5_module.initialize(
            MT5_TERMINAL_PATH,
            **kwargs,
        )
    else:
        ok = mt5_module.initialize(**kwargs)

    if not ok:
        _connected = False
        error = mt5_module.last_error()
        raise HTTPException(
            status_code=503,
            detail=f"MT5 initialization failed: {error}",
        )

    _connected = True


def ensure_connection() -> Any:
    mt5_module = require_mt5()

    if not _connected:
        initialize_mt5()

    terminal = mt5_module.terminal_info()

    if terminal is None:
        initialize_mt5()
        terminal = mt5_module.terminal_info()

    if terminal is None:
        raise HTTPException(
            status_code=503,
            detail=f"MT5 terminal unavailable: {mt5_module.last_error()}",
        )

    return mt5_module


def account_is_demo(account: Any) -> bool:
    """
    MT5 exposes account trade mode.

    ACCOUNT_TRADE_MODE_DEMO = demo account.
    ACCOUNT_TRADE_MODE_REAL = real account.
    """

    mt5_module = require_mt5()

    demo_mode = getattr(
        mt5_module,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    real_mode = getattr(
        mt5_module,
        "ACCOUNT_TRADE_MODE_REAL",
        2,
    )

    mode = getattr(account, "trade_mode", None)

    if mode == real_mode and not ALLOW_REAL_ACCOUNT:
        return False

    return mode == demo_mode


def require_demo_account() -> Any:
    mt5_module = ensure_connection()

    account = mt5_module.account_info()

    if account is None:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to read MT5 account: {mt5_module.last_error()}",
        )

    if not account_is_demo(account):
        raise HTTPException(
            status_code=403,
            detail=(
                "REAL MT5 accounts are blocked by the Raymond execution "
                "bridge. DEMO account required."
            ),
        )

    return account


def symbol_info_or_404(symbol: str) -> Any:
    mt5_module = ensure_connection()

    info = mt5_module.symbol_info(symbol)

    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"MT5 symbol not found: {symbol}",
        )

    if not info.visible:
        if not mt5_module.symbol_select(symbol, True):
            raise HTTPException(
                status_code=400,
                detail=f"Unable to select MT5 symbol: {symbol}",
            )

    return info


def position_to_dict(position: Any) -> dict[str, Any]:
    return {
        "ticket": int(position.ticket),
        "symbol": position.symbol,
        "type": int(position.type),
        "volume": float(position.volume),
        "price_open": float(position.price_open),
        "price_current": float(position.price_current),
        "stop_loss": float(position.sl),
        "take_profit": float(position.tp),
        "profit": float(position.profit),
        "swap": float(position.swap),
        "magic": int(position.magic),
        "comment": position.comment,
        "time": int(position.time),
    }


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _connected

    # Do not fail application startup if MT5 is temporarily unavailable.
    # The status endpoint will expose the actual condition.
    try:
        if mt5 is not None:
            initialize_mt5()
    except Exception:
        _connected = False

    yield

    if mt5 is not None:
        try:
            mt5.shutdown()
        except Exception:
            pass

    _connected = False


app = FastAPI(
    title="Raymond v2.8 MT5 Execution Bridge",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Public health endpoint
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "raymond-mt5-execution-bridge",
        "demo_only": True,
        "real_accounts_allowed": False,
        "mt5_package_installed": mt5 is not None,
        "connected": _connected,
        "uptime_seconds": round(time.time() - _started_at, 2),
    }


# ---------------------------------------------------------------------------
# Protected status
# ---------------------------------------------------------------------------


@app.get(
    "/api/status",
    dependencies=[Depends(require_api_key)],
)
def status() -> dict[str, Any]:
    mt5_module = ensure_connection()
    account = mt5_module.account_info()
    terminal = mt5_module.terminal_info()

    if account is None:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to read account: {mt5_module.last_error()}",
        )

    is_demo = account_is_demo(account)

    return {
        "service": "raymond-mt5-execution-bridge",
        "connected": True,
        "demo_only": True,
        "real_accounts_allowed": False,
        "account": {
            "login": int(account.login),
            "server": account.server,
            "trade_mode": int(account.trade_mode),
            "is_demo": is_demo,
            "balance": float(account.balance),
            "equity": float(account.equity),
            "margin": float(account.margin),
            "free_margin": float(account.margin_free),
            "currency": account.currency,
        },
        "terminal": {
            "connected": bool(getattr(terminal, "connected", False)),
            "trade_allowed": bool(
                getattr(terminal, "trade_allowed", False)
            ),
            "tradeapi_disabled": bool(
                getattr(terminal, "tradeapi_disabled", False)
            ),
        },
    }


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


@app.get(
    "/api/account",
    dependencies=[Depends(require_api_key)],
)
def account() -> dict[str, Any]:
    mt5_module = ensure_connection()
    info = require_demo_account()

    return {
        "login": int(info.login),
        "server": info.server,
        "trade_mode": int(info.trade_mode),
        "is_demo": account_is_demo(info),
        "balance": float(info.balance),
        "equity": float(info.equity),
        "margin": float(info.margin),
        "free_margin": float(info.margin_free),
        "currency": info.currency,
        "leverage": int(info.leverage),
        "profit": float(info.profit),
    }


# ---------------------------------------------------------------------------
# Symbol information
# ---------------------------------------------------------------------------


@app.get(
    "/api/symbol/{symbol}",
    dependencies=[Depends(require_api_key)],
)
def symbol(symbol: str) -> dict[str, Any]:
    info = symbol_info_or_404(symbol)

    return {
        "symbol": info.name,
        "visible": bool(info.visible),
        "digits": int(info.digits),
        "point": float(info.point),
        "trade_tick_size": float(info.trade_tick_size),
        "trade_tick_value": float(info.trade_tick_value),
        "trade_tick_value_profit": float(
            getattr(info, "trade_tick_value_profit", 0.0)
        ),
        "trade_tick_value_loss": float(
            getattr(info, "trade_tick_value_loss", 0.0)
        ),
        "trade_contract_size": float(info.trade_contract_size),
        "volume_min": float(info.volume_min),
        "volume_max": float(info.volume_max),
        "volume_step": float(info.volume_step),
        "volume_limit": float(info.volume_limit),
        "trade_stops_level": int(info.trade_stops_level),
        "trade_freeze_level": int(info.trade_freeze_level),
        "spread": int(info.spread),
        "currency_base": info.currency_base,
        "currency_profit": info.currency_profit,
        "currency_margin": info.currency_margin,
    }


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------


@app.get(
    "/api/tick/{symbol}",
    dependencies=[Depends(require_api_key)],
)
def tick(symbol: str) -> dict[str, Any]:
    mt5_module = ensure_connection()

    symbol_info_or_404(symbol)

    value = mt5_module.symbol_info_tick(symbol)

    if value is None:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to read tick for {symbol}: "
            f"{mt5_module.last_error()}",
        )

    return {
        "symbol": symbol,
        "time": int(value.time),
        "bid": float(value.bid),
        "ask": float(value.ask),
        "last": float(value.last),
        "volume": int(value.volume),
    }


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


@app.get(
    "/api/positions",
    dependencies=[Depends(require_api_key)],
)
def positions() -> dict[str, Any]:
    mt5_module = ensure_connection()

    require_demo_account()

    values = mt5_module.positions_get()

    if values is None:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to read positions: {mt5_module.last_error()}",
        )

    return {
        "count": len(values),
        "positions": [
            position_to_dict(position)
            for position in values
        ],
    }


# ---------------------------------------------------------------------------
# Order execution - DEMO ONLY
# ---------------------------------------------------------------------------


@app.post(
    "/api/orders",
    dependencies=[Depends(require_api_key)],
)
def create_order(request: OrderRequest) -> dict[str, Any]:
    mt5_module = ensure_connection()

    # HARD ACCOUNT SAFETY CHECK BEFORE order_check/order_send.
    require_demo_account()

    info = symbol_info_or_404(request.symbol)

    tick = mt5_module.symbol_info_tick(request.symbol)

    if tick is None:
        raise HTTPException(
            status_code=503,
            detail=f"No market tick available for {request.symbol}",
        )

    if request.order_type == "BUY":
        order_type = mt5_module.ORDER_TYPE_BUY
        price = request.price if request.price is not None else tick.ask
    else:
        order_type = mt5_module.ORDER_TYPE_SELL
        price = request.price if request.price is not None else tick.bid

    # Validate volume against broker specification.
    if request.volume < info.volume_min:
        raise HTTPException(
            status_code=400,
            detail=f"Volume below broker minimum: {info.volume_min}",
        )

    if request.volume > info.volume_max:
        raise HTTPException(
            status_code=400,
            detail=f"Volume above broker maximum: {info.volume_max}",
        )

    request_data = {
        "action": mt5_module.TRADE_ACTION_DEAL,
        "symbol": request.symbol,
        "volume": request.volume,
        "type": order_type,
        "price": price,
        "sl": request.stop_loss or 0.0,
        "tp": request.take_profit or 0.0,
        "deviation": request.deviation,
        "magic": request.magic,
        "comment": request.comment,
        "type_time": mt5_module.ORDER_TIME_GTC,
        "type_filling": mt5_module.ORDER_FILLING_IOC,
    }

    check = mt5_module.order_check(request_data)

    if check is None:
        raise HTTPException(
            status_code=502,
            detail=f"MT5 order_check failed: {mt5_module.last_error()}",
        )

    check_retcode = int(getattr(check, "retcode", -1))

    if check_retcode != 0:
        return {
            "accepted": False,
            "stage": "order_check",
            "retcode": check_retcode,
            "comment": getattr(check, "comment", ""),
        }

    result = mt5_module.order_send(request_data)

    if result is None:
        raise HTTPException(
            status_code=502,
            detail=f"MT5 order_send failed: {mt5_module.last_error()}",
        )

    success_codes = {
        getattr(mt5_module, "TRADE_RETCODE_DONE", 10009),
        getattr(mt5_module, "TRADE_RETCODE_DONE_PARTIAL", 10010),
    }

    retcode = int(result.retcode)

    return {
        "accepted": retcode in success_codes,
        "stage": "order_send",
        "retcode": retcode,
        "comment": result.comment,
        "order": int(getattr(result, "order", 0)),
        "deal": int(getattr(result, "deal", 0)),
        "volume": float(getattr(result, "volume", 0.0)),
        "price": float(getattr(result, "price", 0.0)),
        "request_id": int(getattr(result, "request_id", 0)),
    }


# ---------------------------------------------------------------------------
# Modify SL / TP
# ---------------------------------------------------------------------------


@app.post(
    "/api/positions/modify",
    dependencies=[Depends(require_api_key)],
)
def modify_position(
    request: ModifyPositionRequest,
) -> dict[str, Any]:
    mt5_module = ensure_connection()

    require_demo_account()

    values = mt5_module.positions_get(ticket=request.ticket)

    if not values:
        raise HTTPException(
            status_code=404,
            detail=f"Position not found: {request.ticket}",
        )

    position = values[0]

    modification = {
        "action": mt5_module.TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "position": request.ticket,
        "sl": request.stop_loss or 0.0,
        "tp": request.take_profit or 0.0,
    }

    result = mt5_module.order_send(modification)

    if result is None:
        raise HTTPException(
            status_code=502,
            detail=f"SL/TP modification failed: {mt5_module.last_error()}",
        )

    return {
        "accepted": int(result.retcode)
        == getattr(mt5_module, "TRADE_RETCODE_DONE", 10009),
        "retcode": int(result.retcode),
        "comment": result.comment,
        "ticket": request.ticket,
    }


# ---------------------------------------------------------------------------
# Close position
# ---------------------------------------------------------------------------


@app.post(
    "/api/positions/close",
    dependencies=[Depends(require_api_key)],
)
def close_position(
    request: ClosePositionRequest,
) -> dict[str, Any]:
    mt5_module = ensure_connection()

    require_demo_account()

    values = mt5_module.positions_get(ticket=request.ticket)

    if not values:
        raise HTTPException(
            status_code=404,
            detail=f"Position not found: {request.ticket}",
        )

    position = values[0]

    tick = mt5_module.symbol_info_tick(position.symbol)

    if tick is None:
        raise HTTPException(
            status_code=503,
            detail=f"No market tick for {position.symbol}",
        )

    if position.type == mt5_module.POSITION_TYPE_BUY:
        order_type = mt5_module.ORDER_TYPE_SELL
        price = tick.bid
    else:
        order_type = mt5_module.ORDER_TYPE_BUY
        price = tick.ask

    request_data = {
        "action": mt5_module.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": float(position.volume),
        "type": order_type,
        "position": int(position.ticket),
        "price": price,
        "deviation": request.deviation,
        "magic": int(position.magic),
        "comment": "RAYMOND_DEMO_CLOSE",
        "type_time": mt5_module.ORDER_TIME_GTC,
        "type_filling": mt5_module.ORDER_FILLING_IOC,
    }

    result = mt5_module.order_send(request_data)

    if result is None:
        raise HTTPException(
            status_code=502,
            detail=f"MT5 close failed: {mt5_module.last_error()}",
        )

    success_codes = {
        getattr(mt5_module, "TRADE_RETCODE_DONE", 10009),
        getattr(mt5_module, "TRADE_RETCODE_DONE_PARTIAL", 10010),
    }

    return {
        "accepted": int(result.retcode) in success_codes,
        "retcode": int(result.retcode),
        "comment": result.comment,
        "ticket": request.ticket,
        "deal": int(getattr(result, "deal", 0)),
        "price": float(getattr(result, "price", 0.0)),
    }


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


@app.get(
    "/api/last-error",
    dependencies=[Depends(require_api_key)],
)
def last_error() -> dict[str, Any]:
    mt5_module = ensure_connection()

    return {
        "error": mt5_module.last_error(),
    }
