
"""
RAYMOND v2.8 - Trade Journal Persistence

Features:
- Persists demo/paper trades to the existing Trade table.
- Supports authenticated-user ownership filtering.
- Reads journal history safely.
- Keeps paper and live execution types explicit.
- Never sends orders to MT5, Exness, or any broker.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

try:
    from .demo_trading import DemoTrade
    from .models import Trade, TradeDirection, PositionStatus
except ImportError:
    from demo_trading import DemoTrade
    from models import Trade, TradeDirection, PositionStatus


class TradeJournalError(RuntimeError):
    """Raised when trade-journal persistence cannot continue safely."""


class TradeJournal:
    """Persistence adapter for the RAYMOND trade journal."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _direction(value: str) -> TradeDirection:
        normalized = value.lower().strip()

        if normalized == "buy":
            return TradeDirection.BUY

        if normalized == "sell":
            return TradeDirection.SELL

        raise TradeJournalError(
            "Trade direction must be 'buy' or 'sell'."
        )

    @staticmethod
    def _pnl_percent(
        entry_price: float,
        quantity: float,
        pnl: float,
    ) -> float:
        notional = abs(entry_price * quantity)

        if notional <= 0:
            return 0.0

        return (pnl / notional) * 100.0

    @staticmethod
    def _trade_query(
        db: Session,
        trade_id: str,
        owner_user_id: Optional[str] = None,
    ):
        """
        Find a trade by ID.

        When owner_user_id is supplied, the query is restricted
        to that owner. When omitted, legacy internal callers retain
        the previous global lookup behavior.

        Authenticated API routes must always supply owner_user_id.
        """
        query = db.query(Trade).filter(
            Trade.trade_id == trade_id
        )

        if owner_user_id is not None:
            query = query.filter(
                Trade.owner_user_id == owner_user_id
            )

        return query

    def save_demo_trade(
        self,
        trade: DemoTrade,
        owner_user_id: Optional[str] = None,
    ) -> Trade:
        """
        Create a persistent paper-trade journal row.

        Only paper/demo trades are accepted.

        Pass owner_user_id for a user-owned trade. Existing
        automated/internal callers may omit it while ownership
        is being wired through the remaining application.
        """
        if trade.execution_type != "paper":
            raise TradeJournalError(
                "TradeJournal only accepts paper trades."
            )

        existing = self._trade_query(
            self.db,
            trade.trade_id,
            owner_user_id,
        ).first()

        if existing is not None:
            return existing

        row = Trade(
            trade_id=trade.trade_id,
            owner_user_id=owner_user_id,
            symbol=trade.symbol,
            direction=self._direction(trade.direction),
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            pnl=trade.pnl,
            pnl_percent=self._pnl_percent(
                trade.entry_price,
                trade.quantity,
                trade.pnl,
            ),
            status=(
                PositionStatus.CLOSED
                if trade.status == "closed"
                else PositionStatus.OPEN
            ),
            execution_type="paper",
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            notes="RAYMOND demo/paper trade",
        )

        try:
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        except Exception:
            self.db.rollback()
            raise

        return row

    def update_demo_trade(
        self,
        trade: DemoTrade,
        owner_user_id: Optional[str] = None,
    ) -> Trade:
        """
        Persist the latest state of an existing demo trade.

        When owner_user_id is provided, only that user's row can
        be updated. A missing owned row is saved as a new owned row;
        this avoids silently claiming a legacy unowned row.
        """
        if trade.execution_type != "paper":
            raise TradeJournalError(
                "TradeJournal only accepts paper trades."
            )

        row = self._trade_query(
            self.db,
            trade.trade_id,
            owner_user_id,
        ).first()

        if row is None:
            return self.save_demo_trade(
                trade,
                owner_user_id=owner_user_id,
            )

        row.exit_price = trade.exit_price
        row.pnl = trade.pnl
        row.pnl_percent = self._pnl_percent(
            trade.entry_price,
            trade.quantity,
            trade.pnl,
        )
        row.status = (
            PositionStatus.CLOSED
            if trade.status == "closed"
            else PositionStatus.OPEN
        )
        row.closed_at = trade.closed_at

        try:
            self.db.commit()
            self.db.refresh(row)
        except Exception:
            self.db.rollback()
            raise

        return row

    def sync_demo_trade(
        self,
        trade: DemoTrade,
        owner_user_id: Optional[str] = None,
    ) -> Trade:
        """
        Insert a demo trade if missing, otherwise update its journal
        entry. Ownership is enforced whenever owner_user_id is given.
        """
        existing = self._trade_query(
            self.db,
            trade.trade_id,
            owner_user_id,
        ).first()

        if existing is None:
            return self.save_demo_trade(
                trade,
                owner_user_id=owner_user_id,
            )

        return self.update_demo_trade(
            trade,
            owner_user_id=owner_user_id,
        )

    def list_trades(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        execution_type: Optional[str] = None,
        owner_user_id: Optional[str] = None,
    ) -> tuple[list[Trade], int]:
        """
        Return persisted journal trades with pagination.

        Authenticated routes must pass owner_user_id. Supplying it
        excludes both other users' records and legacy rows whose
        owner_user_id is NULL.
        """
        if limit < 1 or limit > 500:
            raise TradeJournalError(
                "limit must be between 1 and 500."
            )

        if offset < 0:
            raise TradeJournalError(
                "offset cannot be negative."
            )

        query = self.db.query(Trade)

        if owner_user_id is not None:
            query = query.filter(
                Trade.owner_user_id == owner_user_id
            )

        if execution_type is not None:
            normalized = execution_type.lower().strip()

            if normalized not in {"paper", "live"}:
                raise TradeJournalError(
                    "execution_type must be 'paper' or 'live'."
                )

            query = query.filter(
                Trade.execution_type == normalized
            )

        total = query.count()

        rows = (
            query
            .order_by(Trade.opened_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return rows, total

    @staticmethod
    def serialize_trade(row: Trade) -> dict[str, Any]:
        """Convert a journal row into a safe API response."""

        direction = (
            row.direction.value
            if row.direction
            else None
        )

        status = (
            row.status.value
            if row.status
            else None
        )

        return {
            "trade_id": row.trade_id,
            "symbol": row.symbol,
            "direction": direction,
            "entry_price": row.entry_price,
            "exit_price": row.exit_price,
            "quantity": row.quantity,
            "pnl": row.pnl,
            "pnl_percent": row.pnl_percent,
            "status": status,
            "execution_type": row.execution_type,
            "opened_at": row.opened_at,
            "closed_at": row.closed_at,
            "stop_loss": row.stop_loss,
            "take_profit": row.take_profit,
            "notes": row.notes,
        }
