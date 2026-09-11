"""Step 13 - AI trading decision engine validation."""

import pytest

from app.ai_trading_decision import (
    AIDecisionConfig,
    AIDecisionError,
    AIDirection,
    AITradingDecisionEngine,
    TechnicalContext,
    ai_decision_to_dict,
)


def _bullish_context():
    return TechnicalContext(
        symbol="XAUUSD",
        timeframe="M15",
        close=2300.0,
        ema20=2295.0,
        ema50=2285.0,
        rsi14=60.0,
        atr14=10.0,
        macd=5.0,
        macd_signal=3.0,
        macd_histogram=2.0,
        trend="Bullish",
        score=75,
        signal="BUY",
        candles_used=100,
    )


def _bearish_context():
    return TechnicalContext(
        symbol="XAUUSD",
        timeframe="M15",
        close=2300.0,
        ema20=2305.0,
        ema50=2315.0,
        rsi14=40.0,
        atr14=10.0,
        macd=-5.0,
        macd_signal=-3.0,
        macd_histogram=-2.0,
        trend="Bearish",
        score=25,
        signal="SELL",
        candles_used=100,
    )


def _neutral_context():
    return TechnicalContext(
        symbol="XAUUSD",
        timeframe="M15",
        close=2300.0,
        ema20=2300.0,
        ema50=2300.0,
        rsi14=50.0,
        atr14=10.0,
        macd=0.0,
        macd_signal=0.0,
        macd_histogram=0.0,
        trend="Neutral",
        score=50,
        signal="WAIT",
        candles_used=100,
    )


def test_bullish_context_produces_buy_proposal():
    engine = AITradingDecisionEngine()

    decision = engine.evaluate(
        _bullish_context()
    )

    assert decision.direction == AIDirection.BUY
    assert decision.symbol == "XAUUSD"
    assert decision.timeframe == "M15"
    assert decision.technical_score == 75
    assert decision.trend == "Bullish"
    assert decision.signal == "BUY"

    assert decision.proposal is not None

    proposal = decision.proposal

    assert proposal.direction == AIDirection.BUY
    assert proposal.entry_price == 2300.0
    assert proposal.stop_loss == 2290.0
    assert proposal.take_profit == 2320.0
    assert proposal.risk_reward == 2.0

    assert proposal.execution_type == "paper"
    assert proposal.read_only is True
    assert proposal.broker_order_required is False
    assert proposal.risk_engine_required is True


def test_bearish_context_produces_sell_proposal():
    engine = AITradingDecisionEngine()

    decision = engine.evaluate(
        _bearish_context()
    )

    assert decision.direction == AIDirection.SELL
    assert decision.symbol == "XAUUSD"
    assert decision.technical_score == 25
    assert decision.trend == "Bearish"
    assert decision.signal == "SELL"

    assert decision.proposal is not None

    proposal = decision.proposal

    assert proposal.direction == AIDirection.SELL
    assert proposal.entry_price == 2300.0
    assert proposal.stop_loss == 2310.0
    assert proposal.take_profit == 2280.0
    assert proposal.risk_reward == 2.0

    assert proposal.execution_type == "paper"
    assert proposal.read_only is True
    assert proposal.broker_order_required is False
    assert proposal.risk_engine_required is True


def test_neutral_context_produces_wait():
    engine = AITradingDecisionEngine()

    decision = engine.evaluate(
        _neutral_context()
    )

    assert decision.direction == AIDirection.WAIT
    assert decision.proposal is None
    assert decision.signal == "WAIT"
    assert decision.trend == "Neutral"
    assert decision.read_only is True
    assert decision.broker_order_required is False
    assert decision.risk_engine_required is True


def test_misaligned_buy_signal_returns_wait():
    engine = AITradingDecisionEngine()

    context = TechnicalContext(
        symbol="XAUUSD",
        timeframe="M15",
        close=2300.0,
        ema20=2295.0,
        ema50=2285.0,
        rsi14=60.0,
        atr14=10.0,
        macd=5.0,
        macd_signal=3.0,
        macd_histogram=2.0,
        trend="Bearish",
        score=75,
        signal="BUY",
        candles_used=100,
    )

    decision = engine.evaluate(context)

    assert decision.direction == AIDirection.WAIT
    assert decision.proposal is None


def test_misaligned_sell_signal_returns_wait():
    engine = AITradingDecisionEngine()

    context = TechnicalContext(
        symbol="XAUUSD",
        timeframe="M15",
        close=2300.0,
        ema20=2305.0,
        ema50=2315.0,
        rsi14=40.0,
        atr14=10.0,
        macd=-5.0,
        macd_signal=-3.0,
        macd_histogram=-2.0,
        trend="Bullish",
        score=25,
        signal="SELL",
        candles_used=100,
    )

    decision = engine.evaluate(context)

    assert decision.direction == AIDirection.WAIT
    assert decision.proposal is None


