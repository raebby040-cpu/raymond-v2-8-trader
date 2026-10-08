"""
RAYMOND v2.8 - Canonical Trading State

Batch 1 - Canonical Trading State Foundation

This module establishes the persistent application-level
source of truth for Raymond trading positions and account state.

Architecture:

    PAPER / DEMO / LIVE execution
                |
                v
        CanonicalTradingPosition
                |
                v
       TradingStateRepository
                |
        +-------+-------+
        |               |
        v               v
    Flutter UI     Risk / Protection /
                   Reconciliation

IMPORTANT:

- This module does NOT place broker orders.
- This module does NOT modify MT5 positions.
- This module does NOT enable live trading.
- PAPER accounting is sourced from the persistent paper account.
- DEMO/LIVE account snapshots remain available through the
  canonical trading-state snapshot table.
- PostgreSQL remains the application persistence layer.
- MT5 remains authoritative for actual broker execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import Session

try:
    from .database import Base, SessionLocal
except ImportError:
    from database import Base, SessionLocal

try:
    from .persistent_paper_account import (
        build_persistent_paper_account,
    )
except ImportError:
    from persistent_paper_account import (
        build_persistent_paper_account,
    )


# ============================================================
# CONSTANTS
# ============================================================

XAUUSD_CONTRACT_SIZE = 100.0

VALID_MODES = {
    "paper",
    "demo",
    "live",
}

VALID_SIDES = {
    "buy",
    "sell",
}

VALID_STATUSES = {
    "open",
    "closing",
    "closed",
    "unknown",
}


# ============================================================
# TIME HELPERS
# ============================================================

def utc_now() -> datetime:
    """
    Return a timezone-aware UTC timestamp.
    """
    return datetime.now(timezone.utc)


# ============================================================
# DATABASE MODELS
# ============================================================

class CanonicalTradingPosition(Base):
    """
    Canonical persistent application state for one trading position.

    String values are intentionally used for mode/side/status so
    PAPER, DEMO and LIVE can evolve without destructive enum
    migrations.
    """

    __tablename__ = "canonical_trading_positions"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    canonical_id = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    # --------------------------------------------------------
    # EXECUTION IDENTITY
    # --------------------------------------------------------

    mode = Column(
        String,
        nullable=False,
        index=True,
    )

    broker_account_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    broker = Column(
        String,
        nullable=True,
    )

    platform = Column(
        String,
        nullable=True,
    )

    server = Column(
        String,
        nullable=True,
    )

    # --------------------------------------------------------
    # POSITION IDENTITY
    # --------------------------------------------------------

    symbol = Column(
        String,
        nullable=False,
        index=True,
    )

    side = Column(
        String,
        nullable=False,
    )

    status = Column(
        String,
        nullable=False,
        default="open",
        index=True,
    )

    # --------------------------------------------------------
    # VOLUME / PRICE
    # --------------------------------------------------------

    volume = Column(
        Float,
        nullable=False,
    )

    original_volume = Column(
        Float,
        nullable=False,
    )

    entry_price = Column(
        Float,
        nullable=False,
    )

    current_price = Column(
        Float,
        nullable=True,
    )

    stop_loss = Column(
        Float,
        nullable=True,
    )

    take_profit = Column(
        Float,
        nullable=True,
    )

    take_profit_1 = Column(
        Float,
        nullable=True,
    )

    take_profit_2 = Column(
        Float,
        nullable=True,
    )

    # --------------------------------------------------------
    # PNL
    # --------------------------------------------------------

    realized_pnl = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    unrealized_pnl = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    total_pnl = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    pnl_percent = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    current_r = Column(
        Float,
        nullable=True,
    )

    risk_1r = Column(
        Float,
        nullable=True,
    )

    # --------------------------------------------------------
    # MANAGEMENT STATE
    # --------------------------------------------------------

    break_even_applied = Column(
        Integer,
        nullable=False,
        default=0,
    )

    trailing_active = Column(
        Integer,
        nullable=False,
        default=0,
    )

    partial_close_applied = Column(
        Integer,
        nullable=False,
        default=0,
    )

    partial_close_quantity = Column(
        Float,
        nullable=True,
    )

    partial_close_price = Column(
        Float,
        nullable=True,
    )

    management_status = Column(
        String,
        nullable=False,
        default="open",
    )

    protection_status = Column(
        String,
        nullable=False,
        default="unknown",
    )

    reconciliation_status = Column(
        String,
        nullable=False,
        default="unknown",
    )

    # --------------------------------------------------------
    # BROKER IDENTIFIERS
    # --------------------------------------------------------

    broker_position_ticket = Column(
        String,
        nullable=True,
        index=True,
    )

    broker_order_ticket = Column(
        String,
        nullable=True,
    )

    broker_deal_ticket = Column(
        String,
        nullable=True,
    )

    client_order_id = Column(
        String,
        nullable=True,
        index=True,
    )

    strategy_signal_id = Column(
        String,
        nullable=True,
        index=True,
    )

    # --------------------------------------------------------
    # EXECUTION METADATA
    # --------------------------------------------------------

    magic = Column(
        Integer,
        nullable=True,
    )

    comment = Column(
        String,
        nullable=True,
    )

    # --------------------------------------------------------
    # THESIS / AUDIT
    # --------------------------------------------------------

    trade_thesis = Column(
        String,
        nullable=True,
    )

    last_error = Column(
        String,
        nullable=True,
    )

    # --------------------------------------------------------
    # TIMESTAMPS
    # --------------------------------------------------------

    opened_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    closed_at = Column(
        DateTime,
        nullable=True,
    )

    last_broker_sync = Column(
        DateTime,
        nullable=True,
    )

    last_price_update = Column(
        DateTime,
        nullable=True,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
    )


class TradingAccountSnapshot(Base):
    """
    Persistent account-level trading state.

    DEMO/LIVE may use this snapshot representation.

    PAPER does not use this table as its authoritative account
    calculation. PAPER is calculated directly from the persistent
    paper position/account system.
    """

    __tablename__ = "trading_account_snapshots"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    snapshot_id = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    mode = Column(
        String,
        nullable=False,
        index=True,
    )

    broker_account_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    broker = Column(
        String,
        nullable=True,
    )

    server = Column(
        String,
        nullable=True,
    )

    currency = Column(
        String,
        nullable=False,
        default="USD",
    )

    balance = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    equity = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    floating_pnl = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    realized_pnl = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    available_balance = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    margin = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    free_margin = Column(
        Float,
        nullable=False,
        default=0.0,
    )

    open_positions = Column(
        Integer,
        nullable=False,
        default=0,
    )

    last_error = Column(
        String,
        nullable=True,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
    )


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_mode(mode: str) -> str:
    value = str(mode).strip().lower()

    if value not in VALID_MODES:
        raise ValueError(
            f"Unsupported trading mode: {mode}"
        )

    return value


def normalize_side(side: str) -> str:
    value = str(side).strip().lower()

    if value not in VALID_SIDES:
        raise ValueError(
            f"Unsupported trading side: {side}"
        )

    return value


def normalize_status(status: str) -> str:
    value = str(status).strip().lower()

    if value not in VALID_STATUSES:
        raise ValueError(
            f"Unsupported trading status: {status}"
        )

    return value


# ============================================================
# ACCOUNTING
# ============================================================

def contract_size(symbol: str) -> float:
    """
    Return Raymond's canonical accounting contract size.

    XAUUSD:
        1.00 lot = 100 oz.
    """

    if str(symbol).upper() == "XAUUSD":
        return XAUUSD_CONTRACT_SIZE

    return 1.0


def calculate_unrealized_pnl(
    *,
    symbol: str,
    side: str,
    entry_price: float,
    current_price: Optional[float],
    volume: float,
) -> float:
    """
    Calculate floating P/L using canonical Raymond accounting.

    XAUUSD example:

        BUY 2051 -> 2056 at 0.02 lot

        (2056 - 2051) * 0.02 * 100
        = $10
    """

    if current_price is None:
        return 0.0

    movement = (
        float(current_price)
        - float(entry_price)
    )

    if normalize_side(side) == "sell":
        movement = -movement

    return (
        movement
        * float(volume)
        * contract_size(symbol)
    )


def calculate_pnl_percent(
    *,
    symbol: str,
    entry_price: float,
    volume: float,
    total_pnl: float,
) -> float:
    notional = (
        abs(float(entry_price))
        * float(volume)
        * contract_size(symbol)
    )

    if notional <= 0:
        return 0.0

    return (
        float(total_pnl)
        / notional
    ) * 100.0


def calculate_current_r(
    *,
    side: str,
    entry_price: float,
    current_price: Optional[float],
    risk_1r: Optional[float],
) -> Optional[float]:
    if current_price is None:
        return None

    if risk_1r is None:
        return None

    risk = abs(float(risk_1r))

    if risk <= 0:
        return None

    movement = (
        float(current_price)
        - float(entry_price)
    )

    if normalize_side(side) == "sell":
        movement = -movement

    return movement / risk


# ============================================================
# SERIALIZATION
# ============================================================

def serialize_position(
    position: CanonicalTradingPosition,
) -> dict[str, Any]:
    return {
        "canonical_id": position.canonical_id,
        "mode": position.mode,
        "broker_account_id": position.broker_account_id,
        "broker": position.broker,
        "platform": position.platform,
        "server": position.server,
        "symbol": position.symbol,
        "side": position.side,
        "status": position.status,
        "volume": float(position.volume or 0.0),
        "original_volume": float(
            position.original_volume or 0.0
        ),
        "entry_price": float(
            position.entry_price or 0.0
        ),
        "current_price": (
            float(position.current_price)
            if position.current_price is not None
            else None
        ),
        "stop_loss": position.stop_loss,
        "take_profit": position.take_profit,
        "take_profit_1": position.take_profit_1,
        "take_profit_2": position.take_profit_2,
        "realized_pnl": float(
            position.realized_pnl or 0.0
        ),
        "unrealized_pnl": float(
            position.unrealized_pnl or 0.0
        ),
        "total_pnl": float(
            position.total_pnl or 0.0
        ),
        "pnl_percent": float(
            position.pnl_percent or 0.0
        ),
        "current_r": position.current_r,
        "risk_1r": position.risk_1r,
        "break_even_applied": bool(
            position.break_even_applied
        ),
        "trailing_active": bool(
            position.trailing_active
        ),
        "partial_close_applied": bool(
            position.partial_close_applied
        ),
        "partial_close_quantity": (
            position.partial_close_quantity
        ),
        "partial_close_price": (
            position.partial_close_price
        ),
        "management_status": (
            position.management_status
        ),
        "protection_status": (
            position.protection_status
        ),
        "reconciliation_status": (
            position.reconciliation_status
        ),
        "broker_position_ticket": (
            position.broker_position_ticket
        ),
        "broker_order_ticket": (
            position.broker_order_ticket
        ),
        "broker_deal_ticket": (
            position.broker_deal_ticket
        ),
        "client_order_id": (
            position.client_order_id
        ),
        "strategy_signal_id": (
            position.strategy_signal_id
        ),
        "magic": position.magic,
        "comment": position.comment,
        "trade_thesis": position.trade_thesis,
        "last_error": position.last_error,
        "opened_at": (
            position.opened_at.isoformat()
            if position.opened_at
            else None
        ),
        "closed_at": (
            position.closed_at.isoformat()
            if position.closed_at
            else None
        ),
        "last_broker_sync": (
            position.last_broker_sync.isoformat()
            if position.last_broker_sync
            else None
        ),
        "last_price_update": (
            position.last_price_update.isoformat()
            if position.last_price_update
            else None
        ),
        "updated_at": (
            position.updated_at.isoformat()
            if position.updated_at
            else None
        ),
    }


def serialize_account(
    snapshot: TradingAccountSnapshot,
) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "mode": snapshot.mode,
        "broker_account_id": snapshot.broker_account_id,
        "broker": snapshot.broker,
        "server": snapshot.server,
        "currency": snapshot.currency,
        "balance": float(
            snapshot.balance or 0.0
        ),
        "equity": float(
            snapshot.equity or 0.0
        ),
        "floating_pnl": float(
            snapshot.floating_pnl or 0.0
        ),
        "realized_pnl": float(
            snapshot.realized_pnl or 0.0
        ),
        "available_balance": float(
            snapshot.available_balance or 0.0
        ),
        "margin": float(
            snapshot.margin or 0.0
        ),
        "free_margin": float(
            snapshot.free_margin or 0.0
        ),
        "open_positions": int(
            snapshot.open_positions or 0
        ),
        "last_error": snapshot.last_error,
        "updated_at": (
            snapshot.updated_at.isoformat()
            if snapshot.updated_at
            else None
        ),
    }


# ============================================================
# REPOSITORY
# ============================================================

class TradingStateRepository:
    """
    Canonical application-state repository.

    Application-level position mutations should eventually pass
    through this class.

    Broker execution code must not create a second competing
    persistent representation.
    """

    def __init__(self, db: Session):
        self.db = db

    # --------------------------------------------------------
    # POSITIONS
    # --------------------------------------------------------

    def get_position(
        self,
        canonical_id: str,
    ) -> Optional[CanonicalTradingPosition]:
        return (
            self.db.query(
                CanonicalTradingPosition
            )
            .filter(
                CanonicalTradingPosition.canonical_id
                == str(canonical_id)
            )
            .first()
        )

    def get_position_by_ticket(
        self,
        *,
        mode: str,
        broker_position_ticket: str,
    ) -> Optional[CanonicalTradingPosition]:
        return (
            self.db.query(
                CanonicalTradingPosition
            )
            .filter(
                CanonicalTradingPosition.mode
                == normalize_mode(mode),
                CanonicalTradingPosition.broker_position_ticket
                == str(broker_position_ticket),
            )
            .first()
        )

    def list_positions(
        self,
        *,
        mode: Optional[str] = None,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> list[CanonicalTradingPosition]:
        query = self.db.query(
            CanonicalTradingPosition
        )

        if mode:
            query = query.filter(
                CanonicalTradingPosition.mode
                == normalize_mode(mode)
            )

        if status:
            query = query.filter(
                CanonicalTradingPosition.status
                == normalize_status(status)
            )

        if symbol:
            query = query.filter(
                CanonicalTradingPosition.symbol
                == str(symbol).strip()
            )

        return (
            query
            .order_by(
                CanonicalTradingPosition.updated_at.desc()
            )
            .limit(
                max(
                    1,
                    min(int(limit), 500),
                )
            )
            .all()
        )

    def create_position(
        self,
        *,
        mode: str,
        symbol: str,
        side: str,
        volume: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        take_profit_1: Optional[float] = None,
        take_profit_2: Optional[float] = None,
        risk_1r: Optional[float] = None,
        realized_pnl: float = 0.0,
        broker_account_id: Optional[int] = None,
        broker: Optional[str] = None,
        platform: Optional[str] = None,
        server: Optional[str] = None,
        broker_position_ticket: Optional[str] = None,
        broker_order_ticket: Optional[str] = None,
        broker_deal_ticket: Optional[str] = None,
        client_order_id: Optional[str] = None,
        strategy_signal_id: Optional[str] = None,
        magic: Optional[int] = None,
        comment: Optional[str] = None,
        trade_thesis: Optional[str] = None,
    ) -> CanonicalTradingPosition:
        mode = normalize_mode(mode)
        side = normalize_side(side)

        volume = float(volume)

        if volume <= 0:
            raise ValueError(
                "Position volume must be greater than zero."
            )

        entry_price = float(entry_price)

        if entry_price <= 0:
            raise ValueError(
                "Position entry price must be greater than zero."
            )

        now = utc_now()

        position = CanonicalTradingPosition(
            canonical_id=(
                f"RAYMOND-{mode.upper()}-"
                f"{uuid4().hex}"
            ),
            mode=mode,
            broker_account_id=broker_account_id,
            broker=broker,
            platform=platform,
            server=server,
            symbol=str(symbol).strip(),
            side=side,
            status="open",
            volume=volume,
            original_volume=volume,
            entry_price=entry_price,
            current_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            take_profit_1=(
                take_profit_1
                if take_profit_1 is not None
                else take_profit
            ),
            take_profit_2=take_profit_2,
            realized_pnl=float(realized_pnl),
            unrealized_pnl=0.0,
            total_pnl=float(realized_pnl),
            pnl_percent=calculate_pnl_percent(
                symbol=str(symbol),
                entry_price=entry_price,
                volume=volume,
                total_pnl=float(realized_pnl),
            ),
            current_r=0.0,
            risk_1r=risk_1r,
            broker_position_ticket=(
                str(broker_position_ticket)
                if broker_position_ticket is not None
                else None
            ),
            broker_order_ticket=(
                str(broker_order_ticket)
                if broker_order_ticket is not None
                else None
            ),
            broker_deal_ticket=(
                str(broker_deal_ticket)
                if broker_deal_ticket is not None
                else None
            ),
            client_order_id=client_order_id,
            strategy_signal_id=strategy_signal_id,
            magic=magic,
            comment=comment,
            trade_thesis=trade_thesis,
            opened_at=now,
            last_broker_sync=(
                now
                if broker_position_ticket is not None
                else None
            ),
            last_price_update=now,
            updated_at=now,
        )

        self.db.add(position)
        self.db.commit()
        self.db.refresh(position)

        return position

    def update_market(
        self,
        position: CanonicalTradingPosition,
        *,
        current_price: float,
        broker_sync: bool = False,
    ) -> CanonicalTradingPosition:
        current_price = float(current_price)

        if current_price <= 0:
            raise ValueError(
                "Current market price must be greater than zero."
            )

        position.current_price = current_price

        position.unrealized_pnl = (
            calculate_unrealized_pnl(
                symbol=position.symbol,
                side=position.side,
                entry_price=position.entry_price,
                current_price=current_price,
                volume=position.volume,
            )
        )

        position.total_pnl = (
            float(position.realized_pnl or 0.0)
            + float(position.unrealized_pnl or 0.0)
        )

        position.pnl_percent = (
            calculate_pnl_percent(
                symbol=position.symbol,
                entry_price=position.entry_price,
                volume=position.volume,
                total_pnl=position.total_pnl,
            )
        )

        position.current_r = calculate_current_r(
            side=position.side,
            entry_price=position.entry_price,
            current_price=current_price,
            risk_1r=position.risk_1r,
        )

        now = utc_now()

        position.last_price_update = now

        if broker_sync:
            position.last_broker_sync = now

        position.updated_at = now

        self.db.commit()
        self.db.refresh(position)

        return position

    def update_management(
        self,
        position: CanonicalTradingPosition,
        *,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        volume: Optional[float] = None,
        break_even_applied: Optional[bool] = None,
        trailing_active: Optional[bool] = None,
        partial_close_applied: Optional[bool] = None,
        management_status: Optional[str] = None,
        protection_status: Optional[str] = None,
        reconciliation_status: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> CanonicalTradingPosition:
        if stop_loss is not None:
            position.stop_loss = float(stop_loss)

        if take_profit is not None:
            position.take_profit = float(take_profit)

        if volume is not None:
            volume = float(volume)

            if volume < 0:
                raise ValueError(
                    "Position volume cannot be negative."
                )

            position.volume = volume

        if break_even_applied is not None:
            position.break_even_applied = int(
                bool(break_even_applied)
            )

        if trailing_active is not None:
            position.trailing_active = int(
                bool(trailing_active)
            )

        if partial_close_applied is not None:
            position.partial_close_applied = int(
                bool(partial_close_applied)
            )

        if management_status is not None:
            position.management_status = str(
                management_status
            )

        if protection_status is not None:
            position.protection_status = str(
                protection_status
            )

        if reconciliation_status is not None:
            position.reconciliation_status = str(
                reconciliation_status
            )

        if last_error is not None:
            position.last_error = str(last_error)

        position.updated_at = utc_now()

        self.db.commit()
        self.db.refresh(position)

        return position

    def apply_partial_close(
        self,
        position: CanonicalTradingPosition,
        *,
        close_volume: float,
        execution_price: float,
    ) -> CanonicalTradingPosition:
        close_volume = float(close_volume)
        execution_price = float(execution_price)

        if close_volume <= 0:
            raise ValueError(
                "Partial-close volume must be greater than zero."
            )

        if close_volume > float(position.volume):
            raise ValueError(
                "Partial-close volume exceeds remaining "
                "position volume."
            )

        realized_delta = calculate_unrealized_pnl(
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            current_price=execution_price,
            volume=close_volume,
        )

        position.realized_pnl = (
            float(position.realized_pnl or 0.0)
            + realized_delta
        )

        position.volume = (
            float(position.volume)
            - close_volume
        )

        position.partial_close_applied = 1
        position.partial_close_quantity = close_volume
        position.partial_close_price = execution_price

        if position.volume <= 0:
            position.volume = 0.0
            position.status = "closed"
            position.closed_at = utc_now()
            position.unrealized_pnl = 0.0
        else:
            position.status = "open"
            position.unrealized_pnl = (
                calculate_unrealized_pnl(
                    symbol=position.symbol,
                    side=position.side,
                    entry_price=position.entry_price,
                    current_price=position.current_price,
                    volume=position.volume,
                )
            )

        position.total_pnl = (
            float(position.realized_pnl or 0.0)
            + float(position.unrealized_pnl or 0.0)
        )

        position.pnl_percent = (
            calculate_pnl_percent(
                symbol=position.symbol,
                entry_price=position.entry_price,
                volume=max(
                    float(position.volume),
                    0.00000001,
                ),
                total_pnl=position.total_pnl,
            )
        )

        position.updated_at = utc_now()

        self.db.commit()
        self.db.refresh(position)

        return position

    def close_position(
        self,
        position: CanonicalTradingPosition,
        *,
        execution_price: float,
    ) -> CanonicalTradingPosition:
        execution_price = float(execution_price)

        final_unrealized = calculate_unrealized_pnl(
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            current_price=execution_price,
            volume=position.volume,
        )

        position.realized_pnl = (
            float(position.realized_pnl or 0.0)
            + final_unrealized
        )

        position.unrealized_pnl = 0.0
        position.total_pnl = (
            float(position.realized_pnl or 0.0)
        )

        position.current_price = execution_price
        position.status = "closed"
        position.volume = 0.0
        position.closed_at = utc_now()
        position.last_price_update = utc_now()
        position.updated_at = utc_now()

        position.pnl_percent = (
            calculate_pnl_percent(
                symbol=position.symbol,
                entry_price=position.entry_price,
                volume=max(
                    float(position.original_volume),
                    0.00000001,
                ),
                total_pnl=position.total_pnl,
            )
        )

        self.db.commit()
        self.db.refresh(position)

        return position

    # --------------------------------------------------------
    # ACCOUNT SNAPSHOT
    # --------------------------------------------------------

    def get_latest_account(
        self,
        *,
        mode: str,
        broker_account_id: Optional[int] = None,
    ) -> Optional[TradingAccountSnapshot]:
        query = self.db.query(
            TradingAccountSnapshot
        ).filter(
            TradingAccountSnapshot.mode
            == normalize_mode(mode)
        )

        if broker_account_id is not None:
            query = query.filter(
                TradingAccountSnapshot.broker_account_id
                == int(broker_account_id)
            )

        return (
            query
            .order_by(
                TradingAccountSnapshot.updated_at.desc()
            )
            .first()
        )

    def upsert_account_snapshot(
        self,
        *,
        mode: str,
        balance: float,
        equity: float,
        floating_pnl: float,
        realized_pnl: float = 0.0,
        available_balance: Optional[float] = None,
        margin: float = 0.0,
        free_margin: Optional[float] = None,
        open_positions: int = 0,
        broker_account_id: Optional[int] = None,
        broker: Optional[str] = None,
        server: Optional[str] = None,
        currency: str = "USD",
        last_error: Optional[str] = None,
    ) -> TradingAccountSnapshot:
        mode = normalize_mode(mode)

        snapshot = self.get_latest_account(
            mode=mode,
            broker_account_id=broker_account_id,
        )

        now = utc_now()

        if snapshot is None:
            snapshot = TradingAccountSnapshot(
                snapshot_id=(
                    f"RAYMOND-ACCOUNT-{mode.upper()}-"
                    f"{uuid4().hex}"
                ),
                mode=mode,
                broker_account_id=broker_account_id,
            )
            self.db.add(snapshot)

        snapshot.broker = broker
        snapshot.server = server
        snapshot.currency = currency

        snapshot.balance = float(balance)
        snapshot.equity = float(equity)
        snapshot.floating_pnl = float(floating_pnl)
        snapshot.realized_pnl = float(realized_pnl)

        if available_balance is None:
            available_balance = float(balance)

        snapshot.available_balance = float(
            available_balance
        )

        snapshot.margin = float(margin)

        if free_margin is None:
            free_margin = (
                float(equity)
                - float(margin)
            )

        snapshot.free_margin = float(
            free_margin
        )

        snapshot.open_positions = int(
            open_positions
        )

        snapshot.last_error = last_error
        snapshot.updated_at = now

        self.db.commit()
        self.db.refresh(snapshot)

        return snapshot


# ============================================================
# FASTAPI ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/canonical",
    tags=["canonical-trading-state"],
)


# ============================================================
# POSITIONS
# ============================================================

@router.get("/positions")
def canonical_positions(
    mode: Optional[str] = Query(
        default=None,
    ),
    status: Optional[str] = Query(
        default=None,
    ),
    symbol: Optional[str] = Query(
        default=None,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
):
    """
    Read canonical Raymond positions.

    This endpoint is read-only.
    """

    db = SessionLocal()

    try:
        repository = TradingStateRepository(db)

        positions = repository.list_positions(
            mode=mode,
            status=status,
            symbol=symbol,
            limit=limit,
        )

        return {
            "status": "ok",
            "source_of_truth": (
                "raymond_canonical_trading_state"
            ),
            "positions": [
                serialize_position(position)
                for position in positions
            ],
        }

    finally:
        db.close()


@router.get("/positions/{canonical_id}")
def canonical_position(
    canonical_id: str,
):
    """
    Read one canonical position.

    This endpoint is read-only.
    """

    db = SessionLocal()

    try:
        repository = TradingStateRepository(db)

        position = repository.get_position(
            canonical_id
        )

        if position is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": (
                        "CANONICAL_POSITION_NOT_FOUND"
                    ),
                    "canonical_id": canonical_id,
                },
            )

        return {
            "status": "ok",
            "source_of_truth": (
                "raymond_canonical_trading_state"
            ),
            "position": serialize_position(
                position
            ),
        }

    finally:
        db.close()


# ============================================================
# ACCOUNT
# ============================================================

@router.get("/account/{mode}")
def canonical_account(
    mode: str,
    broker_account_id: Optional[int] = Query(
        default=None,
    ),
):
    """
    Return the canonical account state.

    PAPER:
        Calculated directly from the persistent paper account.

        balance = $1,000 + realized P&L
        equity  = balance + unrealized P&L

    DEMO/LIVE:
        Read from TradingAccountSnapshot.

    This prevents the Flutter PAPER dashboard from receiving
    stale account values from an unrelated snapshot row.
    """

    db = SessionLocal()

    try:
        try:
            normalized_mode = normalize_mode(mode)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "INVALID_TRADING_MODE",
                    "message": str(exc),
                },
            ) from exc

        # ====================================================
        # PAPER ACCOUNT
        # ====================================================
        #
        # PAPER is calculated from persistent paper positions.
        #
        # This is the authoritative paper accounting path.
        #
        if normalized_mode == "paper":
            account = build_persistent_paper_account(db)

            return {
                "status": "ok",
                "source_of_truth": (
                    "persistent_paper_positions"
                ),
                "account": account,
            }

        # ====================================================
        # DEMO / LIVE ACCOUNT
        # ====================================================

        repository = TradingStateRepository(db)

        snapshot = repository.get_latest_account(
            mode=normalized_mode,
            broker_account_id=broker_account_id,
        )

        if snapshot is None:
            return {
                "status": "ok",
                "source_of_truth": (
                    "raymond_canonical_trading_state"
                ),
                "account": None,
            }

        return {
            "status": "ok",
            "source_of_truth": (
                "raymond_canonical_trading_state"
            ),
            "account": serialize_account(
                snapshot
            ),
        }

    finally:
        db.close()


# ============================================================
# HEALTH
# ============================================================

@router.get("/health")
def canonical_health():
    return {
        "status": "ok",
        "canonical_state": True,
        "application_source_of_truth": (
            "postgresql_or_runtime_sqlalchemy_database"
        ),
        "paper_account_source_of_truth": (
            "persistent_paper_positions"
        ),
        "broker_reality_source": "mt5_broker",
        "live_trading_enabled": False,
    }


# ============================================================
# PUBLIC EXPORTS
# ============================================================

__all__ = [
    "CanonicalTradingPosition",
    "TradingAccountSnapshot",
    "TradingStateRepository",
    "calculate_unrealized_pnl",
    "calculate_pnl_percent",
    "calculate_current_r",
    "serialize_position",
    "serialize_account",
    "router",
]
