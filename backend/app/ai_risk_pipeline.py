"""
RAYMOND v2.8 - AI Risk Pipeline

Step 6:
- AI strategy decision
- Risk-engine validation
- Broker-aware position sizing
- Paper execution only
- No live trading
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

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
from .strategy import AIDecisionLayer


class AIRiskPipelineError(ValueError):
    """Raised when the AI-to-risk pipeline cannot produce a safe decision."""


@dataclass(frozen=True)
class PipelineResult:
    """Complete Step 6 decision result."""

    ai_decision: Dict[str, Any]
    risk_decision: RiskDecision
    execution_result: Optional[ExecutionResult]


class AIRiskExecutionPipeline:
    """
    Connect the AI decision layer to the risk engine and paper gateway.

    This class does not contain any live broker execution.
    """

    def __init__(
        self,
        ai_layer: Optional[AIDecisionLayer] = None,
        risk_engine: Optional[RiskEngine] = None,
        execution_gateway: Optional[ExecutionGateway] = None,
    ):
        self.ai_layer = ai_layer or AIDecisionLayer()
        self.risk_engine = risk_engine or RiskEngine()
        self.execution_gateway = execution_gateway

    def make_ai_decision(
        self,
        market_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate an AI strategy decision."""

        if not isinstance(market_data, dict):
            raise AIRiskPipelineError(
                "market_data must be a dictionary"
            )

        try:
            return self.ai_layer.make_decision(
                market_data
            )
        except Exception as exc:
            raise AIRiskPipelineError(
                f"AI decision failed: {exc}"
            ) from exc

    @staticmethod
    def _normalize_signal(
        decision: Dict[str, Any],
    ) -> Optional[str]:
        """
        Convert the strategy recommendation into BUY/SELL/HOLD.
        """

        recommendation = decision.get(
            "recommendation",
            {},
        )

        action = str(
            recommendation.get(
                "action",
                "",
            )
        ).upper().strip()

        if action in {"BUY", "SELL"}:
            return action

        return None

    @staticmethod
    def _calculate_proposed_exposure(
        volume: float,
        entry_price: float,
        specification: SymbolSpecification,
    ) -> float:
        """
        Estimate notional exposure.

        This is intentionally conservative and broker-neutral.
        """

        if volume <= 0:
            raise AIRiskPipelineError(
                "volume must be greater than zero"
            )

        if entry_price <= 0:
            raise AIRiskPipelineError(
                "entry_price must be greater than zero"
            )

        if specification.contract_size <= 0:
            raise AIRiskPipelineError(
                "contract_size must be greater than zero"
            )

        return (
            volume
            * entry_price
            * specification.contract_size
        )

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
        proposed_volume: Optional[float] = None,
    ) -> PipelineResult:
        """
        Evaluate AI decision and risk checks.

        This method does NOT execute an order.
        """

        ai_decision = self.make_ai_decision(
            market_data
        )

        action = self._normalize_signal(
            ai_decision
        )

        if action is None:
            raise AIRiskPipelineError(
                "AI decision is HOLD/WAIT; no trade should be created"
            )

        recommendation = ai_decision.get(
            "recommendation",
            {},
        )

        entry_price = float(
            recommendation.get(
                "suggested_entry",
                0,
            )
        )

        stop_loss_price = recommendation.get(
            "stop_loss"
        )

        take_profit_price = recommendation.get(
            "take_profit"
        )

        if entry_price <= 0:
            raise AIRiskPipelineError(
                "AI did not provide a valid entry price"
            )

        if stop_loss_price is None:
            raise AIRiskPipelineError(
                "AI did not provide a stop-loss"
            )

        if take_profit_price is None:
            raise AIRiskPipelineError(
                "AI did not provide a take-profit"
            )

        stop_loss_price = float(
            stop_loss_price
        )

        take_profit_price = float(
            take_profit_price
        )

        if proposed_volume is None:
            proposed_volume = (
                self.risk_engine.calculate_position_size_from_symbol(
                    equity=equity,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss_price,
                    specification=specification,
                )
            )

        volume = float(
            proposed_volume
        )

        if volume <= 0:
            raise AIRiskPipelineError(
                "risk engine calculated zero usable volume"
            )

        proposed_exposure = (
            self._calculate_proposed_exposure(
                volume=volume,
                entry_price=entry_price,
                specification=specification,
            )
        )

        risk_decision = (
            self.risk_engine.pre_trade_check(
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
                existing_direction_volume=(
                    existing_direction_volume
                ),
            )
        )

        return PipelineResult(
            ai_decision=ai_decision,
            risk_decision=risk_decision,
            execution_result=None,
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
        proposed_volume: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> PipelineResult:
        """
        Evaluate AI + risk, then send only to the supplied execution gateway.

        The gateway must be the paper gateway for Step 6.
        """

        result = self.evaluate(
            market_data=market_data,
            equity=equity,
            daily_loss=daily_loss,
            open_positions=open_positions,
            current_exposure=current_exposure,
            specification=specification,
            existing_direction_volume=(
                existing_direction_volume
            ),
            proposed_volume=proposed_volume,
        )

        if not result.risk_decision.allowed:
            return result

        if self.execution_gateway is None:
            raise AIRiskPipelineError(
                "execution gateway is not configured"
            )

        action = self._normalize_signal(
            result.ai_decision
        )

        recommendation = result.ai_decision[
            "recommendation"
        ]

        side = (
            OrderSide.BUY
            if action == "BUY"
            else OrderSide.SELL
        )

        order = OrderRequest(
            symbol=specification.symbol,
            side=side,
            order_type=OrderType.MARKET,
            volume=float(
                result.risk_decision.proposed_exposure
                / (
                    recommendation[
                        "suggested_entry"
                    ]
                    * specification.contract_size
                )
            ),
            price=None,
            stop_loss=float(
                recommendation["stop_loss"]
            ),
            take_profit=float(
                recommendation["take_profit"]
            ),
            client_order_id=client_order_id,
        )

        try:
            execution_result = (
                await self.execution_gateway.execute(
                    order
                )
            )
        except ExecutionGatewayError:
            raise

        return PipelineResult(
            ai_decision=result.ai_decision,
            risk_decision=result.risk_decision,
            execution_result=execution_result,
        )
