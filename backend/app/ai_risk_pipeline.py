from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    from .execution_gateway import (
        ExecutionGateway,
        ExecutionResult,
        OrderRequest,
        OrderSide,
        OrderType,
    )
    from .risk_engine import (
        RiskDecision,
        RiskEngine,
        SymbolSpecification,
    )
    from .strategy import AIDecisionLayer
except ImportError:
    from execution_gateway import (
        ExecutionGateway,
        ExecutionResult,
        OrderRequest,
        OrderSide,
        OrderType,
    )
    from risk_engine import (
        RiskDecision,
        RiskEngine,
        SymbolSpecification,
    )
    from strategy import AIDecisionLayer


class AIRiskPipelineError(Exception):
    """Raised when the AI → risk → execution pipeline cannot continue."""


@dataclass(frozen=True)
class PipelineResult:
    """Result of the AI decision and risk-validation pipeline."""

    allowed: bool
    action: str
    reason: str
    volume: float
    recommendation: Dict[str, Any]
    risk_decision: RiskDecision
    execution_result: Optional[ExecutionResult] = None


class AIRiskPipeline:
    """
    Connects the AI strategy layer to the risk engine and paper execution gateway.

    This pipeline does not place live broker orders.
    """

    def __init__(
        self,
        *,
        strategy: Optional[AIDecisionLayer] = None,
        risk_engine: Optional[RiskEngine] = None,
        execution_gateway: Optional[ExecutionGateway] = None,
    ) -> None:
        self.strategy = strategy or AIDecisionLayer()
        self.risk_engine = risk_engine or RiskEngine()
        self.execution_gateway = execution_gateway

    def evaluate(
        self,
        *,
        market_data: Dict[str, Any],
        equity: float,
        daily_loss: float,
        open_positions: int,
        current_exposure: float,
        specification: SymbolSpecification,
        existing_direction_volume: float = 0.0,
    ) -> PipelineResult:
        """
        Generate an AI recommendation, calculate broker-aware position size,
        and run the complete risk pre-trade check.
        """

        try:
            recommendation = self.strategy.make_decision(market_data)
        except Exception as exc:
            raise AIRiskPipelineError(
                f"AI strategy evaluation failed: {exc}"
            ) from exc

        action = str(
            recommendation.get("action")
            or recommendation.get("signal")
            or recommendation.get("decision")
            or "HOLD"
        ).upper()

        if action in {"HOLD", "WAIT", "NO_TRADE"}:
            raise AIRiskPipelineError(
                "AI decision does not request a trade."
            )

        if action not in {"BUY", "SELL"}:
            raise AIRiskPipelineError(
                f"Unsupported AI action: {action}"
            )

        entry_price = float(
            recommendation.get("suggested_entry")
            or recommendation.get("entry_price")
            or 0.0
        )

        stop_loss_price = recommendation.get("stop_loss")
        take_profit_price = recommendation.get("take_profit")

        if entry_price <= 0:
            raise AIRiskPipelineError(
                "AI recommendation did not provide a valid entry price."
            )

        if stop_loss_price is not None:
            stop_loss_price = float(stop_loss_price)

        if take_profit_price is not None:
            take_profit_price = float(take_profit_price)

        volume = self.risk_engine.calculate_position_size_from_symbol(
            equity=equity,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            specification=specification,
        )

        proposed_exposure = (
            volume
            * entry_price
            * specification.contract_size
        )

        risk_decision = self.risk_engine.pre_trade_check(
            equity=equity,
            daily_loss=daily_loss,
            open_positions=open_positions,
            current_exposure=current_exposure,
            proposed_exposure=proposed_exposure,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            volume=volume,
            side=action,
            specification=specification,
            existing_direction_volume=existing_direction_volume,
        )

        return PipelineResult(
            allowed=risk_decision.allowed,
            action=action,
            reason=risk_decision.reason,
            volume=volume,
            recommendation=recommendation,
            risk_decision=risk_decision,
        )

    async def evaluate_and_execute_paper(
        self,
        *,
        market_data: Dict[str, Any],
        equity: float,
        daily_loss: float,
        open_positions: int,
        current_exposure: float,
        specification: SymbolSpecification,
        existing_direction_volume: float = 0.0,
    ) -> PipelineResult:
        """
        Run AI + risk validation and, if approved, send the exact
        risk-approved volume to the paper execution gateway.

        This method does not place live broker orders.
        """

        if self.execution_gateway is None:
            raise AIRiskPipelineError(
                "Execution gateway is not configured."
            )

        result = self.evaluate(
            market_data=market_data,
            equity=equity,
            daily_loss=daily_loss,
            open_positions=open_positions,
            current_exposure=current_exposure,
            specification=specification,
            existing_direction_volume=existing_direction_volume,
        )

        if not result.allowed:
            raise AIRiskPipelineError(
                f"Trade rejected by risk engine: {result.reason}"
            )

        recommendation = result.recommendation

        entry_price = float(
            recommendation.get("suggested_entry")
            or recommendation.get("entry_price")
            or 0.0
        )

        stop_loss = recommendation.get("stop_loss")
        take_profit = recommendation.get("take_profit")

        order_side = (
            OrderSide.BUY
            if result.action == "BUY"
            else OrderSide.SELL
        )

        order = OrderRequest(
            symbol=specification.symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            volume=result.volume,
            price=entry_price,
            stop_loss=(
                float(stop_loss)
                if stop_loss is not None
                else None
            ),
            take_profit=(
                float(take_profit)
                if take_profit is not None
                else None
            ),
        )

        execution_result = await self.execution_gateway.execute(order)

        return PipelineResult(
            allowed=result.allowed,
            action=result.action,
            reason=result.reason,
            volume=result.volume,
            recommendation=result.recommendation,
            risk_decision=result.risk_decision,
            execution_result=execution_result,
        )
