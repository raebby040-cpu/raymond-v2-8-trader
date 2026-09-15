"""
RAYMOND v2.8 - Automatic Trade Manager

Stage 17.5

ADDITIVE ONLY.

This module does NOT replace or modify:
- the 9 brains
- indicators
- existing strategy
- AI scoring
- risk engine
- entry pipeline
- paper execution gateway
- existing persistent position system
- existing lifecycle manager

This manager is responsible only for an ALREADY OPEN paper position.

Possible decisions:
- HOLD
- CLOSE
- MODIFY_SL
- MODIFY_TP
- MODIFY_SL_TP

Safety:
- Paper only
- Read only decision layer
- Never contacts MT5
- Never contacts a live broker
- Never creates a new position
- Never widens an existing stop-loss
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AutomaticManagementAction(str, Enum):
    HOLD = "hold"
    CLOSE = "close"
    MODIFY_SL = "modify_sl"
    MODIFY_TP = "modify_tp"
    MODIFY_SL_TP = "modify_sl_tp"


@dataclass(frozen=True)
class AutomaticManagementConfig:
    """
    Configuration for automatic management.

    These are deliberately conservative defaults.
    """

    # When profit reaches this many R, protection can begin.
    profit_protection_r: float = 1.0

    # Amount of the original risk that may be locked as profit.
    lock_profit_r: float = 0.25

    # Strong reversal threshold.
    reversal_threshold: float = 0.75

    # Trailing distance in price units.
    trailing_distance: float = 5.0

    # Minimum stop movement before another modification.
    trailing_step: float = 1.0

    # Allow TP extension after strong profitable continuation.
    extend_tp_after_r: float = 2.0

    # Distance added beyond current price when extending TP.
    tp_extension_distance: float = 5.0

    def validate(self) -> None:
        if self.profit_protection_r <= 0:
            raise ValueError(
                "profit_protection_r must be greater than zero"
            )

        if self.lock_profit_r < 0:
            raise ValueError(
                "lock_profit_r cannot be negative"
            )

        if not 0 < self.reversal_threshold <= 1:
            raise ValueError(
                "reversal_threshold must be between 0 and 1"
            )

        if self.trailing_distance <= 0:
            raise ValueError(
                "trailing_distance must be greater than zero"
            )

        if self.trailing_step <= 0:
            raise ValueError(
                "trailing_step must be greater than zero"
            )

        if self.extend_tp_after_r <= 0:
            raise ValueError(
                "extend_tp_after_r must be greater than zero"
            )

        if self.tp_extension_distance <= 0:
            raise ValueError(
                "tp_extension_distance must be greater than zero"
            )


@dataclass(frozen=True)
class AutomaticManagementDecision:
    """
    Decision produced by the automatic trade manager.

    This is a decision only.
    It does not execute anything.
    """

    action: AutomaticManagementAction

    trade_id: str

    new_stop_loss: Optional[float]

    new_take_profit: Optional[float]

    profit_r: float

    reason: str

    execution_type: str = "paper"

    read_only: bool = True

    broker_order_required: bool = False

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "trade_id": self.trade_id,
            "new_stop_loss": self.new_stop_loss,
            "new_take_profit": self.new_take_profit,
            "profit_r": self.profit_r,
            "reason": self.reason,
            "execution_type": self.execution_type,
            "read_only": self.read_only,
            "broker_order_required": self.broker_order_required,
        }


class AutomaticTradeManager:
    """
    Higher-level management decision engine.

    The existing RAYMOND entry system decides whether to OPEN.

    This manager decides what to do AFTER a position is already open.

    It can:
        HOLD
        CLOSE
        MODIFY_SL
        MODIFY_TP
        MODIFY_SL_TP

    It never creates a new position.
    """

    def __init__(
        self,
        config: Optional[AutomaticManagementConfig] = None,
    ) -> None:

        self.config = (
            config
            if config is not None
            else AutomaticManagementConfig()
        )

        self.config.validate()

    # ============================================================
    # BASIC CALCULATIONS
    # ============================================================

    @staticmethod
    def profit_distance(
        direction: str,
        entry_price: float,
        current_price: float,
    ) -> float:

        direction = direction.lower()

        if direction == "buy":
            return current_price - entry_price

        if direction == "sell":
            return entry_price - current_price

        raise ValueError(
            "direction must be BUY or SELL"
        )

    @staticmethod
    def risk_distance(
        entry_price: float,
        stop_loss: Optional[float],
    ) -> float:

        if stop_loss is None:
            raise ValueError(
                "stop_loss is required for R-based management"
            )

        distance = abs(
            entry_price - stop_loss
        )

        if distance <= 0:
            raise ValueError(
                "stop_loss distance must be greater than zero"
            )

        return distance

    @classmethod
    def profit_r(
        cls,
        direction: str,
        entry_price: float,
        current_price: float,
        stop_loss: Optional[float],
    ) -> float:

        profit = cls.profit_distance(
            direction,
            entry_price,
            current_price,
        )

        risk = cls.risk_distance(
            entry_price,
            stop_loss,
        )

        return profit / risk

    # ============================================================
    # STOP SAFETY
    # ============================================================

    @staticmethod
    def stop_improves(
        direction: str,
        old_stop: Optional[float],
        new_stop: float,
    ) -> bool:

        if old_stop is None:
            return True

        direction = direction.lower()

        if direction == "buy":
            return new_stop > old_stop

        if direction == "sell":
            return new_stop < old_stop

        raise ValueError(
            "direction must be BUY or SELL"
        )

    @staticmethod
    def stop_is_valid(
        direction: str,
        entry_price: float,
        stop_loss: float,
    ) -> bool:

        direction = direction.lower()

        if direction == "buy":
            return stop_loss < entry_price

        if direction == "sell":
            return stop_loss > entry_price

        raise ValueError(
            "direction must be BUY or SELL"
        )

    @staticmethod
    def take_profit_is_valid(
        direction: str,
        entry_price: float,
        take_profit: float,
    ) -> bool:

        direction = direction.lower()

        if direction == "buy":
            return take_profit > entry_price

        if direction == "sell":
            return take_profit < entry_price

        raise ValueError(
            "direction must be BUY or SELL"
        )

    # ============================================================
    # MAIN DECISION
    # ============================================================

    def evaluate(
        self,
        *,
        trade_id: str,
        direction: str,
        entry_price: float,
        current_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        market_strength: float = 0.0,
        thesis_invalidated: bool = False,
    ) -> AutomaticManagementDecision:

        direction = direction.lower()

        if direction not in {
            "buy",
            "sell",
        }:
            raise ValueError(
                "direction must be BUY or SELL"
            )

        if entry_price <= 0:
            raise ValueError(
                "entry_price must be greater than zero"
            )

        if current_price <= 0:
            raise ValueError(
                "current_price must be greater than zero"
            )

        if stop_loss is None:
            raise ValueError(
                "An open managed position requires a stop_loss"
            )

        if not self.stop_is_valid(
            direction,
            entry_price,
            stop_loss,
        ):
            raise ValueError(
                "Existing stop_loss is invalid for position direction"
            )

        current_r = self.profit_r(
            direction,
            entry_price,
            current_price,
            stop_loss,
        )

        # ========================================================
        # 1. THESIS INVALIDATION
        # ========================================================

        if thesis_invalidated:

            return AutomaticManagementDecision(
                action=AutomaticManagementAction.CLOSE,
                trade_id=trade_id,
                new_stop_loss=None,
                new_take_profit=None,
                profit_r=current_r,
                reason=(
                    "Original trade thesis has been invalidated; "
                    "close the paper position."
                ),
            )

        # ========================================================
        # 2. STRONG REVERSAL WHILE LOSING
        # ========================================================

        strong_reversal = (
            (
                direction == "buy"
                and market_strength
                <= -self.config.reversal_threshold
            )
            or
            (
                direction == "sell"
                and market_strength
                >= self.config.reversal_threshold
            )
        )

        if strong_reversal and current_r < 0:

            return AutomaticManagementDecision(
                action=AutomaticManagementAction.CLOSE,
                trade_id=trade_id,
                new_stop_loss=None,
                new_take_profit=None,
                profit_r=current_r,
                reason=(
                    "Strong market reversal detected while "
                    "the position is losing; close now."
                ),
            )

        # ========================================================
        # 3. PROFIT PROTECTION
        # ========================================================

        if current_r >= self.config.profit_protection_r:

            if direction == "buy":

                protected_stop = (
                    entry_price
                    + (
                        self.risk_distance(
                            entry_price,
                            stop_loss,
                        )
                        * self.config.lock_profit_r
                    )
                )

                trailing_stop = (
                    current_price
                    - self.config.trailing_distance
                )

                candidate_stop = max(
                    protected_stop,
                    trailing_stop,
                )

            else:

                protected_stop = (
                    entry_price
                    - (
                        self.risk_distance(
                            entry_price,
                            stop_loss,
                        )
                        * self.config.lock_profit_r
                    )
                )

                trailing_stop = (
                    current_price
                    + self.config.trailing_distance
                )

                candidate_stop = min(
                    protected_stop,
                    trailing_stop,
                )

            if (
                self.stop_is_valid(
                    direction,
                    entry_price,
                    candidate_stop,
                )
                and self.stop_improves(
                    direction,
                    stop_loss,
                    candidate_stop,
                )
            ):

                if (
                    abs(
                        candidate_stop - stop_loss
                    )
                    >= self.config.trailing_step
                ):

                    return AutomaticManagementDecision(
                        action=AutomaticManagementAction.MODIFY_SL,
                        trade_id=trade_id,
                        new_stop_loss=candidate_stop,
                        new_take_profit=None,
                        profit_r=current_r,
                        reason=(
                            "Profit protection conditions justify "
                            "tightening the stop-loss."
                        ),
                    )

        # ========================================================
        # 4. TP EXTENSION
        # ========================================================

        continuation = (
            (
                direction == "buy"
                and market_strength
                >= self.config.reversal_threshold
            )
            or
            (
                direction == "sell"
                and market_strength
                <= -self.config.reversal_threshold
            )
        )

        if (
            continuation
            and current_r
            >= self.config.extend_tp_after_r
            and take_profit is not None
        ):

            if direction == "buy":

                candidate_tp = max(
                    take_profit,
                    current_price
                    + self.config.tp_extension_distance,
                )

            else:

                candidate_tp = min(
                    take_profit,
                    current_price
                    - self.config.tp_extension_distance,
                )

            if (
                candidate_tp != take_profit
                and self.take_profit_is_valid(
                    direction,
                    entry_price,
                    candidate_tp,
                )
            ):

                return AutomaticManagementDecision(
                    action=AutomaticManagementAction.MODIFY_TP,
                    trade_id=trade_id,
                    new_stop_loss=None,
                    new_take_profit=candidate_tp,
                    profit_r=current_r,
                    reason=(
                        "Strong continuation detected; "
                        "extend take-profit to allow the trend "
                        "to continue."
                    ),
                )

        # ========================================================
        # 5. NOTHING REQUIRES CHANGE
        # ========================================================

        return AutomaticManagementDecision(
            action=AutomaticManagementAction.HOLD,
            trade_id=trade_id,
            new_stop_loss=None,
            new_take_profit=None,
            profit_r=current_r,
            reason=(
                "Current market conditions do not require "
                "closing or modifying the position."
            ),
        )


def automatic_management_decision_to_dict(
    decision: AutomaticManagementDecision,
) -> dict:

    return decision.to_dict()
