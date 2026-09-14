"""
RAYMOND v2.8 - Step 17 Integration Safety Tests

Verifies the complete backend safety chain:

    Technical Context
        ->
    Step 13 AI
        ->
    Step 14 Risk Engine
        ->
    Paper Execution Gateway

Also verifies that the 8-brain advisory layer remains advisory-only
and cannot replace Step 13, bypass Step 14, or execute trades.

These tests do not connect to MT5 or any live broker.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

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
    PaperExecutionGateway,
)
from app.risk_engine import (
    RiskDecision,
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
    return AITradeProposal(
        direction=direction,
        symbol="XAUUSD",
        entry_price=4309.905,
        stop_loss=4328.7812
        if direction is AIDirection.SELL
        else 4291.0288,
        take_profit=4281.5907
        if direction is AIDirection.SELL
        else 4338.2193,
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
        proposal = None
        confidence = 50.0
        score = 0
        trend = "Neutral"
        signal = "WAIT"
    elif direction is AIDirection.BUY:
        proposal = make_proposal(direction)
        confidence = 77.8
        score = 80
        trend = "Bullish"
        signal = "BUY"
    else:
        proposal = make_proposal(direction)
        confidence = 77.8
        score = 14
        trend = "Bearish"
        signal = "SELL"

    return AIDecision(
        direction=direction,
        symbol="XAUUSD",
        timeframe="H1",
        confidence=confidence,
        technical_score=score,
        trend=trend,
        signal=signal,
        proposal=proposal,
        reasoning="Integration safety test.",
        execution_type="paper",
        read_only=True,
        broker_order_required=False,
        risk_engine_required=True,
        market_regime=(
            "trending_up"
            if direction is AIDirection.BUY
            else "trending_down"
            if direction is AIDirection.SELL
            else "uncertain"
        ),
        setup=(
            "bullish_continuation"
            if direction is AIDirection.BUY
            else "bearish_continuation"
            if direction is AIDirection.SELL
            else "no_setup"
        ),
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
    elif direction == "SELL":
        buy_votes = 0
        sell_votes = 8
        wait_votes = 0
        score = -64.25
    else:
        buy_votes = 0
        sell_votes = 0
        wait_votes = 8
        score = 0.0

    return AdvisorySnapshot(
        brains=tuple(),
        master_direction=direction,
        master_confidence=confidence,
        master_score=score,
        buy_votes=buy_votes,
        sell_votes=sell_votes,
        wait_votes=wait_votes,
        agreement_percent=agreement,
        entry_quality="STRONG",
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
        spread=0.0,
        spread_float=True,
    )


# ============================================================
# SIMPLE TEST DOUBLES
# ============================================================


class FakeAIEngine:
    """Controlled Step 13 replacement used only by tests."""

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
    """Controlled Risk Engine replacement used only by tests."""

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
    """Paper gateway that records execution attempts."""

    def __init__(
        self,
        *,
        live_trading_enabled: bool = False,
    ) -> None:
        super().__init__(
            live_trading_enabled=live_trading_enabled
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
    assert result.status == "DISAGREE"


def test_advisory_same_direction_is_only_comparison() -> None:
    raymond = make_decision(AIDirection.SELL)
    advisory = make_advisory("SELL")

    result = compare_decision_with_advisory(
        raymond,
        advisory,
    )

    assert result.status == "AGREE"
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

    assert result.status == "WEAK_ENTRY"
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


def test_paper_gateway_never_executes_live() -> None:
    gateway = PaperExecutionGateway(
        live_trading_enabled=False,
    )

    order = OrderRequest(
        symbol="XAUUSD",
        side="sell",
        order_type="market",
        volume=0.05,
        price=4309.905,
        stop_loss=4328.7812,
        take_profit=4281.5907,
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
        side="sell",
        order_type="market",
        volume=0.05,
        price=4309.905,
        stop_loss=4328.7812,
        take_profit=4281.5907,
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


def test_trading_pipeline_service_decision_is_step13() -> None:
    service = TradingPipelineService()

    decision = service.evaluate_decision(
        symbol="XAUUSD",
        timeframe="H1",
        candles=[
            {
                "time": 1,
                "open": 4300.0,
                "high": 4310.0,
                "low": 4290.0,
                "close": 4305.0,
                "volume": 100,
            }
            for _ in range(100)
        ],
    )

    assert isinstance(decision, AIDecision)
    assert decision.read_only is True
    assert decision.broker_order_required is False
    assert decision.risk_engine_required is True


def test_advisory_snapshot_contains_no_execution_authority() -> None:
    snapshot = make_advisory("SELL")

    data = snapshot.to_dict()

    assert "execution_authorized" not in data
    assert "broker_order_allowed" not in data
    assert "place_order" not in data
    assert "execute_order" not in data


def test_comparison_contains_no_execution_authority() -> None:
    raymond = make_decision(AIDirection.SELL)
    advisory = make_advisory("SELL")

    result = compare_decision_with_advisory(
        raymond,
        advisory,
    )

    data = result.to_dict()

    assert "execution_authorized" not in data
    assert "broker_order_allowed" not in data
    assert "place_order" not in data
    assert "execute_order" not in data


def test_advisory_does_not_modify_raymond_decision() -> None:
    raymond = make_decision(AIDirection.SELL)

    before = raymond

    advisory = make_advisory("SELL")

    compare_decision_with_advisory(
        raymond,
        advisory,
    )

    assert raymond is before
    assert raymond.direction is AIDirection.SELL
    assert raymond.signal == "SELL"
    assert raymond.confidence == 77.8
    assert raymond.technical_score == 14


def test_step14_requires_risk_engine_before_execution() -> None:
    decision = make_decision(AIDirection.SELL)

    ai = FakeAIEngine(decision)
    risk = FakeRiskEngine(allowed=True)
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

    assert risk.pre_trade_calls == 1
    assert gateway.execute_calls == 1
    assert result.risk_decision.allowed is True


# ============================================================
# FINAL SAFETY CONTRACT
# ============================================================


def test_step17_final_safety_contract() -> None:
    service = TradingPipelineService()

    assert service.execution_gateway.live_trading_enabled is False

    decision = make_decision(AIDirection.SELL)
    advisory = make_advisory("SELL")

    comparison = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert comparison.raymond_direction == "SELL"
    assert comparison.advisory_direction == "SELL"
    assert comparison.status == "AGREE"

    assert decision.direction is AIDirection.SELL
    assert decision.risk_engine_required is True
    assert decision.broker_order_required is False
    assert decision.read_only is True

    assert service.execution_gateway is not None
    assert isinstance(
        service.execution_gateway,
        PaperExecutionGateway,
    )


