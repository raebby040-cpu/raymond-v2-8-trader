"""
RAYMOND v2.8 - Paper Position Lifecycle

Stage 17.4.1
Automatic paper-position TP/SL lifecycle detection.

SAFETY
------
This module is PAPER ONLY.

It:
- evaluates persistent open paper positions,
- detects take-profit and stop-loss hits,
- calculates final paper PnL,
- persists the position as closed,
- records the close reason,
- prevents already-closed positions from being processed again.

It NEVER:
- places broker orders,
- contacts MetaTrader 5,
- contacts Exness,
- enables live trading,
- modifies a real broker position,
- bypasses the Risk Engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from .models import Position, PositionStatus, TradeDirection
except ImportError:
    from models import Position, PositionStatus, TradeDirection


class PaperPositionLifecycleError(Exception):
    """Raised when paper-position lifecycle processing fails."""


@dataclass(frozen=True)
class PaperPositionLifecycleResult:
    """Safe result returned by the paper lifecycle engine."""

    position_id: str
    trade_id: Optional[str]
    symbol: str
    direction: str
    action: str
    close_reason: Optional[str]
    entry_price: float
    current_price: float
    quantity: float
    stop_loss: Optional[float]
    take_profit_1: Optional[float]
    take_profit_2: Optional[float]
    pnl: float
    pnl_percent: float
    closed: bool
    persisted: bool
    execution_type: str = "paper"
    read_only: bool = True
    broker_order_required: bool = False
    live_trading_enabled: bool = False
    broker_orders_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result safely."""

        return {
            "position_id": self.position_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "action": self.action,
            "close_reason": self.close_reason,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "quantity": self.quantity,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "closed": self.closed,
            "persisted": self.persisted,
            "execution_type": self.execution_type,
            "read_only": self.read_only,
            "broker_order_required": self.broker_order_required,
            "live_trading_enabled": self.live_trading_enabled,
            "broker_orders_allowed": self.broker_orders_allowed,
        }


