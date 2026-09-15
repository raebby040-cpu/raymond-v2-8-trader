"""Online deployment entrypoint for RAYMOND v2.8."""

from datetime import datetime, timezone
import asyncio

from app.main import app
from app.online_market_api import (
    router as online_market_router,
    _fetch_price,
)
from app.advisory_api import router as advisory_analysis_router
from app.paper_position_management_api import (
    router as paper_position_management_router,
)
from app.paper_position_lifecycle_market_loop import (
    LifecycleAwarePaperPositionMarketLoop,
)
from app.paper_position_market_loop import (
    PaperPositionMarketLoopConfig,
)
from app.automatic_trade_management_service import (
    AutomaticTradeManagementService,
    AutomaticTradeManagementServiceConfig,
)
from app.database import SessionLocal


# ---------------------------------------------------------------------------
# ROUTERS
# ---------------------------------------------------------------------------

# Online public market-data and analysis routes.
app.include_router(online_market_router)

# Stage 16.4:
# 8-brain advisory comparison API.
app.include_router(advisory_analysis_router)

# Stage 17.2:
# Persistent paper-position management API.
#
# SAFETY:
# - Paper positions only.
# - No broker orders.
# - No MT5 execution.
# - Live trading remains disabled.
app.include_router(paper_position_management_router)


# ---------------------------------------------------------------------------
# STAGE 17.4.3
# LIFECYCLE-AWARE AUTOMATIC PAPER POSITION MARKET LOOP
# ---------------------------------------------------------------------------
#
# Existing worker:
#
# Public XAUUSD price
#        ↓
# Lifecycle engine
#        ↓
# SL / TP detection
#        ↓
# Persist closed positions
#        ↓
# Advanced paper-position management
#        ↓
# BE / trailing / partial management
#
# ---------------------------------------------------------------------------

_paper_market_loop = None
_paper_market_loop_db = None


async def _paper_market_price_provider(symbol: str) -> float:
    """
    Supply the automatic paper-position lifecycle/management loop
    with the latest public market price.

    SAFETY:
    - Public market data only.
    - No broker connection.
    - No MT5 execution.
    - No live trading.
    """

    market_data = await _fetch_price(symbol)

    price = market_data.get("price")

    if price is None:
        raise RuntimeError(
            "Online market feed returned no usable price"
        )

    return float(price)


# ---------------------------------------------------------------------------
# STAGE 17.5
# AUTOMATIC TRADE MANAGEMENT WORKER
# ---------------------------------------------------------------------------
#
# This worker is ADDITIVE.
#
# It does not replace Stage 17.4.3.
#
# Flow:
#
# Open paper position
#        ↓
# Fresh public XAUUSD candles
#        ↓
# Existing indicators / AI decision pipeline
#        ↓
# Automatic Trade Manager
#        ↓
# HOLD / CLOSE / MODIFY SL / MODIFY TP / MODIFY SL+TP
#        ↓
# Persist approved SL/TP modifications
#
# CLOSE is currently decision-only.
# Existing lifecycle closure remains authoritative.
#
# SAFETY:
# - PAPER ONLY
# - NO BROKER ORDERS
# - NO MT5
# - NO LIVE TRADING
# - NO NEW POSITION CREATION
# - NO RISK ENGINE BYPASS
# ---------------------------------------------------------------------------

_automatic_management_task = None


async def _automatic_trade_management_worker():
    """
    Run Stage 17.5 automatic management every 30 seconds.

    A fresh database session is created for every cycle.

    This is intentional:
    - prevents a long-lived SQLAlchemy session from becoming stale
    - isolates management commits/rollbacks
    - keeps this worker independent from the existing lifecycle worker
    """

    config = AutomaticTradeManagementServiceConfig(
        symbol="XAUUSD",
        timeframe="M15",
        candle_limit=100,
        enabled=True,
    )

    while True:
        db = SessionLocal()

        try:
            service = AutomaticTradeManagementService(
                db=db,
                config=config,
            )

            results = (
                await service.evaluate_open_positions()
            )

            for result in results:
                print(
                    "RAYMOND Stage 17.5: "
                    f"position={result.position_id} "
                    f"trade={result.trade_id} "
                    f"action={result.action} "
                    f"price={result.current_price} "
                    f"profit_r={result.profit_r:.3f} "
                    f"persisted={result.persisted} "
                    f"reason={result.reason}"
                )

                if result.error:
                    print(
                        "RAYMOND Stage 17.5 ERROR: "
                        f"position={result.position_id} "
                        f"{result.error}"
                    )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            # Management failure must never bring down the
            # Render web service or the existing lifecycle worker.
            print(
                "RAYMOND Stage 17.5: "
                "automatic management cycle failed safely: "
                f"{exc}"
            )

        finally:
            db.close()

        await asyncio.sleep(30.0)