def test_low_confidence_forces_wait():
    engine = AITradingDecisionEngine(
        AIDecisionConfig(
            minimum_confidence=95.0,
        )
    )

    decision = engine.evaluate(
        _bullish_context()
    )

    assert decision.direction == AIDirection.WAIT
    assert decision.proposal is None


def test_buy_requires_atr():
    engine = AITradingDecisionEngine()

    context = TechnicalContext(
        symbol="XAUUSD",
        timeframe="M15",
        close=2300.0,
        ema20=2295.0,
        ema50=2285.0,
        rsi14=60.0,
        atr14=None,
        macd=5.0,
        macd_signal=3.0,
        macd_histogram=2.0,
        trend="Bullish",
        score=75,
        signal="BUY",
        candles_used=100,
    )

    decision = engine.evaluate(context)

    assert decision.direction == AIDirection.WAIT
    assert decision.proposal is None
    assert "ATR" in decision.reasoning


def test_sell_requires_atr():
    engine = AITradingDecisionEngine()

    context = TechnicalContext(
        symbol="XAUUSD",
        timeframe="M15",
        close=2300.0,
        ema20=2305.0,
        ema50=2315.0,
        rsi14=40.0,
        atr14=None,
        macd=-5.0,
        macd_signal=-3.0,
        macd_histogram=-2.0,
        trend="Bearish",
        score=25,
        signal="SELL",
        candles_used=100,
    )

    decision = engine.evaluate(context)

    assert decision.direction == AIDirection.WAIT
    assert decision.proposal is None
    assert "ATR" in decision.reasoning


def test_risk_reward_meets_minimum():
    engine = AITradingDecisionEngine(
        AIDecisionConfig(
            minimum_risk_reward=1.5,
        )
    )

    decision = engine.evaluate(
        _bullish_context()
    )

    assert decision.proposal is not None
    assert (
        decision.proposal.risk_reward
        >= 1.5
    )


def test_serialization_contains_safety_flags():
    engine = AITradingDecisionEngine()

    decision = engine.evaluate(
        _bullish_context()
    )

    data = ai_decision_to_dict(
        decision
    )

    assert data["direction"] == "buy"
    assert data["symbol"] == "XAUUSD"
    assert data["timeframe"] == "M15"
    assert data["technical_score"] == 75

    assert data["execution_type"] == "paper"
    assert data["read_only"] is True
    assert data["broker_order_required"] is False
    assert data["risk_engine_required"] is True

    assert data["proposal"] is not None

    assert (
        data["proposal"]["direction"]
        == "buy"
    )

    assert (
        data["proposal"]["execution_type"]
        == "paper"
    )

    assert (
        data["proposal"]["broker_order_required"]
        is False
    )


def test_invalid_score_is_rejected():
    with pytest.raises(AIDecisionError):
        TechnicalContext(
            symbol="XAUUSD",
            timeframe="M15",
            close=2300.0,
            ema20=2295.0,
            ema50=2285.0,
            rsi14=60.0,
            atr14=10.0,
            macd=5.0,
            macd_signal=3.0,
            macd_histogram=2.0,
            trend="Bullish",
            score=101,
            signal="BUY",
            candles_used=100,
        ).validate()


def test_invalid_rsi_is_rejected():
    with pytest.raises(AIDecisionError):
        TechnicalContext(
            symbol="XAUUSD",
            timeframe="M15",
            close=2300.0,
            ema20=2295.0,
            ema50=2285.0,
            rsi14=101.0,
            atr14=10.0,
            macd=5.0,
            macd_signal=3.0,
            macd_histogram=2.0,
            trend="Bullish",
            score=75,
            signal="BUY",
            candles_used=100,
        ).validate()


def test_invalid_configuration_is_rejected():
    with pytest.raises(AIDecisionError):
        AITradingDecisionEngine(
            AIDecisionConfig(
                minimum_confidence=101.0,
            )
        )


def test_ai_never_requires_broker_order():
    engine = AITradingDecisionEngine()

    for context in (
        _bullish_context(),
        _bearish_context(),
        _neutral_context(),
    ):
        decision = engine.evaluate(
            context
        )

        assert (
            decision.broker_order_required
            is False
        )

        if decision.proposal is not None:
            assert (
                decision.proposal
                .broker_order_required
                is False
            )


def test_ai_always_requires_risk_engine():
    engine = AITradingDecisionEngine()

    for context in (
        _bullish_context(),
        _bearish_context(),
        _neutral_context(),
    ):
        decision = engine.evaluate(
            context
        )

        assert (
            decision.risk_engine_required
            is True
        )

        if decision.proposal is not None:
            assert (
                decision.proposal
                .risk_engine_required
                is True
            )
