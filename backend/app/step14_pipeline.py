from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.ai_trading_decision import (
    AIDirection,
    AITradingDecisionEngine,
    TechnicalContext,
)
from app.execution_gateway import (
    ExecutionGatewayError,
    OrderRequest,
    OrderSide,
    OrderType,
)
from app.risk_engine import (
    RiskDecision,
    RiskEngine,
    SymbolSpecification,
)


class Step14PipelineError(RuntimeError):
    """Raised when Step 14 cannot safely complete."""


@dataclass(frozen=True)
class Step14Result:
    """Complete Step 14 evaluation result."""

    decision: Any
    risk_decision: RiskDecision | None
    position_size: float | None = None
    execution_result: Any | None = None


class Step14Pipeline:
    """
    Connect Step 13 AI decisions to the Risk Engine
    and paper-only execution gateway.

    Safety rules:
    - WAIT never reaches the Risk Engine.
    - Risk rejection never reaches execution.
    - Live execution is always rejected.
    - Position size comes from the Risk Engine.
    - Paper execution only.
    """

    def __init__(
        self,
        ai_engine: AITradingDecisionEngine,
        risk_engine: RiskEngine,
        execution_gateway: Any | None = None,
    ) -> None:
        self.ai_engine = ai_engine
        self.risk_engine = risk_engine
        self.execution_gateway = execution_gateway

    def evaluate(
        self,
        context: TechnicalContext,
        specification: SymbolSpecification,
        *,
        account_equity: float,
        daily_loss: float = 0.0,
        open_positions: int = 0,
        total_exposure: float = 0.0,
    ) -> Step14Result:
        """
        Run AI decision -> position sizing -> risk check.

        This method does not execute an order.
        """

        decision = self.ai_engine.evaluate(context)

        # --------------------------------------------------
        # WAIT: stop immediately.
        # --------------------------------------------------

        if decision.direction is AIDirection.WAIT:
            return Step14Result(
                decision=decision,
                risk_decision=None,
                position_size=None,
                execution_result=None,
            )

        proposal = decision.proposal

        if proposal is None:
            raise Step14PipelineError(
                "Trade direction was approved without a proposal."
            )

        if (
            proposal.stop_loss is None
            or proposal.take_profit is None
        ):
            raise Step14PipelineError(
                "Trade proposal is missing stop-loss or take-profit."
            )

        # --------------------------------------------------
        # Risk Engine calculates the actual position size.
        # --------------------------------------------------

        position_size = (
            self.risk_engine.calculate_position_size_from_symbol(
                equity=account_equity,
                entry_price=proposal.entry_price,
                stop_loss_price=proposal.stop_loss,
                specification=specification,
            )
        )

        if position_size <= 0:
            raise Step14PipelineError(
                "Risk Engine returned a zero or invalid position size."
            )

        # --------------------------------------------------
        # Calculate proposed exposure.
        # --------------------------------------------------

        proposed_exposure = abs(
            position_size
            * proposal.entry_price
            * specification.contract_size
        )

        # --------------------------------------------------
        # Risk Engine is the final authority before execution.
        # --------------------------------------------------

        risk_decision = self.risk_engine.pre_trade_check(
            equity=account_equity,
            daily_loss=daily_loss,
            open_positions=open_positions,
            current_exposure=total_exposure,
            proposed_exposure=proposed_exposure,
            entry_price=proposal.entry_price,
            stop_loss_price=proposal.stop_loss,
            take_profit_price=proposal.take_profit,
            volume=position_size,
            side=proposal.direction.value,
            specification=specification,
        )

        return Step14Result(
            decision=decision,
            risk_decision=risk_decision,
            position_size=position_size,
            execution_result=None,
        )

    async def evaluate_and_execute_paper(
        self,
        context: TechnicalContext,
        specification: SymbolSpecification,
        *,
        account_equity: float,
        daily_loss: float = 0.0,
        open_positions: int = 0,
        total_exposure: float = 0.0,
    ) -> Step14Result:
        """
        Run the complete Step 14 paper-only pipeline.

        AI -> Risk Engine -> Paper Gateway.

        Live execution is never permitted.
        """

        if self.execution_gateway is None:
            raise Step14PipelineError(
                "Step 14 requires a paper execution gateway."
            )

        # --------------------------------------------------
        # Hard live-trading safety gate.
        # --------------------------------------------------

        if getattr(
            self.execution_gateway,
            "live_trading_enabled",
            False,
        ):
            raise Step14PipelineError(
                "Live trading is not permitted by Step 14."
            )

        # --------------------------------------------------
        # AI -> Risk.
        # --------------------------------------------------

        result = self.evaluate(
            context,
            specification,
            account_equity=account_equity,
            daily_loss=daily_loss,
            open_positions=open_positions,
            total_exposure=total_exposure,
        )

        # --------------------------------------------------
        # WAIT or risk rejection:
        # NEVER execute.
        # --------------------------------------------------

        if result.risk_decision is None:
            return result

        if not result.risk_decision.allowed:
            return result

        # --------------------------------------------------
        # A successful risk decision must have:
        # - proposal
        # - position size
        # --------------------------------------------------

        proposal = result.decision.proposal

        if proposal is None:
            raise Step14PipelineError(
                "Approved risk decision has no trade proposal."
            )

        if result.position_size is None:
            raise Step14PipelineError(
                "Approved risk decision has no position size."
            )

        # --------------------------------------------------
        # Map AI direction to the actual execution gateway.
        # --------------------------------------------------

        if proposal.direction is AIDirection.BUY:
            order_side = OrderSide.BUY

        elif proposal.direction is AIDirection.SELL:
            order_side = OrderSide.SELL

        else:
            raise Step14PipelineError(
                "WAIT cannot reach paper execution."
            )

        # --------------------------------------------------
        # Construct the actual OrderRequest API.
        # --------------------------------------------------

        order = OrderRequest(
            symbol=proposal.symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            volume=result.position_size,
            price=proposal.entry_price,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit,
        )

        # --------------------------------------------------
        # Paper execution is asynchronous.
        # --------------------------------------------------

        try:
            execution_result = (
                await self.execution_gateway.execute(order)
            )

        except ExecutionGatewayError as exc:
            raise Step14PipelineError(str(exc)) from exc

        return Step14Result(
            decision=result.decision,
            risk_decision=result.risk_decision,
            position_size=result.position_size,
            execution_result=execution_result,
        )


def _context_from_mapping(
    data: Mapping[str, Any],
) -> TechnicalContext:
    """Build a technical context from mapping-like API input."""

    return TechnicalContext(**dict(data))