@app.on_event("startup")
async def start_paper_position_market_loop():
    """
    Start both automatic paper-position workers.

    Stage 17.4.3:
        lifecycle + existing BE/trailing/partial management

    Stage 17.5:
        fresh market analysis + automatic trade management
    """

    global _paper_market_loop
    global _paper_market_loop_db
    global _automatic_management_task

    # ---------------------------------------------------------------
    # STAGE 17.4.3 EXISTING WORKER
    # ---------------------------------------------------------------

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    _paper_market_loop_db = SessionLocal()

    _paper_market_loop = LifecycleAwarePaperPositionMarketLoop(
        db=_paper_market_loop_db,
        price_provider=_paper_market_price_provider,
        config=config,
    )

    started = _paper_market_loop.start()

    if started:
        print(
            "RAYMOND Stage 17.4.3: "
            "lifecycle-aware paper-position market loop started "
            "(XAUUSD / 30s / PAPER ONLY)"
        )
    else:
        print(
            "RAYMOND Stage 17.4.3: "
            "lifecycle-aware paper-position market loop was not started"
        )

    # ---------------------------------------------------------------
    # STAGE 17.5 NEW WORKER
    # ---------------------------------------------------------------

    if (
        _automatic_management_task is None
        or _automatic_management_task.done()
    ):
        _automatic_management_task = asyncio.create_task(
            _automatic_trade_management_worker()
        )

        print(
            "RAYMOND Stage 17.5: "
            "automatic trade-management worker started "
            "(XAUUSD / M15 / 30s / PAPER ONLY)"
        )


@app.on_event("shutdown")
async def stop_paper_position_market_loop():
    """
    Stop all automatic paper-position workers cleanly.
    """

    global _paper_market_loop
    global _paper_market_loop_db
    global _automatic_management_task

    # ---------------------------------------------------------------
    # STOP STAGE 17.5
    # ---------------------------------------------------------------

    if _automatic_management_task is not None:
        _automatic_management_task.cancel()

        try:
            await _automatic_management_task
        except asyncio.CancelledError:
            pass

        _automatic_management_task = None

    # ---------------------------------------------------------------
    # STOP STAGE 17.4.3
    # ---------------------------------------------------------------

    if _paper_market_loop is not None:
        await _paper_market_loop.stop()
        _paper_market_loop = None

    if _paper_market_loop_db is not None:
        _paper_market_loop_db.close()
        _paper_market_loop_db = None

    print(
        "RAYMOND: "
        "paper-position workers stopped"
    )


# ---------------------------------------------------------------------------
# HEALTH
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health():
    """Lightweight health check for Render."""

    return {
        "status": "healthy",
        "service": "raymond-v2-8-trader",
        "timestamp": datetime.now(timezone.utc).isoformat(),

        # ---------------------------------------------------------------
        # SAFETY LOCK — LIVE TRADING REMAINS DISABLED.
        # ---------------------------------------------------------------
        "live_trading_enabled": False,

        "paper_trading_enabled": True,

        "paper_position_market_loop": {
            "enabled": True,
            "running": (
                _paper_market_loop.running
                if _paper_market_loop is not None
                else False
            ),
            "symbol": "XAUUSD",
            "interval_seconds": 30.0,
            "lifecycle_enabled": True,
        },

        "automatic_trade_management": {
            "enabled": True,
            "running": (
                _automatic_management_task is not None
                and not _automatic_management_task.done()
            ),
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "interval_seconds": 30.0,
            "close_execution_enabled": False,
        },

        "safety": {
            "paper_only": True,
            "read_only": True,
            "execution_authorized": False,
            "broker_orders_allowed": False,
            "mt5_execution_allowed": False,
            "risk_engine_bypass": False,
        },
}
