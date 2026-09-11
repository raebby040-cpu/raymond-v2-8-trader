"""
RAYMOND v2.8 Backend - FastAPI Application

Step 15:
- Connect existing MT5 market data to the validated trading pipeline.
- Real MT5 candles -> technical indicators -> Step 13 AI
  -> Step 14 Risk -> Paper Execution Gateway.
- Paper trading only.
- Live trading remains disabled.
- Existing market, dashboard, demo, safety and read-only endpoints
  remain available.

IMPORTANT:
Real broker order execution is NOT implemented.
Step 15 never sends an order to MT5 or Exness.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


# ============================================================
# MT5 SERVICE
# ============================================================

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
# EXECUTION GATEWAY
# ============================================================

try:
    from .execution_gateway import (
        ExecutionGatewayError,
        OrderRequest,
        OrderSide,
        OrderType,
        create_execution_gateway,
    )
except ImportError:
    from execution_gateway import (
        ExecutionGatewayError,
        OrderRequest,
        OrderSide,
        OrderType,
        create_execution_gateway,
    )


# ============================================================
# STEP 9A - DASHBOARD / SAFETY
# ============================================================

try:
    from .dashboard_provider import build_dashboard_state
    from .emergency_stop import (
        EmergencyStopError,
        EmergencyStopManager,
    )
    from .websocket_handler import DashboardWebSocketManager
except ImportError:
    from dashboard_provider import build_dashboard_state
    from emergency_stop import (
        EmergencyStopError,
        EmergencyStopManager,
    )
    from websocket_handler import DashboardWebSocketManager


# ============================================================
# STEP 10A - DEMO TRADING API
# ============================================================

try:
    from .demo_api import (
        demo_engine,
        router as demo_trading_router,
    )
except ImportError:
    from demo_api import (
        demo_engine,
        router as demo_trading_router,
    )


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

try:
    from .technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )
except ImportError:
    from technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )


# ============================================================
# STEP 15 - APPLICATION TRADING PIPELINE
# ============================================================

try:
    from .risk_engine import SymbolSpecification
    from .trading_pipeline_service import (
        PaperRiskState,
        TradingPipelineService,
        TradingPipelineServiceError,
    )
except ImportError:
    from risk_engine import SymbolSpecification
    from trading_pipeline_service import (
        PaperRiskState,
        TradingPipelineService,
        TradingPipelineServiceError,
    )


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# SERVICES
# ============================================================

# Existing generic execution gateway.
# This remains paper-only.
execution_gateway = create_execution_gateway()

# Existing emergency-stop safety manager.
safety_manager = EmergencyStopManager()

# Existing dashboard WebSocket manager.
dashboard_ws_manager = DashboardWebSocketManager(
    heartbeat_interval_seconds=5.0
)

# Step 15 application pipeline.
#
# This internally connects:
#
# MT5 candles
#     ->
# Technical Indicators
#     ->
# Step 13 AI
#     ->
# Step 14 Risk
#     ->
# PaperExecutionGateway
#
# It never enables live execution.
trading_pipeline_service = TradingPipelineService()


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
# STEP 10A - DEMO TRADING ROUTER
# ============================================================

app.include_router(
    demo_trading_router,
    prefix="/api/demo",
    tags=["Demo Trading"],
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
        "time_update": position.get("time_update"),
        "symbol": position.get("symbol"),
        "type": position_type,
        "type_name": type_name,
        "volume": position.get("volume"),
        "price_open": position.get("price_open"),
        "price_current": position.get("price_current"),
        "price_stop_loss": position.get("sl"),
        "price_take_profit": position.get("tp"),
        "profit": position.get("profit"),
        "swap": position.get("swap"),
        "commission": position.get("commission"),
        "magic": position.get("magic"),
        "comment": position.get("comment"),
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
            "error": "MT5 connection/service unavailable",
            "message": str(exc),
            "timestamp": utc_timestamp(),
        },
    )


# ============================================================
# STEP 15 - PAPER RISK STATE
# ============================================================

def build_paper_risk_state() -> PaperRiskState:
    """
    Build the current paper-trading risk state.

    Step 15 deliberately uses the existing DemoTradingEngine
    as the paper-state source.

    It does NOT use real MT5 positions as paper positions.

    This keeps the Step 15 pipeline paper-only and prevents
    real broker positions from being mixed with simulated
    paper positions.
    """

    try:
        daily_closed_pnl = float(
            demo_engine.daily_closed_pnl()
        )

        open_positions = len(
            demo_engine.open_trades
        )

        # RiskEngine expects daily_loss to be a positive
        # loss amount, not a negative P&L number.
        daily_loss = max(
            0.0,
            -daily_closed_pnl,
        )

        return PaperRiskState(
            daily_loss=daily_loss,
            open_positions=open_positions,
            total_exposure=0.0,
        )

    except Exception as exc:
        raise TradingPipelineServiceError(
            f"Unable to build paper risk state: {exc}"
        ) from exc


def get_paper_equity() -> float:
    """
    Return current simulated paper equity.

    The demo engine starts with a paper balance of 10,000.
    Closed paper P&L is applied to that balance.

    Real MT5 account equity is intentionally NOT used for
    paper-trade position sizing.
    """

    try:
        performance = demo_engine.performance()

        equity = (
            float(demo_engine.initial_balance)
            + float(performance.total_pnl)
        )

    except Exception as exc:
        raise TradingPipelineServiceError(
            f"Unable to determine paper equity: {exc}"
        ) from exc

    if equity <= 0:
        raise TradingPipelineServiceError(
            "Paper equity is not greater than zero."
        )

    return equity


def build_symbol_specification(
    specification: dict,
) -> SymbolSpecification:
    """
    Convert the MT5 symbol specification dictionary into
    the exact Risk Engine SymbolSpecification object.
    """

    required_fields = [
        "symbol",
        "digits",
        "point",
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
        "spread",
        "spread_float",
    ]

    missing = [
        field
        for field in required_fields
        if field not in specification
    ]

    if missing:
        raise TradingPipelineServiceError(
            "MT5 symbol specification is missing required "
            f"fields: {', '.join(missing)}"
        )

    try:
        result = SymbolSpecification(
            symbol=str(
                specification["symbol"]
            ),
            digits=int(
                specification["digits"]
            ),
            point=float(
                specification["point"]
            ),
            tick_size=float(
                specification["tick_size"]
            ),
            tick_value=float(
                specification["tick_value"]
            ),
            tick_value_profit=float(
                specification["tick_value_profit"]
            ),
            tick_value_loss=float(
                specification["tick_value_loss"]
            ),
            contract_size=float(
                specification["contract_size"]
            ),
            volume_min=float(
                specification["volume_min"]
            ),
            volume_max=float(
                specification["volume_max"]
            ),
            volume_step=float(
                specification["volume_step"]
            ),
            volume_limit=float(
                specification["volume_limit"]
            ),
            trade_mode=int(
                specification["trade_mode"]
            ),
            trade_execution_mode=int(
                specification[
                    "trade_execution_mode"
                ]
            ),
            trade_stops_level=int(
                specification[
                    "trade_stops_level"
                ]
            ),
            trade_freeze_level=int(
                specification[
                    "trade_freeze_level"
                ]
            ),
            currency_base=str(
                specification["currency_base"]
            ),
            currency_profit=str(
                specification["currency_profit"]
            ),
            currency_margin=str(
                specification["currency_margin"]
            ),
            spread=int(
                specification["spread"]
            ),
            spread_float=bool(
                specification["spread_float"]
            ),
        )

    except (
        TypeError,
        ValueError,
        KeyError,
    ) as exc:
        raise TradingPipelineServiceError(
            "Invalid MT5 symbol specification: "
            f"{exc}"
        ) from exc

    try:
        result.validate()
    except Exception as exc:
        raise TradingPipelineServiceError(
            f"MT5 symbol specification failed validation: {exc}"
        ) from exc

    return result


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


class StrategyPaperTradeRequest(BaseModel):
    """
    Request for the complete Step 15 paper pipeline.

    No volume is accepted from the client.

    Step 14 / Risk Engine calculates the position size.
    """

    symbol: str = Field(
        default="XAUUSD",
        min_length=1,
        max_length=64,
    )

    timeframe: str = Field(
        default="H1",
        min_length=2,
        max_length=4,
    )

    limit: int = Field(
        default=200,
        ge=50,
        le=5000,
    )


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": utc_timestamp(),
        "version": "2.8.0",
        "live_trading_enabled": live_trading_enabled(),
        "step15_pipeline": True,
        "execution_mode": "paper_only",
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
        "broker_support": "MT5-compatible brokers",
        "live_trading_enabled": live_trading_enabled(),
        "execution_mode": "paper_only",
        "step15_pipeline": {
            "enabled": True,
            "path": (
                "MT5 candles -> indicators -> "
                "Step 13 AI -> Step 14 Risk -> "
                "PaperExecutionGateway"
            ),
        },
        "endpoints": {
            "health": "/health",
            "mt5_connect": "/api/mt5/connect",
            "mt5_disconnect": "/api/mt5/disconnect",
            "mt5_status": "/api/mt5/status",
            "mt5_account": "/api/mt5/account",
            "mt5_terminal": "/api/mt5/terminal",
            "market_price": "/api/market/price",
            "market_candles": "/api/market/candlesticks",
            "market_symbols": "/api/market/symbols",
            "market_gold": "/api/market/gold-symbols",
            "market_symbol_specification": (
                "/api/market/symbol-specification"
            ),
            "market_indicators": "/api/market/indicators",
            "trading": "/api/trading",
            "demo_trading": "/api/demo",
            "strategy": "/api/strategy",
            "strategy_decision": (
                "/api/strategy/decision"
            ),
            "strategy_paper_trade": (
                "/api/strategy/paper-trade"
            ),
            "admin": "/api/admin",
            "websocket": "/ws/dashboard",
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
        initialized = await new_service.initialize()

        if not initialized:
            raise MT5ServiceError(
                "MT5 initialization returned false."
            )

        account = await new_service.get_account_info()
        terminal = await new_service.get_terminal_info()

        mt5_service = new_service

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

        safety_manager.mark_connection_lost()

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

        if status.get("connected"):
            safety_manager.record_heartbeat()
        else:
            safety_manager.mark_connection_lost()

        safety_status = safety_manager.status()

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
            "safety": {
                "trading_allowed": (
                    safety_status.trading_allowed
                ),
                "emergency_stop_active": (
                    safety_status.emergency_stop_active
                ),
                "connection_healthy": (
                    safety_status.connection_healthy
                ),
                "reason": safety_status.reason,
            },
        }

    except MT5ServiceError as exc:
        safety_manager.mark_connection_lost()
        raise mt5_error_response(exc) from exc


@app.get("/api/mt5/account")
async def get_mt5_account():
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
        tick = await mt5_service.get_symbol_tick(symbol)

        return {
            "status": "ok",
            "symbol": tick["symbol"],
            "bid": tick["bid"],
            "ask": tick["ask"],
            "last": tick["last"],
            "spread": tick["spread"],
            "volume": tick["volume"],
            "volume_real": tick["volume_real"],
            "time": tick["time"],
            "time_msc": tick["time_msc"],
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
        candles = await mt5_service.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
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
        symbols = await mt5_service.get_symbols(
            query=query
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
    """

    try:
        symbols = await mt5_service.find_gold_symbols()

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

    READ ONLY.
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
        default=200,
        ge=50,
        le=5000,
    ),
):
    """
    Calculate real technical indicators from MT5 OHLC candles.

    Indicators are calculated locally from read-only market data.
    No order is placed, modified, or closed by this endpoint.
    """

    try:
        candles = await mt5_service.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

        result = calculate_indicators(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
        )

        response = indicator_result_to_dict(result)
        response["timestamp"] = utc_timestamp()
        response["source"] = "mt5"
        return response

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc

    except (
        TechnicalIndicatorError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Technical indicator calculation failed",
                "message": str(exc),
                "timestamp": utc_timestamp(),
            },
        ) from exc


