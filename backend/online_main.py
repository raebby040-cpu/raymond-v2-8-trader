"""
RAYMOND v2.8 - Online Application Entry Point

Production online runtime for the RAYMOND trading system.

This module:
- starts the FastAPI application;
- starts the online market-data worker;
- starts the lifecycle-aware paper-position market loop;
- starts the automatic paper-trade management worker;
- starts the automatic paper-entry worker;
- keeps all execution paper-only;
- uses persistent database-backed risk state for automatic entries.

LIVE TRADING IS DISABLED.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from app.automatic_entry_worker import (
    AutomaticEntryWorker,
    AutomaticEntryWorkerConfig,
)
from app.automatic_trade_management_service import (
    AutomaticTradeManagementService,
)
from app.database import SessionLocal
from app.main import (
    app,
    build_symbol_specification,
    get_paper_equity,
)
from app.online_market_api import (
    OnlineMarketDataError,
    fetch_online_market_chart,
)
from app.paper_position_lifecycle_market_loop import (
    PaperPositionLifecycleMarketLoop,
)
from app.persistent_paper_risk import (
    build_persistent_paper_risk_state,
)
from app.risk_engine import (
    SymbolSpecification,
)
from app.trading_pipeline_service import (
    TradingPipelineService,
)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=os.getenv(
        "LOG_LEVEL",
        "INFO",
    ).upper(),
)

# ---------------------------------------------------------------------------
# Production configuration
# ---------------------------------------------------------------------------

_SYMBOL = os.getenv(
    "RAYMOND_SYMBOL",
    "XAUUSD",
)

_TIMEFRAME = os.getenv(
    "RAYMOND_TIMEFRAME",
    "M15",
)

_MARKET_INTERVAL_SECONDS = float(
    os.getenv(
        "RAYMOND_MARKET_INTERVAL_SECONDS",
        "30",
    )
)

_AUTOMATIC_ENTRY_ENABLED = (
    os.getenv(
        "RAYMOND_AUTOMATIC_ENTRY_ENABLED",
        "true",
    ).strip().lower()
    in {
        "1",
        "true",
        "yes",
        "on",
    }
)

_AUTOMATIC_ENTRY_INTERVAL_SECONDS = float(
    os.getenv(
        "RAYMOND_AUTOMATIC_ENTRY_INTERVAL_SECONDS",
        "30",
    )
)

_AUTOMATIC_MANAGEMENT_INTERVAL_SECONDS = float(
    os.getenv(
        "RAYMOND_AUTOMATIC_MANAGEMENT_INTERVAL_SECONDS",
        "30",
    )
)

# ---------------------------------------------------------------------------
# XAUUSD specification
# ---------------------------------------------------------------------------

_XAUUSD_SPECIFICATION: SymbolSpecification = (
    build_symbol_specification(
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
)

# ---------------------------------------------------------------------------
# Shared services
# ---------------------------------------------------------------------------

_trading_pipeline_service = TradingPipelineService()

_automatic_trade_management_service = (
    AutomaticTradeManagementService(
        db=SessionLocal(),
        pipeline=_trading_pipeline_service,
        symbol=_SYMBOL,
        timeframe=_TIMEFRAME,
        interval_seconds=_AUTOMATIC_MANAGEMENT_INTERVAL_SECONDS,
    )
)

_paper_position_market_loop = (
    PaperPositionLifecycleMarketLoop(
        db=SessionLocal(),
        symbol=_SYMBOL,
        timeframe=_TIMEFRAME,
        interval_seconds=_MARKET_INTERVAL_SECONDS,
        trading_pipeline_service=_trading_pipeline_service,
    )
)

_automatic_entry_worker = AutomaticEntryWorker(
    db=SessionLocal(),
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

    config=AutomaticEntryWorkerConfig(
        symbol=_SYMBOL,
        timeframe=_TIMEFRAME,
        limit=100,
        interval_seconds=_AUTOMATIC_ENTRY_INTERVAL_SECONDS,
        enabled=_AUTOMATIC_ENTRY_ENABLED,
    ),
)

# ---------------------------------------------------------------------------
# Worker state
# ---------------------------------------------------------------------------

_market_worker_task: Optional[asyncio.Task] = None
_management_worker_task: Optional[asyncio.Task] = None
_entry_worker_task: Optional[asyncio.Task] = None
_position_market_worker_task: Optional[asyncio.Task] = None


# ---------------------------------------------------------------------------
# Online market worker
# ---------------------------------------------------------------------------


async def _online_market_worker() -> None:
    """
    Continuously fetch the live XAUUSD market chart.

    This worker is market-data only.

    It does not:
    - place orders;
    - bypass the risk engine;
    - modify the trading strategy;
    - enable live trading.
    """

    logger.info(
        "RAYMOND online market worker started: "
        "symbol=%s timeframe=%s interval=%.1fs",
        _SYMBOL,
        _TIMEFRAME,
        _MARKET_INTERVAL_SECONDS,
    )

    while True:
        try:
            await fetch_online_market_chart(
                symbol=_SYMBOL,
                timeframe=_TIMEFRAME,
                limit=100,
            )

        except asyncio.CancelledError:
            logger.info(
                "RAYMOND online market worker stopped"
            )
            raise

        except OnlineMarketDataError as exc:
            logger.warning(
                "Online market data error: %s",
                exc,
            )

        except Exception:
            logger.exception(
                "Unexpected online market worker error"
            )

        await asyncio.sleep(
            _MARKET_INTERVAL_SECONDS
        )


# ---------------------------------------------------------------------------
# Automatic management worker
# ---------------------------------------------------------------------------


async def _automatic_trade_management_worker() -> None:
    """
    Continuously manage open persistent paper positions.

    Stage 17.5 remains decision-only and paper-only.
    """

    logger.info(
        "RAYMOND automatic trade-management worker started: "
        "%s / %s / %.0fs / PAPER ONLY",
        _SYMBOL,
        _TIMEFRAME,
        _AUTOMATIC_MANAGEMENT_INTERVAL_SECONDS,
    )

    while True:
        try:
            await _automatic_trade_management_service.run_once()

        except asyncio.CancelledError:
            logger.info(
                "RAYMOND automatic trade-management worker stopped"
            )
            raise

        except Exception:
            logger.exception(
                "Automatic trade-management worker error"
            )

        await asyncio.sleep(
            _AUTOMATIC_MANAGEMENT_INTERVAL_SECONDS
        )


# ---------------------------------------------------------------------------
# Automatic paper-entry worker
# ---------------------------------------------------------------------------


async def _automatic_paper_entry_worker() -> None:
    """
    Continuously evaluate and, when authorized by all existing gates,
    create paper trades.

    Stage 17.6:
    - remains paper-only;
    - uses the existing RAYMOND decision engine;
    - uses the existing risk engine;
    - uses persistent Position records as authoritative risk state;
    - does not communicate with a live broker.
    """

    logger.info(
        "RAYMOND automatic paper-entry worker started: "
        "%s / %s / %.0fs / PAPER ONLY",
        _SYMBOL,
        _TIMEFRAME,
        _AUTOMATIC_ENTRY_INTERVAL_SECONDS,
    )

    while True:
        try:
            await _automatic_entry_worker.run_once()

        except asyncio.CancelledError:
            logger.info(
                "RAYMOND automatic paper-entry worker stopped"
            )
            raise

        except Exception:
            logger.exception(
                "Automatic paper-entry worker error"
            )

        await asyncio.sleep(
            _AUTOMATIC_ENTRY_INTERVAL_SECONDS
        )


# ---------------------------------------------------------------------------
# Persistent paper-position lifecycle market worker
# ---------------------------------------------------------------------------


async def _paper_position_lifecycle_worker() -> None:
    """
    Continuously evaluate persistent paper positions against market prices.

    This handles lifecycle events such as:
    - stop-loss;
    - take-profit;
    - break-even;
    - trailing;
    - partial-close management.

    It never places live broker orders.
    """

    logger.info(
        "RAYMOND paper-position lifecycle market worker started: "
        "%s / %s / %.0fs",
        _SYMBOL,
        _TIMEFRAME,
        _MARKET_INTERVAL_SECONDS,
    )

    while True:
        try:
            await _paper_position_market_loop.run_once()

        except asyncio.CancelledError:
            logger.info(
                "RAYMOND paper-position lifecycle market worker stopped"
            )
            raise

        except Exception:
            logger.exception(
                "Paper-position lifecycle worker error"
            )

        await asyncio.sleep(
            _MARKET_INTERVAL_SECONDS
        )


# ---------------------------------------------------------------------------
# FastAPI lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Start and stop all online workers with the FastAPI application.
    """

    global \
        _market_worker_task, \
        _management_worker_task, \
        _entry_worker_task, \
        _position_market_worker_task

    logger.info(
        "RAYMOND v2.8 online runtime starting"
    )

    logger.info(
        "LIVE TRADING DISABLED"
    )

    logger.info(
        "Paper trading enabled=True"
    )

    logger.info(
        "Automatic entry enabled=%s",
        _AUTOMATIC_ENTRY_ENABLED,
    )

    logger.info(
        "Persistent paper risk state enabled=True"
    )

    # Start online market-data worker.
    _market_worker_task = asyncio.create_task(
        _online_market_worker(),
        name="raymond-online-market-worker",
    )

    # Start lifecycle-aware persistent paper-position market worker.
    _position_market_worker_task = asyncio.create_task(
        _paper_position_lifecycle_worker(),
        name="raymond-paper-position-lifecycle-worker",
    )

    # Start automatic management worker.
    _management_worker_task = asyncio.create_task(
        _automatic_trade_management_worker(),
        name="raymond-automatic-trade-management-worker",
    )

    # Start automatic paper-entry worker.
    _entry_worker_task = asyncio.create_task(
        _automatic_paper_entry_worker(),
        name="raymond-automatic-paper-entry-worker",
    )

    try:
        yield

    finally:
        logger.info(
            "RAYMOND v2.8 online runtime shutting down"
        )

        tasks = [
            _market_worker_task,
            _position_market_worker_task,
            _management_worker_task,
            _entry_worker_task,
        ]

        for task in tasks:
            if task is not None:
                task.cancel()

        for task in tasks:
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception(
                        "Worker shutdown error"
                    )

        logger.info(
            "RAYMOND v2.8 online runtime stopped"
        )


# ---------------------------------------------------------------------------
# Attach lifecycle to existing FastAPI application
# ---------------------------------------------------------------------------

app.router.lifespan_context = lifespan


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "online_main:app",
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "8000",
            )
        ),
        reload=False,
    )
