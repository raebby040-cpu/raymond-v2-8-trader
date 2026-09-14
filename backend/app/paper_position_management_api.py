"""
RAYMOND v2.8 - Paper Position Management API

Stage 17.2
Safe API integration for persistent paper-position management.

SAFETY
------
This router is PAPER ONLY.

It:
- evaluates persistent paper positions,
- updates persistent paper market price/P&L,
- applies safe paper management state,
- supports break-even,
- supports trailing-stop state,
- supports partial-close state.

It NEVER:
- places broker orders,
- contacts MetaTrader 5,
- contacts Exness,
- enables live trading,
- bypasses Step 14 Risk Engine,
- modifies a real broker position.

The existing /paper-positions endpoint remains READ-ONLY.
This endpoint is explicitly a PAPER MANAGEMENT operation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .paper_position_manager import (
        PaperPositionManagementError,
        PaperPositionManager,
    )
except ImportError:
    from database import get_db
    from paper_position_manager import (
        PaperPositionManagementError,
        PaperPositionManager,
    )


router = APIRouter(
    prefix="/api/online",
    tags=["Paper Position Management"],
)


def _utc() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


@router.post("/manage-paper-positions")
def manage_paper_positions_endpoint(
    symbol: str = Query(
        "XAUUSD",
        min_length=1,
        max_length=32,
    ),
    current_price: float = Query(
        ...,
        gt=0,
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Evaluate and safely manage all open paper positions for one symbol.

    This endpoint is intentionally explicit: the caller supplies the
    current market price and requests PAPER position management.

    No broker or MT5 execution is possible through this endpoint.
    """

    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "symbol is required",
                "timestamp": _utc(),
            },
        )

    try:
        manager = PaperPositionManager(db)

        results = manager.evaluate_symbol(
            normalized_symbol,
            float(current_price),
        )

        return {
            "accepted": True,
            "symbol": normalized_symbol,
            "current_price": float(current_price),
            "count": len(results),
            "results": [
                result.to_dict()
                for result in results
            ],
            "safety": {
                "paper_only": True,
                "read_only": True,
                "live_trading_enabled": False,
                "execution_authorized": False,
                "broker_orders_allowed": False,
                "mt5_execution_allowed": False,
                "risk_engine_bypass": False,
            },
            "timestamp": _utc(),
        }

    except PaperPositionManagementError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Paper position management failed",
                "message": str(exc),
                "timestamp": _utc(),
            },
        ) from exc


@router.get("/paper-position-management/status")
def paper_position_management_status() -> dict[str, Any]:
    """
    Return the hard safety declaration for Stage 17.2.

    This endpoint performs no database writes and no management action.
    """

    return {
        "accepted": True,
        "stage": "17.2",
        "component": "paper_position_management_api",
        "status": "available",
        "safety": {
            "paper_only": True,
            "read_only": True,
            "live_trading_enabled": False,
            "execution_authorized": False,
            "broker_orders_allowed": False,
            "mt5_execution_allowed": False,
            "risk_engine_bypass": False,
        },
        "timestamp": _utc(),
    }


__all__ = [
    "router",
]
