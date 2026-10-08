"""
RAYMOND v2.8 - Canonical Paper Position Management API

Stage 17.2

This API is the execution-facing management layer for the
persistent paper-position system.

CANONICAL ACCOUNTING
--------------------
The database-backed Position records are the source of truth.

The API:
- reads persistent open positions,
- evaluates them through PaperPositionManager,
- updates current market price/P&L,
- applies paper-only management,
- persists management state,
- supports break-even,
- supports trailing-stop state,
- supports partial-close state,
- returns the resulting persistent position state.

SAFETY
------
This router is PAPER ONLY.

It NEVER:
- places broker orders,
- contacts MetaTrader 5 for execution,
- contacts Exness for execution,
- enables live trading,
- changes a real broker position,
- bypasses the Risk Engine,
- authorizes broker execution.

A market price is supplied by the caller.
That price is used only to manage the simulated persistent
paper position.
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


# ============================================================
# HELPERS
# ============================================================

def _utc() -> str:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """Safely convert a value to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """Safely convert a value to int."""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _enum_value(value: Any) -> Any:
    """Return enum.value when applicable."""
    if value is None:
        return None

    return getattr(
        value,
        "value",
        value,
    )


def _serialize_position(position: Any) -> dict[str, Any]:
    """
    Serialize the persistent Position model without assuming
    every optional management field exists.
    """

    if position is None:
        return {}

    opened_at = getattr(
        position,
        "opened_at",
        None,
    )

    closed_at = getattr(
        position,
        "closed_at",
        None,
    )

    last_management_time = getattr(
        position,
        "last_management_time",
        None,
    )

    return {
        "id": getattr(
            position,
            "id",
            None,
        ),
        "position_id": getattr(
            position,
            "position_id",
            None,
        ),
        "trade_id": getattr(
            position,
            "trade_id",
            None,
        ),
        "symbol": getattr(
            position,
            "symbol",
            None,
        ),
        "direction": _enum_value(
            getattr(
                position,
                "direction",
                None,
            )
        ),

        # ----------------------------------------------------
        # ORIGINAL TRADE
        # ----------------------------------------------------

        "entry_price": _safe_float(
            getattr(
                position,
                "entry_price",
                None,
            ),
            0.0,
        ),

        "original_quantity": _safe_float(
            getattr(
                position,
                "original_quantity",
                None,
            ),
            0.0,
        ),

        "initial_stop_loss": getattr(
            position,
            "initial_stop_loss",
            None,
        ),

        "take_profit_1": getattr(
            position,
            "take_profit_1",
            None,
        ),

        "take_profit_2": getattr(
            position,
            "take_profit_2",
            None,
        ),

        "risk_1r": getattr(
            position,
            "risk_1r",
            None,
        ),

        # ----------------------------------------------------
        # CURRENT POSITION
        # ----------------------------------------------------

        "current_price": getattr(
            position,
            "current_price",
            None,
        ),

        "current_stop_loss": getattr(
            position,
            "current_stop_loss",
            None,
        ),

        "remaining_quantity": getattr(
            position,
            "remaining_quantity",
            None,
        ),

        # Compatibility fields
        "quantity": getattr(
            position,
            "quantity",
            None,
        ),

        "stop_loss": getattr(
            position,
            "stop_loss",
            None,
        ),

        "take_profit": getattr(
            position,
            "take_profit",
            None,
        ),

        # ----------------------------------------------------
        # P&L
        # ----------------------------------------------------

        "pnl": getattr(
            position,
            "pnl",
            None,
        ),

        "pnl_percent": getattr(
            position,
            "pnl_percent",
            None,
        ),

        # ----------------------------------------------------
        # AI THESIS
        # ----------------------------------------------------

        "regime": getattr(
            position,
            "regime",
            None,
        ),

        "setup": getattr(
            position,
            "setup",
            None,
        ),

        "technical_score": getattr(
            position,
            "technical_score",
            None,
        ),

        "confluence": getattr(
            position,
            "confluence",
            None,
        ),

        "confidence": getattr(
            position,
            "confidence",
            None,
        ),

        "trade_thesis": getattr(
            position,
            "trade_thesis",
            None,
        ),

        # ----------------------------------------------------
        # MANAGEMENT
        # ----------------------------------------------------

        "break_even_applied": bool(
            getattr(
                position,
                "break_even_applied",
                False,
            )
        ),

        "partial_close_applied": bool(
            getattr(
                position,
                "partial_close_applied",
                False,
            )
        ),

        "trailing_active": bool(
            getattr(
                position,
                "trailing_active",
                False,
            )
        ),

        "management_status": getattr(
            position,
            "management_status",
            None,
        ),

        "last_management_action": getattr(
            position,
            "last_management_action",
            None,
        ),

        "last_management_time": (
            last_management_time.isoformat()
            if isinstance(
                last_management_time,
                datetime,
            )
            else last_management_time
        ),

        # ----------------------------------------------------
        # EXTREMES
        # ----------------------------------------------------

        "max_drawdown": getattr(
            position,
            "max_drawdown",
            None,
        ),

        "max_profit": getattr(
            position,
            "max_profit",
            None,
        ),

        # ----------------------------------------------------
        # STATUS / DATES
        # ----------------------------------------------------

        "status": _enum_value(
            getattr(
                position,
                "status",
                None,
            )
        ),

        "opened_at": (
            opened_at.isoformat()
            if isinstance(
                opened_at,
                datetime,
            )
            else opened_at
        ),

        "closed_at": (
            closed_at.isoformat()
            if isinstance(
                closed_at,
                datetime,
            )
            else closed_at
        ),
    }