class PaperPositionLifecycle:
    """
    Detect and persist automatic paper-position closures.

    This class is deliberately independent from broker execution.
    The market loop supplies the latest public market price.
    """

    def __init__(self, db) -> None:
        self.db = db

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _direction(position: Position) -> str:
        value = getattr(position.direction, "value", position.direction)
        return str(value).lower()

    @staticmethod
    def _quantity(position: Position) -> float:
        quantity = getattr(
            position,
            "remaining_quantity",
            None,
        )

        if quantity is None:
            quantity = getattr(
                position,
                "quantity",
                0.0,
            )

        return float(quantity or 0.0)

    @staticmethod
    def _stop_loss(position: Position) -> Optional[float]:
        value = getattr(
            position,
            "current_stop_loss",
            None,
        )

        if value is None:
            value = getattr(
                position,
                "stop_loss",
                None,
            )

        if value is None:
            return None

        return float(value)

    @staticmethod
    def _take_profit_1(position: Position) -> Optional[float]:
        value = getattr(
            position,
            "take_profit_1",
            None,
        )

        if value is None:
            value = getattr(
                position,
                "take_profit",
                None,
            )

        if value is None:
            return None

        return float(value)

    @staticmethod
    def _take_profit_2(position: Position) -> Optional[float]:
        value = getattr(
            position,
            "take_profit_2",
            None,
        )

        if value is None:
            return None

        return float(value)

    @staticmethod
    def _pnl(
        position: Position,
        current_price: float,
    ) -> float:
        """Calculate paper PnL from the remaining quantity."""

        quantity = PaperPositionLifecycle._quantity(
            position
        )

        entry = float(position.entry_price)
        current = float(current_price)

        direction = PaperPositionLifecycle._direction(
            position
        )

        if direction == TradeDirection.BUY.value:
            return (current - entry) * quantity

        if direction == TradeDirection.SELL.value:
            return (entry - current) * quantity

        raise PaperPositionLifecycleError(
            f"Unsupported position direction: {direction}"
        )

    @staticmethod
    def _pnl_percent(
        position: Position,
        pnl: float,
    ) -> float:
        """Calculate PnL percentage against remaining entry notional."""

        quantity = PaperPositionLifecycle._quantity(
            position
        )

        if quantity <= 0:
            return 0.0

        entry_notional = (
            abs(float(position.entry_price))
            * quantity
        )

        if entry_notional <= 0:
            return 0.0

        return (
            float(pnl)
            / entry_notional
        ) * 100.0

    @staticmethod
    def _hit_stop_loss(
        position: Position,
        current_price: float,
    ) -> bool:
        stop_loss = PaperPositionLifecycle._stop_loss(
            position
        )

        if stop_loss is None:
            return False

        direction = PaperPositionLifecycle._direction(
            position
        )

        if direction == TradeDirection.BUY.value:
            return current_price <= stop_loss

        if direction == TradeDirection.SELL.value:
            return current_price >= stop_loss

        return False

    @staticmethod
    def _hit_take_profit_1(
        position: Position,
        current_price: float,
    ) -> bool:
        take_profit = PaperPositionLifecycle._take_profit_1(
            position
        )

        if take_profit is None:
            return False

        direction = PaperPositionLifecycle._direction(
            position
        )

        if direction == TradeDirection.BUY.value:
            return current_price >= take_profit

        if direction == TradeDirection.SELL.value:
            return current_price <= take_profit

        return False

    @staticmethod
    def _hit_take_profit_2(
        position: Position,
        current_price: float,
    ) -> bool:
        take_profit = PaperPositionLifecycle._take_profit_2(
            position
        )

        if take_profit is None:
            return False

        direction = PaperPositionLifecycle._direction(
            position
        )

        if direction == TradeDirection.BUY.value:
            return current_price >= take_profit

        if direction == TradeDirection.SELL.value:
            return current_price <= take_profit

        return False

    @staticmethod
    def _position_id(position: Position) -> str:
        return str(position.position_id)

    @staticmethod
    def _trade_id(position: Position) -> Optional[str]:
        value = getattr(
            position,
            "trade_id",
            None,
        )

        if value is None:
            return None

        return str(value)

    @staticmethod
    def _symbol(position: Position) -> str:
        return str(position.symbol).upper()

    @staticmethod
    def _utc() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    # ============================================================
    # CLOSE PERSISTENCE
    # ============================================================

    def _persist_close(
        self,
        position: Position,
        current_price: float,
        close_reason: str,
    ) -> None:
        """
        Persist the final paper-position state.

        This changes only the application's persistent paper
        position record.

        No broker order is sent.
        """

        pnl = self._pnl(
            position,
            current_price,
        )

        pnl_percent = self._pnl_percent(
            position,
            pnl,
        )

        position.current_price = float(
            current_price
        )

        position.pnl = float(pnl)

        position.pnl_percent = float(
            pnl_percent
        )

        position.status = PositionStatus.CLOSED

        position.closed_at = datetime.utcnow()

        position.management_status = (
            "closed"
        )

        position.last_management_action = (
            close_reason
        )

        position.last_management_time = (
            datetime.utcnow()
        )

        # Keep legacy fields synchronized.
        if hasattr(position, "quantity"):
            position.quantity = 0.0

        if hasattr(position, "remaining_quantity"):
            position.remaining_quantity = 0.0

        try:
            self.db.commit()
            self.db.refresh(position)

        except Exception as exc:
            self.db.rollback()

            raise PaperPositionLifecycleError(
                f"Failed to persist paper position close: {exc}"
            ) from exc

    # ============================================================
    # SINGLE POSITION
    # ============================================================

    def evaluate_position(
        self,
        position: Position,
        current_price: float,
    ) -> PaperPositionLifecycleResult:
        """
        Evaluate one persistent paper position.

        Closure priority:
        1. Stop-loss
        2. TP2
        3. TP1

        A closed position is never processed again.
        """

        try:
            price = float(current_price)

        except (TypeError, ValueError) as exc:
            raise PaperPositionLifecycleError(
                "current_price must be numeric"
            ) from exc

        if price <= 0:
            raise PaperPositionLifecycleError(
                "current_price must be greater than zero"
            )

        position_id = self._position_id(
            position
        )

        trade_id = self._trade_id(
            position
        )

        symbol = self._symbol(
            position
        )

        direction = self._direction(
            position
        )

        quantity = self._quantity(
            position
        )

        stop_loss = self._stop_loss(
            position
        )

        take_profit_1 = self._take_profit_1(
            position
        )

        take_profit_2 = self._take_profit_2(
            position
        )

        # --------------------------------------------------------
        # Already closed
        # --------------------------------------------------------

        if position.status != PositionStatus.OPEN:
            pnl = float(
                getattr(position, "pnl", 0.0)
                or 0.0
            )

            pnl_percent = float(
                getattr(
                    position,
                    "pnl_percent",
                    0.0,
                )
                or 0.0
            )

            return PaperPositionLifecycleResult(
                position_id=position_id,
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                action="ALREADY_CLOSED",
                close_reason=getattr(
                    position,
                    "last_management_action",
                    None,
                ),
                entry_price=float(
                    position.entry_price
                ),
                current_price=float(
                    getattr(
                        position,
                        "current_price",
                        price,
                    )
                    or price
                ),
                quantity=0.0,
                stop_loss=stop_loss,
                take_profit_1=take_profit_1,
                take_profit_2=take_profit_2,
                pnl=pnl,
                pnl_percent=pnl_percent,
                closed=True,
                persisted=False,
            )

        # --------------------------------------------------------
        # Determine closure
        # --------------------------------------------------------

        close_reason: Optional[str] = None

        if self._hit_stop_loss(
            position,
            price,
        ):
            close_reason = "STOP_LOSS_HIT"

        elif self._hit_take_profit_2(
            position,
            price,
        ):
            close_reason = "TAKE_PROFIT_2_HIT"

        elif self._hit_take_profit_1(
            position,
            price,
        ):
            close_reason = "TAKE_PROFIT_1_HIT"

        # --------------------------------------------------------
        # No closure
        # --------------------------------------------------------

        if close_reason is None:
            pnl = self._pnl(
                position,
                price,
            )

            pnl_percent = self._pnl_percent(
                position,
                pnl,
            )

            # Persist latest price/PnL even while still open.
            position.current_price = price
            position.pnl = float(pnl)
            position.pnl_percent = float(
                pnl_percent
            )

            try:
                self.db.commit()
                self.db.refresh(position)

            except Exception as exc:
                self.db.rollback()

                raise PaperPositionLifecycleError(
                    f"Failed to persist paper position price: {exc}"
                ) from exc

            return PaperPositionLifecycleResult(
                position_id=position_id,
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                action="HOLD",
                close_reason=None,
                entry_price=float(
                    position.entry_price
                ),
                current_price=price,
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit_1=take_profit_1,
                take_profit_2=take_profit_2,
                pnl=float(pnl),
                pnl_percent=float(
                    pnl_percent
                ),
                closed=False,
                persisted=True,
            )

        # --------------------------------------------------------
        # Closure
        # --------------------------------------------------------

        self._persist_close(
            position,
            price,
            close_reason,
        )

        final_pnl = float(
            getattr(position, "pnl", 0.0)
            or 0.0
        )

        final_pnl_percent = float(
            getattr(
                position,
                "pnl_percent",
                0.0,
            )
            or 0.0
        )

        return PaperPositionLifecycleResult(
            position_id=position_id,
            trade_id=trade_id,
            symbol=symbol,
            direction=direction,
            action="CLOSE_POSITION",
            close_reason=close_reason,
            entry_price=float(
                position.entry_price
            ),
            current_price=price,
            quantity=0.0,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            pnl=final_pnl,
            pnl_percent=final_pnl_percent,
            closed=True,
            persisted=True,
        )

    # ============================================================
    # SYMBOL
    # ============================================================

    def evaluate_symbol(
        self,
        symbol: str,
        current_price: float,
    ) -> list[PaperPositionLifecycleResult]:
        """
        Evaluate every open paper position for a symbol.
        """

        normalized_symbol = str(
            symbol
        ).strip().upper()

        if not normalized_symbol:
            raise PaperPositionLifecycleError(
                "symbol is required"
            )

        try:
            price = float(current_price)

        except (TypeError, ValueError) as exc:
            raise PaperPositionLifecycleError(
                "current_price must be numeric"
            ) from exc

        if price <= 0:
            raise PaperPositionLifecycleError(
                "current_price must be greater than zero"
            )

        positions = (
            self.db.query(Position)
            .filter(
                Position.symbol == normalized_symbol,
                Position.status == PositionStatus.OPEN,
            )
            .order_by(
                Position.opened_at.asc()
            )
            .all()
        )

        results: list[
            PaperPositionLifecycleResult
        ] = []

        for position in positions:
            results.append(
                self.evaluate_position(
                    position,
                    price,
                )
            )

        return results

    # ============================================================
    # ALL OPEN POSITIONS
    # ============================================================

    def evaluate_open_positions(
        self,
        prices: dict[str, float],
    ) -> list[PaperPositionLifecycleResult]:
        """
        Evaluate all open paper positions using a price map.

        Example:

            {
                "XAUUSD": 4312.50
            }
        """

        if not isinstance(
            prices,
            dict,
        ):
            raise PaperPositionLifecycleError(
                "prices must be a dictionary"
            )

        positions = (
            self.db.query(Position)
            .filter(
                Position.status == PositionStatus.OPEN
            )
            .order_by(
                Position.opened_at.asc()
            )
            .all()
        )

        results: list[
            PaperPositionLifecycleResult
        ] = []

        for position in positions:
            symbol = self._symbol(
                position
            )

            if symbol not in prices:
                continue

            results.append(
                self.evaluate_position(
                    position,
                    float(prices[symbol]),
                )
            )

        return results


__all__ = [
    "PaperPositionLifecycle",
    "PaperPositionLifecycleError",
    "PaperPositionLifecycleResult",
                    ]
