"""
RAYMOND v2.8 - Automatic Trade Manager Adapter

Stage 17.5A

PURPOSE
-------
Bridge the Stage 17.5 AutomaticTradeManager decision engine
to the existing persistent paper-position system.

This module is ADDITIVE ONLY.

It does NOT replace or modify:
- the 9 brains
- indicators
- existing strategy
- AI scoring
- Risk Engine
- entry pipeline
- paper execution gateway
- PositionRepository
- PaperPositionManager
- lifecycle manager
- break-even management
- trailing management
- partial-close management

SAFETY
------
- PAPER ONLY
- NO MT5
- NO Exness
- NO broker connection
- NO live orders
- NO new position creation
- NO Risk Engine bypass

The adapter only manages positions that already exist in
the persistent paper-position database.

IMPORTANT
---------
The existing PaperPositionManager remains responsible for the
existing mechanical management system.

This adapter adds higher-level decisions:
    HOLD
    CLOSE
    MODIFY_SL
    MODIFY_TP
    MODIFY_SL_TP

The adapter never creates an entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

try:
    from .automatic_trade_manager import (
        AutomaticManagementAction,
        AutomaticManagementDecision,
        AutomaticTradeManager,
    )
    from .models import PositionStatus
    from .position_repository import PositionRepository
except ImportError:
    from automatic_trade_manager import (
        AutomaticManagementAction,
        AutomaticManagementDecision,
        AutomaticTradeManager,
    )
    from models import PositionStatus
    from position_repository import PositionRepository


# ============================================================
# RESULT
# ============================================================


@dataclass(frozen=True)
class AutomaticManagementResult:
    """
    Result of evaluating one persistent paper position.

    This object describes what the adapter decided/applied.
    """

    position_id: str
    trade_id: Optional[str]
    symbol: str
    action: str
    applied: bool
    profit_r: Optional[float]
    reason: str
    error: Optional[str] = None

    paper_only: bool = True
    live_trading_enabled: bool = False
    broker_order_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "action": self.action,
            "applied": self.applied,
            "profit_r": self.profit_r,
            "reason": self.reason,
            "error": self.error,
            "safety": {
                "paper_only": self.paper_only,
                "live_trading_enabled": self.live_trading_enabled,
                "broker_order_allowed": self.broker_order_allowed,
            },
        }


# ============================================================
# ADAPTER
# ============================================================


class AutomaticTradeManagerAdapter:
    """
    Safe bridge between AutomaticTradeManager and PositionRepository.

    The adapter receives an already-open persistent position and
    applies only paper/database state changes.

    It does not execute broker orders.
    """

    def __init__(
        self,
        db,
        manager: Optional[AutomaticTradeManager] = None,
    ) -> None:

        self.db = db

        self.manager = (
            manager
            if manager is not None
            else AutomaticTradeManager()
        )

    # ========================================================
    # SAFETY
    # ========================================================

    @staticmethod
    def _assert_paper_only() -> None:
        """
        Hard safety barrier.

        This adapter must never become a live execution path.
        """

        live_trading_enabled = False
        broker_orders_allowed = False
        execution_authorized = False

        if live_trading_enabled:
            raise RuntimeError(
                "AutomaticTradeManagerAdapter cannot operate "
                "with live trading enabled."
            )

        if broker_orders_allowed:
            raise RuntimeError(
                "AutomaticTradeManagerAdapter cannot send "
                "broker orders."
            )

        if execution_authorized:
            raise RuntimeError(
                "AutomaticTradeManagerAdapter cannot operate "
                "with execution authorization enabled."
            )

    # ========================================================
    # NORMALIZATION
    # ========================================================

    @staticmethod
    def _direction(position) -> str:
        direction = position.direction

        value = getattr(
            direction,
            "value",
            direction,
        )

        value = str(value).lower()

        if value not in {
            "buy",
            "sell",
        }:
            raise ValueError(
                f"Unsupported position direction: {value}"
            )

        return value

    @staticmethod
    def _current_stop(position) -> Optional[float]:
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
    def _current_take_profit(
        position,
    ) -> Optional[float]:

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
    def _trade_id(position) -> str:
        trade_id = getattr(
            position,
            "trade_id",
            None,
        )

        if trade_id:
            return str(trade_id)

        return str(
            getattr(
                position,
                "position_id",
                "",
            )
        )

    # ========================================================
    # DECISION INPUT
    # ========================================================

    @staticmethod
    def _build_decision_inputs(
        position,
        current_price: float,
        market_strength: float,
        thesis_invalidated: bool,
    ) -> dict[str, Any]:

        return {
            "trade_id": AutomaticTradeManagerAdapter._trade_id(
                position
            ),
            "direction": AutomaticTradeManagerAdapter._direction(
                position
            ),
            "entry_price": float(
                position.entry_price
            ),
            "current_price": float(
                current_price
            ),
            "stop_loss": AutomaticTradeManagerAdapter._current_stop(
                position
            ),
            "take_profit": AutomaticTradeManagerAdapter._current_take_profit(
                position
            ),
            "market_strength": float(
                market_strength
            ),
            "thesis_invalidated": bool(
                thesis_invalidated
            ),
        }

    # ========================================================
    # APPLY CLOSE
    # ========================================================

    def _apply_close(
        self,
        position,
        current_price: float,
        decision: AutomaticManagementDecision,
    ) -> None:
        """
        Close the persistent PAPER position.

        This changes database state only.

        It does not send a broker close order.
        """

        PositionRepository.close(
            self.db,
            position.position_id,
            exit_price=float(current_price),
            management_action=(
                "AUTOMATIC_TRADE_MANAGER_CLOSE"
            ),
        )

    # ========================================================
    # APPLY STOP LOSS
    # ========================================================

    def _apply_stop_loss(
        self,
        position,
        new_stop_loss: float,
    ) -> None:
        """
        Persist a tighter paper stop-loss.

        The existing repository protects the original stop-loss
        and updates only the current stop-loss.
        """

        old_stop = self._current_stop(
            position
        )

        if old_stop is not None:

            direction = self._direction(
                position
            )

            if direction == "buy":
                if float(new_stop_loss) <= float(old_stop):
                    return

            elif direction == "sell":
                if float(new_stop_loss) >= float(old_stop):
                    return

        PositionRepository.update_stop_loss(
            self.db,
            position.position_id,
            float(new_stop_loss),
            management_action=(
                "AUTOMATIC_TRADE_MANAGER_MODIFY_SL"
            ),
            management_status="protected",
        )

    # ========================================================
    # APPLY TAKE PROFIT
    # ========================================================

    def _apply_take_profit(
        self,
        position,
        new_take_profit: float,
    ) -> None:
        """
        Persist a higher-level paper TP change.

        The repository's generic state API does not expose a
        dedicated TP mutation method, so this adapter performs
        the minimal direct persistent-field update through the
        existing SQLAlchemy position object.

        No broker order is sent.
        """

        direction = self._direction(
            position
        )

        entry_price = float(
            position.entry_price
        )

        candidate = float(
            new_take_profit
        )

        if direction == "buy":
            if candidate <= entry_price:
                raise ValueError(
                    "BUY take-profit must remain above entry price"
                )

        else:
            if candidate >= entry_price:
                raise ValueError(
                    "SELL take-profit must remain below entry price"
                )

        # Keep both Stage 16 fields and legacy compatibility field
        # synchronized.
        position.take_profit_1 = candidate
        position.take_profit = candidate

        position.last_management_action = (
            "AUTOMATIC_TRADE_MANAGER_MODIFY_TP"
        )

        position.management_status = (
            "protected"
        )

        from datetime import datetime

        position.last_management_time = (
            datetime.utcnow()
        )

        self.db.commit()
        self.db.refresh(position)

    # ========================================================
    # APPLY SL + TP
    # ========================================================

    def _apply_stop_and_take_profit(
        self,
        position,
        new_stop_loss: Optional[float],
        new_take_profit: Optional[float],
    ) -> None:
        """
        Apply both paper SL and TP changes.

        The SL must improve the existing stop.
        """

        if new_stop_loss is not None:
            self._apply_stop_loss(
                position,
                float(new_stop_loss),
            )

            position = PositionRepository.get_by_position_id(
                self.db,
                position.position_id,
            )

        if new_take_profit is not None:
            self._apply_take_profit(
                position,
                float(new_take_profit),
            )

    # ========================================================
    # APPLY DECISION
    # ========================================================

    def apply_decision(
        self,
        position,
        decision: AutomaticManagementDecision,
        current_price: float,
    ) -> bool:
        """
        Apply a decision produced by AutomaticTradeManager.

        Returns True when a state-changing action was applied.
        """

        self._assert_paper_only()

        action = decision.action

        if action == AutomaticManagementAction.HOLD:
            return False

        if action == AutomaticManagementAction.CLOSE:

            self._apply_close(
                position,
                current_price,
                decision,
            )

            return True

        if action == AutomaticManagementAction.MODIFY_SL:

            if decision.new_stop_loss is None:
                return False

            self._apply_stop_loss(
                position,
                float(decision.new_stop_loss),
            )

            return True

        if action == AutomaticManagementAction.MODIFY_TP:

            if decision.new_take_profit is None:
                return False

            self._apply_take_profit(
                position,
                float(decision.new_take_profit),
            )

            return True

        if action == AutomaticManagementAction.MODIFY_SL_TP:

            self._apply_stop_and_take_profit(
                position,
                decision.new_stop_loss,
                decision.new_take_profit,
            )

            return True

        raise ValueError(
            f"Unsupported automatic management action: {action}"
        )

    # ========================================================
    # EVALUATE ONE POSITION
    # ========================================================

    def evaluate_position(
        self,
        position,
        current_price: float,
        *,
        market_strength: float = 0.0,
        thesis_invalidated: bool = False,
    ) -> AutomaticManagementResult:
        """
        Evaluate and, when appropriate, apply automatic management
        to one already-open persistent paper position.

        The caller supplies the market/strategy assessment.

        This keeps the 9 brains and existing strategy untouched.
        """

        self._assert_paper_only()

        position_id = str(
            position.position_id
        )

        trade_id = getattr(
            position,
            "trade_id",
            None,
        )

        symbol = str(
            position.symbol
        )

        # Never act on closed positions.
        if position.status != PositionStatus.OPEN:

            return AutomaticManagementResult(
                position_id=position_id,
                trade_id=trade_id,
                symbol=symbol,
                action=(
                    AutomaticManagementAction.HOLD.value
                ),
                applied=False,
                profit_r=None,
                reason=(
                    "Position is not open; "
                    "automatic management skipped."
                ),
            )

        try:

            inputs = self._build_decision_inputs(
                position,
                float(current_price),
                float(market_strength),
                bool(thesis_invalidated),
            )

            decision = self.manager.evaluate(
                **inputs
            )

            applied = self.apply_decision(
                position,
                decision,
                float(current_price),
            )

            return AutomaticManagementResult(
                position_id=position_id,
                trade_id=trade_id,
                symbol=symbol,
                action=decision.action.value,
                applied=applied,
                profit_r=decision.profit_r,
                reason=decision.reason,
            )

        except Exception as exc:

            return AutomaticManagementResult(
                position_id=position_id,
                trade_id=trade_id,
                symbol=symbol,
                action=(
                    AutomaticManagementAction.HOLD.value
                ),
                applied=False,
                profit_r=None,
                reason=(
                    "Automatic management evaluation "
                    "was safely skipped because the "
                    "position state was incompatible."
                ),
                error=str(exc),
            )

    # ========================================================
    # EVALUATE SYMBOL
    # ========================================================

    def evaluate_symbol(
        self,
        symbol: str,
        current_price: float,
        *,
        market_strength: float = 0.0,
        thesis_invalidated: bool = False,
    ) -> list[AutomaticManagementResult]:
        """
        Evaluate all open persistent paper positions for a symbol.

        No new positions are created.
        """

        self._assert_paper_only()

        normalized_symbol = (
            str(symbol)
            .strip()
            .upper()
        )

        if not normalized_symbol:
            raise ValueError(
                "symbol is required"
            )

        price = float(
            current_price
        )

        if price <= 0:
            raise ValueError(
                "current_price must be greater than zero"
            )

        positions = (
            PositionRepository.get_open_positions(
                self.db
            )
        )

        results: list[
            AutomaticManagementResult
        ] = []

        for position in positions:

            if (
                str(position.symbol)
                .strip()
                .upper()
                != normalized_symbol
            ):
                continue

            results.append(
                self.evaluate_position(
                    position,
                    price,
                    market_strength=(
                        market_strength
                    ),
                    thesis_invalidated=(
                        thesis_invalidated
                    ),
                )
            )

        return results

    # ========================================================
    # READ-ONLY STATUS
    # ========================================================

    @staticmethod
    def status() -> dict[str, Any]:
        """
        Return the safety declaration for this adapter.
        """

        return {
            "component": (
                "automatic_trade_manager_adapter"
            ),
            "stage": "17.5A",
            "status": "available",
            "capabilities": [
                "HOLD",
                "CLOSE",
                "MODIFY_SL",
                "MODIFY_TP",
                "MODIFY_SL_TP",
            ],
            "safety": {
                "paper_only": True,
                "read_only_decision_layer": True,
                "live_trading_enabled": False,
                "execution_authorized": False,
                "broker_orders_allowed": False,
                "mt5_execution_allowed": False,
                "risk_engine_bypass": False,
                "creates_new_positions": False,
            },
        }


__all__ = [
    "AutomaticManagementResult",
    "AutomaticTradeManagerAdapter",
]
