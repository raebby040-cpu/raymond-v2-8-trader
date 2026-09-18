"""
RAYMOND v2.8 - Persistent Paper Risk State

Authoritative risk-state reader for the automatic paper-entry worker.

This module:
- reads persistent Position records;
- counts only OPEN persistent positions;
- calculates monetary risk exposure from the original 1R risk;
- calculates daily closed paper loss from persistent positions;
- never creates, modifies, or closes positions;
- never communicates with a broker;
- never enables live trading.
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


def _enum_value(value: Any) -> Any:
    if value is None:
        return None

    return getattr(value, "value", value)


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_persistent_paper_risk_state() -> PaperRiskState:
    """
    Build the authoritative paper-risk state from persistent positions.

    Open-position count and exposure MUST come from the persistent
    Position table because Stage 17.6 persists positions there.

    Exposure is monetary stop-loss risk, matching Step 14's model.
    """

    db = SessionLocal()

    try:
        open_positions = (
            db.query(Position)
            .filter(
                Position.status == PositionStatus.OPEN
            )
            .all()
        )

        open_count = len(open_positions)

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

            # Position.risk_1r is the original price-distance risk.
            #
            # The Position persistence layer stores quantity and risk_1r.
            # For XAUUSD the monetary exposure is derived using the same
            # tick model used by Step 14.
            #
            # XAUUSD specification:
            # tick_size = 0.01
            # tick_value_loss = 1.00
            #
            # Therefore:
            #     monetary risk =
            #         (risk_1r / 0.01) * 1.00 * quantity
            #
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
        # DAILY CLOSED P&L
        # ----------------------------------------------------

        now_utc = datetime.now(timezone.utc)

        start_of_day = now_utc.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        closed_positions = (
            db.query(Position)
            .filter(
                Position.status == PositionStatus.CLOSED
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

            # Database timestamps may be naive UTC datetimes.
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(
                    tzinfo=timezone.utc
                )

            if closed_at >= start_of_day:
                daily_closed_pnl += _as_float(
                    getattr(
                        position,
                        "pnl",
                        None,
                    )
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
