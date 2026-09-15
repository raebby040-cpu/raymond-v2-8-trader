"""
RAYMOND v2.8 - Automatic Trade Manager

Stage 17.5

ADDITIVE ONLY.

This module manages an ALREADY OPEN paper position.

It does NOT replace or modify:
- the 9 brains
- indicators
- existing strategy
- AI scoring
- risk engine
- entry pipeline
- paper execution gateway
- persistent position system
- existing lifecycle manager
- existing break-even/trailing/partial manager

Possible decisions:
- HOLD
- CLOSE
- MODIFY_SL
- MODIFY_TP
- MODIFY_SL_TP

Safety:
- Paper decision layer only
- Never creates a position
- Never opens a trade
- Never contacts MT5
- Never contacts a live broker
- Never widens an existing stop-loss
"""

from __future__ import annotations

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
    Conservative configuration for automatic position management.
    """

    # Begin protection once profit reaches this many R.
    profit_protection_r: float = 1.0

    # Lock this much of the ORIGINAL risk as profit.
    lock_profit_r: float = 0.25

    # Strong reversal threshold.
    reversal_threshold: float = 0.75

    # Trailing distance in price units.
    trailing_distance: float = 5.0

    # Minimum stop movement before another SL modification.
    trailing_step: float = 1.0

    # Allow TP extension after this many R.
    extend_tp_after_r: float = 2.0

    # Distance beyond current price for TP extension.
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

    This object does not execute anything.
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

    Existing RAYMOND components decide whether to OPEN.

    This component decides what to do AFTER a position is open.

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
        """
        Positive value means the position is profitable.
        Negative value means the position is losing.
        """

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
        """
        Calculate a positive price-distance risk.

        NOTE:
        This is intended to work with the original protective
        stop or another stable 1R reference.
        """

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
        initial_stop_loss: Optional[float] = None,
    ) -> float:
        """
        Calculate current profit in R.

        If initial_stop_loss is available, it is preferred.

        This prevents R from changing artificially when an
        existing stop has already been moved to breakeven/profit.
        """

        profit = cls.profit_distance(
            direction,
            entry_price,
            current_price,
        )

        risk_reference = (
            initial_stop_loss
            if initial_stop_loss is not None
            else stop_loss
        )

        risk = cls.risk_distance(
            entry_price,
            risk_reference,
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
        """
        A stop may only move in the protective direction.

        BUY:
            higher stop = improvement

        SELL:
            lower stop = improvement
        """

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
        current_price: Optional[float] = None,
    ) -> bool:
        """
        Validate that a stop is on the protective side.

        IMPORTANT:
        A stop is allowed to move beyond entry once the trade
        becomes profitable.

        BUY:
            stop must remain below current market price.

        SELL:
            stop must remain above current market price.
        """

        direction = direction.lower()

        reference_price = (
            current_price
            if current_price is not None
            else entry_price
        )

        if direction == "buy":
            return stop_loss < reference_price

        if direction == "sell":
            return stop_loss > reference_price

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
    # DECISION HELPERS
    # ============================================================

    @staticmethod
    def _close_decision(
        *,
        trade_id: str,
        current_r: float,
        reason: str,
    ) -> AutomaticManagementDecision:

        return AutomaticManagementDecision(
            action=AutomaticManagementAction.CLOSE,
            trade_id=trade_id,
            new_stop_loss=None,
            new_take_profit=None,
            profit_r=current_r,
            reason=reason,
        )

    @staticmethod
    def _hold_decision(
        *,
        trade_id: str,
        current_r: float,
        reason: str,
    ) -> AutomaticManagementDecision:

        return AutomaticManagementDecision(
            action=AutomaticManagementAction.HOLD,
            trade_id=trade_id,
            new_stop_loss=None,
            new_take_profit=None,
            profit_r=current_r,
            reason=reason,
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
        initial_stop_loss: Optional[float] = None,
    ) -> AutomaticManagementDecision:
        """
        Evaluate one already-open paper position.

        market_strength:
            -1.0 = strong bearish pressure
             0.0 = neutral
            +1.0 = strong bullish pressure

        thesis_invalidated:
            True means the original trade thesis is no longer valid.

        initial_stop_loss:
            Original SL used to establish stable 1R calculations.
        """

        direction = direction.lower()

        if direction not in {
            "buy",
            "sell",
        }:
            raise ValueError(
                "direction must be BUY or SELL"
            )

        if not trade_id.strip():
            raise ValueError(
                "trade_id is required"
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
            current_price=current_price,
        ):
            raise ValueError(
                "Existing stop_loss is invalid for "
                "the current position direction/price"
            )

        if not -1.0 <= market_strength <= 1.0:
            raise ValueError(
                "market_strength must be between -1.0 and 1.0"
            )

        current_r = self.profit_r(
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            stop_loss=stop_loss,
            initial_stop_loss=initial_stop_loss,
        )

        # ========================================================
        # 1. THESIS INVALIDATION
        # ========================================================

        if thesis_invalidated:

            return self._close_decision(
                trade_id=trade_id,
                current_r=current_r,
                reason=(
                    "Original trade thesis has been invalidated; "
                    "close the paper position at the current market price."
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

            return self._close_decision(
                trade_id=trade_id,
                current_r=current_r,
                reason=(
                    "Strong market reversal detected while "
                    "the position is losing; close at the "
                    "current market price."
                ),
            )

        # ========================================================
        # 3. PROFIT PROTECTION
        # ========================================================

        if current_r >= self.config.profit_protection_r:

            risk_distance = self.risk_distance(
                entry_price,
                (
                    initial_stop_loss
                    if initial_stop_loss is not None
                    else stop_loss
                ),
            )

            if direction == "buy":

                protected_stop = (
                    entry_price
                    + (
                        risk_distance
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
                        risk_distance
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

            stop_change_is_valid = (
                self.stop_is_valid(
                    direction,
                    entry_price,
                    candidate_stop,
                    current_price=current_price,
                )
                and self.stop_improves(
                    direction,
                    stop_loss,
                    candidate_stop,
                )
            )

            if stop_change_is_valid:

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
            and current_r >= self.config.extend_tp_after_r
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
                        "extend take-profit to allow the "
                        "trend to continue."
                    ),
                )

        # ========================================================
        # 5. NOTHING REQUIRES CHANGE
        # ========================================================

        return self._hold_decision(
            trade_id=trade_id,
            current_r=current_r,
            reason=(
                "Current market conditions do not require "
                "closing or modifying the position."
            ),
        )


def automatic_management_decision_to_dict(
    decision: AutomaticManagementDecision,
) -> dict:
    """
    Compatibility helper for API/dashboard serialization.
    """

    return decision.to_dict()
