"""

RAYMOND v2.8 - Application Trading Pipeline Service

Step 15:

Connects the existing application components in one controlled path:

    MT5 candles

        ->

    Technical Indicators

        ->

    Market Pressure

        ->

    TechnicalContext

        ->

    Step 13 AI

        ->

    Step 14 Risk

        ->

    Paper Execution Gateway

This service does NOT:

- connect to MT5 directly

- place live broker orders

- bypass the Risk Engine

- bypass Step 14

- modify positions

- enable live trading

Market pressure is an ADVISORY confluence layer.

It does not replace the established Raymond strategy.

"""

from __future__ import annotations

from dataclasses import dataclass

from typing import Any, Mapping, Optional, Sequence

from app.ai_trading_decision import (

    AIDecision,

    AITradingDecisionEngine,

    TechnicalContext,

)

from app.execution_gateway import (

    PaperExecutionGateway,

)

from app.market_pressure import (

    MarketPressureError,

    MarketPressureResult,

    calculate_market_pressure,

)

from app.risk_engine import (

    RiskDecision,

    RiskEngine,

    SymbolSpecification,

)

from app.step14_pipeline import (

    Step14Pipeline,

    Step14Result,

)

from app.technical_indicators import (

    IndicatorResult,

    TechnicalIndicatorError,

    calculate_indicators,

)

class TradingPipelineServiceError(RuntimeError):

    """Raised when the application trading pipeline fails safely."""

@dataclass(frozen=True)

class PaperRiskState:

    """Current paper-trading state supplied to Step 14."""

    daily_loss: float

    open_positions: int

    total_exposure: float

