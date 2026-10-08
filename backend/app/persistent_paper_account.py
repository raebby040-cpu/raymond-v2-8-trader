"""
RAYMOND v2.8 - Canonical Persistent Paper Account

PAPER ONLY.

This module is the single accounting source for the Raymond
persistent paper-trading account.

ACCOUNTING RULES
----------------
Starting balance:
    $1,000.00

Balance:
    starting balance + realized P&L

Equity:
    balance + unrealized P&L

Open positions:
    contribute unrealized P&L to equity.

Closed positions:
    contribute realized P&L to balance.

Partial closes:
    their realized P&L contributes immediately to balance,
    while the remaining position continues contributing
    unrealized P&L to equity.

No second in-memory balance is used here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .database import SessionLocal
from .models import Position, PositionStatus


PAPER_STARTING_BALANCE = 1_000.0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _partial_pnl(position: Position) -> float:
    return _float(
        getattr(
            position,
            "partial_close_pnl",
            0.0,
        )
    )


def _remaining_pnl(position: Position) -> float:
    """
    PnL of the currently remaining quantity.

    Position.pnl is continuously recalculated from the
    current market price by PositionRepository.update_price().
    """
    return _float(
        getattr(
            position,
            "pnl",
            0.0,
        )
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
    day_start: datetime,
) -> bool:
    if value is None:
        return False

    if not isinstance(value, datetime):
        return False

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value >= day_start


def build_persistent_paper_account() -> dict[str, Any]:
    """
    Build the canonical persistent paper account.

    IMPORTANT:

    Open position PnL is NOT added to balance.

    It is added only to equity.

    Therefore:

        balance = $1,000 + realized PnL

        equity = balance + unrealized PnL
    """

    db = SessionLocal()

    try:
        positions = (
            db.query(Position)
            .all()
        )

        realized_pnl = 0.0
        unrealized_pnl = 0.0
        daily_realized_pnl = 0.0
        open_positions = 0

        day_start = _utc_day_start()

        for position in positions:

            partial_pnl = _partial_pnl(
                position
            )

            current_pnl = _remaining_pnl(
                position
            )

            status = getattr(
                position,
                "status",
                None,
            )

            if status == PositionStatus.OPEN:

                open_positions += 1

                # Partial closes have already become
                # realized money.
                realized_pnl += partial_pnl

                # The remaining position is still floating.
                unrealized_pnl += current_pnl

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
                    daily_realized_pnl += (
                        partial_pnl
                    )

            elif status == PositionStatus.CLOSED:

                # At closure, Position.pnl is the final PnL
                # of the remaining quantity.
                total_realized = (
                    partial_pnl
                    + current_pnl
                )

                realized_pnl += (
                    total_realized
                )

                if _is_today(
                    getattr(
                        position,
                        "closed_at",
                        None,
                    ),
                    day_start,
                ):
                    daily_realized_pnl += (
                        total_realized
                    )

        balance = (
            PAPER_STARTING_BALANCE
            + realized_pnl
        )

        equity = (
            balance
            + unrealized_pnl
        )

        return {
            "starting_balance": (
                PAPER_STARTING_BALANCE
            ),
            "balance": balance,
            "equity": equity,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "available_balance": balance,
            "daily_realized_pnl": (
                daily_realized_pnl
            ),
            "open_positions": open_positions,
            "execution_type": "paper",
            "mode": "paper",
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "canonical": True,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    finally:
        db.close()


def get_persistent_paper_equity() -> float:
    """
    Return live paper equity.

    This is the value that the Risk Engine should use
    when calculating the next paper position size.
    """

    account = (
        build_persistent_paper_account()
    )

    equity = _float(
        account["equity"]
    )

    if equity <= 0:
        raise RuntimeError(
            "Persistent paper equity must be greater than zero."
        )

    return equity


def get_persistent_paper_balance() -> float:
    """
    Return realized account balance.

    Floating PnL is deliberately excluded.
    """

    account = (
        build_persistent_paper_account()
    )

    balance = _float(
        account["balance"]
    )

    if balance <= 0:
        raise RuntimeError(
            "Persistent paper balance must be greater than zero."
        )

    return balance


__all__ = [
    "PAPER_STARTING_BALANCE",
    "build_persistent_paper_account",
    "get_persistent_paper_equity",
    "get_persistent_paper_balance",
]
