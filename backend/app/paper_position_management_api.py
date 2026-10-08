"""
RAYMOND v2.8 - Canonical Paper Position Management API

Stage 17.2

Persistent paper-position management only.

The database-backed Position records remain the canonical source
of truth for paper positions and account state.

This router:
- receives the latest market price,
- evaluates persistent paper positions,
- persists management state,
- returns management results,
- exposes paper-accounting metadata,
- never executes broker orders.

LIVE TRADING IS DISABLED.
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
    """Return an ISO-8601 UTC timestamp."""
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


def _enum_value(value: Any) -> Any:
    """Return enum.value when an enum is supplied."""
    if value is None:
        return None

    return getattr(value, "value", value)


def _serialize_position(position: Any) -> dict[str, Any]:
    """Serialize a persistent Position defensively."""

    if position is None:
        return {}

    opened_at = getattr(position, "opened_at", None)
    closed_at = getattr(position, "closed_at", None)
    last_management_time = getattr(
        position,
        "last_management_time",
        None,
    )

    def timestamp(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    return {
        "id": getattr(position, "id", None),
        "position_id": getattr(position, "position_id", None),
        "trade_id": getattr(position, "trade_id", None),
        "symbol": getattr(position, "symbol", None),
        "direction": _enum_value(
            getattr(position, "direction", None)
        ),
        "entry_price": _safe_float(
            getattr(position, "entry_price", None)
        ),
        "original_quantity": _safe_float(
            getattr(position, "original_quantity", None)
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
        "last_management_time": timestamp(
            last_management_time
        ),
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
        "status": _enum_value(
            getattr(position, "status", None)
        ),
        "opened_at": timestamp(opened_at),
        "closed_at": timestamp(closed_at),
    }


def _serialize_result(result: Any) -> dict[str, Any]:
    """Serialize a management result."""

    if result is None:
        return {}

    if hasattr(result, "to_dict"):
        try:
            data = result.to_dict()

            if isinstance(data, dict):
                return data
        except Exception:
            pass

    if isinstance(result, dict):
        return result

    return {
        "result": str(result),
    }


def _safety_payload() -> dict[str, Any]:
    """
    Centralized hard safety declaration.

    Management remains simulated/persistent paper management.
    """
    return {
        "paper_only": True,
        "read_only": True,
        "live_trading_enabled": False,
        "execution_authorized": False,
        "broker_orders_allowed": False,
        "broker_position_modification_allowed": False,
        "mt5_execution_allowed": False,
        "exness_execution_allowed": False,
        "risk_engine_bypass": False,
    }


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
    Evaluate and persist management for open paper positions.

    No broker or live execution is performed.
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

    price = _safe_float(current_price)

    if price <= 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error": (
                    "current_price must be greater than zero"
                ),
                "timestamp": _utc(),
            },
        )

    try:
        manager = PaperPositionManager(db)

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
            "component": "paper_position_management_api",
            "symbol": normalized_symbol,
            "current_price": price,
            "count": len(serialized_results),
            "results": serialized_results,
            "accounting": {
                "source": (
                    "persistent_database_positions"
                ),
                "canonical": True,
                "balance_uses_realized_pnl": True,
                "equity_includes_unrealized_pnl": True,
            },
            "safety": _safety_payload(),
            "timestamp": _utc(),
        }

    except PaperPositionManagementError as exc:
        db.rollback()

        raise HTTPException(
            status_code=422,
            detail={
                "error": str(exc),
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
        "component": "paper_position_management_api",
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
        "safety": _safety_payload(),
        "timestamp": _utc(),
    }


__all__ = [
    "router",
    "manage_paper_positions_endpoint",
    "paper_position_management_status",
]
