"""Online deployment entrypoint for RAYMOND v2.8.

Stages started here:
- 17.4.3 lifecycle-aware paper-position market loop
- 17.5 automatic paper trade management
- 17.6 automatic paper entry worker

SAFETY:
- Paper trading only.
- No broker orders.
- No MT5 execution.
- No live trading.
- Stage 17.6 delegates risk, sizing, execution and persistence to the
  existing TradingPipelineService / Step 14 path.
"""

from datetime import datetime, timezone
import asyncio

from app.main import (
    app,
    build_symbol_specification,
    get_paper_equity,
)
from app.persistent_paper_risk import (
    build_persistent_paper_risk_state,
)
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
from app.automatic_entry_worker import (
    AutomaticEntryWorker,
    AutomaticEntryWorkerConfig,
)
from app.database import SessionLocal


# ---------------------------------------------------------------------------
# ROUTERS
# ---------------------------------------------------------------------------

app.include_router(online_market_router)
app.include_router(advisory_analysis_router)
app.include_router(paper_position_management_router)


# ---------------------------------------------------------------------------
# XAUUSD PAPER SYMBOL SPECIFICATION
# ---------------------------------------------------------------------------
#
# Stage 17.6 requires the same SymbolSpecification shape used by the existing
# Step 14 risk/execution pipeline. These values match the repository's tested
# XAUUSD paper specification.
# ---------------------------------------------------------------------------

_XAUUSD_SPECIFICATION = build_symbol_specification(
    {
        "symbol": "XAUUSD",
        "digits": 2,
        "point": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "tick_value_profit": 1.0,
        "tick_value_loss": 1.0,
        "contract_size": 100.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "volume_limit": 100.0,
        "trade_mode": 4,
        "trade_execution_mode": 0,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "currency_base": "XAU",
        "currency_profit": "USD",
        "currency_margin": "USD",
        "spread": 30,
        "spread_float": True,
    }
)


# ---------------------------------------------------------------------------
# STAGE 17.4.3
# LIFECYCLE-AWARE AUTOMATIC PAPER POSITION MARKET LOOP
# ---------------------------------------------------------------------------

_paper_market_loop = None
_paper_market_loop_db = None


async def _paper_market_price_provider(symbol: str) -> float:
    """Return the latest public market price. Never executes a trade."""

    market_data = await _fetch_price(symbol)
    price = market_data.get("price")

    if price is None:
        raise RuntimeError("Online market feed returned no usable price")

    return float(price)


# ---------------------------------------------------------------------------
# STAGE 17.5
# AUTOMATIC TRADE MANAGEMENT WORKER
# ---------------------------------------------------------------------------

_automatic_management_task = None


async def _automatic_trade_management_worker():
    """Run Stage 17.5 automatic paper-position management every 30 seconds."""

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

            results = await service.evaluate_open_positions()

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
                        f"position={result.position_id} {result.error}"
                    )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                "RAYMOND Stage 17.5: "
                "automatic management cycle failed safely: "
                f"{exc}"
            )

        finally:
            db.close()

        await asyncio.sleep(30.0)


# ---------------------------------------------------------------------------
# STAGE 17.6
# AUTOMATIC PAPER ENTRY WORKER
# ---------------------------------------------------------------------------
#
# Flow:
#
# Fresh XAUUSD M15 candles
#        -> existing indicators / AI decision engine
#        -> WAIT: do nothing
#        -> BUY/SELL: existing Step 14 risk + sizing
#        -> existing PaperExecutionGateway
#        -> existing persistence path
#
# This worker deliberately does NOT create positions directly and does NOT
# duplicate the risk engine.
# ---------------------------------------------------------------------------

_automatic_entry_worker = None


async def _automatic_entry_worker_task():
    """Run Stage 17.6 automatic paper entries every 30 seconds."""

    global _automatic_entry_worker

    config = AutomaticEntryWorkerConfig(
        symbol="XAUUSD",
        timeframe="M15",
        candle_limit=100,
        interval_seconds=30.0,
        enabled=True,
    )

    db = SessionLocal()

    try:
        _automatic_entry_worker = AutomaticEntryWorker(
            db=db,
            specification=_XAUUSD_SPECIFICATION,
            account_equity_provider=get_paper_equity,

            # IMPORTANT:
            # Stage 17.6 must use persistent Position records for:
            # - open-position count;
            # - monetary exposure;
            # - daily closed loss.
            #
            # Do NOT replace this with build_paper_risk_state.
            risk_state_provider=build_persistent_paper_risk_state,

            config=config,
        )

        await _automatic_entry_worker.run()

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        print(
            "RAYMOND Stage 17.6: "
            "automatic paper-entry worker failed safely: "
            f"{exc}"
        )

    finally:
        db.close()
        _automatic_entry_worker = None


_automatic_entry_task = None


# ---------------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def start_paper_position_market_loop():
    """Start all automatic paper-position and paper-entry workers."""

    global _paper_market_loop
    global _paper_market_loop_db
    global _automatic_management_task
    global _automatic_entry_task

    # ---------------------------------------------------------------
    # STAGE 17.4.3 EXISTING LIFECYCLE WORKER
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
    # STAGE 17.5 AUTOMATIC MANAGEMENT
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

    # ---------------------------------------------------------------
    # STAGE 17.6 AUTOMATIC ENTRY
    # ---------------------------------------------------------------

    if _automatic_entry_task is None or _automatic_entry_task.done():
        _automatic_entry_task = asyncio.create_task(
            _automatic_entry_worker_task()
        )

        print(
            "RAYMOND Stage 17.6: "
            "automatic paper-entry worker started "
            "(XAUUSD / M15 / 30s / PAPER ONLY)"
        )


# ---------------------------------------------------------------------------
# SHUTDOWN
# ---------------------------------------------------------------------------

@app.on_event("shutdown")
async def stop_paper_position_market_loop():
    """Stop all automatic paper workers cleanly."""

    global _paper_market_loop
    global _paper_market_loop_db
    global _automatic_management_task
    global _automatic_entry_task
    global _automatic_entry_worker

    # ---------------------------------------------------------------
    # STOP STAGE 17.6
    # ---------------------------------------------------------------

    if _automatic_entry_worker is not None:
        try:
            await _automatic_entry_worker.stop()
        except Exception as exc:
            print(
                "RAYMOND Stage 17.6: "
                f"worker stop warning: {exc}"
            )

    if _automatic_entry_task is not None:
        _automatic_entry_task.cancel()

        try:
            await _automatic_entry_task
        except asyncio.CancelledError:
            pass

        _automatic_entry_task = None

    _automatic_entry_worker = None

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

    print("RAYMOND: paper-position and paper-entry workers stopped")


# ---------------------------------------------------------------------------
# HEALTH
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health():
    """Lightweight Render health check with worker status."""

    return {
        "status": "healthy",
        "service": "raymond-v2-8-trader",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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

        "automatic_paper_entry": {
            "enabled": True,
            "running": (
                _automatic_entry_task is not None
                and not _automatic_entry_task.done()
            ),
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "interval_seconds": 30.0,
            "paper_only": True,
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
