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
    Existing indicator + AI decision pipeline
            ↓
    AutomaticTradeManagerAdapter
            ↓
    AutomaticTradeManager
            ↓
    HOLD / CLOSE / MODIFY_SL / MODIFY_TP / MODIFY_SL_TP
            ↓
    Persist SL/TP modifications

IMPORTANT:

CLOSE decisions are reported but are NOT executed by this
service yet. Existing lifecycle closure remains authoritative.
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
        AutomaticTradeManagerAdapter,
    )
    from automatic_trade_management_persistence import (
        AutomaticTradeManagementPersistence,
    )


@dataclass(frozen=True)
class AutomaticTradeManagementServiceConfig:
    """
    Configuration for Stage 17.5 automatic management.
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
    Result for one automatic management evaluation.
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

    This service manages EXISTING persistent paper positions.

    It does not create trades or place broker orders.
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
        Return all currently open persistent paper positions.
        """

        return (
            self.db.query(Position)
            .filter(
                Position.status == PositionStatus.OPEN,
            )
            .all()
        )

    # ============================================================
    # CURRENT MARKET PRICE
    # ============================================================

    @staticmethod
    def _current_price(
        market_data: dict[str, Any],
    ) -> float:
        """
        Extract and validate the latest public-feed price.
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
    # FRESH MARKET ANALYSIS
    # ============================================================

    async def _fresh_analysis(
        self,
    ) -> tuple[float, Any]:
        """
        Fetch fresh public XAUUSD candles and run the EXISTING
        RAYMOND indicator + AI decision pipeline.

        Decision-only.

        No Risk Engine execution occurs here.
        No paper order occurs here.
        No broker order occurs here.
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
    # POSITION IDENTIFIERS
    # ============================================================

    @staticmethod
    def _position_id(
        position: Position,
    ) -> str:
        """
        Safely obtain the persistent position ID.
        """

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
        """
        Safely obtain the associated paper trade ID.
        """

        value = getattr(
            position,
            "trade_id",
            None,
        )

        if value is None:
            return None

        return str(value)

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
        Evaluate one existing open paper position.

        If market price and decision are not supplied, this
        method obtains fresh public market analysis.

        IMPORTANT:

        The AutomaticTradeManagerAdapter is called with the
        actual Position object.

        The adapter then builds AutomaticManagementInput itself.

        This is required because the adapter's thesis validation
        function requires BOTH the decision and the position.
        """

        position_id = self._position_id(
            position
        )

        trade_id = self._trade_id(
            position
        )

        try:

            # ----------------------------------------------------
            # FRESH ANALYSIS
            # ----------------------------------------------------

            if (
                current_price is None
                or decision is None
            ):
                (
                    current_price,
                    decision,
                ) = await self._fresh_analysis()

            # ----------------------------------------------------
            # CRITICAL ADAPTER INTEGRATION
            # ----------------------------------------------------
            #
            # DO NOT pass AutomaticManagementInput here.
            #
            # The current adapter expects:
            #
            #   position=
            #   decision=
            #   current_price=
            #
            # The adapter itself then:
            #
            #   1. reads the persistent position
            #   2. calculates market strength
            #   3. checks thesis invalidation
            #   4. builds AutomaticManagementInput
            #   5. calls AutomaticTradeManager
            #
            # This preserves the existing management architecture.
            # ----------------------------------------------------

            management_decision = (
                self.adapter.evaluate(
                    position=position,
                    decision=decision,
                    current_price=current_price,
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

            profit_r = float(
                management_decision.profit_r
            )

            reason = (
                management_decision.reason
            )

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
                    profit_r=profit_r,
                    reason=reason,
                    persisted=False,
                )

            # ----------------------------------------------------
            # STOP LOSS / TAKE PROFIT MODIFICATION
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
                    profit_r=profit_r,
                    reason=reason,
                    persisted=persisted,
                )

            # ----------------------------------------------------
            # CLOSE
            # ----------------------------------------------------
            #
            # The automatic manager can generate a CLOSE decision.
            #
            # Stage 17.5 deliberately does NOT execute CLOSE.
            #
            # Existing lifecycle SL/TP closure remains authoritative.
            # ----------------------------------------------------

            if self.adapter.is_close(
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
                    profit_r=profit_r,
                    reason=(
                        "CLOSE decision generated by "
                        "automatic trade manager; "
                        "existing lifecycle closure remains "
                        "authoritative."
                    ),
                    persisted=False,
                )

            # ----------------------------------------------------
            # FALLBACK
            # ----------------------------------------------------

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
                profit_r=profit_r,
                reason=reason,
                persisted=False,
            )

        except Exception as exc:

            # Never leave a failed management transaction open.
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
        Evaluate every open persistent paper position.

        One fresh market analysis is performed for the cycle and
        applied independently to each open position.

        No new positions are created.
        """

        if not self.config.enabled:
            return []

        positions = self.get_open_positions()

        if not positions:
            return []

        # --------------------------------------------------------
        # ONE MARKET ANALYSIS FOR THE WHOLE MANAGEMENT CYCLE
        # --------------------------------------------------------

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

        # --------------------------------------------------------
        # APPLY THE DECISION TO EVERY OPEN POSITION
        # --------------------------------------------------------

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
    # DICTIONARY API
    # ============================================================

    async def evaluate_open_positions_dict(
        self,
    ) -> list[dict[str, Any]]:
        """
        Convenience API for workers and API integrations.
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
