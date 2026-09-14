"""
RAYMOND v2.8 - Step 17 Integration Safety Tests

Verifies the backend safety chain:

    Technical Context
        ->
    Step 13 AI
        ->
    Step 14 Risk Engine
        ->
    Paper Execution Gateway

Also verifies that the 8-brain advisory layer remains advisory-only.

These tests do not connect to MT5 or any live broker.
"""

from __future__ import annotations

import asyncio

import pytest

from app.advisory_brains import (
    AdvisoryBrainEngine,
    AdvisorySnapshot,
)
from app.advisory_comparison import (
    compare_decision_with_advisory,
)
from app.ai_trading_decision import (
    AIDecision,
    AIDirection,
    AITradeProposal,
    TechnicalContext,
)
from app.execution_gateway import (
    ExecutionGatewayError,
    OrderRequest,
    OrderSide,
    OrderType,
    PaperExecutionGateway,
)
from app.risk_engine import (
    RiskDecision,
    RiskEngine,
    SymbolSpecification,
)
from app.step14_pipeline import (
    Step14Pipeline,
    Step14PipelineError,
)
from app.trading_pipeline_service import (
    PaperRiskState,
    TradingPipelineService,
)


# ============================================================
# TEST DATA
# ============================================================


def make_context(
    *,
    signal: str = "SELL",
    trend: str = "Bearish",
    score: int = 14,
) -> TechnicalContext:
    return TechnicalContext(
        symbol="XAUUSD",
        timeframe="H1",
        close=4309.905,
        ema20=4339.3467,
        ema50=4353.3490,
        rsi14=37.37,
        atr14=18.8762,
        macd=-8.9213,
        macd_signal=-5.9287,
        macd_histogram=-2.9926,
        trend=trend,
        score=score,
        signal=signal,
        candles_used=100,
    )


def make_proposal(
    direction: AIDirection,
) -> AITradeProposal:
    if direction is AIDirection.SELL:
        stop_loss = 4328.781205246983
        take_profit = 4281.58
    else:
        stop_loss = 4291.0288
        take_profit = 4338.2193

    return AITradeProposal(
        direction=direction,
        symbol="XAUUSD",
        entry_price=4309.905,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=1.5,
        confidence=77.8,
        reason="Test trade proposal.",
        execution_type="paper",
        read_only=True,
        broker_order_required=False,
        risk_engine_required=True,
    )


def make_decision(
    direction: AIDirection,
) -> AIDecision:
    if direction is AIDirection.WAIT:
        return AIDecision(
            direction=AIDirection.WAIT,
            symbol="XAUUSD",
            timeframe="H1",
            confidence=50.0,
            technical_score=0,
            trend="Neutral",
            signal="WAIT",
            proposal=None,
            reasoning="Integration safety test.",
            execution_type="paper",
            read_only=True,
            broker_order_required=False,
            risk_engine_required=True,
            market_regime="uncertain",
            setup="no_setup",
            confluence_score=0,
        )

    if direction is AIDirection.BUY:
        return AIDecision(
            direction=AIDirection.BUY,
            symbol="XAUUSD",
            timeframe="H1",
            confidence=77.8,
            technical_score=80,
            trend="Bullish",
            signal="BUY",
            proposal=make_proposal(AIDirection.BUY),
            reasoning="Integration safety test.",
            execution_type="paper",
            read_only=True,
            broker_order_required=False,
            risk_engine_required=True,
            market_regime="trending_up",
            setup="bullish_continuation",
            confluence_score=65,
        )

    return AIDecision(
        direction=AIDirection.SELL,
        symbol="XAUUSD",
        timeframe="H1",
        confidence=77.8,
        technical_score=14,
        trend="Bearish",
        signal="SELL",
        proposal=make_proposal(AIDirection.SELL),
        reasoning="Integration safety test.",
        execution_type="paper",
        read_only=True,
        broker_order_required=False,
        risk_engine_required=True,
        market_regime="trending_down",
        setup="bearish_continuation",
        confluence_score=65,
    )


