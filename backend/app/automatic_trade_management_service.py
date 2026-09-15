"""
RAYMOND v2.8 - Automatic Trade Management Service

Stage 17.5

ADDITIVE ONLY.

This service manages ALREADY OPEN paper positions.

It does NOT:
- create new positions
- run the entry pipeline
- bypass the Risk Engine
- modify the 9 brains
- modify indicators
- modify AI scoring
- modify paper execution
- contact MT5
- contact a live broker
- enable live trading
- replace Stage 12 management
- replace lifecycle SL/TP closure

Flow:

    Open paper position
            ↓
    Fresh public XAUUSD candles
            ↓
    Existing indicator engine
            ↓
    Existing AI decision engine
            ↓
    AutomaticTradeManager
            ↓
    HOLD / CLOSE / MODIFY_SL / MODIFY_TP / MODIFY_SL_TP
            ↓
    Persist SL/TP modifications

IMPORTANT:

CLOSE decisions are reported but are NOT executed by this
service yet. Existing lifecycle closure remains authoritative
until the dedicated CLOSE integration stage is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

try:
    from .models import Position, PositionStatus
    from .online_market_api import _fetch_chart
    from .trading_pipeline_service import TradingPipelineService
    from .automatic_trade_manager_adapter import (
        AutomaticManagementInput,
        AutomaticTradeManagerAdapter,
    )
    from .automatic_trade_management_persistence import (
        AutomaticTradeManagementPersistence,
    )
except ImportError:
    from models import Position, PositionStatus
    from online_market_api import _fetch_chart
    from trading_pipeline_service import TradingPipelineService
    from automatic_trade_manager_adapter import (
        AutomaticManagementInput,
        AutomaticTradeManagerAdapter,
    )
    from automatic_trade_management_persistence import (
        AutomaticTradeManagementPersistence,
    )


@dataclass(frozen=True)
class AutomaticTradeManagementServiceConfig:
    """
    Configuration for the automatic management service.
    """

    symbol: str = "XAUUSD"

    timeframe: str = "M15"

    candle_limit: int = 100

    enabled: bool = True

    def validate(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol must not be empty"
            )

        if not self.timeframe.strip():
            raise ValueError(
                "timeframe must not be empty"
            )

        if self.candle_limit < 60:
            raise ValueError(
                "candle_limit must be at least 60"
            )


@dataclass(frozen=True)
class AutomaticTradeManagementResult:
    """
    Result for one management evaluation.
    """

    position_id: str

    trade_id: Optional[str]

    symbol: str

    action: str

    current_price: float

    new_stop_loss: Optional[float]

    new_take_profit: Optional[float]

    profit_r: float

    reason: str

    persisted: bool

    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "action": self.action,
            "current_price": self.current_price,
            "new_stop_loss": self.new_stop_loss,
            "new_take_profit": self.new_take_profit,
            "profit_r": self.profit_r,
            "reason": self.reason,
            "persisted": self.persisted,
            "error": self.error,
        }


class AutomaticTradeManagementService:
    """
    Orchestrates Stage 17.5 automatic management.

    This class is intentionally separate from the existing
    30-second paper-position lifecycle loop.

    It can therefore be connected to the online worker without
    rewriting the existing lifecycle or advanced management code.
    """

    def __init__(
        self,
        db: Session,
        *,
        config: Optional[
            AutomaticTradeManagementServiceConfig
        ] = None,
        pipeline: Optional[
            TradingPipelineService
        ] = None,
        adapter: Optional[
            AutomaticTradeManagerAdapter
        ] = None,
    ) -> None:

        self.db = db

        self.config = (
            config
            if config is not None
            else AutomaticTradeManagementServiceConfig()
        )

        self.config.validate()

        self.pipeline = (
            pipeline
            if pipeline is not None
            else TradingPipelineService()
        )

        self.adapter = (
            adapter
            if adapter is not None
            else AutomaticTradeManagerAdapter()
        )

    # ============================================================
    # POSITION DISCOVERY
    # ============================================================

    def get_open_positions(self) -> list[Position]:
        """
        Return all currently open persistent positions.

        Only open positions are eligible for automatic management.
        """

        return (
            self.db.query(Position)
            .filter(
                Position.status == PositionStatus.OPEN,
            )
            .all()
        )

    # ============================================================
    # CURRENT PRICE
    # ============================================================

    @staticmethod
    def _current_price(
        market_data: dict[str, Any],
    ) -> float:
        """
        Extract the latest public-feed price.
        """

        price = market_data.get("price")

        if price is None:
            raise RuntimeError(
                "Online market feed returned no usable price"
            )

        value = float(price)

        if value <= 0:
            raise RuntimeError(
                "Online market feed returned an invalid price"
            )

        return value

    # ============================================================
    # MARKET ANALYSIS
    # ============================================================

    async def _fresh_analysis(
        self,
    ) -> tuple[float, Any]:
        """
        Fetch fresh public candles and run the EXISTING
        indicator + AI decision pipeline.

        This is decision-only.

        No Risk Engine execution occurs.
        No paper order occurs.
        No broker order occurs.
        """

        chart = await _fetch_chart(
            self.config.symbol,
            self.config.timeframe,
            self.config.candle_limit,
        )

        candles = chart.get("candles") or []

        if len(candles) < 60:
            raise RuntimeError(
                "Insufficient candles for automatic management"
            )

        current_price = self._current_price(
            chart
        )

        decision = self.pipeline.evaluate_decision(
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            candles=candles,
        )

        return current_price, decision

    # ============================================================
    # POSITION → MANAGEMENT INPUT
    # ============================================================

    @staticmethod
    def _direction(
        position: Position,
    ) -> str:
        """
        Normalize the SQLAlchemy TradeDirection enum.
        """

        value = getattr(
            position.direction,
            "value",
            position.direction,
        )

        return str(value).lower()

    @staticmethod
    def _position_id(
        position: Position,
    ) -> str:
        value = getattr(
            position,
            "position_id",
            None,
        )

        if value is None:
            raise RuntimeError(
                "Open position has no position_id"
            )

        return str(value)

    @staticmethod
    def _trade_id(
        position: Position,
    ) -> Optional[str]:
        value = getattr(
            position,
            "trade_id",
            None,
        )

        if value is None:
            return None

        return str(value)

    @staticmethod
    def _float_or_none(
        value: Any,
    ) -> Optional[float]:
        if value is None:
            return None

        return float(value)

    def _build_management_input(
        self,
        *,
        position: Position,
        current_price: float,
        decision: Any,
    ) -> AutomaticManagementInput:
        """
        Build the Stage 17.5 adapter input from the persistent
        position plus the fresh existing AI decision.
        """

        return AutomaticManagementInput(
            trade_id=(
                self._trade_id(position)
                or self._position_id(position)
            ),
            direction=self._direction(position),
            entry_price=float(
                position.entry_price
            ),
            current_price=float(
                current_price
            ),
            stop_loss=(
                self._float_or_none(
                    getattr(
                        position,
                        "current_stop_loss",
                        None,
                    )
                )
                or self._float_or_none(
                    getattr(
                        position,
                        "stop_loss",
                        None,
                    )
                )
            ),
            take_profit=(
                self._float_or_none(
                    getattr(
                        position,
                        "take_profit_1",
                        None,
                    )
                )
                or self._float_or_none(
                    getattr(
                        position,
                        "take_profit",
                        None,
                    )
                )
            ),
            initial_stop_loss=(
                self._float_or_none(
                    getattr(
                        position,
                        "initial_stop_loss",
                        None,
                    )
                )
            ),
            risk_1r=(
                self._float_or_none(
                    getattr(
                        position,
                        "risk_1r",
                        None,
                    )
                )
            ),
            market_strength=(
                self.adapter.market_strength_from_decision(
                    decision
                )
            ),
            thesis_invalidated=(
                self.adapter.thesis_invalidated_from_decision(
                    decision
                )
            ),
        )

    # ============================================================
    # ONE POSITION
    # ============================================================

    async def evaluate_position(
        self,
        position: Position,
        *,
        current_price: Optional[float] = None,
        decision: Any = None,
    ) -> AutomaticTradeManagementResult:
        """
        Evaluate one open position.

        If current_price and decision are not supplied, fresh
        public market analysis is performed.
        """

        position_id = self._position_id(
            position
        )

        trade_id = self._trade_id(
            position
        )

        try:
            if current_price is None or decision is None:
                (
                    current_price,
                    decision,
                ) = await self._fresh_analysis()

            management_input = (
                self._build_management_input(
                    position=position,
                    current_price=current_price,
                    decision=decision,
                )
            )

            management_decision = (
                self.adapter.evaluate(
                    management_input
                )
            )

            action = str(
                management_decision.action.value
            ).lower()

            new_stop_loss = (
                management_decision.new_stop_loss
            )

            new_take_profit = (
                management_decision.new_take_profit
            )

            persisted = False

            # ----------------------------------------------------
            # HOLD
            # ----------------------------------------------------

            if self.adapter.is_actionable(
                management_decision
            ) is False:
                return AutomaticTradeManagementResult(
                    position_id=position_id,
                    trade_id=trade_id,
                    symbol=self.config.symbol,
                    action=action,
                    current_price=float(
                        current_price
                    ),
                    new_stop_loss=new_stop_loss,
                    new_take_profit=new_take_profit,
                    profit_r=float(
                        management_decision.profit_r
                    ),
                    reason=management_decision.reason,
                    persisted=False,
                )

            # ----------------------------------------------------
            # SL / TP MODIFICATIONS
            # ----------------------------------------------------

            if (
                self.adapter.is_stop_modification(
                    management_decision
                )
                or self.adapter.is_take_profit_modification(
                    management_decision
                )
            ):
                updated = (
                    AutomaticTradeManagementPersistence
                    .persist_decision(
                        self.db,
                        position_id=position_id,
                        action=action,
                        new_stop_loss=new_stop_loss,
                        new_take_profit=new_take_profit,
                    )
                )

                persisted = (
                    updated is not None
                )

            # ----------------------------------------------------
            # CLOSE
            # ----------------------------------------------------
            #
            # CLOSE is deliberately NOT executed here yet.
            #
            # The existing lifecycle/persistence closure path
            # remains authoritative until the dedicated CLOSE
            # integration stage is added.
            # ----------------------------------------------------

            elif self.adapter.is_close(
                management_decision
            ):
                return AutomaticTradeManagementResult(
                    position_id=position_id,
                    trade_id=trade_id,
                    symbol=self.config.symbol,
                    action="close",
                    current_price=float(
                        current_price
                    ),
                    new_stop_loss=None,
                    new_take_profit=None,
                    profit_r=float(
                        management_decision.profit_r
                    ),
                    reason=(
                        "CLOSE decision generated by "
                        "automatic trade manager; "
                        "existing lifecycle closure remains "
                        "authoritative."
                    ),
                    persisted=False,
                )

            return AutomaticTradeManagementResult(
                position_id=position_id,
                trade_id=trade_id,
                symbol=self.config.symbol,
                action=action,
                current_price=float(
                    current_price
                ),
                new_stop_loss=new_stop_loss,
                new_take_profit=new_take_profit,
                profit_r=float(
                    management_decision.profit_r
                ),
                reason=management_decision.reason,
                persisted=persisted,
            )

        except Exception as exc:
            self.db.rollback()

            return AutomaticTradeManagementResult(
                position_id=position_id,
                trade_id=trade_id,
                symbol=self.config.symbol,
                action="error",
                current_price=float(
                    current_price
                    if current_price is not None
                    else 0.0
                ),
                new_stop_loss=None,
                new_take_profit=None,
                profit_r=0.0,
                reason=(
                    "Automatic management evaluation "
                    "failed safely."
                ),
                persisted=False,
                error=str(exc),
            )

    # ============================================================
    # ALL OPEN POSITIONS
    # ============================================================

    async def evaluate_open_positions(
        self,
    ) -> list[AutomaticTradeManagementResult]:
        """
        Evaluate every open paper position.

        One fresh market analysis is performed for the cycle,
        then that analysis is applied to each open position.

        This avoids making a separate public-feed request for
        every position.
        """

        if not self.config.enabled:
            return []

        positions = self.get_open_positions()

        if not positions:
            return []

        try:
            (
                current_price,
                decision,
            ) = await self._fresh_analysis()

        except Exception as exc:
            return [
                AutomaticTradeManagementResult(
                    position_id=self._position_id(
                        position
                    ),
                    trade_id=self._trade_id(
                        position
                    ),
                    symbol=self.config.symbol,
                    action="error",
                    current_price=0.0,
                    new_stop_loss=None,
                    new_take_profit=None,
                    profit_r=0.0,
                    reason=(
                        "Fresh market analysis failed; "
                        "position was not modified."
                    ),
                    persisted=False,
                    error=str(exc),
                )
                for position in positions
            ]

        results: list[
            AutomaticTradeManagementResult
        ] = []

        for position in positions:
            result = await self.evaluate_position(
                position,
                current_price=current_price,
                decision=decision,
            )

            results.append(result)

        return results

    # ============================================================
    # SERIALIZATION
    # ============================================================

    async def evaluate_open_positions_dict(
        self,
    ) -> list[dict[str, Any]]:
        """
        Convenience API for worker/API integration.
        """

        results = (
            await self.evaluate_open_positions()
        )

        return [
            result.to_dict()
            for result in results
        ]


__all__ = [
    "AutomaticTradeManagementService",
    "AutomaticTradeManagementServiceConfig",
    "AutomaticTradeManagementResult",
]
