"""
RAYMOND v2.8 - Step 14 AI -> Risk -> Paper Execution Pipeline

This module makes the Step 13 deterministic AI decision engine an explicit
part of the safety pipeline. It does not contact MT5/Exness and cannot place
live broker orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .ai_trading_decision import (
    AIDirection,
    AITradingDecisionEngine,
    TechnicalContext,
)
from .execution_gateway import (
    ExecutionGateway,
    ExecutionGatewayError,
    ExecutionResult,
    OrderRequest,
    OrderSide,
    OrderType,
)
from .risk_engine import (
    RiskDecision,
    RiskEngine,
    RiskEngineError,
    SymbolSpecification,
)


class Step14PipelineError(RuntimeError):
    """Raised when the Step 14 safety pipeline cannot continue."""


@dataclass(frozen=True)
class Step14Result:
    """Complete result of AI decision, risk validation and optional execution."""

    allowed: bool
    action: str
    reason: str
    confidence: float
    volume: float
    decision_reasoning: str
    risk_decision: Optional[RiskDecision]
    execution_result: Optional[ExecutionResult] = None


class Step14Pipeline:
    """
    Safety-first pipeline:

        TechnicalContext
            -> Step 13 AI decision
            -> Risk Engine
            -> Paper Execution Gateway

    The AI layer can recommend a trade, but it cannot bypass risk controls.
    The execution gateway supplied to this class must remain paper-only.
    """

    def __init__(
        self,
        *,
        decision_engine: Optional[AITradingDecisionEngine] = None,
        risk_engine: Optional[RiskEngine] = None,
        execution_gateway: Optional[ExecutionGateway] = None,
    ) -> None:
        self.decision_engine = decision_engine or AITradingDecisionEngine()
        self.risk_engine = risk_engine or RiskEngine()
        self.execution_gateway = execution_gateway

    @staticmethod
    def _context_from_mapping(market: Dict[str, Any]) -> TechnicalContext:
        """Convert the API/strategy mapping into the Step 13 context contract."""
        indicators = market.get("indicators") or {}

        price = float(
            market.get("current_price")
            or market.get("close")
            or 0.0
        )

        signal = str(
            market.get("signal")
            or indicators.get("signal")
            or "WAIT"
        ).upper()

        trend = str(
            market.get("trend")
            or indicators.get("trend")
            or "Neutral"
        )

        score = int(
            market.get("score")
            if market.get("score") is not None
            else indicators.get("score", 50)
        )

        return TechnicalContext(
            symbol=str(market.get("symbol") or "XAUUSD"),
            timeframe=str(market.get("timeframe") or "M15"),
            close=price,
            ema20=indicators.get("ema20"),
            ema50=indicators.get("ema50"),
            rsi14=indicators.get(
                "rsi14",
                indicators.get("rsi"),
            ),
            atr14=indicators.get(
                "atr14",
                indicators.get("atr"),
            ),
            macd=indicators.get("macd"),
            macd_signal=indicators.get("macd_signal"),
            macd_histogram=indicators.get("macd_histogram"),
            trend=trend,
            score=score,
            signal=signal,
            candles_used=int(
                market.get("candles_used")
                or indicators.get("candles_used")
                or 1
            ),
        )

    def evaluate(
        self,
        *,
        context: TechnicalContext,
        equity: float,
        daily_loss: float,
        open_positions: int,
        current_exposure: float,
        specification: SymbolSpecification,
        existing_direction_volume: float = 0.0,
    ) -> Step14Result:
        """Run AI decision + fail-closed risk validation without execution."""

        try:
            decision = self.decision_engine.evaluate(context)
        except Exception as exc:
            raise Step14PipelineError(
                f"AI decision evaluation failed: {exc}"
            ) from exc

        if decision.direction is AIDirection.WAIT:
            return Step14Result(
                allowed=False,
                action="WAIT",
                reason=decision.reasoning,
                confidence=decision.confidence,
                volume=0.0,
                decision_reasoning=decision.reasoning,
                risk_decision=None,
            )

        proposal = decision.proposal

        if proposal is None:
            raise Step14PipelineError(
                "AI returned BUY/SELL without a trade proposal."
            )

        side = (
            "BUY"
            if decision.direction is AIDirection.BUY
            else "SELL"
        )

        if proposal.stop_loss is None or proposal.take_profit is None:
            raise Step14PipelineError(
                "Trade proposal is missing stop-loss or take-profit."
            )

        try:
            volume = self.risk_engine.calculate_position_size_from_symbol(
                equity=equity,
                entry_price=proposal.entry_price,
                stop_loss_price=proposal.stop_loss,
                specification=specification,
            )

            if volume <= 0:
                raise Step14PipelineError(
                    "Risk engine calculated a zero-sized position."
                )

            proposed_exposure = (
                volume
                * proposal.entry_price
                * specification.contract_size
            )

            risk_decision = self.risk_engine.pre_trade_check(
                equity=equity,
                daily_loss=daily_loss,
                open_positions=open_positions,
                current_exposure=current_exposure,
                proposed_exposure=proposed_exposure,
                entry_price=proposal.entry_price,
                stop_loss_price=proposal.stop_loss,
                take_profit_price=proposal.take_profit,
                volume=volume,
                side=side,
                specification=specification,
                existing_direction_volume=existing_direction_volume,
            )

        except (RiskEngineError, ValueError) as exc:
            raise Step14PipelineError(
                f"Risk validation failed closed: {exc}"
            ) from exc

        return Step14Result(
            allowed=risk_decision.allowed,
            action=side,
            reason=risk_decision.reason,
            confidence=decision.confidence,
            volume=volume,
            decision_reasoning=decision.reasoning,
            risk_decision=risk_decision,
        )

    async def evaluate_and_execute_paper(
        self,
        *,
        context: TechnicalContext,
        equity: float,
        daily_loss: float,
        open_positions: int,
        current_exposure: float,
        specification: SymbolSpecification,
        existing_direction_volume: float = 0.0,
    ) -> Step14Result:
        """
        Run the complete pipeline and execute only through a paper gateway.

        Live execution is rejected even if a caller accidentally enables a
        live-trading environment flag.
        """

        if self.execution_gateway is None:
            raise Step14PipelineError(
                "Execution gateway is not configured."
            )

        result = self.evaluate(
            context=context,
            equity=equity,
            daily_loss=daily_loss,
            open_positions=open_positions,
            current_exposure=current_exposure,
            specification=specification,
            existing_direction_volume=existing_direction_volume,
        )

        if not result.allowed:
            return result

        if getattr(
            self.execution_gateway,
            "live_trading_enabled",
            False,
        ):
            raise Step14PipelineError(
                "Step 14 refuses to execute through a live-enabled gateway."
            )

        direction = (
            OrderSide.BUY
            if result.action == "BUY"
            else OrderSide.SELL
        )

        proposal = self.decision_engine.evaluate(context).proposal

        if proposal is None:
            raise Step14PipelineError(
                "Approved decision has no proposal."
            )

        order = OrderRequest(
            symbol=specification.symbol,
            side=direction,
            order_type=OrderType.MARKET,
            volume=result.volume,
            price=proposal.entry_price,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit,
        )

        try:
            execution = await self.execution_gateway.execute(order)
        except ExecutionGatewayError as exc:
            raise Step14PipelineError(
                f"Paper execution rejected: {exc}"
            ) from exc

        return Step14Result(
            allowed=result.allowed,
            action=result.action,
            reason=result.reason,
            confidence=result.confidence,
            volume=result.volume,
            decision_reasoning=result.decision_reasoning,
            risk_decision=result.risk_decision,
            execution_result=execution,
        )
