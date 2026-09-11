from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.ai_trading_decision import (
    AIDirection,
    AITradingDecisionEngine,
    TechnicalContext,
)
from app.execution_gateway import ExecutionGatewayError, OrderRequest
from app.risk_engine import RiskDecision, RiskEngine, SymbolSpecification


class Step14PipelineError(RuntimeError):
    """Raised when Step 14 cannot safely complete."""


@dataclass(frozen=True)
class Step14Result:
    decision: Any
    risk_decision: RiskDecision | None
    execution_result: Any | None = None


class Step14Pipeline:
    """Connect Step 13 AI decisions to risk checks and paper execution."""

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
        decision = self.ai_engine.evaluate(context)

        if decision.direction is AIDirection.WAIT:
            return Step14Result(
                decision=decision,
                risk_decision=None,
            )

        proposal = decision.proposal

        if proposal is None:
            raise Step14PipelineError(
                "Trade direction was approved without a proposal."
            )

        if proposal.stop_loss is None or proposal.take_profit is None:
            raise Step14PipelineError(
                "Trade proposal is missing stop-loss or take-profit."
            )

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
                "Risk engine returned a zero or invalid position size."
            )

        proposed_exposure = abs(
            position_size
            * proposal.entry_price
            * specification.contract_size
        )

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
        )

    def evaluate_and_execute_paper(
        self,
        context: TechnicalContext,
        specification: SymbolSpecification,
        *,
        account_equity: float,
        daily_loss: float = 0.0,
        open_positions: int = 0,
        total_exposure: float = 0.0,
    ) -> Step14Result:
        if self.execution_gateway is None:
            raise Step14PipelineError(
                "Step 14 requires a paper execution gateway."
            )

        if getattr(
            self.execution_gateway,
            "live_trading_enabled",
            False,
        ):
            raise Step14PipelineError(
                "Live trading is not permitted by Step 14."
            )

        result = self.evaluate(
            context,
            specification,
            account_equity=account_equity,
            daily_loss=daily_loss,
            open_positions=open_positions,
            total_exposure=total_exposure,
        )

        if (
            result.risk_decision is None
            or not result.risk_decision.allowed
        ):
            return result

        proposal = result.decision.proposal

        if proposal is None:
            raise Step14PipelineError(
                "Approved risk decision has no trade proposal."
            )

        try:
            execution_result = self.execution_gateway.execute(
                OrderRequest(
                    symbol=proposal.symbol,
                    direction=proposal.direction.value,
                    volume=result.risk_decision.risk_amount,
                    entry_price=proposal.entry_price,
                    stop_loss=proposal.stop_loss,
                    take_profit=proposal.take_profit,
                )
            )
        except ExecutionGatewayError as exc:
            raise Step14PipelineError(str(exc)) from exc

        return Step14Result(
            decision=result.decision,
            risk_decision=result.risk_decision,
            execution_result=execution_result,
        )


def _context_from_mapping(
    data: Mapping[str, Any],
) -> TechnicalContext:
    """Build a technical context from mapping-like API input."""
    return TechnicalContext(**dict(data))
