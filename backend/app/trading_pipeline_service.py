 __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from app.ai_trading_decision import AIDecision, AITradingDecisionEngine, TechnicalContext
from app.execution_gateway import PaperExecutionGateway
from app.market_pressure import MarketPressureError, MarketPressureResult, calculate_market_pressure
from app.risk_engine import RiskDecision, RiskEngine, SymbolSpecification
from app.step14_pipeline import Step14Pipeline, Step14Result
from app.technical_indicators import IndicatorResult, TechnicalIndicatorError, calculate_indicators


class TradingPipelineServiceError(RuntimeError):
    """Raised when the application trading pipeline fails safely."""


@dataclass(frozen=True)
class PaperRiskState:
    """Current paper-trading state supplied to Step 14."""

    daily_loss: float
    open_positions: int
    total_exposure: float


class TradingPipelineService:
    """Application-level composition of Raymond's controlled trading layers.

    Market pressure is an advisory confluence layer and does not replace
    the established technical strategy.
    """

    def __init__(
        self,
        *,
        ai_engine: Optional[AITradingDecisionEngine] = None,
        risk_engine: Optional[RiskEngine] = None,
        execution_gateway: Optional[PaperExecutionGateway] = None,
    ) -> None:
        self.ai_engine = ai_engine or AITradingDecisionEngine()
        self.risk_engine = risk_engine or RiskEngine()
        self.execution_gateway = (
            execution_gateway
            or PaperExecutionGateway(live_trading_enabled=False)
        )
        self.step14 = Step14Pipeline(
            ai_engine=self.ai_engine,
            risk_engine=self.risk_engine,
            execution_gateway=self.execution_gateway,
        )

    @staticmethod
    def indicator_to_context(
        result: IndicatorResult,
        *,
        market_pressure: Optional[MarketPressureResult] = None,
    ) -> TechnicalContext:
        """Convert indicator output into the Step 13 technical context."""
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
                market_pressure.score if market_pressure is not None else None
            ),
            market_pressure_label=(
                market_pressure.label if market_pressure is not None else "UNAVAILABLE"
            ),
            market_pressure_available=(
                market_pressure.available if market_pressure is not None else False
            ),
        )

    def build_context(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: Sequence[Mapping[str, Any]],
    ) -> TechnicalContext:
        """Build technical context while treating pressure as advisory."""
        if not symbol.strip():
            raise TradingPipelineServiceError("Symbol is required.")
        if not timeframe.strip():
            raise TradingPipelineServiceError("Timeframe is required.")
        if not candles:
            raise TradingPipelineServiceError("At least one candle is required.")

        try:
            result = calculate_indicators(
                symbol=symbol,
                timeframe=timeframe,
                candles=candles,
            )
        except (TechnicalIndicatorError, ValueError) as exc:
            raise TradingPipelineServiceError(
                f"Technical indicator calculation failed: {exc}"
            ) from exc

        market_pressure: Optional[MarketPressureResult] = None
        try:
            market_pressure = calculate_market_pressure(candles)
        except (MarketPressureError, ValueError):
            # Pressure must never disable Raymond's established strategy.
            market_pressure = None

        return self.indicator_to_context(
            result,
            market_pressure=market_pressure,
        )

    def evaluate_decision(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: Sequence[Mapping[str, Any]],
    ) -> AIDecision:
        """Run indicators -> pressure -> Step 13 AI; no execution occurs."""
        context = self.build_context(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
        )
        try:
            return self.ai_engine.evaluate(context)
        except Exception as exc:
            raise TradingPipelineServiceError(
                f"AI decision failed safely: {exc}"
            ) from exc

    def evaluate_risk(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: Sequence[Mapping[str, Any]],
        specification: SymbolSpecification,
        account_equity: float,
        risk_state: PaperRiskState,
    ) -> Step14Result:
        """Run indicators -> pressure -> Step 13 -> Step 14; no execution."""
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

    async def execute_paper(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: Sequence[Mapping[str, Any]],
        specification: SymbolSpecification,
        account_equity: float,
        risk_state: PaperRiskState,
    ) -> Step14Result:
        """Run the complete paper-only pipeline. Live execution is disabled."""
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
            raise TradingPipelineServiceError(
                f"Paper trading pipeline failed safely: {exc}"
            ) from exc

    @staticmethod
    def serialize_decision(decision: AIDecision) -> dict:
        """Convert an AIDecision into a stable API response."""
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
            "broker_order_required": decision.broker_order_required,
            "risk_engine_required": decision.risk_engine_required,
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
                    "broker_order_required": proposal.broker_order_required,
                    "risk_engine_required": proposal.risk_engine_required,
                }
                if proposal is not None
                else None
            ),
        }

        for field in (
            "market_pressure_score",
            "market_pressure_label",
            "market_pressure_available",
        ):
            if hasattr(decision, field):
                payload[field] = getattr(decision, field)

        return payload

    @staticmethod
    def serialize_risk_decision(
        risk_decision: Optional[RiskDecision],
    ) -> Optional[dict]:
        if risk_decision is None:
            return None
        return {
            "allowed": risk_decision.allowed,
            "reason": risk_decision.reason,
            "risk_amount": risk_decision.risk_amount,
            "daily_loss_limit": risk_decision.daily_loss_limit,
            "total_exposure_limit": risk_decision.total_exposure_limit,
            "proposed_exposure": risk_decision.proposed_exposure,
            "open_positions": risk_decision.open_positions,
        }

    @staticmethod
    def serialize_execution(execution_result: Any) -> Optional[dict]:
        if execution_result is None:
            return None
        return {
            "order_id": execution_result.order_id,
            "client_order_id": execution_result.client_order_id,
            "status": execution_result.status.value,
            "execution_type": execution_result.execution_type,
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
    def serialize_step14_result(cls, result: Step14Result) -> dict:
        return {
            "decision": cls.serialize_decision(result.decision),
            "risk": cls.serialize_risk_decision(result.risk_decision),
            "position_size": result.position_size,
            "execution": cls.serialize_execution(result.execution_result),
        }


__all__ = [
    "TradingPipelineService",
    "TradingPipelineServiceError",
    "PaperRiskState",
]