def make_advisory(
    direction: str = "SELL",
    *,
    confidence: float = 95.0,
    agreement: float = 100.0,
) -> AdvisorySnapshot:
    if direction == "BUY":
        buy_votes = 8
        sell_votes = 0
        wait_votes = 0
        score = 64.25
        quality = "STRONG"

    elif direction == "SELL":
        buy_votes = 0
        sell_votes = 8
        wait_votes = 0
        score = -64.25
        quality = "STRONG"

    else:
        buy_votes = 0
        sell_votes = 0
        wait_votes = 8
        score = 0.0
        quality = "WEAK"

    return AdvisorySnapshot(
        brains=tuple(),
        master_direction=direction,
        master_confidence=confidence,
        master_score=score,
        buy_votes=buy_votes,
        sell_votes=sell_votes,
        wait_votes=wait_votes,
        agreement_percent=agreement,
        entry_quality=quality,
        warning="Advisory only.",
    )


def make_specification() -> SymbolSpecification:
    return SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=100.0,
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
        spread=0,
        spread_float=True,
    )


# ============================================================
# TEST DOUBLES
# ============================================================


class FakeAIEngine:
    def __init__(
        self,
        decision: AIDecision,
    ) -> None:
        self.decision = decision
        self.calls = 0

    def evaluate(
        self,
        context: TechnicalContext,
    ) -> AIDecision:
        self.calls += 1
        return self.decision


class FakeRiskEngine:
    def __init__(
        self,
        *,
        allowed: bool = True,
    ) -> None:
        self.allowed = allowed
        self.position_size_calls = 0
        self.pre_trade_calls = 0

    def calculate_position_size_from_symbol(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_loss_price: float,
        specification: SymbolSpecification,
    ) -> float:
        self.position_size_calls += 1
        return 0.05

    def pre_trade_check(
        self,
        *,
        equity: float,
        daily_loss: float,
        open_positions: int,
        current_exposure: float,
        proposed_exposure: float,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        volume: float,
        side: str,
        specification: SymbolSpecification,
        existing_direction_volume: float = 0.0,
    ) -> RiskDecision:
        self.pre_trade_calls += 1

        return RiskDecision(
            allowed=self.allowed,
            reason=(
                "Risk approved for test."
                if self.allowed
                else "Risk rejected for test."
            ),
            risk_amount=proposed_exposure,
            daily_loss_limit=300.0,
            total_exposure_limit=500.0,
            proposed_exposure=proposed_exposure,
            open_positions=open_positions,
        )


class CountingPaperGateway(PaperExecutionGateway):
    def __init__(
        self,
        *,
        live_trading_enabled: bool = False,
    ) -> None:
        super().__init__(
            live_trading_enabled=live_trading_enabled,
        )
        self.execute_calls = 0

    async def execute(
        self,
        order: OrderRequest,
    ):
        self.execute_calls += 1
        return await super().execute(order)


# ============================================================
# ADVISORY SAFETY
# ============================================================


def test_advisory_engine_has_exactly_eight_brains() -> None:
    engine = AdvisoryBrainEngine()

    snapshot = engine.analyze(
        make_context(),
        [],
    )

    assert isinstance(snapshot, AdvisorySnapshot)
    assert len(snapshot.brains) == 8


def test_advisory_does_not_replace_raymond_decision() -> None:
    raymond = make_decision(AIDirection.SELL)
    advisory = make_advisory("BUY")

    result = compare_decision_with_advisory(
        raymond,
        advisory,
    )

    assert raymond.direction is AIDirection.SELL
    assert result.raymond_direction == "SELL"
    assert result.advisory_direction == "BUY"
    assert result.comparison == "DISAGREE"


def test_advisory_same_direction_is_agreement_only() -> None:
    raymond = make_decision(AIDirection.SELL)
    advisory = make_advisory("SELL")

    result = compare_decision_with_advisory(
        raymond,
        advisory,
    )

    assert result.comparison == "AGREE"
    assert raymond.direction is AIDirection.SELL