# ============================================================
# STEP 5 - PAPER TRADE EXECUTION GATEWAY
# ============================================================

@app.post("/api/trading/place-order")
async def place_order(
    order_data: dict,
):
    """
    STEP 5 - PAPER EXECUTION GATEWAY.

    No real broker order is placed.
    """

    logger.info(
        "Trade execution request received "
        "through Step 5 execution gateway."
    )

    try:
        symbol = str(
            order_data.get(
                "symbol",
                "",
            )
        ).strip()

        side_value = str(
            order_data.get(
                "side",
                order_data.get(
                    "direction",
                    "",
                ),
            )
        ).strip().lower()

        if side_value == "long":
            side_value = "buy"

        elif side_value == "short":
            side_value = "sell"

        order_type_value = str(
            order_data.get(
                "order_type",
                "market",
            )
        ).strip().lower()

        volume_value = order_data.get(
            "volume",
            order_data.get(
                "quantity",
                0.1,
            ),
        )

        price_value = order_data.get("price")
        stop_loss_value = order_data.get("stop_loss")
        take_profit_value = order_data.get("take_profit")
        client_order_id = order_data.get("client_order_id")

        order = OrderRequest(
            symbol=symbol,
            side=OrderSide(side_value),
            order_type=OrderType(order_type_value),
            volume=float(volume_value),
            price=(
                float(price_value)
                if price_value is not None
                else None
            ),
            stop_loss=(
                float(stop_loss_value)
                if stop_loss_value is not None
                else None
            ),
            take_profit=(
                float(take_profit_value)
                if take_profit_value is not None
                else None
            ),
            client_order_id=client_order_id,
        )

        # SAFETY GATE:
        # Emergency stop, connection loss, stale heartbeat,
        # or any other unsafe state blocks execution.
        safety_manager.require_trade_permission()

        result = await execution_gateway.execute(order)

        return {
            "order_id": result.order_id,
            "client_order_id": result.client_order_id,
            "status": result.status.value,
            "execution_type": result.execution_type,
            "broker": result.broker,
            "symbol": result.symbol,
            "side": result.side,
            "order_type": result.order_type,
            "volume": result.volume,
            "quantity": result.volume,
            "price": result.price,
            "stop_loss": result.stop_loss,
            "take_profit": result.take_profit,
            "timestamp": result.timestamp,
            "message": result.message,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid order request: {exc}",
        ) from exc

    except ExecutionGatewayError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


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

    READ ONLY.
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
# STEP 15 - STRATEGY / AI DECISION
# ============================================================

