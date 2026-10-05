"""
RAYMOND v2.8 - Persistent Paper Account

PAPER / RESEARCH ONLY.

The account is derived exclusively from persistent Position records.

Economic accounting:

    realized partial PnL
    +
    final remaining-position PnL
    =
    total trade PnL
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .database import SessionLocal
from .models import Position, PositionStatus


PAPER_STARTING_BALANCE = 10_000.0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


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
    """
    Total economic PnL represented by a Position.

    For a position with partial closes:

        cumulative partial realized PnL
        +
        final/current remaining PnL
    """

    return (
        _partial_pnl(position)
        + _final_pnl(position)
    )


def _utc_day_start() -> datetime:
    now = datetime.now(timezone.utc)

    return now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _is_today(
    value: Any,
    start: datetime,
) -> bool:
    if value is None:
        return False

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value >= start


def build_persistent_paper_account() -> dict[str, float | str]:
    """
    Build the authoritative persistent paper account.

    OPEN:
        realized partial PnL contributes to balance.
        remaining PnL contributes to unrealized PnL.

    CLOSED:
        partial PnL + final PnL contributes to realized PnL.
    """

    db = SessionLocal()

    try:
        positions = db.query(Position).all()

        realized_pnl = 0.0
        unrealized_pnl = 0.0
        daily_realized_pnl = 0.0
        open_positions = 0

        day_start = _utc_day_start()

        for position in positions:

            partial_pnl = _partial_pnl(position)
            final_pnl = _final_pnl(position)

            if position.status == PositionStatus.OPEN:

                open_positions += 1

                # Partial closes are already realized.
                realized_pnl += partial_pnl

                # Remaining quantity is still unrealized.
                unrealized_pnl += final_pnl

                # The existing schema does not preserve a timestamp
                # for every partial-close event. Therefore we only
                # count the cumulative partial PnL in daily PnL when
                # the latest persisted management action is a partial
                # close today.
                if (
                    getattr(
                        position,
                        "last_management_action",
                        None,
                    )
                    == "PARTIAL_CLOSE"
                    and _is_today(
                        getattr(
                            position,
                            "last_management_time",
                            None,
                        ),
                        day_start,
                    )
                ):
                    daily_realized_pnl += partial_pnl

            elif position.status == PositionStatus.CLOSED:

                total_pnl = (
                    partial_pnl
                    + final_pnl
                )

                realized_pnl += total_pnl

                if _is_today(
                    getattr(
                        position,
                        "closed_at",
                        None,
                    ),
                    day_start,
                ):
                    daily_realized_pnl += total_pnl

        balance = (
            PAPER_STARTING_BALANCE
            + realized_pnl
        )

        equity = (
            balance
            + unrealized_pnl
        )

        return {
            "starting_balance": PAPER_STARTING_BALANCE,
            "balance": balance,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "equity": equity,
            "available_balance": balance,
            "daily_realized_pnl": daily_realized_pnl,
            "open_positions": float(open_positions),
            "execution_type": "paper",
            "live_trading_enabled": "false",
        }

    finally:
        db.close()


def get_persistent_paper_equity() -> float:
    account = build_persistent_paper_account()

    equity = _as_float(
        account["equity"]
    )

    if equity <= 0:
        raise RuntimeError(
            "Persistent paper equity must be greater than zero."
        )

    return equity
