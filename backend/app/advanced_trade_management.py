"""
RAYMOND v2.8 - Advanced Trade Management

STEP 12:
- Break-even stop management.
- Trailing-stop management.
- Partial-close planning.
- BUY/SELL aware price handling.
- Never worsens an existing stop-loss.
- Never executes broker orders.
- Never contacts MT5.
- Paper/read-only management decisions only.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TradeManagementError(ValueError):
    """Raised when trade-management input is unsafe or invalid."""


class TradeDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ManagementAction(str, Enum):
    HOLD = "hold"
    MOVE_TO_BREAK_EVEN = "move_to_break_even"
    TRAIL_STOP = "trail_stop"
    PARTIAL_CLOSE = "partial_close"


@dataclass(frozen=True)
class TradeManagementConfig:
    """
    Advanced trade-management configuration.

    All distances are expressed in price units.
    """

    break_even_trigger_r: float = 1.0
    break_even_offset: float = 0.0

    trailing_enabled: bool = True
    trailing_distance: float = 5.0
    trailing_step: float = 1.0

    partial_close_enabled: bool = True
    partial_close_percent: float = 50.0
    partial_close_trigger_r: float = 2.0

    def validate(self) -> None:
        if self.break_even_trigger_r <= 0:
            raise TradeManagementError(
                "break_even_trigger_r must be greater than zero"
            )

        if self.break_even_offset < 0:
            raise TradeManagementError(
                "break_even_offset cannot be negative"
            )

        if self.trailing_distance <= 0:
            raise TradeManagementError(
                "trailing_distance must be greater than zero"
            )

        if self.trailing_step <= 0:
            raise TradeManagementError(
                "trailing_step must be greater than zero"
            )

        if not 0 < self.partial_close_percent < 100:
            raise TradeManagementError(
                "partial_close_percent must be between 0 and 100"
            )

        if self.partial_close_trigger_r <= 0:
            raise TradeManagementError(
                "partial_close_trigger_r must be greater than zero"
            )


@dataclass(frozen=True)
class PositionSnapshot:
    """Read-only snapshot of an open paper position."""

    trade_id: str
    symbol: str
    direction: TradeDirection

    entry_price: float
    current_price: float
    quantity: float

    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    break_even_applied: bool = False
    partial_close_applied: bool = False

    def validate(self) -> None:
        if not self.trade_id or not self.trade_id.strip():
            raise TradeManagementError(
                "trade_id is required"
            )

        if not self.symbol or not self.symbol.strip():
            raise TradeManagementError(
                "symbol is required"
            )

        if self.entry_price <= 0:
            raise TradeManagementError(
                "entry_price must be greater than zero"
            )

        if self.current_price <= 0:
            raise TradeManagementError(
                "current_price must be greater than zero"
            )

        if self.quantity <= 0:
            raise TradeManagementError(
                "quantity must be greater than zero"
            )

        if self.stop_loss is not None:
            if self.stop_loss <= 0:
                raise TradeManagementError(
                    "stop_loss must be greater than zero"
                )

        if self.take_profit is not None:
            if self.take_profit <= 0:
                raise TradeManagementError(
                    "take_profit must be greater than zero"
                )

        if self.direction == TradeDirection.BUY:
            if (
                self.stop_loss is not None
                and self.stop_loss >= self.entry_price
            ):
                raise TradeManagementError(
                    "BUY stop_loss must be below entry_price"
                )

            if (
                self.take_profit is not None
                and self.take_profit <= self.entry_price
            ):
                raise TradeManagementError(
                    "BUY take_profit must be above entry_price"
                )

        elif self.direction == TradeDirection.SELL:
            if (
                self.stop_loss is not None
                and self.stop_loss <= self.entry_price
            ):
                raise TradeManagementError(
                    "SELL stop_loss must be above entry_price"
                )

            if (
                self.take_profit is not None
                and self.take_profit >= self.entry_price
            ):
                raise TradeManagementError(
                    "SELL take_profit must be below entry_price"
                )

        else:
            raise TradeManagementError(
                "direction must be BUY or SELL"
            )


@dataclass(frozen=True)
class ManagementDecision:
    """Safe, deterministic trade-management decision."""

    action: ManagementAction
    trade_id: str

    new_stop_loss: Optional[float]
    partial_close_quantity: float

    profit_price_distance: float
    profit_r: float

    reason: str

    execution_type: str = "paper"
    read_only: bool = True
    broker_order_required: bool = False


class AdvancedTradeManager:
    """
    Calculate advanced trade-management actions.

    This class does NOT:
    - send orders,
    - modify stops at a broker,
    - close positions,
    - call MT5,
    - call Exness.

    It only produces a management decision.
    """

    def __init__(
        self,
        config: Optional[TradeManagementConfig] = None,
    ) -> None:
        self.config = config or TradeManagementConfig()
        self.config.validate()

    @staticmethod
    def _risk_distance(
        position: PositionSnapshot,
    ) -> float:
        if position.stop_loss is None:
            raise TradeManagementError(
                "stop_loss is required for R-based management"
            )

        distance = abs(
            position.entry_price
            - position.stop_loss
        )

        if distance <= 0:
            raise TradeManagementError(
                "stop_loss distance must be greater than zero"
            )

        return distance

    @staticmethod
    def _profit_distance(
        position: PositionSnapshot,
    ) -> float:
        if position.direction == TradeDirection.BUY:
            return (
                position.current_price
                - position.entry_price
            )

        if position.direction == TradeDirection.SELL:
            return (
                position.entry_price
                - position.current_price
            )

        raise TradeManagementError(
            "direction must be BUY or SELL"
        )

    def profit_r(
        self,
        position: PositionSnapshot,
    ) -> float:
        """Return current unrealized profit measured in R."""

        position.validate()

        risk_distance = self._risk_distance(
            position
        )

        profit_distance = self._profit_distance(
            position
        )

        return (
            profit_distance
            / risk_distance
        )

    def break_even_stop(
        self,
        position: PositionSnapshot,
    ) -> float:
        """
        Calculate the break-even stop.

        BUY:
            entry + offset

        SELL:
            entry - offset
        """

        position.validate()

        if position.direction == TradeDirection.BUY:
            return (
                position.entry_price
                + self.config.break_even_offset
            )

        return (
            position.entry_price
            - self.config.break_even_offset
        )

    def trailing_stop(
        self,
        position: PositionSnapshot,
    ) -> float:
        """
        Calculate a candidate trailing stop.

        BUY:
            current - trailing distance

        SELL:
            current + trailing distance
        """

        position.validate()

        if position.direction == TradeDirection.BUY:
            candidate = (
                position.current_price
                - self.config.trailing_distance
            )

            if candidate <= 0:
                raise TradeManagementError(
                    "calculated BUY trailing stop must be positive"
                )

            return candidate

        candidate = (
            position.current_price
            + self.config.trailing_distance
        )

        if candidate <= 0:
            raise TradeManagementError(
                "calculated SELL trailing stop must be positive"
            )

        return candidate

    @staticmethod
    def _stop_improves(
        position: PositionSnapshot,
        candidate: float,
    ) -> bool:
        """
        Return True only when the candidate stop improves protection.

        BUY:
            higher stop is better.

        SELL:
            lower stop is better.
        """

        if position.stop_loss is None:
            return True

        if position.direction == TradeDirection.BUY:
            return candidate > position.stop_loss

        return candidate < position.stop_loss

    def _stop_changed_enough(
        self,
        position: PositionSnapshot,
        candidate: float,
    ) -> bool:
        """Require at least the configured trailing step."""

        if position.stop_loss is None:
            return True

        difference = abs(
            candidate - position.stop_loss
        )

        return (
            difference
            >= self.config.trailing_step
        )

    def partial_close_quantity(
        self,
        position: PositionSnapshot,
    ) -> float:
        """Calculate the quantity to close during partial close."""

        position.validate()

        if position.partial_close_applied:
            return 0.0

        quantity = (
            position.quantity
            * self.config.partial_close_percent
            / 100.0
        )

        if quantity <= 0:
            return 0.0

        if quantity >= position.quantity:
            return 0.0

        return round(
            quantity,
            8,
        )

    def evaluate(
        self,
        position: PositionSnapshot,
    ) -> ManagementDecision:
        """
        Evaluate one position and return one safe action.

        Priority:
        1. Partial close when triggered.
        2. Break-even when triggered.
        3. Trailing stop when triggered.
        4. Hold.

        No action is executed.
        """

        position.validate()

        profit_distance = self._profit_distance(
            position
        )

        current_r = self.profit_r(
            position
        )

        # A losing or flat position does not get
        # break-even, trailing, or partial-close actions.
        if current_r <= 0:
            return ManagementDecision(
                action=ManagementAction.HOLD,
                trade_id=position.trade_id,
                new_stop_loss=None,
                partial_close_quantity=0.0,
                profit_price_distance=profit_distance,
                profit_r=current_r,
                reason=(
                    "Position is not in profit; "
                    "no advanced management action is required."
                ),
            )

        # ----------------------------------------------------
        # PARTIAL CLOSE
        # ----------------------------------------------------

        if (
            self.config.partial_close_enabled
            and not position.partial_close_applied
            and current_r
            >= self.config.partial_close_trigger_r
        ):
            quantity = (
                self.partial_close_quantity(
                    position
                )
            )

            if quantity > 0:
                return ManagementDecision(
                    action=ManagementAction.PARTIAL_CLOSE,
                    trade_id=position.trade_id,
                    new_stop_loss=None,
                    partial_close_quantity=quantity,
                    profit_price_distance=profit_distance,
                    profit_r=current_r,
                    reason=(
                        "Partial-close trigger reached."
                    ),
                )

        # ----------------------------------------------------
        # BREAK EVEN
        # ----------------------------------------------------

        if (
            not position.break_even_applied
            and current_r
            >= self.config.break_even_trigger_r
        ):
            candidate = (
                self.break_even_stop(position)
            )

            if self._stop_improves(
                position,
                candidate,
            ):
                return ManagementDecision(
                    action=ManagementAction.MOVE_TO_BREAK_EVEN,
                    trade_id=position.trade_id,
                    new_stop_loss=candidate,
                    partial_close_quantity=0.0,
                    profit_price_distance=profit_distance,
                    profit_r=current_r,
                    reason=(
                        "Break-even trigger reached; "
                        "candidate stop improves protection."
                    ),
                )

        # ----------------------------------------------------
        # TRAILING STOP
        # ----------------------------------------------------

        if self.config.trailing_enabled:
            candidate = (
                self.trailing_stop(position)
            )

            if (
                self._stop_improves(
                    position,
                    candidate,
                )
                and self._stop_changed_enough(
                    position,
                    candidate,
                )
            ):
                return ManagementDecision(
                    action=ManagementAction.TRAIL_STOP,
                    trade_id=position.trade_id,
                    new_stop_loss=candidate,
                    partial_close_quantity=0.0,
                    profit_price_distance=profit_distance,
                    profit_r=current_r,
                    reason=(
                        "Trailing-stop candidate improves "
                        "the existing stop-loss."
                    ),
                )

        return ManagementDecision(
            action=ManagementAction.HOLD,
            trade_id=position.trade_id,
            new_stop_loss=None,
            partial_close_quantity=0.0,
            profit_price_distance=profit_distance,
            profit_r=current_r,
            reason=(
                "No advanced trade-management trigger "
                "requires action."
            ),
        )


def management_decision_to_dict(
    decision: ManagementDecision,
) -> dict:
    """Serialize a management decision safely."""

    return {
        "action": decision.action.value,
        "trade_id": decision.trade_id,
        "new_stop_loss": decision.new_stop_loss,
        "partial_close_quantity": (
            decision.partial_close_quantity
        ),
        "profit_price_distance": (
            decision.profit_price_distance
        ),
        "profit_r": decision.profit_r,
        "reason": decision.reason,
        "execution_type": decision.execution_type,
        "read_only": decision.read_only,
        "broker_order_required": (
            decision.broker_order_required
        ),
    }
