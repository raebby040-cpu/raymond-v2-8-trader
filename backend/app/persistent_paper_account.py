"""
RAYMOND v2.8 - Persistent Paper Account

Stage 19 establishes a persistent-source-of-truth account view.
The account is derived from persisted paper positions rather than
the in-memory DemoTradingEngine.

Live trading is never enabled by this module.
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


def _utc_day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _is_today(value: Any, start: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value >= start


def build_persistent_paper_account() -> dict[str, float | str]:
    """Build the authoritative paper account view from persisted positions."""
    db = SessionLocal()
    try:
        positions = db.query(Position).all()

        realized_pnl = 0.0
        unrealized_pnl = 0.0
        daily_realized_pnl = 0.0
        open_positions = 0
        day_start = _utc_day_start()

        for position in positions:
            pnl = _as_float(getattr(position, "pnl", None))

            if position.status == PositionStatus.OPEN:
                open_positions += 1
                unrealized_pnl += pnl
            elif position.status == PositionStatus.CLOSED:
                realized_pnl += pnl
                if _is_today(getattr(position, "closed_at", None), day_start):
                    daily_realized_pnl += pnl

        balance = PAPER_STARTING_BALANCE + realized_pnl
        equity = balance + unrealized_pnl

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
    equity = _as_float(account["equity"])
    if equity <= 0:
        raise RuntimeError("Persistent paper equity must be greater than zero.")
    return equity
