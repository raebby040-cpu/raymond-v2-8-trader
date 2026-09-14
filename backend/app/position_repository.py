"""
RAYMOND v2.8 - Persistent Position Repository

Stage 16.2
Persistent Position State

This repository provides the single persistence layer for the
authoritative Position model.

Responsibilities:
- Create persistent paper positions.
- Load positions by position_id or trade_id.
- Update live position state.
- Update management state.
- Close positions.
- Prevent duplicate position creation.
- Keep database transactions atomic.
- Work with both SQLite and PostgreSQL.

This module does NOT:
- place broker orders,
- modify MT5 positions,
- make trading decisions,
- calculate AI signals,
- bypass the Risk Engine,
- execute live trades.

It is a persistence layer only.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .models import (
        Position,
        PositionStatus,
        TradeDirection,
    )
except ImportError:
    from models import (
        Position,
        PositionStatus,
        TradeDirection,
    )


class PositionRepository:
    """
    Persistent CRUD/service layer for Position records.

    A caller supplies an existing SQLAlchemy Session.

    The repository commits successful mutations and rolls back
    failed mutations so a partially written position state is
    never intentionally left pending in the caller's session.
    """

    # ========================================================
    # NORMALIZATION HELPERS
    # ========================================================

    @staticmethod
    def _direction_value(direction) -> str:
        """
        Normalize TradeDirection or string direction to a string.
        """

        if isinstance(direction, TradeDirection):
            return direction.value

        return str(direction).lower()

    @staticmethod
    def _direction_enum(direction) -> TradeDirection:
        """
        Convert a direction value to TradeDirection.
        """

        if isinstance(direction, TradeDirection):
            return direction

        return TradeDirection(
            str(direction).lower()
        )

    @staticmethod
    def _status_enum(status) -> PositionStatus:
        """
        Convert a status value to PositionStatus.
        """

        if isinstance(status, PositionStatus):
            return status

        return PositionStatus(
            str(status).lower()
        )

    @staticmethod
    def _set_compatibility_fields(position: Position) -> None:
        """
        Keep legacy Position fields synchronized with the new
        Stage 16.2 fields.

        stop_loss    -> current_stop_loss
        take_profit  -> take_profit_1
        quantity     -> remaining_quantity
        """

        if position.current_stop_loss is not None:
            position.stop_loss = position.current_stop_loss

        elif position.initial_stop_loss is not None:
            position.stop_loss = position.initial_stop_loss

        if position.take_profit_1 is not None:
            position.take_profit = position.take_profit_1

        if position.remaining_quantity is not None:
            position.quantity = position.remaining_quantity

    @staticmethod
    def _calculate_pnl(
        position: Position,
        current_price: Optional[float],
    ) -> float:
        """
        Calculate paper unrealized PnL using price movement.

        This is a price-distance calculation. Broker-specific
        contract specifications remain the responsibility of the
        risk/execution layers.

        BUY:
            (current - entry) * quantity

        SELL:
            (entry - current) * quantity
        """

        if current_price is None:
            return float(position.pnl or 0.0)

        quantity = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )

        if quantity is None:
            return 0.0

        direction = PositionRepository._direction_value(
            position.direction
        )

        if direction == TradeDirection.BUY.value:
            return (
                float(current_price)
                - float(position.entry_price)
            ) * float(quantity)

        return (
            float(position.entry_price)
            - float(current_price)
        ) * float(quantity)

    @staticmethod
    def _calculate_pnl_percent(
        position: Position,
        pnl: float,
    ) -> float:
        """
        Calculate PnL percentage relative to entry notional.
        """

        quantity = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )

        if not quantity:
            return 0.0

        entry_notional = (
            abs(float(position.entry_price))
            * float(quantity)
        )

        if entry_notional == 0:
            return 0.0

        return (
            float(pnl)
            / entry_notional
        ) * 100.0

    @staticmethod
    def _update_profit_extremes(
        position: Position,
        pnl: float,
    ) -> None:
        """
        Track maximum profit and maximum drawdown.

        max_profit is stored as the highest observed PnL.

        max_drawdown is stored as a non-negative magnitude of the
        worst observed negative PnL.
        """

        current_max_profit = float(
            position.max_profit or 0.0
        )

        if pnl > current_max_profit:
            position.max_profit = pnl

        current_max_drawdown = float(
            position.max_drawdown or 0.0
        )

        if pnl < 0:
            drawdown = abs(pnl)

            if drawdown > current_max_drawdown:
                position.max_drawdown = drawdown

    # ========================================================
    # CREATE
    # ========================================================

    @staticmethod
    def create(
        db: Session,
        *,
        position_id: str,
        trade_id: Optional[str],
        symbol: str,
        direction,
        entry_price: float,
        original_quantity: float,
        initial_stop_loss: Optional[float],
        take_profit_1: Optional[float],
        take_profit_2: Optional[float] = None,
        risk_1r: Optional[float] = None,
        regime: Optional[str] = None,
        setup: Optional[str] = None,
        technical_score: Optional[float] = None,
        confluence: Optional[float] = None,
        confidence: Optional[float] = None,
        current_price: Optional[float] = None,
        management_status: str = "open",
    ) -> Position:
        """
        Create one persistent Position.

        Idempotency:
        - position_id must be unique.
        - trade_id must be unique when supplied.

        If either identifier already exists, the existing position
        is returned instead of creating a duplicate.
        """

        existing = None

        if trade_id:
            existing = (
                db.query(Position)
                .filter(
                    Position.trade_id == trade_id
                )
                .first()
            )

        if existing is None:
            existing = (
                db.query(Position)
                .filter(
                    Position.position_id == position_id
                )
                .first()
            )

        if existing is not None:
            return existing

        direction_enum = PositionRepository._direction_enum(
            direction
        )

        if risk_1r is None and initial_stop_loss is not None:
            risk_1r = abs(
                float(entry_price)
                - float(initial_stop_loss)
            )

        if current_price is None:
            current_price = float(entry_price)

        position = Position(
            position_id=position_id,
            trade_id=trade_id,
            symbol=symbol,
            direction=direction_enum,

            quantity=float(original_quantity),

            entry_price=float(entry_price),
            original_quantity=float(original_quantity),

            initial_stop_loss=(
                float(initial_stop_loss)
                if initial_stop_loss is not None
                else None
            ),

            take_profit_1=(
                float(take_profit_1)
                if take_profit_1 is not None
                else None
            ),

            take_profit_2=(
                float(take_profit_2)
                if take_profit_2 is not None
                else None
            ),

            risk_1r=(
                float(risk_1r)
                if risk_1r is not None
                else None
            ),

            current_price=float(current_price),

            current_stop_loss=(
                float(initial_stop_loss)
                if initial_stop_loss is not None
                else None
            ),

            remaining_quantity=float(original_quantity),

            stop_loss=(
                float(initial_stop_loss)
                if initial_stop_loss is not None
                else None
            ),

            take_profit=(
                float(take_profit_1)
                if take_profit_1 is not None
                else None
            ),

            pnl=0.0,
            pnl_percent=0.0,

            regime=regime,
            setup=setup,
            technical_score=technical_score,
            confluence=confluence,
            confidence=confidence,

            break_even_applied=0,
            partial_close_applied=0,
            trailing_active=0,

            management_status=management_status,
            last_management_action="OPEN",
            last_management_time=datetime.utcnow(),

            max_drawdown=0.0,
            max_profit=0.0,

            status=PositionStatus.OPEN,

            opened_at=datetime.utcnow(),
            closed_at=None,
        )

        try:
            db.add(position)
            db.commit()
            db.refresh(position)

            return position

        except IntegrityError:
            db.rollback()

            # Another request/process may have created the same
            # position between our lookup and commit.
            existing = None

            if trade_id:
                existing = (
                    db.query(Position)
                    .filter(
                        Position.trade_id == trade_id
                    )
                    .first()
                )

            if existing is None:
                existing = (
                    db.query(Position)
                    .filter(
                        Position.position_id == position_id
                    )
                    .first()
                )

            if existing is not None:
                return existing

            raise

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # READ
    # ========================================================

    @staticmethod
    def get_by_position_id(
        db: Session,
        position_id: str,
    ) -> Optional[Position]:
        """
        Load one position by its persistent position_id.
        """

        return (
            db.query(Position)
            .filter(
                Position.position_id == position_id
            )
            .first()
        )

    @staticmethod
    def get_by_trade_id(
        db: Session,
        trade_id: str,
    ) -> Optional[Position]:
        """
        Load one position by paper execution/order ID.
        """

        return (
            db.query(Position)
            .filter(
                Position.trade_id == trade_id
            )
            .first()
        )

    @staticmethod
    def get_open_positions(
        db: Session,
    ) -> list[Position]:
        """
        Return all currently open positions.
        """

        return (
            db.query(Position)
            .filter(
                Position.status == PositionStatus.OPEN
            )
            .order_by(
                Position.opened_at.asc()
            )
            .all()
        )

    @staticmethod
    def get_all(
        db: Session,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Position]:
        """
        Return persistent positions ordered by newest first.
        """

        return (
            db.query(Position)
            .order_by(
                Position.opened_at.desc()
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    # ========================================================
    # LIVE PRICE UPDATE
    # ========================================================

    @staticmethod
    def update_price(
        db: Session,
        position_id: str,
        current_price: float,
    ) -> Optional[Position]:
        """
        Persist a new market price and recalculate paper PnL.

        This does NOT close a position or move its stop.
        """

        position = PositionRepository.get_by_position_id(
            db,
            position_id,
        )

        if position is None:
            return None

        if position.status != PositionStatus.OPEN:
            return position

        price = float(current_price)

        position.current_price = price

        pnl = PositionRepository._calculate_pnl(
            position,
            price,
        )

        position.pnl = pnl
        position.pnl_percent = (
            PositionRepository._calculate_pnl_percent(
                position,
                pnl,
            )
        )

        PositionRepository._update_profit_extremes(
            position,
            pnl,
        )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # STOP-LOSS UPDATE
    # ========================================================

    @staticmethod
    def update_stop_loss(
        db: Session,
        position_id: str,
        new_stop_loss: float,
        *,
        management_action: str = "UPDATE_STOP_LOSS",
        management_status: Optional[str] = None,
    ) -> Optional[Position]:
        """
        Persist a new current stop-loss.

        initial_stop_loss is NEVER changed.

        This distinction is critical because risk 1R must remain
        based on the original trade risk, not a later moved stop.
        """

        position = PositionRepository.get_by_position_id(
            db,
            position_id,
        )

        if position is None:
            return None

        if position.status != PositionStatus.OPEN:
            return position

        position.current_stop_loss = float(
            new_stop_loss
        )

        # Maintain compatibility with existing API consumers.
        position.stop_loss = float(
            new_stop_loss
        )

        position.last_management_action = (
            management_action
        )

        position.last_management_time = (
            datetime.utcnow()
        )

        if management_status is not None:
            position.management_status = (
                management_status
            )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # BREAK-EVEN STATE
    # ========================================================

    @staticmethod
    def mark_break_even(
        db: Session,
        position_id: str,
        break_even_stop_loss: float,
    ) -> Optional[Position]:
        """
        Mark break-even as applied and persist the new SL.
        """

        position = PositionRepository.get_by_position_id(
            db,
            position_id,
        )

        if position is None:
            return None

        if position.status != PositionStatus.OPEN:
            return position

        position.current_stop_loss = float(
            break_even_stop_loss
        )

        position.stop_loss = float(
            break_even_stop_loss
        )

        position.break_even_applied = 1

        position.management_status = "protected"

        position.last_management_action = (
            "MOVE_TO_BREAK_EVEN"
        )

        position.last_management_time = (
            datetime.utcnow()
        )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # PARTIAL CLOSE STATE
    # ========================================================

    @staticmethod
    def mark_partial_close(
        db: Session,
        position_id: str,
        remaining_quantity: float,
    ) -> Optional[Position]:
        """
        Mark TP1/partial reduction as completed.

        The remaining quantity is persisted so the same partial
        close cannot be accidentally applied twice after restart.
        """

        position = PositionRepository.get_by_position_id(
            db,
            position_id,
        )

        if position is None:
            return None

        if position.status != PositionStatus.OPEN:
            return position

        remaining = float(remaining_quantity)

        if remaining < 0:
            raise ValueError(
                "remaining_quantity cannot be negative"
            )

        position.remaining_quantity = remaining
        position.quantity = remaining

        position.partial_close_applied = 1

        position.management_status = "reduced"

        position.last_management_action = (
            "PARTIAL_CLOSE"
        )

        position.last_management_time = (
            datetime.utcnow()
        )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # TRAILING STATE
    # ========================================================

    @staticmethod
    def mark_trailing_active(
        db: Session,
        position_id: str,
        new_stop_loss: Optional[float] = None,
    ) -> Optional[Position]:
        """
        Mark trailing management as active.

        If a new stop is supplied, it becomes the current SL.
        """

        position = PositionRepository.get_by_position_id(
            db,
            position_id,
        )

        if position is None:
            return None

        if position.status != PositionStatus.OPEN:
            return position

        if new_stop_loss is not None:
            position.current_stop_loss = float(
                new_stop_loss
            )

            position.stop_loss = float(
                new_stop_loss
            )

        position.trailing_active = 1

        position.management_status = "trailing"

        position.last_management_action = (
            "TRAIL_STOP"
        )

        position.last_management_time = (
            datetime.utcnow()
        )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # GENERIC MANAGEMENT STATE
    # ========================================================

    @staticmethod
    def update_management_state(
        db: Session,
        position_id: str,
        *,
        management_status: Optional[str] = None,
        last_management_action: Optional[str] = None,
        last_management_time: Optional[datetime] = None,
        break_even_applied: Optional[bool] = None,
        partial_close_applied: Optional[bool] = None,
        trailing_active: Optional[bool] = None,
    ) -> Optional[Position]:
        """
        Persist management-state changes atomically.
        """

        position = PositionRepository.get_by_position_id(
            db,
            position_id,
        )

        if position is None:
            return None

        if management_status is not None:
            position.management_status = (
                management_status
            )

        if last_management_action is not None:
            position.last_management_action = (
                last_management_action
            )

        if last_management_time is not None:
            position.last_management_time = (
                last_management_time
            )
        elif (
            management_status is not None
            or last_management_action is not None
            or break_even_applied is not None
            or partial_close_applied is not None
            or trailing_active is not None
        ):
            position.last_management_time = (
                datetime.utcnow()
            )

        if break_even_applied is not None:
            position.break_even_applied = (
                1 if break_even_applied else 0
            )

        if partial_close_applied is not None:
            position.partial_close_applied = (
                1 if partial_close_applied else 0
            )

        if trailing_active is not None:
            position.trailing_active = (
                1 if trailing_active else 0
            )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # GENERAL STATE UPDATE
    # ========================================================

    @staticmethod
    def update_state(
        db: Session,
        position_id: str,
        *,
        current_price: Optional[float] = None,
        current_stop_loss: Optional[float] = None,
        remaining_quantity: Optional[float] = None,
        management_status: Optional[str] = None,
        last_management_action: Optional[str] = None,
    ) -> Optional[Position]:
        """
        Persist multiple live-state fields in one transaction.

        This method is intended for supervisor/recovery code that
        needs to save a complete state transition atomically.
        """

        position = PositionRepository.get_by_position_id(
            db,
            position_id,
        )

        if position is None:
            return None

        if position.status != PositionStatus.OPEN:
            return position

        if current_price is not None:
            position.current_price = float(
                current_price
            )

        if current_stop_loss is not None:
            position.current_stop_loss = float(
                current_stop_loss
            )

            position.stop_loss = float(
                current_stop_loss
            )

        if remaining_quantity is not None:
            remaining = float(
                remaining_quantity
            )

            if remaining < 0:
                raise ValueError(
                    "remaining_quantity cannot be negative"
                )

            position.remaining_quantity = remaining
            position.quantity = remaining

        if management_status is not None:
            position.management_status = (
                management_status
            )

        if last_management_action is not None:
            position.last_management_action = (
                last_management_action
            )

        if (
            management_status is not None
            or last_management_action is not None
        ):
            position.last_management_time = (
                datetime.utcnow()
            )

        if current_price is not None:
            pnl = PositionRepository._calculate_pnl(
                position,
                float(current_price),
            )

            position.pnl = pnl

            position.pnl_percent = (
                PositionRepository._calculate_pnl_percent(
                    position,
                    pnl,
                )
            )

            PositionRepository._update_profit_extremes(
                position,
                pnl,
            )

        PositionRepository._set_compatibility_fields(
            position
        )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # CLOSE
    # ========================================================

    @staticmethod
    def close(
        db: Session,
        position_id: str,
        *,
        exit_price: Optional[float] = None,
        management_action: str = "EXIT",
    ) -> Optional[Position]:
        """
        Mark a position closed and persist final state.

        This is a database-state operation only.

        It does NOT send a broker close order.
        """

        position = PositionRepository.get_by_position_id(
            db,
            position_id,
        )

        if position is None:
            return None

        if position.status == PositionStatus.CLOSED:
            return position

        if exit_price is not None:
            position.current_price = float(
                exit_price
            )

        if position.current_price is not None:
            pnl = PositionRepository._calculate_pnl(
                position,
                position.current_price,
            )

            position.pnl = pnl

            position.pnl_percent = (
                PositionRepository._calculate_pnl_percent(
                    position,
                    pnl,
                )
            )

            PositionRepository._update_profit_extremes(
                position,
                pnl,
            )

        position.status = PositionStatus.CLOSED

        position.management_status = "closed"

        position.last_management_action = (
            management_action
        )

        position.last_management_time = (
            datetime.utcnow()
        )

        position.closed_at = datetime.utcnow()

        position.remaining_quantity = 0.0
        position.quantity = 0.0

        PositionRepository._set_compatibility_fields(
            position
        )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    # ========================================================
    # SERIALIZATION
    # ========================================================

    @staticmethod
    def to_dict(
        position: Optional[Position],
    ) -> Optional[dict]:
        """
        Convert a Position ORM object into a JSON-safe dictionary.
        """

        if position is None:
            return None

        direction = position.direction

        if isinstance(direction, TradeDirection):
            direction = direction.value

        status = position.status

        if isinstance(status, PositionStatus):
            status = status.value

        return {
            "id": position.id,
            "position_id": position.position_id,
            "trade_id": position.trade_id,

            "symbol": position.symbol,
            "direction": direction,

            "entry_price": position.entry_price,
            "original_quantity": position.original_quantity,

            "initial_stop_loss": (
                position.initial_stop_loss
            ),

            "take_profit_1": (
                position.take_profit_1
            ),

            "take_profit_2": (
                position.take_profit_2
            ),

            "risk_1r": position.risk_1r,

            "current_price": position.current_price,

            "current_stop_loss": (
                position.current_stop_loss
            ),

            "remaining_quantity": (
                position.remaining_quantity
            ),

            # Compatibility fields
            "quantity": position.quantity,
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,

            "pnl": position.pnl,
            "pnl_percent": position.pnl_percent,

            "regime": position.regime,
            "setup": position.setup,
            "technical_score": position.technical_score,
            "confluence": position.confluence,
            "confidence": position.confidence,

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
                position.last_management_time.isoformat()
                if position.last_management_time
                else None
            ),

            "max_drawdown": position.max_drawdown,
            "max_profit": position.max_profit,

            "status": status,

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
          }
