"""
RAYMOND v2.8 - Persistent Position Repository

Stage 16.2
Persistent Position State

Stage 16.3
Persistent Trade Thesis

Stage 18
Persistent Partial-Close Accounting

Responsibilities:
- Create persistent paper positions.
- Persist trade thesis.
- Load positions.
- Update live position state.
- Update management state.
- Close positions.
- Prevent duplicate position creation.
- Keep database transactions atomic.
- Calculate XAUUSD paper PnL using 100 oz contract size.
- Persist exact partial-close execution accounting.

This module does NOT:
- place broker orders,
- modify MT5 positions,
- make trading decisions,
- calculate AI signals,
- bypass the Risk Engine,
- execute live trades.
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

    Successful mutations are committed.
    Failed mutations are rolled back.
    """

    # ========================================================
    # SYMBOL ACCOUNTING
    # ========================================================

    # XAUUSD:
    # 1.00 lot = 100 troy ounces.
    #
    # Therefore:
    # $1.00 price movement × 1.00 lot = $100
    # $1.00 price movement × 0.02 lot = $2
    #
    # Example:
    # BUY 2056 -> 2051 at 0.02 lot = -$10
    # SELL 2056 -> 2051 at 0.02 lot = +$10

    XAUUSD_CONTRACT_SIZE = 100.0

    @staticmethod
    def _contract_size(symbol: str) -> float:
        """
        Return the contract size used for persistent paper PnL.
        """

        if str(symbol).upper() == "XAUUSD":
            return PositionRepository.XAUUSD_CONTRACT_SIZE

        # Preserve existing legacy behavior for other symbols.
        return 1.0

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

        return TradeDirection(str(direction).lower())

    @staticmethod
    def _status_enum(status) -> PositionStatus:
        """
        Convert a status value to PositionStatus.
        """

        if isinstance(status, PositionStatus):
            return status

        return PositionStatus(str(status).lower())

    @staticmethod
    def _set_compatibility_fields(position: Position) -> None:
        """
        Keep legacy Position fields synchronized with the
        Stage 16.2 fields.
        """

        if position.current_stop_loss is not None:
            position.stop_loss = position.current_stop_loss

        elif position.initial_stop_loss is not None:
            position.stop_loss = position.initial_stop_loss

        if position.take_profit_1 is not None:
            position.take_profit = position.take_profit_1

        if position.remaining_quantity is not None:
            position.quantity = position.remaining_quantity

    # ========================================================
    # PNL CALCULATION
    # ========================================================

    @staticmethod
    def _calculate_pnl(
        position: Position,
        current_price: Optional[float],
    ) -> float:
        """
        Calculate paper unrealized PnL.

        BUY:
            (current - entry) × lots × contract_size

        SELL:
            (entry - current) × lots × contract_size

        XAUUSD contract size = 100.
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

        contract_size = PositionRepository._contract_size(
            position.symbol
        )

        entry_price = float(position.entry_price)
        market_price = float(current_price)
        lots = float(quantity)

        if direction == TradeDirection.BUY.value:
            return (
                market_price - entry_price
            ) * lots * contract_size

        if direction == TradeDirection.SELL.value:
            return (
                entry_price - market_price
            ) * lots * contract_size

        raise ValueError(
            f"Unsupported position direction: {position.direction}"
        )

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

        contract_size = PositionRepository._contract_size(
            position.symbol
        )

        entry_notional = (
            abs(float(position.entry_price))
            * float(quantity)
            * contract_size
        )

        if entry_notional == 0:
            return 0.0

        return (
            float(pnl) / entry_notional
        ) * 100.0

    @staticmethod
    def _update_profit_extremes(
        position: Position,
        pnl: float,
    ) -> None:
        """
        Track maximum profit and maximum drawdown.

        max_profit:
            highest observed PnL.

        max_drawdown:
            non-negative magnitude of worst negative PnL.
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
        trade_thesis: Optional[str] = None,
        current_price: Optional[float] = None,
        management_status: str = "open",
    ) -> Position:
        """
        Create one persistent Position.

        Duplicate position_id or trade_id returns the
        existing position rather than creating a duplicate.
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

        entry = float(entry_price)
        quantity = float(original_quantity)

        if entry <= 0:
            raise ValueError(
                "entry_price must be greater than zero."
            )

        if quantity <= 0:
            raise ValueError(
                "original_quantity must be greater than zero."
            )

        if initial_stop_loss is None:
            raise ValueError(
                "initial_stop_loss is required for "
                "a persistent paper position."
            )

        initial_stop = float(initial_stop_loss)

        if initial_stop <= 0:
            raise ValueError(
                "initial_stop_loss must be greater than zero."
            )

        if direction_enum == TradeDirection.BUY:

            if initial_stop >= entry:
                raise ValueError(
                    "BUY initial_stop_loss must be below entry_price."
                )

            if (
                take_profit_1 is not None
                and float(take_profit_1) <= entry
            ):
                raise ValueError(
                    "BUY take_profit_1 must be above entry_price."
                )

            if (
                take_profit_2 is not None
                and float(take_profit_2) <= entry
            ):
                raise ValueError(
                    "BUY take_profit_2 must be above entry_price."
                )

        elif direction_enum == TradeDirection.SELL:

            if initial_stop <= entry:
                raise ValueError(
                    "SELL initial_stop_loss must be above entry_price."
                )

            if (
                take_profit_1 is not None
                and float(take_profit_1) >= entry
            ):
                raise ValueError(
                    "SELL take_profit_1 must be below entry_price."
                )

            if (
                take_profit_2 is not None
                and float(take_profit_2) >= entry
            ):
                raise ValueError(
                    "SELL take_profit_2 must be below entry_price."
                )

        else:
            raise ValueError(
                f"Unsupported position direction: {direction_enum}"
            )

        if risk_1r is None:
            risk_1r = abs(
                entry - initial_stop
            )

        if float(risk_1r) <= 0:
            raise ValueError(
                "risk_1r must be greater than zero."
            )

        if current_price is None:
            current_price = entry

        now = datetime.utcnow()

        position = Position(
            position_id=position_id,
            trade_id=trade_id,
            symbol=symbol,
            direction=direction_enum,

            quantity=quantity,
            original_quantity=quantity,

            entry_price=entry,

            initial_stop_loss=initial_stop,

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

            risk_1r=float(risk_1r),

            current_price=float(current_price),

            current_stop_loss=initial_stop,

            remaining_quantity=quantity,

            stop_loss=initial_stop,

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

            trade_thesis=trade_thesis,

            break_even_applied=0,
            partial_close_applied=0,
            trailing_active=0,

            partial_close_price=None,
            partial_close_quantity=None,
            partial_close_pnl=0.0,

            management_status=management_status,
            last_management_action="OPEN",
            last_management_time=now,

            max_drawdown=0.0,
            max_profit=0.0,

            status=PositionStatus.OPEN,

            opened_at=now,
            closed_at=None,
        )

        try:
            db.add(position)
            db.commit()
            db.refresh(position)

            return position

        except IntegrityError:
            db.rollback()

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
        Load one position by persistent position_id.
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
        Load one position by trade_id.
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
        Return persistent positions ordered newest first.
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

        Does not close a position or move its stop.
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

        initial_stop_loss is never changed.
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
    # PARTIAL CLOSE
    # ========================================================

    @staticmethod
    def mark_partial_close(
        db: Session,
        position_id: str,
        remaining_quantity: float,
        *,
        execution_price: float,
        closed_quantity: Optional[float] = None,
    ) -> Optional[Position]:
        """
        Persist a paper partial-close event.

        partial_close_pnl is CUMULATIVE.

        Therefore:

            total_trade_pnl =
                cumulative partial-close PnL
                +
                final remaining-position PnL

        This prevents earlier partial-close profits/losses
        from being overwritten.

        PAPER ONLY.
        No broker order is created.
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
        price = float(execution_price)

        if remaining < 0:
            raise ValueError(
                "remaining_quantity cannot be negative"
            )

        if price <= 0:
            raise ValueError(
                "execution_price must be greater than zero"
            )

        current_quantity = float(
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )

        if closed_quantity is None:
            closed = current_quantity - remaining
        else:
            closed = float(closed_quantity)

        if closed <= 0:
            raise ValueError(
                "closed_quantity must be greater than zero"
            )

        if closed > current_quantity + 1e-12:
            raise ValueError(
                "closed_quantity cannot exceed "
                "current remaining quantity"
            )

        expected_remaining = (
            current_quantity - closed
        )

        if abs(
            expected_remaining - remaining
        ) > 1e-9:
            raise ValueError(
                "remaining_quantity and closed_quantity "
                "are inconsistent"
            )

        direction = PositionRepository._direction_value(
            position.direction
        )

        entry_price = float(
            position.entry_price
        )

        if direction == TradeDirection.BUY.value:

            price_move = (
                price - entry_price
            )

        elif direction == TradeDirection.SELL.value:

            price_move = (
                entry_price - price
            )

        else:
            raise ValueError(
                f"Unsupported position direction: "
                f"{position.direction}"
            )

        contract_size = PositionRepository._contract_size(
            position.symbol
        )

        realized_partial_pnl = (
            price_move
            * closed
            * contract_size
        )

        # ----------------------------------------------------
        # CUMULATIVE PARTIAL PNL
        # ----------------------------------------------------

        previous_partial_pnl = float(
            position.partial_close_pnl or 0.0
        )

        cumulative_partial_pnl = (
            previous_partial_pnl
            + realized_partial_pnl
        )

        # ----------------------------------------------------
        # REMAINING POSITION
        # ----------------------------------------------------

        position.remaining_quantity = remaining
        position.quantity = remaining

        # ----------------------------------------------------
        # PARTIAL-CLOSE ACCOUNTING
        # ----------------------------------------------------

        position.partial_close_applied = 1

        # These describe the MOST RECENT partial close.
        position.partial_close_price = price
        position.partial_close_quantity = closed

        # This is CUMULATIVE.
        position.partial_close_pnl = (
            cumulative_partial_pnl
        )

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
        Persist multiple live-state fields atomically.
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

            "trade_thesis": getattr(
                position,
                "trade_thesis",
                None,
            ),

            "break_even_applied": bool(
                position.break_even_applied
            ),

            "partial_close_applied": bool(
                position.partial_close_applied
            ),

            "partial_close_price": getattr(
                position,
                "partial_close_price",
                None,
            ),

            "partial_close_quantity": getattr(
                position,
                "partial_close_quantity",
                None,
            ),

            "partial_close_pnl": getattr(
                position,
                "partial_close_pnl",
                None,
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