@app.get("/api/strategy/decision")
async def get_strategy_decision(
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
        default=200,
        ge=50,
        le=5000,
    ),
):
    """
    Run the real Step 13 AI decision pipeline.

    Path:

        MT5 candles
            ->
        Technical Indicators
            ->
        TechnicalContext
            ->
        Step 13 AI

    This endpoint does NOT execute a trade.
    """

    try:
        candles = await mt5_service.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

        decision = (
            trading_pipeline_service.evaluate_decision(
                symbol=symbol,
                timeframe=timeframe,
                candles=candles,
            )
        )

        response = (
            trading_pipeline_service.serialize_decision(
                decision
            )
        )

        response.update(
            {
                "timestamp": utc_timestamp(),
                "source": "step15_step13_ai",
                "execution": "none",
                "read_only": True,
                "live_trading_enabled": (
                    live_trading_enabled()
                ),
            }
        )

        return response

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc

    except TradingPipelineServiceError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Strategy decision pipeline failed",
                "message": str(exc),
                "timestamp": utc_timestamp(),
            },
        ) from exc


# ============================================================
# STEP 15 - COMPLETE PAPER TRADE PIPELINE
# ============================================================

@app.post("/api/strategy/paper-trade")
async def run_strategy_paper_trade(
    request: StrategyPaperTradeRequest,
):
    """
    Run the complete Step 15 paper-trading pipeline.

    Path:

        MT5 candles
            ->
        Technical Indicators
            ->
        Step 13 AI
            ->
        Step 14 Risk Engine
            ->
        PaperExecutionGateway

    IMPORTANT:
    - The client cannot choose the position size.
    - Risk Engine calculates the position size.
    - WAIT never reaches execution.
    - Risk rejection never reaches execution.
    - Live execution is impossible through this endpoint.
    """

    if live_trading_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "error": (
                    "Step 15 refuses to run while "
                    "LIVE_TRADING_ENABLED=true."
                ),
                "timestamp": utc_timestamp(),
            },
        )

    try:
        # ----------------------------------------------------
        # 1. Read real market candles from MT5.
        # ----------------------------------------------------

        candles = await mt5_service.get_candles(
            symbol=request.symbol,
            timeframe=request.timeframe,
            limit=request.limit,
        )

        # ----------------------------------------------------
        # 2. Read broker symbol specification.
        # ----------------------------------------------------

        raw_specification = (
            await mt5_service.get_symbol_specification(
                request.symbol
            )
        )

        specification = (
            build_symbol_specification(
                raw_specification
            )
        )

        # ----------------------------------------------------
        # 3. Build paper-only risk state.
        # ----------------------------------------------------

        risk_state = build_paper_risk_state()

        paper_equity = get_paper_equity()

        # ----------------------------------------------------
        # 4. Execute Step 13 -> Step 14 -> Paper Gateway.
        # ----------------------------------------------------

        result = (
            await trading_pipeline_service.execute_paper(
                symbol=request.symbol,
                timeframe=request.timeframe,
                candles=candles,
                specification=specification,
                account_equity=paper_equity,
                risk_state=risk_state,
            )
        )

        # ----------------------------------------------------
        # 5. Serialize the complete pipeline result.
        # ----------------------------------------------------

        response = (
            trading_pipeline_service.serialize_step14_result(
                result
            )
        )

        response.update(
            {
                "status": "ok",
                "timestamp": utc_timestamp(),
                "source": "step15",
                "execution_mode": "paper_only",
                "paper_equity": paper_equity,
                "risk_state": {
                    "daily_loss": risk_state.daily_loss,
                    "open_positions": (
                        risk_state.open_positions
                    ),
                    "total_exposure": (
                        risk_state.total_exposure
                    ),
                },
                "live_trading_enabled": False,
            }
        )

        return response

    except MT5ServiceError as exc:
        raise mt5_error_response(exc) from exc

    except TradingPipelineServiceError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Paper trading pipeline failed safely",
                "message": str(exc),
                "timestamp": utc_timestamp(),
            },
        ) from exc


