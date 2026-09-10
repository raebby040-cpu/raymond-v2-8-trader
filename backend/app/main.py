"""
RAYMOND v2.8 Backend - FastAPI Application

Step 4B:
- Broker-neutral MT5 connection
- Real MT5 market tick data
- Broker-specific symbol discovery
- Real MT5 OHLC candles
- MT5 account information
- MT5 read-only position synchronization
- Broker-aware symbol specifications
- Risk-engine-ready market data
- Paper trading only

IMPORTANT:
Real order execution is NOT implemented.
No endpoint places, modifies, or closes a real trade.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from .mt5_service import (
        MT5ConnectionConfig,
        MT5Service,
        MT5ServiceError,
        mt5_service,
    )
except ImportError:
    from mt5_service import (
        MT5ConnectionConfig,
        MT5Service,
        MT5ServiceError,
        mt5_service,
    )


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="RAYMOND v2.8 Trading System",
    description=(
        "Broker-neutral MT5 market analysis, "
        "paper trading and AI decision support."
    ),
    version="2.8.0",
)


# ============================================================
# CORS
# ============================================================

origins = [
    "http://localhost:3000",
    "http://localhost:8080",
    "http://localhost:5000",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HELPERS
# ============================================================

def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def live_trading_enabled() -> bool:
    return (
        os.getenv(
            "LIVE_TRADING_ENABLED",
            "false",
        ).lower()
        == "true"
    )


def safe_account_response(
    account: dict,
) -> dict:
    allowed_fields = [
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
    ]

    return {
        field: account.get(field)
        for field in allowed_fields
        if field in account
    }


def safe_terminal_response(
    terminal: dict,
) -> dict:
    allowed_fields = [
        "community_account",
        "community_connection",
        "connected",
        "trade_allowed",
        "tradeapi_disabled",
        "build",
        "maxbars",
        "language",
        "company",
        "name",
    ]

    return {
        field: terminal.get(field)
        for field in allowed_fields
        if field in terminal
    }


def safe_position_response(
    position: dict,
) -> dict:
    """
    Convert a raw MT5 position into the stable
    RAYMOND position format.

    This endpoint is READ ONLY.
    """

    position_type = position.get("type")

    if position_type == 0:
        type_name = "BUY"
    elif position_type == 1:
        type_name = "SELL"
    else:
        type_name = str(position_type)

    return {
        "ticket": position.get("ticket"),
        "time": position.get("time"),
        "time_update": position.get(
            "time_update"
        ),
        "symbol": position.get(
            "symbol"
        ),
        "type": position_type,
        "type_name": type_name,
        "volume": position.get(
            "volume"
        ),
        "price_open": position.get(
            "price_open"
        ),
        "price_current": position.get(
            "price_current"
        ),
        "price_stop_loss": position.get(
            "sl"
        ),
        "price_take_profit": position.get(
            "tp"
        ),
        "profit": position.get(
            "profit"
        ),
        "swap": position.get(
            "swap"
        ),
        "commission": position.get(
            "commission"
        ),
        "magic": position.get(
            "magic"
        ),
        "comment": position.get(
            "comment"
        ),
    }


def safe_symbol_specification_response(
    specification: dict,
) -> dict:
    """
    Return broker-specific symbol information
    required by the RAYMOND risk engine.

    This is READ ONLY.
    """

    allowed_fields = [
        "symbol",
        "digits",
        "point",
        "spread",
        "spread_float",
        "tick_size",
        "tick_value",
        "tick_value_profit",
        "tick_value_loss",
        "contract_size",
        "volume_min",
        "volume_max",
        "volume_step",
        "volume_limit",
        "trade_mode",
        "trade_execution_mode",
        "trade_stops_level",
        "trade_freeze_level",
        "currency_base",
        "currency_profit",
        "currency_margin",
    ]

    return {
        field: specification.get(field)
        for field in allowed_fields
        if field in specification
    }


def mt5_error_response(
    exc: Exception,
) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": (
                "MT5 connection/service unavailable"
            ),
            "message": str(exc),
            "timestamp": utc_timestamp(),
        },
    )


# ============================================================
# REQUEST MODELS
# ============================================================

class MT5ConnectRequest(BaseModel):
    login: int = Field(
        ...,
        gt=0,
    )

    password: str = Field(
        ...,
        min_length=1,
    )

    server: str = Field(
        ...,
        min_length=1,
    )

    terminal_path: Optional[str] = None

    timeout_ms: int = Field(
        default=60000,
        ge=1000,
        le=120000,
    )

    portable: bool = False


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": utc_timestamp(),
        "version": "2.8.0",
        "live_trading_enabled": (
            live_trading_enabled()
        ),
    }


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():
    return {
        "name": "RAYMOND v2.8 Trading System",
        "description": (
            "Broker-neutral MT5 market analysis "
            "and paper trading system"
        ),
        "version": "2.8.0",
        "broker_support": (
            "MT5-compatible brokers"
        ),
        "live_trading_enabled": (
            live_trading_enabled()
        ),
        "endpoints": {
            "health": "/health",
            "mt5_connect": "/api/mt5/connect",
            "mt5_disconnect": "/api/mt5/disconnect",
            "mt5_status": "/api/mt5/status",
            "mt5_account": "/api/mt5/account",
            "mt5_terminal": "/api/mt5/terminal",
            "market_price": "/api/market/price",
            "market_candles": (
                "/api/market/candlesticks"
            ),
            "market_symbols": (
                "/api/market/symbols"
            ),
            "market_gold": (
                "/api/market/gold-symbols"
            ),
            "market_symbol_specification": (
                "/api/market/symbol-specification"
            ),
            "trading": "/api/trading",
            "strategy": "/api/strategy",
            "admin": "/api/admin",
            "docs": "/docs",
        },
    }


# ============================================================
# MT5 CONNECTION
# ============================================================

@app.post("/api/mt5/connect")
async def connect_mt5(
    request: MT5ConnectRequest,
):
    global mt5_service

    config = MT5ConnectionConfig(
        login=request.login,
        password=request.password,
        server=request.server,
        terminal_path=request.terminal_path,
        timeout_ms=request.timeout_ms,
        portable=request.portable,
    )

    new_service = MT5Service(config)

    try:
        # initialize() returns a boolean.
        # It does not return account/terminal dictionaries.
        initialized = await new_service.initialize()

        if not initialized:
            raise MT5ServiceError(
                "MT5 initialization returned false."
            )

        # Read account and terminal information
        # only after successful initialization.
        account = (
            await new_service.get_account_info()
        )

        terminal = (
            await new_service.get_terminal_info()
        )

        # Replace the global service only after
        # successful initialization and validation.
        mt5_service = new_service

        logger.info(
            "MT5 connected: server=%s login=%s",
            account.get("server"),
            account.get("login"),
        )

        return {
            "status": "connected",
            "timestamp": utc_timestamp(),
            "broker": account.get(
                "company"
            ),
            "server": account.get(
                "server"
            ),
            "account": safe_account_response(
                account
            ),
            "terminal": safe_terminal_response(
                terminal
            ),
            "live_trading_enabled": (
                live_trading_enabled()
            ),
        }

    except MT5ServiceError as exc:
        logger.error(
            "MT5 connection failed: %s",
            exc,
        )
        raise mt5_error_response(exc) from exc


@app.post("/api/mt5/disconnect")
async def disconnect_mt5():
    try:
        await mt5_service.shutdown()

        return {
            "status": "disconnected",
            "timestamp": utc_timestamp(),
        }

    except Exception as exc:
        logger.error(
            "MT5 disconnect failed: %s",
            exc,
        )
        raise mt5_error_response(exc) from exc


@app.get("/api/mt5/status")
async def get_mt5_status():
    try:
        status = await mt5_service.heartbeat()

        return {
            "status": (
                "connected"
                if status.get("connected")
                else "disconnected"
            ),
            "timestamp": status.get(
                "timestamp",
                utc_timestamp(),
            ),
            "connected": status.get(
                "connected",
                False,
            ),
            "account_login": status.get(
                "account_login"
            ),
            "server": status.get(
                "server"
            ),
            "trade_allowed": status.get(
                "trade_allowed"
            ),
            "tradeapi_disabled": status.get(
                "tradeapi_disabled"
            ),
            "last_error": status.get(
                "last_error"
            ),
            "live_trading_enabled": (
                live_trading_enabled()
            ),
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


@app.get("/api/mt5/account")
async def get_mt5_account():
    try:
        account = (
            await mt5_service.get_account_info()
        )

        return {
            "status": "connected",
            "timestamp": utc_timestamp(),
            "account": safe_account_response(
                account
            ),
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


@app.get("/api/mt5/terminal")
async def get_mt5_terminal():
    try:
        terminal = (
            await mt5_service.get_terminal_info()
        )

        return {
            "status": "connected",
            "timestamp": utc_timestamp(),
            "terminal": safe_terminal_response(
                terminal
            ),
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


# ============================================================
# REAL MARKET DATA
# ============================================================

@app.get("/api/market/price")
async def get_current_price(
    symbol: str = Query(
        default="XAUUSD",
        min_length=1,
        max_length=64,
    ),
):
    """
    Return the real current MT5 tick.

    No trade is placed.
    """

    try:
        tick = (
            await mt5_service.get_symbol_tick(
                symbol
            )
        )

        return {
            "status": "ok",
            "symbol": tick["symbol"],
            "bid": tick["bid"],
            "ask": tick["ask"],
            "last": tick["last"],
            "spread": tick["spread"],
            "volume": tick["volume"],
            "volume_real": tick[
                "volume_real"
            ],
            "time": tick["time"],
            "time_msc": tick[
                "time_msc"
            ],
            "timestamp": utc_timestamp(),
            "source": "mt5",
        }

    except (
        MT5ServiceError,
        ValueError,
    ) as exc:
        raise mt5_error_response(exc) from exc


@app.get("/api/market/candlesticks")
async def get_candlesticks(
    symbol: str = Query(
        default="XAUUSD",
        min_length=1,
        max_length=64,
    ),
    timeframe: str = Query(
        default="H1",
        min_length=2,
        max_length=4,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=5000,
    ),
):
    """
    Return real OHLC candles from MT5.

    MT5 supplies bar data in UTC.
    """

    try:
        candles = (
            await mt5_service.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        )

        return {
            "status": "ok",
            "symbol": symbol,
            "timeframe": timeframe.upper(),
            "candlesticks": candles,
            "total": len(candles),
            "timestamp": utc_timestamp(),
            "source": "mt5",
        }

    except (
        MT5ServiceError,
        ValueError,
    ) as exc:
        raise mt5_error_response(exc) from exc


@app.get("/api/market/symbols")
async def get_market_symbols(
    query: Optional[str] = Query(
        default=None,
        max_length=32,
    ),
):
    """
    Discover instruments available from the
    connected MT5 broker.
    """

    try:
        symbols = (
            await mt5_service.get_symbols(
                query=query
            )
        )

        return {
            "status": "ok",
            "query": query,
            "symbols": symbols,
            "total": len(symbols),
            "timestamp": utc_timestamp(),
            "source": "mt5",
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


@app.get("/api/market/gold-symbols")
async def get_gold_symbols():
    """
    Find XAUUSD/gold symbols regardless of
    broker suffix.

    Examples:
    XAUUSD
    XAUUSDm
    XAUUSD.a
    GOLD
    """

    try:
        symbols = (
            await mt5_service.find_gold_symbols()
        )

        return {
            "status": "ok",
            "symbols": symbols,
            "total": len(symbols),
            "timestamp": utc_timestamp(),
            "source": "mt5",
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


# ============================================================
# STEP 4B - SYMBOL SPECIFICATION
# ============================================================

@app.get("/api/market/symbol-specification")
async def get_symbol_specification(
    symbol: str = Query(
        default="XAUUSD",
        min_length=1,
        max_length=64,
    ),
):
    """
    Return broker-specific MT5 symbol properties.

    These values are used by the risk engine to
    calculate broker-aware position sizing.

    READ ONLY.

    No order is placed.
    No position is modified.
    """

    try:
        specification = (
            await mt5_service.get_symbol_specification(
                symbol
            )
        )

        return {
            "status": "ok",
            "symbol": specification.get(
                "symbol",
                symbol,
            ),
            "specification": (
                safe_symbol_specification_response(
                    specification
                )
            ),
            "timestamp": utc_timestamp(),
            "source": "mt5",
            "read_only": True,
        }

    except (
        MT5ServiceError,
        ValueError,
    ) as exc:
        raise mt5_error_response(exc) from exc


# ============================================================
# INDICATORS
# ============================================================

@app.get("/api/market/indicators")
async def get_indicators(
    symbol: str = "XAUUSD",
):
    """
    Indicators remain a later step.

    We deliberately do not calculate indicators
    from fake data anymore.
    """

    return {
        "status": "not_implemented",
        "symbol": symbol,
        "message": (
            "Real indicators will be calculated "
            "from MT5 candles in the next market-data "
            "stage."
        ),
        "timestamp": utc_timestamp(),
        "source": "none",
    }


# ============================================================
# TRADING - PAPER ONLY
# ============================================================

@app.post("/api/trading/place-order")
async def place_order(
    order_data: dict,
):
    """
    PAPER TRADING ONLY.

    This endpoint cannot send a real MT5 order.
    """

    logger.warning(
        "Paper trade requested. "
        "Real execution remains disabled."
    )

    return {
        "order_id": "PAPER-ORDER-001",
        "status": "paper_only",
        "symbol": order_data.get(
            "symbol",
            "XAUUSD",
        ),
        "order_type": order_data.get(
            "order_type",
            "market",
        ),
        "quantity": order_data.get(
            "quantity",
            0.1,
        ),
        "price": None,
        "execution_type": "paper",
        "timestamp": utc_timestamp(),
    }


# ============================================================
# STEP 3 - READ-ONLY MT5 POSITIONS
# ============================================================

@app.get("/api/trading/positions")
async def get_positions(
    symbol: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=64,
    ),
):
    """
    Read real open MT5 positions.

    STEP 3:
    - Read-only
    - No position modification
    - No position closing
    - No trade execution
    """

    try:
        positions = await mt5_service.get_positions(
            symbol=symbol
        )

        normalized_positions = [
            safe_position_response(position)
            for position in positions
        ]

        return {
            "status": "ok",
            "symbol": symbol,
            "positions": normalized_positions,
            "total_positions": len(
                normalized_positions
            ),
            "source": "mt5_read_only",
            "timestamp": utc_timestamp(),
            "live_trading_enabled": (
                live_trading_enabled()
            ),
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


@app.post("/api/trading/close-position")
async def close_position(
    position_id: str,
):
    """
    Real position closing is intentionally disabled.
    """

    return {
        "position_id": position_id,
        "status": "disabled",
        "message": (
            "Real MT5 position closing is "
            "not implemented yet."
        ),
        "timestamp": utc_timestamp(),
    }


# ============================================================
# STRATEGY / AI
# ============================================================

@app.get("/api/strategy/decision")
async def get_strategy_decision(
    symbol: str = "XAUUSD",
):
    return {
        "symbol": symbol,
        "timestamp": utc_timestamp(),
        "decision": "hold",
        "confidence": 0.0,
        "reason": (
            "AI execution layer is waiting for "
            "validated real market-data pipeline."
        ),
        "source": "placeholder",
    }


@app.post("/api/strategy/backtest")
async def run_backtest(
    backtest_config: dict,
):
    return {
        "backtest_id": "BT-PENDING",
        "status": "not_implemented",
        "message": (
            "Backtesting will use validated "
            "historical market data."
        ),
        "timestamp": utc_timestamp(),
    }


# ============================================================
# JOURNAL
# ============================================================

@app.get("/api/journal/trades")
async def get_trade_journal(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
):
    return {
        "trades": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "timestamp": utc_timestamp(),
    }


# ============================================================
# ADMIN
# ============================================================

@app.post("/api/admin/emergency-stop")
async def emergency_stop():
    """
    Placeholder only.

    Full execution lockout comes before live trading.
    """

    logger.critical(
        "EMERGENCY STOP REQUEST RECEIVED"
    )

    return {
        "status": "emergency_stop_requested",
        "timestamp": utc_timestamp(),
        "all_positions_closed": False,
        "new_orders_blocked": False,
        "note": (
            "Full execution lockout will be implemented "
            "before live trading."
        ),
    }


@app.get("/api/admin/status")
async def admin_status():
    try:
        mt5_status = (
            await mt5_service.heartbeat()
        )
    except Exception:
        mt5_status = {
            "connected": False,
            "last_error": (
                "MT5 unavailable"
            ),
        }

    return {
        "status": "operational",
        "live_trading_enabled": (
            live_trading_enabled()
        ),
        "environment": os.getenv(
            "RAYMOND_ENV",
            "development",
        ),
        "db_connected": True,
        "market_feed_healthy": (
            mt5_status.get(
                "connected",
                False,
            )
        ),
        "mt5_connected": mt5_status.get(
            "connected",
            False,
        ),
        "timestamp": utc_timestamp(),
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(
    request,
    exc,
):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "timestamp": utc_timestamp(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request,
    exc,
):
    logger.error(
        "Unhandled exception: %s",
        exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": utc_timestamp(),
        },
    )


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
