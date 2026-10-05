"""
RAYMOND v2.8 - Persistent Paper Risk State

PAPER / RESEARCH ONLY.

This module reads persistent positions and never creates,
modifies, closes, or sends broker orders.

Accounting uses:

    cumulative partial-close realized PnL
    +
    final remaining-position PnL
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .database import SessionLocal
from .models import Position, PositionStatus
from .trading_pipeline_service import (
    PaperRiskState,
    TradingPipelineServiceError,
)


def _as_float(
    value: Any,
    default: float = 0.0,
) -> float:
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _partial_pnl(position: Position) -> float:
    return _as_float(
        getattr(
            position,
            "partial_close_pnl",
            None,
        )
    )


def _final_pnl(position: Position) -> float:
    return _as_float(
        getattr(
            position,
            "pnl",
            None,
        )
    )


def _total_trade_pnl(position: Position) -> float:
    return (
        _partial_pnl(position)
        + _final_pnl(position)
    )


def build_persistent_paper_risk_state() -> PaperRiskState:
    """
    Build authoritative paper-risk state.

    Open-position exposure remains based on the ORIGINAL
    persisted 1R price-distance and the CURRENT remaining
    quantity.

    Partial realized PnL is not counted as open exposure.
    """

    db = SessionLocal()

    try:

        open_positions = (
            db.query(Position)
            .filter(
                Position.status
                == PositionStatus.OPEN
            )
            .all()
        )

        open_count = len(
            open_positions
        )

        total_exposure = 0.0

        for position in open_positions:

            quantity = _as_float(
                getattr(
                    position,
                    "remaining_quantity",
                    None,
                )
            )

            if quantity <= 0:
                quantity = _as_float(
                    getattr(
                        position,
                        "original_quantity",
                        None,
                    )
                )

            risk_1r = _as_float(
                getattr(
                    position,
                    "risk_1r",
                    None,
                )
            )

            if quantity <= 0:
                raise TradingPipelineServiceError(
                    "Persistent open position has invalid quantity: "
                    f"{getattr(position, 'position_id', None)}"
                )

            if risk_1r <= 0:
                raise TradingPipelineServiceError(
                    "Persistent open position has invalid 1R risk: "
                    f"{getattr(position, 'position_id', None)}"
                )

            # XAUUSD:
            #
            # risk_1r is PRICE DISTANCE.
            #
            # 0.01 price movement × 1 lot = $1.
            #
            # Therefore:
            #
            # monetary risk =
            #     (risk_1r / 0.01) × quantity

            monetary_risk = (
                risk_1r / 0.01
            ) * quantity

            if monetary_risk <= 0:
                raise TradingPipelineServiceError(
                    "Calculated persistent paper exposure is invalid: "
                    f"{getattr(position, 'position_id', None)}"
                )

            total_exposure += monetary_risk

        # ----------------------------------------------------
        # DAILY REALIZED PNL
        # ----------------------------------------------------

        now_utc = datetime.now(
            timezone.utc
        )

        start_of_day = now_utc.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        closed_positions = (
            db.query(Position)
            .filter(
                Position.status
                == PositionStatus.CLOSED
            )
            .all()
        )

        daily_closed_pnl = 0.0

        for position in closed_positions:

            closed_at = getattr(
                position,
                "closed_at",
                None,
            )

            if closed_at is None:
                continue

            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(
                    tzinfo=timezone.utc
                )

            if closed_at >= start_of_day:
                daily_closed_pnl += (
                    _total_trade_pnl(
                        position
                    )
                )

        # An open position can already have realized PnL from a
        # partial close. The current schema only stores the latest
        # management timestamp, so we can safely attribute it to
        # today only when the latest action is PARTIAL_CLOSE today.
        for position in open_positions:

            action = getattr(
                position,
                "last_management_action",
                None,
            )

            management_time = getattr(
                position,
                "last_management_time",
                None,
            )

            if (
                action == "PARTIAL_CLOSE"
                and management_time is not None
            ):
                if management_time.tzinfo is None:
                    management_time = management_time.replace(
                        tzinfo=timezone.utc
                    )

                if management_time >= start_of_day:
                    daily_closed_pnl += _partial_pnl(
                        position
                    )

        daily_loss = max(
            0.0,
            -daily_closed_pnl,
        )

        return PaperRiskState(
            daily_loss=daily_loss,
            open_positions=open_count,
            total_exposure=total_exposure,
        )

    except TradingPipelineServiceError:
        raise

    except Exception as exc:
        raise TradingPipelineServiceError(
            "Unable to build persistent paper risk state: "
            f"{exc}"
        ) from exc

    finally:
        db.close()