# ============================================================
# BACKTEST
# ============================================================

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
# STEP 9A - DASHBOARD WEBSOCKET
# ============================================================

@app.websocket("/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
):
    """
    Read-only dashboard WebSocket.

    The dashboard receives:
    - market data
    - account data
    - positions
    - safety status
    - heartbeat messages

    This endpoint NEVER places or modifies trades.
    """

    await dashboard_ws_manager.connect(websocket)

    try:
        async def provider():
            return await build_dashboard_state(
                mt5_service=mt5_service,
                safety_manager=safety_manager,
                symbol="XAUUSD",
                live_trading_enabled=(
                    live_trading_enabled()
                ),
            )

        await dashboard_ws_manager.stream(
            websocket,
            provider=provider,
        )

    except Exception as exc:
        logger.info(
            "Dashboard WebSocket disconnected: %s",
            exc,
        )

    finally:
        dashboard_ws_manager.disconnect(websocket)


# ============================================================
# ADMIN / SAFETY
# ============================================================

@app.post("/api/admin/emergency-stop")
async def emergency_stop():
    """
    Activate the RAYMOND emergency stop.

    This blocks trading permission through the
    safety manager.

    It does NOT close existing broker positions.
    """

    status = safety_manager.activate_emergency_stop()

    logger.critical(
        "EMERGENCY STOP ACTIVATED"
    )

    return {
        "status": "emergency_stop_active",
        "timestamp": utc_timestamp(),
        "trading_allowed": status.trading_allowed,
        "emergency_stop_active": (
            status.emergency_stop_active
        ),
        "connection_healthy": (
            status.connection_healthy
        ),
        "reason": status.reason,
        "all_positions_closed": False,
        "new_orders_blocked": True,
        "live_trading_enabled": (
            live_trading_enabled()
        ),
    }


