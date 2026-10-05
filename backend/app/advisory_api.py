"""
RAYMOND v2.8 - Advisory Brain Analysis API

PURPOSE
-------
Expose the independent 8-brain advisory ensemble alongside the
existing RAYMOND Step 13 decision.

Also exposes the persistent PAPER position state required by
the Android trading terminal.

Also exposes a READ-ONLY historical XAUUSD P/L reconciliation
endpoint used to identify positions whose stored P/L was recorded
using the old pre-contract-size calculation.

SAFETY
------
All endpoints in this router are READ-ONLY.

They do NOT:
- place orders
- modify positions
- close positions
- contact MT5 for execution
- contact a broker
- bypass Step 14 Risk Engine
- replace Step 13
- enable live trading
- modify historical database P/L

The existing RAYMOND Step 13 decision remains authoritative.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

try:
    from .advisory_comparison import analyze_and_compare
    from .ai_trading_decision import (
        AIDecisionError,
        AITradingDecisionEngine,
    )
    from .database import get_db
    from .models import Position, PositionStatus
    from .online_market_api import (
        _context,
        _decision_payload,
        _fetch_chart,
    )
    from .position_repository import PositionRepository
    from .technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )
except ImportError:
    from advisory_comparison import analyze_and_compare
    from ai_trading_decision import (
        AIDecisionError,
        AITradingDecisionEngine,
    )
    from database import get_db
    from models import Position, PositionStatus
    from online_market_api import (
        _context,
        _decision_payload,
        _fetch_chart,
    )
    from position_repository import PositionRepository
    from technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )


router = APIRouter(
    prefix="/api/online",
    tags=["Advisory Analysis"],
)

_ai = AITradingDecisionEngine()

XAUUSD_CONTRACT_SIZE = 100.0


def _utc() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _enum_value(value: Any) -> Any:
    """
    Safely serialize enum-like values.
    """
    if hasattr(value, "value"):
        return value.value

    return value


def _datetime_value(value: Any) -> Any:
    """Serialize datetime values safely."""
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def _position_to_dict(
    position: Position,
) -> dict[str, Any]:
    """
    Serialize one persistent paper position.

    This deliberately exposes the complete trading-terminal
    state needed by the Android application.

    No execution action is performed here.
    """

    entry_price = (
        float(position.entry_price)
        if position.entry_price is not None
        else None
    )

    current_price = (
        float(position.current_price)
        if position.current_price is not None
        else entry_price
    )

    current_stop_loss = (
        position.current_stop_loss
        if position.current_stop_loss is not None
        else position.stop_loss
    )

    take_profit_1 = (
        position.take_profit_1
        if position.take_profit_1 is not None
        else position.take_profit
    )

    take_profit_2 = position.take_profit_2

    remaining_quantity = (
        position.remaining_quantity
        if position.remaining_quantity is not None
        else position.quantity
    )

    original_quantity = (
        position.original_quantity
        if position.original_quantity is not None
        else position.quantity
    )

    pnl = float(position.pnl or 0.0)

    pnl_percent = float(
        position.pnl_percent or 0.0
    )

    risk_1r = (
        float(position.risk_1r)
        if position.risk_1r is not None
        else None
    )

    current_r = 0.0

    if (
        entry_price is not None
        and current_price is not None
        and risk_1r is not None
        and risk_1r > 0
    ):
        direction = str(
            _enum_value(position.direction)
        ).lower()

        if direction == "buy":
            profit_distance = (
                current_price - entry_price
            )
        elif direction == "sell":
            profit_distance = (
                entry_price - current_price
            )
        else:
            profit_distance = 0.0

        current_r = (
            profit_distance / risk_1r
        )

    return {
        "id": position.id,
        "position_id": position.position_id,
        "trade_id": position.trade_id,

        "symbol": position.symbol,
        "direction": _enum_value(
            position.direction
        ),

        "status": _enum_value(
            position.status
        ),

        "execution_type": (
            position.execution_type
            if hasattr(position, "execution_type")
            else "paper"
        ),

        "entry_price": entry_price,
        "original_quantity": (
            float(original_quantity)
            if original_quantity is not None
            else None
        ),
        "initial_stop_loss": (
            float(position.initial_stop_loss)
            if position.initial_stop_loss is not None
            else None
        ),
        "take_profit_1": (
            float(take_profit_1)
            if take_profit_1 is not None
            else None
        ),
        "take_profit_2": (
            float(take_profit_2)
            if take_profit_2 is not None
            else None
        ),
        "risk_1r": risk_1r,

        "current_price": current_price,
        "current_stop_loss": (
            float(current_stop_loss)
            if current_stop_loss is not None
            else None
        ),
        "stop_loss": (
            float(current_stop_loss)
            if current_stop_loss is not None
            else None
        ),
        "take_profit": (
            float(take_profit_1)
            if take_profit_1 is not None
            else None
        ),
        "remaining_quantity": (
            float(remaining_quantity)
            if remaining_quantity is not None
            else None
        ),
        "quantity": (
            float(remaining_quantity)
            if remaining_quantity is not None
            else None
        ),

        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "current_r": current_r,
        "max_profit": float(
            position.max_profit or 0.0
        ),
        "max_drawdown": float(
            position.max_drawdown or 0.0
        ),

        "regime": position.regime,
        "setup": position.setup,
        "technical_score": (
            float(position.technical_score)
            if position.technical_score is not None
            else None
        ),
        "confluence": (
            float(position.confluence)
            if position.confluence is not None
            else None
        ),
        "confidence": (
            float(position.confidence)
            if position.confidence is not None
            else None
        ),
        "trade_thesis": position.trade_thesis,

        "break_even_applied": bool(
            position.break_even_applied
        ),
        "partial_close_applied": bool(
            position.partial_close_applied
        ),
        "trailing_active": bool(
            position.trailing_active
        ),
        "management_status": (
            position.management_status
        ),
        "last_management_action": (
            position.last_management_action
        ),
        "last_management_time": (
            _datetime_value(
                position.last_management_time
            )
        ),

        "opened_at": _datetime_value(
            position.opened_at
        ),
        "closed_at": _datetime_value(
            position.closed_at
        ),

        "paper_only": True,
        "read_only": True,
        "live_trading_enabled": False,
        "broker_orders_allowed": False,
    }


@router.get("/advisory-analysis")
async def advisory_analysis(
    symbol: str = Query(
        "XAUUSD",
        min_length=1,
        max_length=32,
    ),
    timeframe: str = Query(
        "H1",
        min_length=2,
        max_length=4,
    ),
    limit: int = Query(
        100,
        ge=60,
        le=500,
    ),
):
    """
    Run RAYMOND Step 13 and the independent 8-brain
    advisory ensemble, then compare their results.

    This endpoint is analysis-only.
    """

    data = await _fetch_chart(
        symbol,
        timeframe,
        limit,
    )

    try:
        indicators = calculate_indicators(
            symbol="XAUUSD",
            timeframe=data["timeframe"],
            candles=data["candles"],
        )

        context = _context(indicators)

        decision = _ai.evaluate(context)

        comparison = analyze_and_compare(
            decision=decision,
            context=context,
            candles=data["candles"],
        )

    except (
        TechnicalIndicatorError,
        AIDecisionError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    return {
        "accepted": True,

        "market": {
            "symbol": "XAUUSD",
            "timeframe": data["timeframe"],
            "price": data["price"],
        },

        "source": data["source"],
        "source_type": data.get(
            "source_type",
            "public_reference_feed",
        ),

        "indicators": indicator_result_to_dict(
            indicators
        ),

        "raymond": _decision_payload(
            decision
        ),

        "advisory_comparison": comparison,

        "safety": {
            "read_only": True,
            "advisory_only": True,
            "paper_trading_enabled": True,
            "live_trading_enabled": False,
            "execution_authorized": False,
            "broker_orders_allowed": False,
            "risk_engine_bypass": False,
            "step13_replaced": False,
        },

        "timestamp": _utc(),
    }


@router.get("/paper-positions")
def paper_positions(
    symbol: str | None = Query(
        None,
        min_length=1,
        max_length=32,
    ),
    status: str = Query(
        "open",
        min_length=1,
        max_length=32,
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    """
    Return persistent PAPER positions for the trading terminal.

    This endpoint is READ-ONLY.
    """

    try:
        normalized_status = (
            status.strip().lower()
        )

        if normalized_status == "open":
            positions = (
                PositionRepository.get_open_positions(
                    db
                )
            )

            if symbol:
                positions = [
                    position
                    for position in positions
                    if position.symbol.lower()
                    == symbol.lower()
                ]

            positions = positions[
                offset: offset + limit
            ]

        elif normalized_status in {
            "all",
            "*",
        }:
            positions = (
                PositionRepository.get_all(
                    db,
                    limit=limit,
                    offset=offset,
                )
            )

            if symbol:
                positions = [
                    position
                    for position in positions
                    if position.symbol.lower()
                    == symbol.lower()
                ]

        else:
            positions = (
                PositionRepository.get_all(
                    db,
                    limit=limit,
                    offset=offset,
                )
            )

            positions = [
                position
                for position in positions
                if str(
                    _enum_value(position.status)
                ).lower()
                == normalized_status
            ]

            if symbol:
                positions = [
                    position
                    for position in positions
                    if position.symbol.lower()
                    == symbol.lower()
                ]

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Unable to load paper positions",
                "message": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    return {
        "accepted": True,

        "positions": [
            _position_to_dict(position)
            for position in positions
        ],

        "count": len(positions),

        "query": {
            "symbol": symbol,
            "status": status,
            "limit": limit,
            "offset": offset,
        },

        "safety": {
            "read_only": True,
            "paper_only": True,
            "live_trading_enabled": False,
            "execution_authorized": False,
            "broker_orders_allowed": False,
            "risk_engine_bypass": False,
        },

        "timestamp": _utc(),
    }


@router.get("/paper-pnl-reconciliation")
def paper_pnl_reconciliation(
    symbol: str = Query(
        "XAUUSD",
        min_length=1,
        max_length=32,
    ),
    limit: int = Query(
        500,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    """
    READ-ONLY historical P/L reconciliation.

    Purpose
    -------
    Compare the P/L stored in historical PAPER positions against
    the corrected XAUUSD contract-size calculation.

    Standard XAUUSD assumption used by RAYMOND:

        1.00 lot = 100 oz

    Therefore:

        P/L = price movement × lot size × 100

    Example:

        BUY  2056 -> 2050 at 0.02 lot = -$12
        SELL 2056 -> 2050 at 0.02 lot = +$12

    IMPORTANT
    ---------
    This endpoint DOES NOT modify the database.

    It only reports:

        stored P/L
        corrected P/L
        difference

    Historical P/L values remain untouched.
    """

    normalized_symbol = symbol.strip().upper()

    if normalized_symbol != "XAUUSD":
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    "P/L reconciliation is currently "
                    "implemented for XAUUSD only."
                ),
                "symbol": normalized_symbol,
            },
        )

    contract_size = XAUUSD_CONTRACT_SIZE

    try:
        query = (
            db.query(Position)
            .filter(
                Position.status
                == PositionStatus.CLOSED
            )
            .filter(
                Position.symbol
                == normalized_symbol
            )
            .order_by(
                Position.closed_at.desc()
            )
        )

        positions = (
            query
            .offset(offset)
            .limit(limit)
            .all()
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": (
                    "Unable to load closed positions "
                    "for P/L reconciliation."
                ),
                "message": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    reconciled = []

    stored_pnl_total = 0.0
    corrected_pnl_total = 0.0
    pnl_difference_total = 0.0

    partial_close_review_count = 0

    for position in positions:
        entry_price = (
            float(position.entry_price)
            if position.entry_price is not None
            else None
        )

        exit_price = (
            float(position.current_price)
            if position.current_price is not None
            else None
        )

        quantity = (
            float(position.original_quantity)
            if position.original_quantity is not None
            else float(position.quantity or 0.0)
        )

        stored_pnl = float(
            position.pnl or 0.0
        )

        direction = str(
            _enum_value(position.direction)
        ).lower()

        partial_close_applied = bool(
            position.partial_close_applied
        )

        if partial_close_applied:
            partial_close_review_count += 1

        if (
            entry_price is None
            or exit_price is None
        ):
            corrected_pnl = None
            pnl_difference = None
            calculation_status = (
                "insufficient_price_data"
            )
        else:
            if direction == "buy":
                price_move = (
                    exit_price - entry_price
                )
            elif direction == "sell":
                price_move = (
                    entry_price - exit_price
                )
            else:
                price_move = 0.0

            corrected_pnl = (
                price_move
                * quantity
                * contract_size
            )

            pnl_difference = (
                corrected_pnl - stored_pnl
            )

            if partial_close_applied:
                calculation_status = (
                    "partial_close_manual_review"
                )
            else:
                calculation_status = (
                    "reconciled"
                )

            stored_pnl_total += stored_pnl
            corrected_pnl_total += corrected_pnl
            pnl_difference_total += pnl_difference

        reconciled.append(
            {
                "id": position.id,
                "position_id": position.position_id,
                "trade_id": position.trade_id,

                "symbol": position.symbol,
                "direction": direction,

                "status": _enum_value(
                    position.status
                ),

                "entry_price": entry_price,
                "recorded_exit_price": exit_price,
                "original_quantity": quantity,

                "stored_pnl": stored_pnl,
                "corrected_pnl": corrected_pnl,
                "pnl_difference": pnl_difference,

                "contract_size": contract_size,

                "partial_close_applied": (
                    partial_close_applied
                ),

                "calculation_status": (
                    calculation_status
                ),

                "opened_at": _datetime_value(
                    position.opened_at
                ),
                "closed_at": _datetime_value(
                    position.closed_at
                ),
            }
        )

    return {
        "accepted": True,

        "reconciliation": {
            "symbol": normalized_symbol,
            "contract_size": contract_size,
            "positions_reconciled": len(
                reconciled
            ),
            "partial_close_manual_review": (
                partial_close_review_count
            ),

            "stored_pnl_total": (
                round(stored_pnl_total, 10)
            ),

            "corrected_pnl_total": (
                round(corrected_pnl_total, 10)
            ),

            "pnl_difference_total": (
                round(pnl_difference_total, 10)
            ),

            "formula": (
                "price movement × original lot quantity "
                "× 100 contract size"
            ),
        },

        "positions": reconciled,

        "query": {
            "symbol": normalized_symbol,
            "limit": limit,
            "offset": offset,
        },

        "safety": {
            "read_only": True,
            "database_modified": False,
            "historical_pnl_modified": False,
            "strategy_modified": False,
            "paper_only": True,
            "live_trading_enabled": False,
            "execution_authorized": False,
            "broker_orders_allowed": False,
            "risk_engine_bypass": False,
        },

        "timestamp": _utc(),
    }


__all__ = [
    "router",
]
