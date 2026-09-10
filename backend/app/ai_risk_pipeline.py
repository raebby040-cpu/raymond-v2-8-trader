"""
RAYMOND v2.8 - Step 6 AI -> Risk -> Paper Execution Pipeline

Safety:
- AI decisions never place live trades.
- Risk validation happens before paper execution.
- HOLD decisions are rejected.
- The execution gateway remains paper-only.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    from .execution_gateway import (
        ExecutionGatewayError,
        ExecutionResult,
        ExecutionGateway,
        OrderRequest,
        OrderSide,
        OrderType,
    )
    from .risk_engine import (
        RiskEngine,
        RiskEngineError,
        RiskDecision,
        SymbolSpecification,
    )
    from .strategy import AIDecisionLayer
except ImportError:
    from execution_gateway import (
        ExecutionGatewayError,
        ExecutionResult,
        ExecutionGateway,
        OrderRequest,
        OrderSide,
        OrderType,
    )
    from risk_engine import (
        RiskEngine,
        RiskEngineError,
        RiskDecision,
        SymbolSpecification,
    )
    from strategy import AIDecisionLayer


class AIRiskPipelineError(Exception):
    """Raised when the AI -> risk -> execution pipeline fails."""


@dataclass(frozen=True)
class PipelineResult:
    """Complete Step 6 decision and execution result."""

    decision: Dict[str, Any]
    risk: RiskDecision
    execution: Optional[ExecutionResult]


class AIRiskExecutionPipeline:
    """
    Connects the existing AI strategy layer to the risk engine
    and paper execution gateway.

    This class deliberately has no live execution capability.
    """

    def __init__(
        self,
        strategy: Optional[AIDecisionLayer] = None,
        risk_engine: Optional[RiskEngine] = None,
        execution_gateway: Optional[ExecutionGateway] = None,
    ):
        self.strategy = strategy or AIDecisionLayer()
        self.risk_engine = risk_engine or RiskEngine()

        if execution_gateway is None:
            raise AIRiskPipelineError(
                "A paper execution gateway must be explicitly provided."
            )

        self.execution_gateway = execution_gateway

    def make_ai_decision(
        self,
        market_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate a trading decision from market data."""

        if not isinstance(market_data, dict):
            raise AIRiskPipelineError(
                "market_data must be a dictionary."
            )

        try:
            decision = self.strategy.make_decision(
                market_data
            )
        except Exception as exc:
            raise AIRiskPipelineError(
                f"AI decision failed: {exc}"
            ) from exc

        if not isinstance(decision, dict):
            raise AIRiskPipelineError(
                "AI strategy returned an invalid decision."
            )

        return decision

    @staticmethod
    def _normalize_signal(
        decision: Dict[str, Any],
    ) -> str:
        """Normalize the AI signal into BUY/SELL/HOLD."""

        signal = decision.get(
            "signal",
            decision.get("action", "HOLD"),
        )

        normalized = str(signal).upper().strip()

        aliases = {
            "LONG": "BUY",
            "SHORT": "SELL",
        }

        return aliases.get(
            normalized,
            normalized,
        )

    def evaluate(
        self,
        market_data: Dict[str, Any],
        *,
        equity: float,
        entry_price: float,
        stop_loss_price: Optional[float],
        take_profit_price: Optional[float],
        specification: SymbolSpecification,
        open_positions: int = 0,
        current_exposure: float = 0.0,
        order_type: OrderType = OrderType.MARKET,
        client_order_id: Optional[str] = None,
    ) -> PipelineResult:
        """
        Run:

        AI decision
            -> risk validation
            -> paper execution

        No live broker call is possible here.
        """

        decision = self.make_ai_decision(
            market_data
        )

        signal = self._normalize_signal(
            decision
        )

        if signal == "HOLD":
            raise AIRiskPipelineError(
                "AI decision is HOLD. No trade will be executed."
            )

        if signal not in {"BUY", "SELL"}:
            raise AIRiskPipelineError(
                f"Unsupported AI signal: {signal}"
            )

        if entry_price <= 0:
            raise AIRiskPipelineError(
                "entry_price must be greater than zero."
            )

        if stop_loss_price is None:
            raise AIRiskPipelineError(
                "Step 6 requires a stop loss."
            )

        if take_profit_price is None:
            raise AIRiskPipelineError(
                "Step 6 requires a take profit."
            )

        side = (
            "BUY"
            if signal == "BUY"
            else "SELL"
        )

        try:
            risk = self.risk_engine.pre_trade_check(
                equity=equity,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                side=side,
                specification=specification,
                open_positions=open_positions,
                current_exposure=current_exposure,
            )
        except RiskEngineError as exc:
            raise AIRiskPipelineError(
                f"Risk check failed: {exc}"
            ) from exc

        if not risk.allowed:
            raise AIRiskPipelineError(
                f"Trade rejected by risk engine: "
                f"{risk.reason}"
            )

        volume = self.risk_engine.calculate_position_size_from_symbol(
            equity=equity,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            specification=specification,
        )

        if volume <= 0:
            raise AIRiskPipelineError(
                "Risk engine calculated an invalid volume."
            )

        order = OrderRequest(
            symbol=specification.symbol,
            side=(
                OrderSide.BUY
                if signal == "BUY"
                else OrderSide.SELL
            ),
            order_type=order_type,
            volume=volume,
            price=entry_price,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
            client_order_id=client_order_id,
        )

        try:
            execution = self._run_paper_execution(
                order
            )
        except ExecutionGatewayError as exc:
            raise AIRiskPipelineError(
                f"Execution failed: {exc}"
            ) from exc

        return PipelineResult(
            decision=decision,
            risk=risk,
            execution=execution,
        )

    async def evaluate_async(
        self,
        market_data: Dict[str, Any],
        *,
        equity: float,
        entry_price: float,
        stop_loss_price: Optional[float],
        take_profit_price: Optional[float],
        specification: SymbolSpecification,
        open_positions: int = 0,
        current_exposure: float = 0.0,
        order_type: OrderType = OrderType.MARKET,
        client_order_id: Optional[str] = None,
    ) -> PipelineResult:
        """
        Async version of the Step 6 pipeline.

        Uses the execution gateway's async interface.
        """

        decision = self.make_ai_decision(
            market_data
        )

        signal = self._normalize_signal(
            decision
        )

        if signal == "HOLD":
            raise AIRiskPipelineError(
                "AI decision is HOLD. No trade will be executed."
            )

        if signal not in {"BUY", "SELL"}:
            raise AIRiskPipelineError(
                f"Unsupported AI signal: {signal}"
            )

        if stop_loss_price is None:
            raise AIRiskPipelineError(
                "Step 6 requires a stop loss."
            )

        if take_profit_price is None:
            raise AIRiskPipelineError(
                "Step 6 requires a take profit."
            )

        side = signal

        try:
            risk = self.risk_engine.pre_trade_check(
                equity=equity,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                side=side,
                specification=specification,
                open_positions=open_positions,
                current_exposure=current_exposure,
            )
        except RiskEngineError as exc:
            raise AIRiskPipelineError(
                f"Risk check failed: {exc}"
            ) from exc

        if not risk.allowed:
            raise AIRiskPipelineError(
                f"Trade rejected by risk engine: "
                f"{risk.reason}"
            )

        volume = self.risk_engine.calculate_position_size_from_symbol(
            equity=equity,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            specification=specification,
        )

        order = OrderRequest(
            symbol=specification.symbol,
            side=(
                OrderSide.BUY
                if signal == "BUY"
                else OrderSide.SELL
            ),
            order_type=order_type,
            volume=volume,
            price=entry_price,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
            client_order_id=client_order_id,
        )

        try:
            execution = await self.execution_gateway.execute(
                order
            )
        except ExecutionGatewayError as exc:
            raise AIRiskPipelineError(
                f"Execution failed: {exc}"
            ) from exc

        return PipelineResult(
            decision=decision,
            risk=risk,
            execution=execution,
        )

    def _run_paper_execution(
        self,
        order: OrderRequest,
    ) -> ExecutionResult:
        """
        Execute synchronously only when the supplied gateway
        exposes a compatible synchronous test implementation.

        Step 6 production flow uses evaluate_async().
        """

        raise ExecutionGatewayError(
            "Use evaluate_async() for execution."
        )