@app.post("/api/admin/emergency-stop/reset")
async def reset_emergency_stop():
    """
    Reset the emergency stop.

    The safety manager still requires a healthy,
    non-stale MT5 connection before trading can
    become permitted.
    """

    status = safety_manager.reset_emergency_stop()

    return {
        "status": "emergency_stop_reset",
        "timestamp": utc_timestamp(),
        "trading_allowed": status.trading_allowed,
        "emergency_stop_active": (
            status.emergency_stop_active
        ),
        "connection_healthy": (
            status.connection_healthy
        ),
        "reason": status.reason,
    }


@app.get("/api/admin/status")
async def admin_status():
    try:
        mt5_status = await mt5_service.heartbeat()

        if mt5_status.get("connected"):
            safety_manager.record_heartbeat()
        else:
            safety_manager.mark_connection_lost()

    except Exception:
        mt5_status = {
            "connected": False,
            "last_error": "MT5 unavailable",
        }

        safety_manager.mark_connection_lost()

    safety_status = safety_manager.status()

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
        "mt5_connected": (
            mt5_status.get(
                "connected",
                False,
            )
        ),
        "step15_pipeline": {
            "enabled": True,
            "execution_mode": "paper_only",
        },
        "safety": {
            "trading_allowed": (
                safety_status.trading_allowed
            ),
            "emergency_stop_active": (
                safety_status.emergency_stop_active
            ),
            "connection_healthy": (
                safety_status.connection_healthy
            ),
            "reason": safety_status.reason,
        },
        "dashboard_websocket_connections": (
            dashboard_ws_manager.connection_count
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


@app.exception_handler(EmergencyStopError)
async def emergency_stop_exception_handler(
    request,
    exc,
):
    logger.warning(
        "Trading blocked by safety gate: %s",
        exc,
    )

    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
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
