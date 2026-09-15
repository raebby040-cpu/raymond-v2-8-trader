"""
RAYMOND v2.8 - Automatic Trade Manager Adapter

Stage 17.5

ADDITIVE INTEGRATION LAYER.

Purpose:
    Connect the existing RAYMOND decision output to the new
    AutomaticTradeManager without changing the existing:

    - 9 brains
    - indicators
    - strategy
    - AI scoring
    - risk engine
    - entry pipeline
    - paper execution gateway
    - persistent position system
    - existing lifecycle manager
    - break-even manager
    - trailing manager
    - partial-close manager

This module ONLY translates existing information into a
management decision.

It does NOT:
    - create positions
    - open trades
    - place broker orders
    - contact MT5
    - bypass Risk Engine
    - close database positions
    - modify database state
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

try:
    from .automatic_trade_manager import (
        AutomaticManagementAction,
        AutomaticManagementDecision,
        AutomaticTradeManager,
    )
except ImportError:
    from automatic_trade_manager import (
        AutomaticManagementAction,
        AutomaticManagementDecision,
        AutomaticTradeManager,
    )


@dataclass(frozen=True)
class AutomaticManagementInput:
    """
    Normalized read-only information required by the manager.
    """

    trade_id: str
    direction: str
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: Optional[float]

    initial_stop_loss: Optional[float] = None
    risk_1r: Optional[float] = None

    market_strength: float = 0.0
    thesis_invalidated: bool = False


class AutomaticTradeManagerAdapter:
    """
    Safe adapter around AutomaticTradeManager.

    This class does not execute decisions.

    It only converts an existing persistent position and
    existing strategy/AI information into a decision object.
    """

    def __init__(
        self,
        manager: Optional[AutomaticTradeManager] = None,
    ) -> None:

        self.manager = (
            manager
            if manager is not None
            else AutomaticTradeManager()
        )

    # ============================================================
    # NORMALIZATION
    # ============================================================

    @staticmethod
    def _value(
        source: Any,
        name: str,
        default: Any = None,
    ) -> Any:
        """
        Read either an object attribute or dictionary key.
        """

        if source is None:
            return default

        if isinstance(source, dict):
            return source.get(name, default)

        return getattr(
            source,
            name,
            default,
        )

    @classmethod
    def _direction(
        cls,
        position: Any,
    ) -> str:
        """
        Normalize Position.direction.

        Supports:
            BUY
            SELL
            buy
            sell
            enum-like values
        """

        direction = cls._value(
            position,
            "direction",
        )

        if direction is None:
            raise ValueError(
                "Open position has no direction"
            )

        if hasattr(direction, "value"):
            direction = direction.value

        direction = str(direction).lower()

        if direction not in {
            "buy",
            "sell",
        }:
            raise ValueError(
                "Position direction must be BUY or SELL"
            )

        return direction

    @classmethod
    def _trade_id(
        cls,
        position: Any,
    ) -> str:
        """
        Prefer trade_id.

        Fall back to position_id so older persistent positions
        can still be evaluated.
        """

        trade_id = cls._value(
            position,
            "trade_id",
        )

        if trade_id:
            return str(trade_id)

        position_id = cls._value(
            position,
            "position_id",
        )

        if position_id:
            return str(position_id)

        raise ValueError(
            "Position has neither trade_id nor position_id"
        )

    @classmethod
    def _entry_price(
        cls,
        position: Any,
    ) -> float:

        value = cls._value(
            position,
            "entry_price",
        )

        if value is None:
            raise ValueError(
                "Position has no entry_price"
            )

        return float(value)

    @classmethod
    def _current_price(
        cls,
        position: Any,
        current_price: Optional[float],
    ) -> float:

        if current_price is not None:
            return float(current_price)

        value = cls._value(
            position,
            "current_price",
        )

        if value is None:
            raise ValueError(
                "Current market price is required"
            )

        return float(value)

    @classmethod
    def _current_stop(
        cls,
        position: Any,
    ) -> float:
        """
        Prefer current_stop_loss.

        Fall back to legacy stop_loss for compatibility.
        """

        value = cls._value(
            position,
            "current_stop_loss",
        )

        if value is None:
            value = cls._value(
                position,
                "stop_loss",
            )

        if value is None:
            raise ValueError(
                "Open position has no stop_loss"
            )

        return float(value)

    @classmethod
    def _initial_stop(
        cls,
        position: Any,
    ) -> Optional[float]:

        value = cls._value(
            position,
            "initial_stop_loss",
        )

        if value is None:
            return None

        return float(value)

    @classmethod
    def _risk_1r(
        cls,
        position: Any,
    ) -> Optional[float]:

        value = cls._value(
            position,
            "risk_1r",
        )

        if value is None:
            return None

        value = float(value)

        if value <= 0:
            return None

        return value

    @classmethod
    def _take_profit(
        cls,
        position: Any,
    ) -> Optional[float]:
        """
        Prefer take_profit_1.

        Fall back to legacy take_profit.
        """

        value = cls._value(
            position,
            "take_profit_1",
        )

        if value is None:
            value = cls._value(
                position,
                "take_profit",
            )

        if value is None:
            return None

        return float(value)

    # ============================================================
    # MARKET-STRENGTH TRANSLATION
    # ============================================================

    @staticmethod
    def _clamp_strength(
        value: float,
    ) -> float:
        """
        Keep market strength within the manager's safe range.
        """

        return max(
            -1.0,
            min(
                1.0,
                float(value),
            ),
        )

    @classmethod
    def market_strength_from_decision(
        cls,
        decision: Any,
    ) -> float:
        """
        Translate existing RAYMOND decision information into
        a normalized directional market-strength value.

        This does NOT recalculate indicators.

        Priority:

        1. Explicit market_strength if already supplied.
        2. Existing direction + confidence.
        3. Existing technical/confluence score.
        4. Neutral fallback.

        The adapter deliberately remains conservative.
        """

        explicit = cls._value(
            decision,
            "market_strength",
            None,
        )

        if explicit is not None:
            return cls._clamp_strength(
                float(explicit)
            )

        direction = cls._value(
            decision,
            "direction",
            None,
        )

        if hasattr(direction, "value"):
            direction = direction.value

        if direction is None:
            return 0.0

        direction = str(direction).lower()

        if direction not in {
            "buy",
            "sell",
        }:
            return 0.0

        confidence = cls._value(
            decision,
            "confidence",
            None,
        )

        if confidence is None:
            confidence = 0.0

        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        # Handle either 0-1 or percentage-style confidence.
        if confidence > 1.0:
            confidence /= 100.0

        confidence = max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        )

        technical_score = cls._value(
            decision,
            "technical_score",
            None,
        )

        if technical_score is not None:
            try:
                score = float(technical_score)

                # Typical score systems may be percentage-like.
                if abs(score) > 1.0:
                    score /= 100.0

                score = cls._clamp_strength(score)

                if direction == "buy":
                    return cls._clamp_strength(
                        max(
                            confidence,
                            score,
                        )
                    )

                return cls._clamp_strength(
                    min(
                        -confidence,
                        score,
                    )
                )

            except (TypeError, ValueError):
                pass

        if direction == "buy":
            return confidence

        if direction == "sell":
            return -confidence

        return 0.0

    # ============================================================
    # THESIS VALIDATION
    # ============================================================

    @classmethod
    def thesis_invalidated_from_decision(
        cls,
        decision: Any,
        position: Any,
    ) -> bool:
        """
        Determine whether the existing trade thesis appears
        invalidated.

        IMPORTANT:

        We do NOT invent a new trading strategy here.

        Explicit invalidation signals are honored when the
        existing system already provides them.

        Otherwise this remains False.

        This prevents the adapter from unexpectedly closing
        trades simply because a field is missing.
        """

        explicit = cls._value(
            decision,
            "thesis_invalidated",
            None,
        )

        if explicit is not None:
            return bool(explicit)

        position_value = cls._value(
            position,
            "thesis_invalidated",
            None,
        )

        if position_value is not None:
            return bool(position_value)

        return False

    # ============================================================
    # BUILD NORMALIZED INPUT
    # ============================================================

    @classmethod
    def build_input(
        cls,
        *,
        position: Any,
        decision: Any = None,
        current_price: Optional[float] = None,
    ) -> AutomaticManagementInput:
        """
        Build the manager's normalized read-only input.
        """

        direction = cls._direction(
            position
        )

        market_strength = (
            cls.market_strength_from_decision(
                decision
            )
            if decision is not None
            else 0.0
        )

        thesis_invalidated = (
            cls.thesis_invalidated_from_decision(
                decision,
                position,
            )
            if decision is not None
            else False
        )

        return AutomaticManagementInput(
            trade_id=cls._trade_id(
                position
            ),
            direction=direction,
            entry_price=cls._entry_price(
                position
            ),
            current_price=cls._current_price(
                position,
                current_price,
            ),
            stop_loss=cls._current_stop(
                position
            ),
            take_profit=cls._take_profit(
                position
            ),
            initial_stop_loss=cls._initial_stop(
                position
            ),
            risk_1r=cls._risk_1r(
                position
            ),
            market_strength=market_strength,
            thesis_invalidated=thesis_invalidated,
        )

    # ============================================================
    # EVALUATE
    # ============================================================

    def evaluate(
        self,
        *,
        position: Any,
        decision: Any = None,
        current_price: Optional[float] = None,
    ) -> AutomaticManagementDecision:
        """
        Evaluate an existing open position.

        Returns a decision only.

        No database mutation occurs.
        No broker operation occurs.
        """

        data = self.build_input(
            position=position,
            decision=decision,
            current_price=current_price,
        )

        return self.manager.evaluate(
            trade_id=data.trade_id,
            direction=data.direction,
            entry_price=data.entry_price,
            current_price=data.current_price,
            stop_loss=data.stop_loss,
            take_profit=data.take_profit,
            market_strength=data.market_strength,
            thesis_invalidated=data.thesis_invalidated,
            initial_stop_loss=data.initial_stop_loss,
        )

    # ============================================================
    # SERIALIZATION
    # ============================================================

    @staticmethod
    def to_dict(
        decision: AutomaticManagementDecision,
    ) -> dict:
        """
        Convert a management decision into API/dashboard-safe
        JSON-compatible data.
        """

        return decision.to_dict()

    @staticmethod
    def is_actionable(
        decision: AutomaticManagementDecision,
    ) -> bool:
        """
        Return True when the decision requires an action.

        HOLD is intentionally non-actionable.
        """

        return (
            decision.action
            != AutomaticManagementAction.HOLD
        )

    @staticmethod
    def is_close(
        decision: AutomaticManagementDecision,
    ) -> bool:

        return (
            decision.action
            == AutomaticManagementAction.CLOSE
        )

    @staticmethod
    def is_stop_modification(
        decision: AutomaticManagementDecision,
    ) -> bool:

        return decision.action in {
            AutomaticManagementAction.MODIFY_SL,
            AutomaticManagementAction.MODIFY_SL_TP,
        }

    @staticmethod
    def is_take_profit_modification(
        decision: AutomaticManagementDecision,
    ) -> bool:

        return decision.action in {
            AutomaticManagementAction.MODIFY_TP,
            AutomaticManagementAction.MODIFY_SL_TP,
        }


def evaluate_automatic_trade_management(
    *,
    position: Any,
    decision: Any = None,
    current_price: Optional[float] = None,
    manager: Optional[AutomaticTradeManager] = None,
) -> AutomaticManagementDecision:
    """
    Convenience function for future service/API integration.

    This remains decision-only.
    """

    adapter = AutomaticTradeManagerAdapter(
        manager=manager
    )

    return adapter.evaluate(
        position=position,
        decision=decision,
        current_price=current_price,
    )
