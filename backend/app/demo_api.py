"""
RAYMOND v2.8 - Demo Trading API

Step 10A:
- Exposes the demo/paper trading engine through FastAPI.
- Persists demo trades into the trade journal.
- Synchronizes demo trade updates with the journal.
- Provides demo performance metrics.
- Never places real broker orders.

SAFETY:
- This router is paper/demo only.
- No MT5 order API is called.
- No Exness live order API is called.
- Real-money execution is not supported.
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session


try:
    from .demo_trading import (
        DemoTradingEngine,
        DemoTradingError,
    )
    from .journal import (
        TradeJournal,
        TradeJournalError,
    )
    from .models import get_db
except ImportError:
    from demo_trading import (
        DemoTradingEngine,
        DemoTradingError,
    )
    from journal import (
        TradeJournal,
        TradeJournalError,
    )
    from models import get_db


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# DEMO ENGINE
# ============================================================

demo_engine = DemoTradingEngine(
    initial_balance=10_000.0,
    max_open_trades=3,
    max_daily_loss=300.0,
)


# ============================================================
# REQUEST MODELS
# ============================================================

class DemoTradeRequest(BaseModel):
    """Request to open a simulated paper trade."""

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=64,
    )

    direction: str = Field(
        ...,
        min_length=1,
        max_length=10,
    )

    entry_price: float = Field(
        ...,
        gt=0,
    )

    quantity: float = Field(
        ...,
        gt=0,
    )

    stop_loss: Optional[float] = Field(
        default=None,
        gt=0,
    )

    take_profit: Optional[float] = Field(
        default=None,
        gt=0,
    )


class DemoTradeCloseRequest(BaseModel):
    """Request to close a simulated paper trade."""

    exit_price: float = Field(
        ...,
        gt=0,
    )


# ============================================================
# SERIALIZATION
# ============================================================

def _json_safe_float(value: float) -> Optional[float]:
    """
    Return a JSON-safe float.

    Python can represent infinity and NaN, but strict JSON cannot.
    Non-finite values are therefore returned as None.
    """

    numeric = float(value)

    if not math.isfinite(numeric):
        return None

    return numeric


def serialize_demo_trade(trade) -> dict:
    """Convert a DemoTrade into a JSON-safe response."""

    return {
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_price": _json_safe_float(
            trade.entry_price
        ),
        "quantity": _json_safe_float(
            trade.quantity
        ),
        "stop_loss": (
            _json_safe_float(
                trade.stop_loss
            )
            if trade.stop_loss is not None
            else None
        ),
        "take_profit": (
            _json_safe_float(
                trade.take_profit
            )
            if trade.take_profit is not None
            else None
        ),
        "exit_price": (
            _json_safe_float(
                trade.exit_price
            )
            if trade.exit_price is not None
            else None
        ),
        "pnl": _json_safe_float(
            trade.pnl
        ),
        "status": trade.status,
        "execution_type": trade.execution_type,
        "opened_at": (
            trade.opened_at.isoformat()
            if trade.opened_at
            else None
        ),
        "closed_at": (
            trade.closed_at.isoformat()
            if trade.closed_at
            else None
        ),
    }


def serialize_performance(performance) -> dict:
    """Convert DemoPerformance into a JSON-safe response."""

    return {
        "total_trades": performance.total_trades,
        "winning_trades": performance.winning_trades,
        "losing_trades": performance.losing_trades,
        "open_trades": performance.open_trades,
        "win_rate": _json_safe_float(
            performance.win_rate
        ),
        "total_pnl": _json_safe_float(
            performance.total_pnl
        ),
        "gross_profit": _json_safe_float(
            performance.gross_profit
        ),
        "gross_loss": _json_safe_float(
            performance.gross_loss
        ),
        "profit_factor": _json_safe_float(
            performance.profit_factor
        ),
        "max_drawdown": _json_safe_float(
            performance.max_drawdown
        ),
        "expectancy": _json_safe_float(
            performance.expectancy
        ),
    }


def serialize_status(status: dict) -> dict:
    """Convert demo engine status into JSON-safe values."""

    result = dict(status)

    float_fields = {
        "win_rate",
        "total_pnl",
        "gross_profit",
        "gross_loss",
        "profit_factor",
        "max_drawdown",
        "expectancy",
        "daily_closed_pnl",
    }

    for field_name in float_fields:
        if (
            field_name in result
            and result[field_name] is not None
        ):
            result[field_name] = _json_safe_float(
                result[field_name]
            )

    return result


# ============================================================
# OPEN DEMO TRADE
# ============================================================

@router.post("/trades")
def open_demo_trade(
    request: DemoTradeRequest,
    db: Session = Depends(get_db),
):
    """
    Open a simulated paper trade.

    The trade is created in memory and then persisted
    into the paper-trade journal.

    No real broker order is placed.
    """

    journal = TradeJournal(db)

    try:
        trade = demo_engine.open_trade(
            symbol=request.symbol,
            direction=request.direction,
            entry_price=request.entry_price,
            quantity=request.quantity,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )

        try:
            journal.save_demo_trade(trade)
        except Exception:
            demo_engine.cancel_trade(
                trade.trade_id
            )
            raise

        return {
            "status": "opened",
            "mode": "demo",
            "execution_type": "paper",
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "trade": serialize_demo_trade(
                trade
            ),
        }

    except DemoTradingError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Demo trade rejected",
                "message": str(exc),
            },
        ) from exc

    except TradeJournalError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Demo trade journal failure",
                "message": str(exc),
            },
        ) from exc


# ============================================================
# CLOSE DEMO TRADE
# ============================================================

@router.post("/trades/{trade_id}/close")
def close_demo_trade(
    trade_id: str,
    request: DemoTradeCloseRequest,
    db: Session = Depends(get_db),
):
    """
    Close a simulated paper trade.

    No real broker order is placed.
    """

    normalized_trade_id = trade_id.strip()

    if not normalized_trade_id:
        raise HTTPException(
            status_code=400,
            detail="Trade ID cannot be empty.",
        )

    journal = TradeJournal(db)

    try:
        trade = demo_engine.close_trade(
            normalized_trade_id,
            request.exit_price,
        )

        journal.update_demo_trade(trade)

        return {
            "status": "closed",
            "mode": "demo",
            "execution_type": "paper",
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "trade": serialize_demo_trade(
                trade
            ),
        }

    except DemoTradingError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Demo trade close rejected",
                "message": str(exc),
            },
        ) from exc

    except TradeJournalError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Demo journal update failed",
                "message": str(exc),
            },
        ) from exc


# ============================================================
# LIST DEMO TRADES
# ============================================================

@router.get("/trades")
def list_demo_trades(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    """
    Return paper trades from the journal.

    Results are newest first.
    """

    journal = TradeJournal(db)

    try:
        trades, total = journal.list_trades(
            limit=limit,
            offset=offset,
            execution_type="paper",
        )

        serialized = [
            journal.serialize_trade(trade)
            for trade in trades
        ]

        return {
            "status": "ok",
            "mode": "demo",
            "execution_type": "paper",
            "live_trading_enabled": False,
            "trades": serialized,
            "count": len(serialized),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except TradeJournalError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Unable to list demo trades",
                "message": str(exc),
            },
        ) from exc


# ============================================================
# PERFORMANCE
# ============================================================

@router.get("/performance")
def demo_performance():
    """
    Return calculated demo performance metrics.
    """

    performance = demo_engine.performance()

    return {
        "status": "ok",
        "mode": "demo",
        "execution_type": "paper",
        "live_trading_enabled": False,
        "real_orders_allowed": False,
        "performance": serialize_performance(
            performance
        ),
    }


# ============================================================
# STATUS
# ============================================================

@router.get("/status")
def demo_status():
    """
    Return demo engine safety and status information.
    """

    return serialize_status(
        demo_engine.status()
    )


# ============================================================
# RESET
# ============================================================

@router.post("/reset")
def reset_demo_trading():
    """
    Reset the in-memory demo engine.

    This does NOT delete database journal records.

    It is intentionally separate from journal deletion.
    """

    demo_engine.reset()

    return {
        "status": "reset",
        "mode": "demo",
        "execution_type": "paper",
        "live_trading_enabled": False,
        "real_orders_allowed": False,
        "message": (
            "Demo engine reset. "
            "Existing journal records were not deleted."
        ),
    }