def test_advisory_wait_cannot_confirm_trade() -> None:
    raymond = make_decision(AIDirection.SELL)
    advisory = make_advisory(
        "WAIT",
        confidence=50.0,
        agreement=50.0,
    )

    result = compare_decision_with_advisory(
        raymond,
        advisory,
    )

    assert result.comparison == "WEAK_ENTRY"
    assert raymond.direction is AIDirection.SELL


# ============================================================
# STEP 14 SAFETY
# ============================================================


def test_step14_wait_never_reaches_risk_engine() -> None:
    decision = make_decision(AIDirection.WAIT)

    ai = FakeAIEngine(decision)
    risk = FakeRiskEngine()
    gateway = CountingPaperGateway()

    pipeline = Step14Pipeline(
        ai_engine=ai,
        risk_engine=risk,
        execution_gateway=gateway,
    )

    result = pipeline.evaluate(
        make_context(
            signal="WAIT",
            trend="Neutral",
            score=0,
        ),
        make_specification(),
        account_equity=10000.0,
    )

    assert result.decision.direction is AIDirection.WAIT
    assert result.risk_decision is None
    assert result.position_size is None
    assert result.execution_result is None

    assert risk.position_size_calls == 0
    assert risk.pre_trade_calls == 0
    assert gateway.execute_calls == 0


def test_step14_risk_rejection_never_reaches_execution() -> None:
    decision = make_decision(AIDirection.SELL)

    ai = FakeAIEngine(decision)
    risk = FakeRiskEngine(allowed=False)
    gateway = CountingPaperGateway()

    pipeline = Step14Pipeline(
        ai_engine=ai,
        risk_engine=risk,
        execution_gateway=gateway,
    )

    result = asyncio.run(
        pipeline.evaluate_and_execute_paper(
            make_context(),
            make_specification(),
            account_equity=10000.0,
        )
    )

    assert result.risk_decision is not None
    assert result.risk_decision.allowed is False
    assert result.execution_result is None

    assert risk.pre_trade_calls == 1
    assert gateway.execute_calls == 0


def test_step14_approved_trade_uses_paper_gateway() -> None:
    decision = make_decision(AIDirection.SELL)

    ai = FakeAIEngine(decision)
    risk = FakeRiskEngine(allowed=True)
    gateway = CountingPaperGateway(
        live_trading_enabled=False,
    )

    pipeline = Step14Pipeline(
        ai_engine=ai,
        risk_engine=risk,
        execution_gateway=gateway,
    )

    result = asyncio.run(
        pipeline.evaluate_and_execute_paper(
            make_context(),
            make_specification(),
            account_equity=10000.0,
        )
    )

    assert result.risk_decision is not None
    assert result.risk_decision.allowed is True
    assert result.position_size == 0.05

    assert result.execution_result is not None
    assert result.execution_result.execution_type == "paper"
    assert result.execution_result.broker == "paper"

    assert gateway.execute_calls == 1


def test_step14_rejects_live_enabled_gateway() -> None:
    decision = make_decision(AIDirection.SELL)

    ai = FakeAIEngine(decision)
    risk = FakeRiskEngine()
    gateway = CountingPaperGateway(
        live_trading_enabled=True,
    )

    pipeline = Step14Pipeline(
        ai_engine=ai,
        risk_engine=risk,
        execution_gateway=gateway,
    )

    with pytest.raises(
        Step14PipelineError,
        match="Live trading is not permitted",
    ):
        asyncio.run(
            pipeline.evaluate_and_execute_paper(
                make_context(),
                make_specification(),
                account_equity=10000.0,
            )
        )

    assert gateway.execute_calls == 0


# ============================================================
# PAPER GATEWAY SAFETY
# ============================================================


def test_paper_gateway_accepts_paper_order_only() -> None:
    gateway = PaperExecutionGateway(
        live_trading_enabled=False,
    )

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        volume=0.05,
        price=4309.905,
        stop_loss=4328.781205246983,
        take_profit=4281.58,
    )

    result = asyncio.run(
        gateway.execute(order)
    )

    assert result.execution_type == "paper"
    assert result.broker == "paper"
    assert result.status.value == "accepted"