def _serialize_result(
    result: Any,
) -> dict[str, Any]:
    """
    Serialize a PaperPositionManager result defensively.

    The manager's to_dict() remains the primary representation,
    while optional attributes are added when available.
    """

    if result is None:
        return {}

    if hasattr(
        result,
        "to_dict",
    ):
        try:
            data = result.to_dict()

            if isinstance(
                data,
                dict,
            ):
                return data

        except Exception:
            pass

    if isinstance(
        result,
        dict,
    ):
        return result

    return {
        "result": str(result),
    }


# ============================================================
# MANAGE PAPER POSITIONS
# ============================================================

@router.post(
    "/manage-paper-positions",
)
def manage_paper_positions_endpoint(
    symbol: str = Query(
        default="XAUUSD",
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
    Manage all persistent open paper positions for a symbol.

    The supplied current_price represents the latest market
    reference price.

    PaperPositionManager performs the actual persistent
    position-management logic.
    """

    normalized_symbol = (
        symbol.strip().upper()
    )

    if not normalized_symbol:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "symbol is required",
                "timestamp": _utc(),
            },
        )

    price = _safe_float(
        current_price,
        0.0,
    )

    if price <= 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "current_price must be greater than zero",
                "timestamp": _utc(),
            },
        )

    try:
        manager = PaperPositionManager(
            db
        )

        results = manager.evaluate_symbol(
            normalized_symbol,
            price,
        )

        serialized_results = [
            _serialize_result(result)
            for result in results
        ]

        return {
            "accepted": True,

            "stage": "17.2",

            "component": (
                "canonical_paper_position_management"
            ),

            "symbol": normalized_symbol,

            "current_price": price,

            "count": len(
                serialized_results
            ),

            "results": serialized_results,

            "accounting": {
                "source": (
                    "persistent_database_positions"
                ),
                "canonical": True,
                "balance_uses_realized_pnl": True,
                "equity_includes_unrealized_pnl": True,
            },

            "safety": {
                "paper_only": True,
                "live_trading_enabled": False,
                "execution_authorized": False,
                "broker_orders_allowed": False,
                "broker_position_modification_allowed": False,
                "mt5_execution_allowed": False,
                "exness_execution_allowed": False,
                "risk_engine_bypass": False,
            },

            "timestamp": _utc(),
        }

    except PaperPositionManagementError as exc:
        db.rollback()

        raise HTTPException(
            status_code=422,
            detail={
                "error": (
                    "Paper position management rejected"
                ),
                "message": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail={
                "error": (
                    "Paper position management failed"
                ),
                "message": str(exc),
                "timestamp": _utc(),
            },
        ) from exc


# ============================================================
# MANAGEMENT STATUS
# ============================================================

@router.get(
    "/paper-position-management/status",
)
def paper_position_management_status() -> dict[str, Any]:
    """
    Return management subsystem status.

    This endpoint performs no database writes.
    """

    return {
        "accepted": True,

        "stage": "17.2",

        "component": (
            "canonical_paper_position_management"
        ),

        "status": "available",

        "accounting": {
            "canonical_source": (
                "persistent_database_positions"
            ),
            "persistent": True,
        },

        "features": {
            "market_price_updates": True,
            "unrealized_pnl_updates": True,
            "break_even": True,
            "trailing_stop": True,
            "partial_close": True,
            "persistent_management_state": True,
        },

        "safety": {
            "paper_only": True,
            "live_trading_enabled": False,
            "execution_authorized": False,
            "broker_orders_allowed": False,
            "broker_position_modification_allowed": False,
            "mt5_execution_allowed": False,
            "exness_execution_allowed": False,
            "risk_engine_bypass": False,
        },

        "timestamp": _utc(),
    }


__all__ = [
    "router",
]
