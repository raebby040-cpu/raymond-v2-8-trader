"""
RAYMOND v2.8 - Paper Position Management Integration

Stage 17
Advanced Trade Management Integration

Responsibilities:
- Load open persistent paper positions.
- Update current market prices.
- Calculate current R.
- Ask AdvancedTradeManager for a management decision.
- Persist safe management state changes.
- Prevent repeated management actions after restart.
- Remain completely paper/read-only.

This module NEVER:
- places broker orders,
- contacts MT5,
- contacts Exness,
- enables live trading,
- modifies a broker position,
- bypasses the Risk Engine.

AdvancedTradeManager produces decisions.
PositionRepository persists those decisions.
This module is the integration layer between them.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

try:
    from .advanced_trade_management import (
        AdvancedTradeManager,
        ManagementAction,
        PositionSnapshot,
        TradeDirection,
        management_decision_to_dict,
    )
    from .position_repository import PositionRepository
    from .models import PositionStatus
except ImportError:
    from advanced_trade_management import (
        AdvancedTradeManager,
        ManagementAction,
        PositionSnapshot,
        TradeDirection,
        management_decision_to_dict,
    )
    from position_repository import PositionRepository
    from models import PositionStatus


class PaperPositionManagementError(ValueError):
    """Raised when paper-position management input is unsafe."""


@dataclass(frozen=True)
class PaperManagementResult:
    """
    Result of evaluating one persistent paper position.
    """

    position_id: str
    trade_id: Optional[str]
    symbol: str
    action: str
    profit_r: float
    current_price: float
    new_stop_loss: Optional[float]
    partial_close_quantity: float
    persisted: bool
    reason: str
    execution_type: str = "paper"
    read_only: bool = True
    broker_order_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "action": self.action,
            "profit_r": self.profit_r,
            "current_price": self.current_price,
            "new_stop_loss": self.new_stop_loss,
            "partial_close_quantity": self.partial_close_quantity,
            "persisted": self.persisted,
            "reason": self.reason,
            "execution_type": self.execution_type,
            "read_only": self.read_only,
            "broker_order_required": self.broker_order_required,
        }


class PaperPositionManager:
    """
    Safe integration layer between persistent paper positions and
    AdvancedTradeManager.

    The manager never performs broker execution.
    """

    def __init__(
        self,
        db: Session,
        *,
        trade_manager: Optional[AdvancedTradeManager] = None,
    ) -> None:
        if db is None:
            raise PaperPositionManagementError(
                "A SQLAlchemy database session is required."
            )

        self.db = db
        self.trade_manager = (
            trade_manager
            if trade_manager is not None
            else AdvancedTradeManager()
        )

    # ============================================================
    # NORMALIZATION
    # ============================================================

    @staticmethod
    def _direction(position: Any) -> TradeDirection:
        value = position.direction

        if isinstance(value, TradeDirection):
            return value

        value = getattr(value, "value", value)

        try:
            return TradeDirection(str(value).lower())
        except ValueError as exc:
            raise PaperPositionManagementError(
                f"Unsupported position direction: {value}"
            ) from exc

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        if value is None:
            return None

        return float(value)

    @staticmethod
    def _position_id(position: Any) -> str:
        value = getattr(position, "position_id", None)

        if not value:
            raise PaperPositionManagementError(
                "Persistent position is missing position_id."
            )

        return str(value)

    @staticmethod
    def _symbol(position: Any) -> str:
        value = getattr(position, "symbol", None)

        if not value or not str(value).strip():
            raise PaperPositionManagementError(
                "Persistent position is missing symbol."
            )

        return str(value).strip()

    @staticmethod
    def _quantity(position: Any) -> float:
        value = getattr(
            position,
            "remaining_quantity",
            None,
        )

        if value is None:
            value = getattr(
                position,
                "quantity",
                None,
            )

        if value is None or float(value) <= 0:
            raise PaperPositionManagementError(
                "Persistent position has invalid remaining quantity."
            )

        return float(value)

    @staticmethod
    def _current_stop_loss(position: Any) -> Optional[float]:
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

        return PaperPositionManager._float_or_none(value)

    @staticmethod
    def _take_profit(position: Any) -> Optional[float]:
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

        return PaperPositionManager._float_or_none(value)

    @staticmethod
    def _break_even_applied(position: Any) -> bool:
        return bool(
            getattr(
                position,
                "break_even_applied",
                0,
            )
        )

    @staticmethod
    def _partial_close_applied(position: Any) -> bool:
        return bool(
            getattr(
                position,
                "partial_close_applied",
                0,
            )
        )

    # ============================================================
    # SNAPSHOT
    # ============================================================

    def _snapshot(
        self,
        position: Any,
        current_price: Optional[float] = None,
    ) -> PositionSnapshot:
        """
        Convert a persistent Position into the read-only snapshot
        expected by AdvancedTradeManager.
        """

        stored_price = getattr(
            position,
            "current_price",
            None,
        )

        price = (
            float(current_price)
            if current_price is not None
            else self._float_or_none(stored_price)
        )

        if price is None or price <= 0:
            raise PaperPositionManagementError(
                "A valid current market price is required."
            )

        entry_price = getattr(
            position,
            "entry_price",
            None,
        )

        if entry_price is None or float(entry_price) <= 0:
            raise PaperPositionManagementError(
                "Persistent position has invalid entry_price."
            )

        return PositionSnapshot(
            trade_id=str(
                getattr(
                    position,
                    "trade_id",
                    None,
                )
                or self._position_id(position)
            ),
            symbol=self._symbol(position),
            direction=self._direction(position),
            entry_price=float(entry_price),
            current_price=price,
            quantity=self._quantity(position),
            stop_loss=self._current_stop_loss(position),
            take_profit=self._take_profit(position),
            break_even_applied=self._break_even_applied(
                position
            ),
            partial_close_applied=self._partial_close_applied(
                position
            ),
        )

    # ============================================================
    # SAFETY
    # ============================================================

    @staticmethod
    def _assert_safe_decision(decision: Any) -> None:
        """
        Refuse any decision that claims to require broker execution.
        """

        if getattr(
            decision,
            "execution_type",
            "paper",
        ) != "paper":
            raise PaperPositionManagementError(
                "Unsafe management decision: execution_type is not paper."
            )

        if not getattr(
            decision,
            "read_only",
            True,
        ):
            raise PaperPositionManagementError(
                "Unsafe management decision: decision is not read-only."
            )

        if getattr(
            decision,
            "broker_order_required",
            False,
        ):
            raise PaperPositionManagementError(
                "Unsafe management decision: broker order required."
            )

    # ============================================================
    # SINGLE POSITION EVALUATION
    # ============================================================

    def evaluate_position(
        self,
        position: Any,
        *,
        current_price: Optional[float] = None,
    ) -> PaperManagementResult:
        """
        Evaluate one persistent open paper position.

        The decision is calculated first.
        Persistence happens only for safe management actions.
        """

        status = getattr(
            position,
            "status",
            None,
        )

        if status != PositionStatus.OPEN:
            return PaperManagementResult(
                position_id=self._position_id(position),
                trade_id=getattr(
                    position,
                    "trade_id",
                    None,
                ),
                symbol=self._symbol(position),
                action=ManagementAction.HOLD.value,
                profit_r=0.0,
                current_price=float(
                    current_price
                    or getattr(
                        position,
                        "current_price",
                        0.0,
                    )
                    or 0.0
                ),
                new_stop_loss=None,
                partial_close_quantity=0.0,
                persisted=False,
                reason="Position is not open; no management action applied.",
            )

        snapshot = self._snapshot(
            position,
            current_price=current_price,
        )

        decision = self.trade_manager.evaluate(
            snapshot
        )

        self._assert_safe_decision(
            decision
        )

        action = decision.action

        persisted = False

        # --------------------------------------------------------
        # Always persist current market price/PnL first.
        # --------------------------------------------------------

        updated = PositionRepository.update_price(
            self.db,
            self._position_id(position),
            snapshot.current_price,
        )

        if updated is None:
            raise PaperPositionManagementError(
                "Position disappeared while updating market price."
            )

        # --------------------------------------------------------
        # HOLD
        # --------------------------------------------------------

        if action == ManagementAction.HOLD:
            return PaperManagementResult(
                position_id=self._position_id(updated),
                trade_id=getattr(
                    updated,
                    "trade_id",
                    None,
                ),
                symbol=self._symbol(updated),
                action=action.value,
                profit_r=float(decision.profit_r),
                current_price=float(
                    snapshot.current_price
                ),
                new_stop_loss=None,
                partial_close_quantity=0.0,
                persisted=True,
                reason=decision.reason,
            )

        # --------------------------------------------------------
        # BREAK EVEN
        # --------------------------------------------------------

        if action == ManagementAction.MOVE_TO_BREAK_EVEN:
            if decision.new_stop_loss is None:
                raise PaperPositionManagementError(
                    "Break-even decision is missing new_stop_loss."
                )

            # Re-read the position after price persistence.
            refreshed = PositionRepository.get_by_position_id(
                self.db,
                self._position_id(updated),
            )

            if refreshed is None:
                raise PaperPositionManagementError(
                    "Position could not be reloaded before break-even."
                )

            if self._break_even_applied(refreshed):
                return PaperManagementResult(
                    position_id=self._position_id(refreshed),
                    trade_id=getattr(
                        refreshed,
                        "trade_id",
                        None,
                    ),
                    symbol=self._symbol(refreshed),
                    action=ManagementAction.HOLD.value,
                    profit_r=float(decision.profit_r),
                    current_price=float(
                        snapshot.current_price
                    ),
                    new_stop_loss=None,
                    partial_close_quantity=0.0,
                    persisted=True,
                    reason=(
                        "Break-even was already applied; "
                        "duplicate action prevented."
                    ),
                )

            PositionRepository.mark_break_even(
                self.db,
                self._position_id(refreshed),
                float(decision.new_stop_loss),
            )

            persisted = True

        # --------------------------------------------------------
        # TRAILING STOP
        # --------------------------------------------------------

        elif action == ManagementAction.TRAIL_STOP:
            if decision.new_stop_loss is None:
                raise PaperPositionManagementError(
                    "Trailing decision is missing new_stop_loss."
                )

            refreshed = PositionRepository.get_by_position_id(
                self.db,
                self._position_id(updated),
            )

            if refreshed is None:
                raise PaperPositionManagementError(
                    "Position could not be reloaded before trailing."
                )

            existing_stop = self._current_stop_loss(
                refreshed
            )

            direction = self._direction(
                refreshed
            )

            candidate = float(
                decision.new_stop_loss
            )

            # Never worsen protection.
            if existing_stop is not None:
                if direction == TradeDirection.BUY:
                    if candidate <= existing_stop:
                        return PaperManagementResult(
                            position_id=self._position_id(refreshed),
                            trade_id=getattr(
                                refreshed,
                                "trade_id",
                                None,
                            ),
                            symbol=self._symbol(refreshed),
                            action=ManagementAction.HOLD.value,
                            profit_r=float(decision.profit_r),
                            current_price=float(
                                snapshot.current_price
                            ),
                            new_stop_loss=None,
                            partial_close_quantity=0.0,
                            persisted=True,
                            reason=(
                                "Trailing stop rejected because "
                                "it would worsen protection."
                            ),
                        )

                else:
                    if candidate >= existing_stop:
                        return PaperManagementResult(
                            position_id=self._position_id(refreshed),
                            trade_id=getattr(
                                refreshed,
                                "trade_id",
                                None,
                            ),
                            symbol=self._symbol(refreshed),
                            action=ManagementAction.HOLD.value,
                            profit_r=float(decision.profit_r),
                            current_price=float(
                                snapshot.current_price
                            ),
                            new_stop_loss=None,
                            partial_close_quantity=0.0,
                            persisted=True,
                            reason=(
                                "Trailing stop rejected because "
                                "it would worsen protection."
                            ),
                        )

            PositionRepository.update_stop_loss(
                self.db,
                self._position_id(refreshed),
                candidate,
                management_action="TRAIL_STOP",
                management_status="protected",
            )

            persisted = True

        # --------------------------------------------------------
        # PARTIAL CLOSE
        # --------------------------------------------------------

        elif action == ManagementAction.PARTIAL_CLOSE:
            quantity = float(
                decision.partial_close_quantity
            )

            if quantity <= 0:
                raise PaperPositionManagementError(
                    "Partial-close decision contains invalid quantity."
                )

            refreshed = PositionRepository.get_by_position_id(
                self.db,
                self._position_id(updated),
            )

            if refreshed is None:
                raise PaperPositionManagementError(
                    "Position could not be reloaded before partial close."
                )

            if self._partial_close_applied(refreshed):
                return PaperManagementResult(
                    position_id=self._position_id(refreshed),
                    trade_id=getattr(
                        refreshed,
                        "trade_id",
                        None,
                    ),
                    symbol=self._symbol(refreshed),
                    action=ManagementAction.HOLD.value,
                    profit_r=float(decision.profit_r),
                    current_price=float(
                        snapshot.current_price
                    ),
                    new_stop_loss=None,
                    partial_close_quantity=0.0,
                    persisted=True,
                    reason=(
                        "Partial close was already applied; "
                        "duplicate action prevented."
                    ),
                )

            remaining = self._quantity(
                refreshed
            ) - quantity

            if remaining <= 0:
                raise PaperPositionManagementError(
                    "Partial close would close the entire position."
                )

            PositionRepository.mark_partial_close(
                self.db,
                self._position_id(refreshed),
                remaining,
            )

            persisted = True

        else:
            raise PaperPositionManagementError(
                f"Unsupported management action: {action}"
            )

        final_position = PositionRepository.get_by_position_id(
            self.db,
            self._position_id(updated),
        )

        if final_position is None:
            raise PaperPositionManagementError(
                "Position could not be reloaded after management."
            )

        return PaperManagementResult(
            position_id=self._position_id(final_position),
            trade_id=getattr(
                final_position,
                "trade_id",
                None,
            ),
            symbol=self._symbol(final_position),
            action=action.value,
            profit_r=float(decision.profit_r),
            current_price=float(
                snapshot.current_price
            ),
            new_stop_loss=decision.new_stop_loss,
            partial_close_quantity=float(
                decision.partial_close_quantity
            ),
            persisted=persisted,
            reason=decision.reason,
        )

    # ============================================================
    # OPEN POSITION BATCH
    # ============================================================

    def evaluate_open_positions(
        self,
        prices: Mapping[str, float],
    ) -> list[PaperManagementResult]:
        """
        Evaluate all open persistent paper positions.

        prices:
            Mapping of symbol -> current market price.

        Positions without a supplied price are skipped safely.
        """

        if prices is None:
            raise PaperPositionManagementError(
                "prices mapping is required."
            )

        results: list[PaperManagementResult] = []

        positions = PositionRepository.get_open_positions(
            self.db
        )

        for position in positions:
            symbol = self._symbol(position)

            if symbol not in prices:
                continue

            price = float(
                prices[symbol]
            )

            if price <= 0:
                continue

            result = self.evaluate_position(
                position,
                current_price=price,
            )

            results.append(result)

        return results

    # ============================================================
    # SYMBOL EVALUATION
    # ============================================================

    def evaluate_symbol(
        self,
        symbol: str,
        current_price: float,
    ) -> list[PaperManagementResult]:
        """
        Evaluate all open positions for one symbol.
        """

        if not symbol or not symbol.strip():
            raise PaperPositionManagementError(
                "symbol is required."
            )

        price = float(current_price)

        if price <= 0:
            raise PaperPositionManagementError(
                "current_price must be greater than zero."
            )

        symbol = symbol.strip()

        positions = [
            position
            for position in PositionRepository.get_open_positions(
                self.db
            )
            if self._symbol(position).upper()
            == symbol.upper()
        ]

        return [
            self.evaluate_position(
                position,
                current_price=price,
            )
            for position in positions
        ]

    # ============================================================
    # SERIALIZATION
    # ============================================================

    @staticmethod
    def result_to_dict(
        result: PaperManagementResult,
    ) -> dict[str, Any]:
        return result.to_dict()

    @staticmethod
    def results_to_dict(
        results: list[PaperManagementResult],
    ) -> list[dict[str, Any]]:
        return [
            result.to_dict()
            for result in results
        ]


def manage_paper_positions(
    db: Session,
    prices: Mapping[str, float],
    *,
    trade_manager: Optional[AdvancedTradeManager] = None,
) -> list[dict[str, Any]]:
    """
    Convenience function for callers that want to manage all
    supplied paper-position prices.

    This remains paper/read-only and never performs broker execution.
    """

    manager = PaperPositionManager(
        db,
        trade_manager=trade_manager,
    )

    results = manager.evaluate_open_positions(
        prices
    )

    return manager.results_to_dict(
        results
    )


