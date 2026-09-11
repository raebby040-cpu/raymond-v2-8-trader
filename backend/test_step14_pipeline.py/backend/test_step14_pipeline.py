"""Step 14 integration tests for the AI -> risk -> paper boundary."""

import asyncio

import pytest

from app.ai_trading_decision import (
    AIDirection,
    AITradingDecisionEngine,
    TechnicalContext,
)
from app.execution_gateway import (
    ExecutionGatewayError,
    PaperExecutionGateway,
)
from app.risk_engine import (
    RiskConfig,
    RiskEngine,
    SymbolSpecification,
)
from app.step14_pipeline import (
    Step14Pipeline,
    Step14PipelineError,
)


def context(**overrides):
    values = dict(
        symbol="XAUUSD",
        timeframe="M15",
        close=2000.0,
        ema20=2005.0,
        ema50=1995.0,
        rsi14=58.0,
        atr14=10.0,
        macd=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        trend="Bullish",
        score=80,
        signal="BUY",
        candles_used=100,
    )

    values.update(overrides)

    return TechnicalContext(**values)


def specification():
    return SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        volume_limit=100.0,
        trade_mode=4,
        trade_execution_mode=0,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="USD",
        spread=10,
        spread_float=True,
    )


def test_step13_buy_flows_into_step14_risk_and_paper_execution():
    gateway = PaperExecutionGateway(
        live_trading_enabled=False
    )

    pipeline = Step14Pipeline(
        decision_engine=AITradingDecisionEngine(),
        risk_engine=RiskEngine(
            RiskConfig(
                risk_per_trade_percent=1.0
            )
        ),
        execution_gateway=gateway,
    )

    result = asyncio.run(
        pipeline.evaluate_and_execute_paper(
            context=context(),
            equity=10000.0,
            daily_loss=0.0,
            open_positions=0,
            current_exposure=0.0,
            specification=specification(),
        )
    )

    assert result.action == "BUY"
    assert result.allowed is True
    assert result.volume > 0
    assert result.execution_result is not None
    assert result.execution_result.execution_type == "paper"
    assert result.execution_result.broker == "paper"
    assert result.execution_result.order_id.startswith(
        "PAPER-"
    )


def test_conflicting_ai_context_stops_before_risk_and_execution():
    pipeline = Step14Pipeline(
        execution_gateway=PaperExecutionGateway()
    )

    result = pipeline.evaluate(
        context=context(
            trend="Bearish",
            signal="BUY",
        ),
        equity=10000.0,
        daily_loss=0.0,
        open_positions=0,
        current_exposure=0.0,
        specification=specification(),
    )

    assert result.action == "WAIT"
    assert result.allowed is False
    assert result.risk_decision is None


def test_risk_rejection_never_reaches_execution():
    gateway = PaperExecutionGateway(
        live_trading_enabled=False
    )

    pipeline = Step14Pipeline(
        execution_gateway=gateway
    )

    result = pipeline.evaluate(
        context=context(),
        equity=10000.0,
        daily_loss=300.0,
        open_positions=0,
        current_exposure=0.0,
        specification=specification(),
    )

    assert result.action == "BUY"
    assert result.allowed is False
    assert result.risk_decision is not None
    assert "daily loss" in result.risk_decision.reason.lower()
    assert result.execution_result is None


def test_live_enabled_gateway_is_rejected_by_step14():
    gateway = PaperExecutionGateway(
        live_trading_enabled=True
    )

    pipeline = Step14Pipeline(
        execution_gateway=gateway
    )

    with pytest.raises(
        Step14PipelineError,
        match="live-enabled",
    ):
        asyncio.run(
            pipeline.evaluate_and_execute_paper(
                context=context(),
                equity=10000.0,
                daily_loss=0.0,
                open_positions=0,
                current_exposure=0.0,
                specification=specification(),
            )
        )


def test_missing_atr_fails_closed_to_wait():
    pipeline = Step14Pipeline(
        execution_gateway=PaperExecutionGateway()
    )

    result = pipeline.evaluate(
        context=context(
            atr14=None
        ),
        equity=10000.0,
        daily_loss=0.0,
        open_positions=0,
        current_exposure=0.0,
        specification=specification(),
    )

    assert result.action == "WAIT"
    assert result.allowed is False


def test_ai_direction_is_conservative():
    engine = AITradingDecisionEngine()

    decision = engine.evaluate(
        context(
            score=64,
            trend="Bullish",
            signal="BUY",
        )
    )

    assert decision.direction is AIDirection.WAIT


def test_paper_gateway_still_refuses_live_execution():
    gateway = PaperExecutionGateway(
        live_trading_enabled=True
    )

    from app.execution_gateway import (
        OrderRequest,
        OrderSide,
        OrderType,
    )

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.01,
    )

    with pytest.raises(
        ExecutionGatewayError,
        match="refuses live execution",
    ):
        asyncio.run(
            gateway.execute(order)
        )
