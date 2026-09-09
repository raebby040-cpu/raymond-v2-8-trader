"""
RAYMOND v2.8 Backend - FastAPI Application

Step 1B:
- Broker-neutral MT5 connection API
- MT5 connection status
- MT5 account information
- MT5 terminal information
- Safe disconnect

IMPORTANT:
Trade execution is NOT implemented here.
No endpoint in this step places, modifies, or closes trades.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
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
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="RAYMOND v2.8 Trading System",
    description=(
        "Broker-neutral MT5 trading system with market analysis, "
        "paper trading, risk management and AI decision support."
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
        os.getenv("LIVE_TRADING_ENABLED", "false").lower()
        == "true"
    )


def safe_account_response(account: dict) -> dict:
    """
    Return only account information needed by the dashboard.

    Sensitive/unnecessary fields such as account holder name
    are intentionally not exposed by this API response.
    """

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


def safe_terminal_response(terminal: dict) -> dict:
    """
    Return safe MT5 terminal information.

    Local filesystem paths and other unnecessary terminal
    details are intentionally excluded.
    """

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


def mt5_error_response(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "MT5 connection/service unavailable",
            "message": str(exc),
            "timestamp": utc_timestamp(),
        },
    )


# ============================================================
# REQUEST MODELS
# ============================================================

class MT5ConnectRequest(BaseModel):
    """
    Broker-neutral MT5 connection settings.

    The broker itself is NOT a fixed value.
    The MT5 server name identifies the broker's trade server.
    """

    login: int = Field(..., gt=0)
    password: str = Field(..., min_length=1)
    server: str = Field(..., min_length=1)

    terminal_path: Optional[str] = None

    timeout_ms: int = Field(
        default=60000,
        ge=1000,
        le=120000,
    )

    portable: bool = False


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""

    return {
        "status": "healthy",
        "timestamp": utc_timestamp(),
        "version": "2.8.0",
        "live_trading_enabled": live_trading_enabled(),
    }


# ============================================================
# API ROOT
# ============================================================

@app.get("/")
async def root():
    """Root endpoint."""

    return {
        "name": "RAYMOND v2.8 Trading System",
        "description": (
            "Broker-neutral MT5 market analysis and "
            "paper trading system"
        ),
        "version": "2.8.0",
        "broker_support": "MT5-compatible brokers",
        "live_trading_enabled": live_trading_enabled(),
        "endpoints": {
            "health": "/health",
            "mt5_connect": "/api/mt5/connect",
            "mt5_disconnect": "/api/mt5/disconnect",
            "mt5_status": "/api/mt5/status",
            "mt5_account": "/api/mt5/account",
            "mt5_terminal": "/api/mt5/terminal",
            "market_data": "/api/market",
            "trading": "/api/trading",
            "strategy": "/api/strategy",
            "admin": "/api/admin",
            "docs": "/docs",
        },
    }


# ============================================================
# MT5 / BROKER CONNECTION
# ============================================================

@app.post("/api/mt5/connect")
async def connect_mt5(request: MT5ConnectRequest):
    """
    Connect RAYMOND to any MT5-compatible broker/account.

    No broker is hardcoded here.
    """

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
        result = await new_service.initialize()

        mt5_service = new_service

        account = result.get("account", {})
        terminal = result.get("terminal", {})

        logger.info(
            "MT5 connected: server=%s login=%s",
            account.get("server"),
            account.get("login"),
        )

        return {
            "status": "connected",
            "timestamp": utc_timestamp(),
            "broker": account.get("company"),
            "server": account.get("server"),
            "account": safe_account_response(account),
            "terminal": safe_terminal_response(terminal),
            "live_trading_enabled": live_trading_enabled(),
        }

    except MT5ServiceError as exc:
        logger.error("MT5 connection failed: %s", exc)
        raise mt5_error_response(exc) from exc


@app.post("/api/mt5/disconnect")
async def disconnect_mt5():
    """
    Disconnect from the current MT5 terminal.

    This does not close positions or execute trades.
    """

    try:
        await mt5_service.shutdown()

        return {
            "status": "disconnected",
            "timestamp": utc_timestamp(),
        }

    except Exception as exc:
        logger.error("MT5 disconnect failed: %s", exc)
        raise mt5_error_response(exc) from exc


@app.get("/api/mt5/status")
async def get_mt5_status():
    """
    Return current MT5 connection heartbeat.

    This endpoint does not execute trades.
    """

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
            "connected": status.get("connected", False),
            "account_login": status.get("account_login"),
            "server": status.get("server"),
            "trade_allowed": status.get("trade_allowed"),
            "tradeapi_disabled": status.get(
                "tradeapi_disabled"
            ),
            "last_error": status.get("last_error"),
            "live_trading_enabled": live_trading_enabled(),
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


@app.get("/api/mt5/account")
async def get_mt5_account():
    """
    Return current MT5 account information.
    """

    try:
        account = await mt5_service.get_account_info()

        return {
            "status": "connected",
            "timestamp": utc_timestamp(),
            "account": safe_account_response(account),
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


@app.get("/api/mt5/terminal")
async def get_mt5_terminal():
    """
    Return current MT5 terminal information.
    """

    try:
        terminal = await mt5_service.get_terminal_info()

        return {
            "status": "connected",
            "timestamp": utc_timestamp(),
            "terminal": safe_terminal_response(terminal),
        }

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc


# ============================================================
# MARKET DATA ROUTES
# ============================================================

@app.get("/api/market/price")
async def get_current_price(symbol: str = "XAUUSD"):
    """Get current market price for a symbol."""

    return {
        "symbol": symbol,
        "price": 2050.45,
        "timestamp": utc_timestamp(),
        "bid": 2050.40,
        "ask": 2050.50,
        "source": "mock",
    }


@app.get("/api/market/candlesticks")
async def get_candlesticks(
    symbol: str = "XAUUSD",
    timeframe: str = "H1",
    limit: int = 100,
):
    """Get candlestick data for technical analysis."""

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candlesticks": [
            {
                "time": utc_timestamp(),
                "open": 2048.50,
                "high": 2051.75,
                "low": 2048.00,
                "close": 2050.45,
                "volume": 1500000,
            }
        ],
        "total": 1,
        "source": "mock",
    }


@app.get("/api/market/indicators")
async def get_indicators(symbol: str = "XAUUSD"):
    """Get technical indicators."""

    return {
        "symbol": symbol,
        "timestamp": utc_timestamp(),
        "indicators": {
            "ema20": 2049.50,
            "ema50": 2047.00,
            "rsi": 65.5,
            "atr": 12.35,
        },
        "source": "mock",
    }


# ============================================================
# TRADING ROUTES
# ============================================================

@app.post("/api/trading/place-order")
async def place_order(order_data: dict):
    """
    PLACE ORDER IS STILL PAPER/MOCK ONLY.

    Real MT5 execution is intentionally not implemented
    in Step 1B.
    """

    logger.warning(
        "Trade execution requested but Step 1B is "
        "still paper/mock only."
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
        "price": 2050.45,
        "execution_type": "paper",
        "timestamp": utc_timestamp(),
    }


@app.get("/api/trading/positions")
async def get_positions():
    """Get mock/paper positions for now."""

    return {
        "positions": [
            {
                "position_id": "POS-001",
                "symbol": "XAUUSD",
                "quantity": 0.5,
                "entry_price": 2048.50,
                "current_price": 2050.45,
                "pnl": 97.50,
                "pnl_percent": 0.19,
                "opened_at": utc_timestamp(),
            }
        ],
        "total_positions": 1,
        "source": "mock",
    }


@app.post("/api/trading/close-position")
async def close_position(position_id: str):
    """Paper/mock position close for now."""

    return {
        "position_id": position_id,
        "status": "paper_closed",
        "closed_at": utc_timestamp(),
        "pnl": 97.50,
    }


# ============================================================
# STRATEGY & AI ROUTES
# ============================================================

@app.get("/api/strategy/decision")
async def get_strategy_decision(
    symbol: str = "XAUUSD",
):
    """Get mock AI trading decision."""

    return {
        "symbol": symbol,
        "timestamp": utc_timestamp(),
        "decision": "buy",
        "confidence": 0.78,
        "reason": (
            "EMA20 crossed above EMA50 with RSI > 60"
        ),
        "recommended_entry": 2050.00,
        "stop_loss": 2045.00,
        "take_profit": 2060.00,
        "source": "mock",
    }


@app.post("/api/strategy/backtest")
async def run_backtest(backtest_config: dict):
    """Run mock backtest."""

    return {
        "backtest_id": "BT-20260908-001",
        "status": "completed",
        "total_trades": 125,
        "winning_trades": 98,
        "losing_trades": 27,
        "win_rate": 0.784,
        "total_pnl": 2150.75,
        "max_drawdown": 0.045,
        "sharpe_ratio": 1.85,
        "started_at": utc_timestamp(),
    }


# ============================================================
# JOURNAL & HISTORY
# ============================================================

@app.get("/api/journal/trades")
async def get_trade_journal(
    limit: int = 50,
    offset: int = 0,
):
    """Get mock trade journal."""

    return {
        "trades": [
            {
                "trade_id": "TRD-001",
                "symbol": "XAUUSD",
                "entry_price": 2048.50,
                "exit_price": 2050.45,
                "quantity": 0.5,
                "pnl": 97.50,
                "duration_minutes": 45,
                "opened_at": utc_timestamp(),
                "closed_at": utc_timestamp(),
                "status": "closed",
            }
        ],
        "total": 1,
        "limit": limit,
        "offset": offset,
    }


# ============================================================
# ADMIN ROUTES
# ============================================================

@app.post("/api/admin/emergency-stop")
async def emergency_stop():
    """
    Emergency stop placeholder.

    Full execution lockout is implemented later in the
    risk/execution gateway.
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
    """Get system status."""

    try:
        mt5_status = await mt5_service.heartbeat()
    except Exception:
        mt5_status = {
            "connected": False,
            "last_error": "MT5 unavailable",
        }

    return {
        "status": "operational",
        "live_trading_enabled": live_trading_enabled(),
        "environment": os.getenv(
            "RAYMOND_ENV",
            "development",
        ),
        "db_connected": True,
        "market_feed_healthy": True,
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