class TradingPipelineService:

    """

    Application-level composition of the existing trading layers.

    The service deliberately contains orchestration only.

    Business rules remain inside:

    - Step 13 AI

    - Step 14

    - Risk Engine

    - Paper Execution Gateway

    Market pressure is calculated here and passed into the

    TechnicalContext as additional advisory information.

    """

    def __init__(

        self,

        *,

        ai_engine: Optional[

            AITradingDecisionEngine

        ] = None,

        risk_engine: Optional[

            RiskEngine

        ] = None,

        execution_gateway: Optional[

            PaperExecutionGateway

        ] = None,

    ) -> None:

        self.ai_engine = (

            ai_engine

            or AITradingDecisionEngine()

        )

        self.risk_engine = (

            risk_engine

            or RiskEngine()

        )

        self.execution_gateway = (

            execution_gateway

            or PaperExecutionGateway(

                live_trading_enabled=False,

            )

        )

        self.step14 = Step14Pipeline(

            ai_engine=self.ai_engine,

            risk_engine=self.risk_engine,

            execution_gateway=self.execution_gateway,

        )

    # ========================================================

    # TECHNICAL CONTEXT

    # ========================================================

    @staticmethod

    def indicator_to_context(

        result: IndicatorResult,

        *,

        market_pressure: Optional[

            MarketPressureResult

        ] = None,

    ) -> TechnicalContext:

        """

        Convert IndicatorResult into Step 13 TechnicalContext.

        Market pressure is optional so existing callers and tests

        remain compatible.

        Pressure is advisory only.

        """

        return TechnicalContext(

            symbol=result.symbol,

            timeframe=result.timeframe,

            close=result.close,

            ema20=result.ema20,

            ema50=result.ema50,

            rsi14=result.rsi14,

            atr14=result.atr14,

            macd=result.macd,

            macd_signal=result.macd_signal,

            macd_histogram=result.macd_histogram,

            trend=result.trend,

            score=result.score,

            signal=result.signal,

            candles_used=result.candles_used,

            market_pressure_score=(

                market_pressure.score

                if market_pressure is not None

                else None

            ),

            market_pressure_label=(

                market_pressure.label

                if market_pressure is not None

                else "UNAVAILABLE"

            ),

            market_pressure_available=(

                market_pressure.available

                if market_pressure is not None

                else False

            ),

        )

    def build_context(

        self,

        *,

        symbol: str,

        timeframe: str,

        candles: Sequence[

            Mapping[str, Any]

        ],

    ) -> TechnicalContext:

        """

        Calculate:

            OHLC candles

                ->

            Technical indicators

                ->

            Market pressure

                ->

            TechnicalContext

        If market-pressure data is unavailable or invalid,

        Raymond keeps the established technical strategy alive

        instead of failing the complete decision pipeline.

        """

        if not symbol.strip():

            raise TradingPipelineServiceError(

                "Symbol is required."

            )

        if not timeframe.strip():

            raise TradingPipelineServiceError(

                "Timeframe is required."

            )

        if not candles:

            raise TradingPipelineServiceError(

                "At least one candle is required."

            )

        # ----------------------------------------------------

        # Existing technical-indicator engine

        # ----------------------------------------------------

        try:

            result = calculate_indicators(

                symbol=symbol,

                timeframe=timeframe,

                candles=candles,

            )

        except (

            TechnicalIndicatorError,

            ValueError,

        ) as exc:

            raise TradingPipelineServiceError(

                f"Technical indicator calculation failed: {exc}"

            ) from exc

        # ----------------------------------------------------

        # Market-pressure engine

        #

        # This is deliberately advisory.

        # A failure here must not destroy the existing

        # technical strategy.

        # ----------------------------------------------------

        market_pressure: Optional[

            MarketPressureResult

        ] = None

        try:

            market_pressure = (

                calculate_market_pressure(

                    candles,

                )

            )

        except (

            MarketPressureError,

            ValueError,

        ):

            market_pressure = None

        return self.indicator_to_context(

            result,

            market_pressure=market_pressure,

        )

    # ========================================================

    # DECISION ONLY

    # ========================================================

    def evaluate_decision(

        self,

        *,

        symbol: str,

        timeframe: str,

        candles: Sequence[

            Mapping[str, Any]

        ],

    ) -> AIDecision:

        """

        Run:

            candles

                ->

            indicators

                ->

            market pressure

                ->

            TechnicalContext

                ->

            Step 13 AI

        No Risk Engine execution and no order execution

        occur here.

        """

        context = self.build_context(

            symbol=symbol,

            timeframe=timeframe,

            candles=candles,

        )

        try:

            return self.ai_engine.evaluate(

                context

            )

        except Exception as exc:

            raise TradingPipelineServiceError(

                f"AI decision failed safely: {exc}"

            ) from exc

    # ========================================================

    # STEP 14 EVALUATION

    # ========================================================

    def evaluate_risk(

        self,

        *,

        symbol: str,

        timeframe: str,

        candles: Sequence[

            Mapping[str, Any]

        ],

        specification: SymbolSpecification,

        account_equity: float,

        risk_state: PaperRiskState,

    ) -> Step14Result:

        """

        Run:

            candles

                ->

            indicators

                ->

            market pressure

                ->

            Step 13

                ->

            Step 14 Risk

        No execution occurs here.

        """

        context = self.build_context(

            symbol=symbol,

            timeframe=timeframe,

            candles=candles,

        )

        return self.step14.evaluate(

            context,

            specification,

            account_equity=account_equity,

            daily_loss=risk_state.daily_loss,

            open_positions=risk_state.open_positions,

            total_exposure=risk_state.total_exposure,

        )

    # ========================================================

    # FULL PAPER PIPELINE

    # ========================================================

    async def execute_paper(

        self,

        *,

        symbol: str,

        timeframe: str,

        candles: Sequence[

            Mapping[str, Any]

        ],

        specification: SymbolSpecification,

        account_equity: float,

        risk_state: PaperRiskState,

    ) -> Step14Result:

        """

        Run the complete application paper pipeline:

            MT5 candles

                ->

            Technical indicators

                ->

            Market pressure

                ->

            TechnicalContext

                ->

            Step 13 AI

                ->

            Step 14 Risk

                ->

            PaperExecutionGateway

        Live execution is never permitted.

        """

        context = self.build_context(

            symbol=symbol,

            timeframe=timeframe,

            candles=candles,

        )

        try:

            return await self.step14.evaluate_and_execute_paper(

                context,

                specification,

                account_equity=account_equity,

                daily_loss=risk_state.daily_loss,

                open_positions=risk_state.open_positions,

                total_exposure=risk_state.total_exposure,

            )

        except Exception as exc:

            if isinstance(

                exc,

                TradingPipelineServiceError,

            ):

                raise

            raise TradingPipelineServiceError(

                f"Paper trading pipeline failed safely: {exc}"

            ) from exc

    # ========================================================

    # SERIALIZATION HELPERS

    # ========================================================

    @staticmethod

    def serialize_decision(

        decision: AIDecision,

    ) -> dict:

        """

        Convert an AIDecision into a stable API response.

        Market-pressure fields are included when supported by

        the Step 13 AIDecision model.

        """

        proposal = decision.proposal

        payload = {

            "direction": decision.direction.value,

            "symbol": decision.symbol,

            "timeframe": decision.timeframe,

            "confidence": decision.confidence,

            "technical_score": decision.technical_score,

            "trend": decision.trend,

            "signal": decision.signal,

            "reasoning": decision.reasoning,

            "execution_type": decision.execution_type,

            "read_only": decision.read_only,

            "broker_order_required": (

                decision.broker_order_required

            ),

            "risk_engine_required": (

                decision.risk_engine_required

            ),

            "proposal": (

                {

                    "direction": proposal.direction.value,

                    "symbol": proposal.symbol,

                    "entry_price": proposal.entry_price,

                    "stop_loss": proposal.stop_loss,

                    "take_profit": proposal.take_profit,

                    "risk_reward": proposal.risk_reward,

                    "confidence": proposal.confidence,

                    "reason": proposal.reason,

                    "execution_type": proposal.execution_type,

                    "read_only": proposal.read_only,

                    "broker_order_required": (

                        proposal.broker_order_required

                    ),

                    "risk_engine_required": (

                        proposal.risk_engine_required

                    ),

                }

                if proposal is not None

                else None

            ),

        }

        # ----------------------------------------------------

        # Add pressure fields if the AIDecision model exposes

        # them. This keeps serialization backwards-compatible

        # while the AI model is being upgraded.

        # ----------------------------------------------------

        if hasattr(

            decision,

            "market_pressure_score",

        ):

            payload[

                "market_pressure_score"

            ] = decision.market_pressure_score

        if hasattr(

            decision,

            "market_pressure_label",

        ):

            payload[

                "market_pressure_label"

            ] = decision.market_pressure_label

        if hasattr(

            decision,

            "market_pressure_available",

        ):

            payload[

                "market_pressure_available"

            ] = decision.market_pressure_available

        return payload

    @staticmethod

    def serialize_risk_decision(

        risk_decision: Optional[

            RiskDecision

        ],

    ) -> Optional[dict]:

        if risk_decision is None:

            return None

        return {

            "allowed": risk_decision.allowed,

            "reason": risk_decision.reason,

            "risk_amount": risk_decision.risk_amount,

            "daily_loss_limit": (

                risk_decision.daily_loss_limit

            ),

            "total_exposure_limit": (

                risk_decision.total_exposure_limit

            ),

            "proposed_exposure": (

                risk_decision.proposed_exposure

            ),

            "open_positions": (

                risk_decision.open_positions

            ),

        }

    @staticmethod

    def serialize_execution(

        execution_result: Any,

    ) -> Optional[dict]:

        if execution_result is None:

            return None

        return {

            "order_id": execution_result.order_id,

            "client_order_id": (

                execution_result.client_order_id

            ),

            "status": execution_result.status.value,

            "execution_type": (

                execution_result.execution_type

            ),

            "broker": execution_result.broker,

            "symbol": execution_result.symbol,

            "side": execution_result.side,

            "order_type": execution_result.order_type,

            "volume": execution_result.volume,

            "price": execution_result.price,

            "stop_loss": execution_result.stop_loss,

            "take_profit": execution_result.take_profit,

            "timestamp": execution_result.timestamp,

            "message": execution_result.message,

        }

    @classmethod

    def serialize_step14_result(

        cls,

        result: Step14Result,

    ) -> dict:

        """

        Convert the complete Step 14 result into

        an API-safe response.

        """

        return {

            "decision": cls.serialize_decision(

                result.decision

            ),

            "risk": cls.serialize_risk_decision(

                result.risk_decision

            ),

            "position_size": result.position_size,

            "execution": cls.serialize_execution(

                result.execution_result

            ),

        }

__all__ = [

    "TradingPipelineService",

    "TradingPipelineServiceError",

    "PaperRiskState",

]
