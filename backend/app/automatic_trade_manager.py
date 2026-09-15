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
- existing break-even manager
- existing trailing manager
- existing partial-close manager

Possible decisions:
- HOLD
- CLOSE
- MODIFY_SL
- MODIFY_TP
- MODIFY_SL_TP

Safety:
- Paper only
- Decision layer only
- Never contacts MT5
- Never contacts a live broker
- Never creates a new position
- Never executes a broker order
- Never widens an existing stop-loss
- Never bypasses the risk engine
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
    Conservative automatic-management configuration.
    """

    # Protection begins after this many R of profit.
    profit_protection_r: float = 1.0

    # At protection, lock this many R of original risk.
    lock_profit_r: float = 0.25

    # Strong reversal threshold.
    reversal_threshold: float = 0.75

    # Trailing distance in price units.
    trailing_distance: float = 5.0

    # Minimum SL movement before another modification.
    trailing_step: float = 1.0

    # TP extension can begin after this many R.
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

        if self.lock_profit_r >= self.profit_protection_r:
            raise ValueError(
                "lock_profit_r must be less than profit_protection_r"
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

    This object contains instructions only.

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
    Automatic management decision engine.

    Existing RAYMOND entry logic decides whether to OPEN.

    This manager acts only AFTER a position already exists.

    It can decide:

        HOLD
        CLOSE
        MODIFY_SL
        MODIFY_TP
        MODIFY_SL_TP

    It never creates a position.
    It never executes an order.
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
        initial_stop_loss: Optional[float] = None,
    ) -> float:
        """
        Calculate profit in R.

        IMPORTANT:

        If initial_stop_loss is available, it is used as the
        denominator so that 1R remains the original trade risk.

        Tightening the current stop therefore does not
        artificially change the trade's R value.
        """

        profit = cls.profit_distance(
            direction,
            entry_price,
            current_price,
        )

        reference_stop = (
            initial_stop_loss
            if initial_stop_loss is not None
            else stop_loss
        )

        risk = cls.risk_distance(
            entry_price,
            reference_stop,
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
        True only when the new SL improves protection.

        BUY:
            higher SL = improvement

        SELL:
            lower SL = improvement
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
        Validate an SL without preventing profitable
        stop-loss movement.

        BUY:
            SL must remain below current price.

        SELL:
            SL must remain above current price.

        This deliberately allows:

        BUY:
            SL > entry

        SELL:
            SL < entry

        once the position is profitable.
        """

        direction = direction.lower()

        if direction == "buy":

            if stop_loss >= entry_price:
                if current_price is None:
                    return True

                return stop_loss < current_price

            return stop_loss < entry_price

        if direction == "sell":

            if stop_loss <= entry_price:
                if current_price is None:
                    return True

                return stop_loss > current_price

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

    @staticmethod
    def take_profit_improves(
        direction: str,
        old_take_profit: Optional[float],
        new_take_profit: float,
    ) -> bool:
        """
        TP modifications are only allowed when they extend
        the target in the direction of the trade.

        BUY:
            higher TP = improvement

        SELL:
            lower TP = improvement
        """

        if old_take_profit is None:
            return True

        direction = direction.lower()

        if direction == "buy":
            return new_take_profit > old_take_profit

        if direction == "sell":
            return new_take_profit < old_take_profit

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
    # CANDIDATE STOP
    # ============================================================

    def _candidate_stop_loss(
        self,
        *,
        direction: str,
        entry_price: float,
        current_price: float,
        current_stop_loss: float,
        current_r: float,
    ) -> Optional[float]:
        """
        Produce a safer SL candidate.

        The candidate can only move the stop in the protective
        direction.

        It can cross entry once the market has moved far enough
        in profit.

        No widening is permitted.
        """

        direction = direction.lower()

        candidate: Optional[float] = None

        # --------------------------------------------------------
        # PROFIT PROTECTION
        # --------------------------------------------------------

        if current_r >= self.config.profit_protection_r:

            if direction == "buy":
                risk_distance = abs(
                    entry_price - current_stop_loss
                )

                # Use original-risk approximation when the current
                # stop has already moved.
                protection_distance = (
                    risk_distance
                    * self.config.lock_profit_r
                )

                candidate = (
                    entry_price
                    + protection_distance
                )

            elif direction == "sell":
                risk_distance = abs(
                    entry_price - current_stop_loss
                )

                protection_distance = (
                    risk_distance
                    * self.config.lock_profit_r
                )

                candidate = (
                    entry_price
                    - protection_distance
                )

        # --------------------------------------------------------
        # TRAILING PROTECTION
        # --------------------------------------------------------

        if direction == "buy":

            trailing_candidate = (
                current_price
                - self.config.trailing_distance
            )

            if candidate is None:
                candidate = trailing_candidate
            else:
                candidate = max(
                    candidate,
                    trailing_candidate,
                )

            if candidate <= current_stop_loss:
                return None

            if candidate >= current_price:
                return None

        elif direction == "sell":

            trailing_candidate = (
                current_price
                + self.config.trailing_distance
            )

            if candidate is None:
                candidate = trailing_candidate
            else:
                candidate = min(
                    candidate,
                    trailing_candidate,
                )

            if candidate >= current_stop_loss:
                return None

            if candidate <= current_price:
                return None

        if candidate is None:
            return None

        if not self.stop_is_valid(
            direction,
            entry_price,
            candidate,
            current_price,
        ):
            return None

        if not self.stop_improves(
            direction,
            current_stop_loss,
            candidate,
        ):
            return None

        movement = abs(
            candidate - current_stop_loss
        )

        if movement < self.config.trailing_step:
            return None

        return candidate

    # ============================================================
    # CANDIDATE TAKE PROFIT
    # ============================================================

    def _candidate_take_profit(
        self,
        *,
        direction: str,
        entry_price: float,
        current_price: float,
        current_take_profit: Optional[float],
        current_r: float,
        market_strength: float,
    ) -> Optional[float]:
        """
        Extend TP only during strong profitable continuation.

        Existing TP is never reduced.
        """

        if current_take_profit is None:
            return None

        if current_r < self.config.extend_tp_after_r:
            return None

        if market_strength < self.config.reversal_threshold:
            return None

        direction = direction.lower()

        if direction == "buy":

            candidate = (
                current_price
                + self.config.tp_extension_distance
            )

            candidate = max(
                candidate,
                current_take_profit
                + self.config.tp_extension_distance,
            )

        elif direction == "sell":

            candidate = (
                current_price
                - self.config.tp_extension_distance
            )

            candidate = min(
                candidate,
                current_take_profit
                - self.config.tp_extension_distance,
            )

        else:
            raise ValueError(
                "direction must be BUY or SELL"
            )

        if not self.take_profit_is_valid(
            direction,
            entry_price,
            candidate,
        ):
            return None

        if not self.take_profit_improves(
            direction,
            current_take_profit,
            candidate,
        ):
            return None

        return candidate

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
        Evaluate an already-open position.

        This method is decision-only.

        It does not:
            - close database records
            - modify database state
            - create orders
            - send broker orders
            - contact MT5
        """

        direction = direction.lower()

        if direction not in {
            "buy",
            "sell",
        }:
            raise ValueError(
                "direction must be BUY or SELL"
            )

        if not trade_id:
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
            current_price,
        ):
            raise ValueError(
                "Existing stop_loss is invalid for position direction"
            )

        try:
            market_strength = float(
                market_strength
            )
        except (TypeError, ValueError):
            raise ValueError(
                "market_strength must be numeric"
            )

        if not -1.0 <= market_strength <= 1.0:
            raise ValueError(
                "market_strength must be between -1 and 1"
            )

        # --------------------------------------------------------
        # STABLE R CALCULATION
        # --------------------------------------------------------

        current_r = self.profit_r(
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            stop_loss=stop_loss,
            initial_stop_loss=initial_stop_loss,
        )

        # --------------------------------------------------------
        # 1. THESIS INVALIDATION
        # --------------------------------------------------------

        if thesis_invalidated:

            return self._close_decision(
                trade_id=trade_id,
                current_r=current_r,
                reason=(
                    "Trade thesis invalidated by existing "
                    "RAYMOND decision information."
                ),
            )

        # --------------------------------------------------------
        # 2. STRONG REVERSAL WHILE LOSING
        # --------------------------------------------------------

        if (
            current_r < 0
            and abs(market_strength)
            >= self.config.reversal_threshold
        ):

            reversal_against_trade = (
                direction == "buy"
                and market_strength
                <= -self.config.reversal_threshold
            ) or (
                direction == "sell"
                and market_strength
                >= self.config.reversal_threshold
            )

            if reversal_against_trade:

                return self._close_decision(
                    trade_id=trade_id,
                    current_r=current_r,
                    reason=(
                        "Strong market reversal detected "
                        "against the open position while "
                        "the position is losing."
                    ),
                )

        # --------------------------------------------------------
        # 3. CALCULATE PROTECTIVE SL CANDIDATE
        # --------------------------------------------------------

        new_stop_loss = self._candidate_stop_loss(
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            current_stop_loss=stop_loss,
            current_r=current_r,
        )

        # --------------------------------------------------------
        # 4. CALCULATE CONTINUATION TP CANDIDATE
        # --------------------------------------------------------

        new_take_profit = self._candidate_take_profit(
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            current_take_profit=take_profit,
            current_r=current_r,
            market_strength=market_strength,
        )

        # --------------------------------------------------------
        # 5. BOTH SL + TP
        # --------------------------------------------------------

        if (
            new_stop_loss is not None
            and new_take_profit is not None
        ):

            return AutomaticManagementDecision(
                action=AutomaticManagementAction.MODIFY_SL_TP,
                trade_id=trade_id,
                new_stop_loss=new_stop_loss,
                new_take_profit=new_take_profit,
                profit_r=current_r,
                reason=(
                    "Profitable continuation detected. "
                    "Protective stop-loss improvement and "
                    "take-profit extension are both justified."
                ),
            )

        # --------------------------------------------------------
        # 6. SL ONLY
        # --------------------------------------------------------

        if new_stop_loss is not None:

            return AutomaticManagementDecision(
                action=AutomaticManagementAction.MODIFY_SL,
                trade_id=trade_id,
                new_stop_loss=new_stop_loss,
                new_take_profit=None,
                profit_r=current_r,
                reason=(
                    "Position has reached a protective level. "
                    "Stop-loss can be improved without widening "
                    "risk."
                ),
            )

        # --------------------------------------------------------
        # 7. TP ONLY
        # --------------------------------------------------------

        if new_take_profit is not None:

            return AutomaticManagementDecision(
                action=AutomaticManagementAction.MODIFY_TP,
                trade_id=trade_id,
                new_stop_loss=None,
                new_take_profit=new_take_profit,
                profit_r=current_r,
                reason=(
                    "Strong profitable continuation detected. "
                    "Take-profit can be extended."
                ),
            )

        # --------------------------------------------------------
        # 8. OTHERWISE HOLD
        # --------------------------------------------------------

        return self._hold_decision(
            trade_id=trade_id,
            current_r=current_r,
            reason=(
                "No management change is currently justified. "
                "Existing position protection remains in place."
            ),
        )


def evaluate_automatic_trade_management(
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
    manager: Optional[AutomaticTradeManager] = None,
) -> AutomaticManagementDecision:
    """
    Convenience function for future integration.

    Decision-only.

    No database or broker action occurs here.
    """

    automatic_manager = (
        manager
        if manager is not None
        else AutomaticTradeManager()
    )

    return automatic_manager.evaluate(
        trade_id=trade_id,
        direction=direction,
        entry_price=entry_price,
        current_price=current_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        market_strength=market_strength,
        thesis_invalidated=thesis_invalidated,
        initial_stop_loss=initial_stop_loss,
    )
