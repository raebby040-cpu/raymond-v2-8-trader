"""Safety regression tests for Raymond's Step 13 AI decision engine."""

from __future__ import annotations

import pytest

from app.ai_trading_decision import (

    AIDecisionError,

    AIDirection,

    AITradingDecisionEngine,

    TechnicalContext,

)

def make_context(**overrides) -> TechnicalContext:

    values = {

        "symbol": "XAUUSD",

        "timeframe": "H1",

        "close": 4309.905,

        "ema20": 4339.3467,

        "ema50": 4353.3490,

        "rsi14": 37.37,

        "atr14": 18.8762,

        "macd": -8.9213,

        "macd_signal": -5.9287,

        "macd_histogram": -2.9926,

        "trend": "Bearish",

        "score": 14,

        "signal": "SELL",

        "candles_used": 100,

    }

    values.update(overrides)

    return TechnicalContext(**values)

def test_missing_core_indicators_fails_closed_to_wait() -> None:

    context = make_context(

        signal="BUY",

        trend="Bullish",

        score=90,

        ema20=4310.0,

        ema50=4300.0,

        rsi14=None,

        macd=None,

        macd_signal=None,

        macd_histogram=None,

        atr14=10.0,

    )

    decision = AITradingDecisionEngine().evaluate(context)

    assert decision.direction is AIDirection.WAIT

    assert decision.proposal is None

def test_configured_minimum_confluence_is_enforced() -> None:

    context = make_context(

        signal="BUY",

        trend="Bullish",

        score=65,

        ema20=4290.0,

        ema50=4300.0,

        rsi14=80.0,

        macd=-1.0,

        macd_signal=1.0,

        macd_histogram=-1.0,

        atr14=10.0,

    )

    engine = AITradingDecisionEngine()

    decision = engine.evaluate(context)

    assert decision.direction is AIDirection.WAIT

    assert decision.proposal is None

    assert decision.confluence_score < engine.config.minimum_confluence

def test_market_pressure_inconsistent_label_and_score_is_rejected() -> None:

    context = make_context(

        market_pressure_available=True,

        market_pressure_score=-60,

        market_pressure_label="BUY_PRESSURE",

    )

    with pytest.raises(AIDecisionError):

        context.validate()

def test_available_pressure_requires_a_score() -> None:

    context = make_context(

        market_pressure_available=True,

        market_pressure_score=None,

        market_pressure_label="BUY_PRESSURE",

    )

    with pytest.raises(AIDecisionError):

        context.validate()

def test_unavailable_pressure_cannot_be_used_as_directional_evidence() -> None:

    context = make_context(

        market_pressure_available=False,

        market_pressure_score=None,

        market_pressure_label="UNAVAILABLE",

    )

    context.validate()

    decision = AITradingDecisionEngine().evaluate(context)

    assert decision.market_pressure_available is False

    assert decision.market_pressure_score is None

    assert decision.market_pressure_label == "UNAVAILABLE"

def test_wait_signal_never_produces_a_trade_proposal() -> None:

    context = make_context(

        signal="WAIT",

        trend="Neutral",

        score=100,

        ema20=4310.0,

        ema50=4300.0,

        rsi14=60.0,

        atr14=10.0,

        macd=2.0,

        macd_signal=1.0,

        macd_histogram=1.0,

    )

    decision = AITradingDecisionEngine().evaluate(context)

    assert decision.direction is AIDirection.WAIT

    assert decision.proposal is None

def test_proposal_is_explicitly_paper_only() -> None:

    context = make_context(

        signal="SELL",

        trend="Bearish",

        score=10,

        ema20=4300.0,

        ema50=4310.0,

        rsi14=40.0,

        atr14=10.0,

        macd=-2.0,

        macd_signal=-1.0,

        macd_histogram=-1.0,

    )

    decision = AITradingDecisionEngine().evaluate(context)

    assert decision.direction is AIDirection.SELL

    assert decision.proposal is not None

    assert decision.proposal.execution_type == "paper"

    assert decision.proposal.read_only is True

    assert decision.proposal.broker_order_required is False

    assert decision.proposal.risk_engine_required is True