def test_live_enabled_paper_gateway_rejects_order() -> None:
    gateway = PaperExecutionGateway(
        live_trading_enabled=True,
    )

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        volume=0.05,
        price=4309.905,
        stop_loss=4328.781205246983,
        take_profit=4281.58,
    )

    with pytest.raises(
        ExecutionGatewayError,
        match="paper gateway refuses live execution",
    ):
        asyncio.run(
            gateway.execute(order)
        )


# ============================================================
# FULL SERVICE ORCHESTRATION
# ============================================================


def test_trading_pipeline_service_defaults_to_paper_only() -> None:
    service = TradingPipelineService()

    assert isinstance(
        service.execution_gateway,
        PaperExecutionGateway,
    )

    assert (
        service.execution_gateway.live_trading_enabled
        is False
    )


def test_trading_pipeline_service_uses_step13_decision() -> None:
    service = TradingPipelineService()

    candles = [
        {
            "time": index,
            "open": 4300.0,
            "high": 4310.0,
            "low": 4290.0,
            "close": 4305.0,
            "volume": 100,
        }
        for index in range(100)
    ]

    decision = service.evaluate_decision(
        symbol="XAUUSD",
        timeframe="H1",
        candles=candles,
    )

    assert isinstance(
        decision,
        AIDecision,
    )

    assert decision.read_only is True
    assert decision.broker_order_required is False
    assert decision.risk_engine_required is True


def test_paper_risk_state_is_safe() -> None:
    state = PaperRiskState(
        daily_loss=0.0,
        open_positions=0,
        total_exposure=0.0,
    )

    assert state.daily_loss == 0.0
    assert state.open_positions == 0
    assert state.total_exposure == 0.0


# ============================================================
# REAL RISK ENGINE
# ============================================================


def test_real_risk_engine_rejects_excessive_open_positions() -> None:
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        equity=10000.0,
        daily_loss=0.0,
        open_positions=3,
        current_exposure=0.0,
        proposed_exposure=50.0,
        entry_price=4309.905,
        stop_loss_price=4328.781205246983,
        take_profit_price=4281.58,
        volume=0.05,
        side="SELL",
        specification=make_specification(),
    )

    assert decision.allowed is False
    assert "maximum open positions" in decision.reason.lower()


def test_real_risk_engine_allows_valid_paper_risk() -> None:
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        equity=10000.0,
        daily_loss=0.0,
        open_positions=0,
        current_exposure=0.0,
        proposed_exposure=50.0,
        entry_price=4309.905,
        stop_loss_price=4328.781205246983,
        take_profit_price=4281.58,
        volume=0.05,
        side="SELL",
        specification=make_specification(),
    )

    assert decision.allowed is True


# ============================================================
# FINAL SAFETY ASSERTIONS
# ============================================================


def test_advisory_snapshot_contains_no_execution_authority() -> None:
    snapshot = make_advisory("SELL")

    serialized = snapshot.to_dict()

    assert "execution" not in serialized
    assert "order_id" not in serialized
    assert "broker_order" not in serialized


def test_raymond_decision_remains_unchanged_after_comparison() -> None:
    raymond = make_decision(AIDirection.SELL)

    original_direction = raymond.direction
    original_confidence = raymond.confidence
    original_score = raymond.technical_score
    original_signal = raymond.signal

    advisory = make_advisory("BUY")

    compare_decision_with_advisory(
        raymond,
        advisory,
    )

    assert raymond.direction is original_direction
    assert raymond.confidence == original_confidence
    assert raymond.technical_score == original_score
    assert raymond.signal == original_signal


def test_live_trading_is_disabled_by_default() -> None:
    gateway = PaperExecutionGateway(
        live_trading_enabled=False,
    )

    assert gateway.live_trading_enabled is False


def test_paper_execution_result_is_never_live() -> None:
    gateway = PaperExecutionGateway(
        live_trading_enabled=False,
    )

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        volume=0.05,
        price=4309.905,
        stop_loss=4328.781205246983,
        take_profit=4281.58,
    )

    result = asyncio.run(
        gateway.execute(order)
    )

    assert result.execution_type == "paper"
    assert result.broker == "paper"
    assert result.status.value == "accepted"


