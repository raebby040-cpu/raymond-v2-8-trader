"""
RAYMOND v2.8 - Advisory Brain Ensemble Tests

These tests verify the advisory layer only.

They do NOT execute trades.
They do NOT contact MT5.
They do NOT contact a broker.
They do NOT modify the existing Step 13 strategy.
"""

from __future__ import annotations

from backend.app.advisory_brains import (
    AdvisoryBrainEngine,
    analyze_advisory_brains,
    master_consensus,
)


class TestContext:
    """Simple context compatible with the advisory engine."""

    symbol = "XAUUSD"
    timeframe = "H1"

    close = 4329.125

    ema20 = 4350.0
    ema50 = 4400.0

    rsi14 = 42.0
    atr14 = 18.0

    macd = -5.0
    macd_signal = -2.0
    macd_histogram = -3.0

    trend = "Bearish"
    score = 35
    signal = "SELL"

    candles_used = 100

    volatility = "normal"

    previous_close = 4340.0

    market_regime = "trending_down"
    setup = "bearish_continuation"


def bearish_candles() -> list[dict]:
    """Create a small bearish continuation sequence."""

    return [
        {
            "open": 4380.0,
            "high": 4390.0,
            "low": 4360.0,
            "close": 4370.0,
            "volume": 100,
        },
        {
            "open": 4370.0,
            "high": 4380.0,
            "low": 4340.0,
            "close": 4350.0,
            "volume": 110,
        },
        {
            "open": 4350.0,
            "high": 4360.0,
            "low": 4320.0,
            "close": 4330.0,
            "volume": 120,
        },
        {
            "open": 4330.0,
            "high": 4340.0,
            "low": 4300.0,
            "close": 4310.0,
            "volume": 130,
        },
        {
            "open": 4310.0,
            "high": 4320.0,
            "low": 4280.0,
            "close": 4290.0,
            "volume": 140,
        },
        {
            "open": 4290.0,
            "high": 4300.0,
            "low": 4260.0,
            "close": 4270.0,
            "volume": 150,
        },
    ]


def bullish_context() -> TestContext:
    """Return a bullish version of the test context."""

    context = TestContext()

    context.ema20 = 4400.0
    context.ema50 = 4350.0

    context.rsi14 = 62.0

    context.macd = 5.0
    context.macd_signal = 2.0
    context.macd_histogram = 3.0

    context.trend = "Bullish"
    context.score = 75
    context.signal = "BUY"

    context.market_regime = "trending_up"
    context.setup = "bullish_continuation"

    return context


def neutral_context() -> TestContext:
    """Return a neutral/mixed context."""

    context = TestContext()

    context.ema20 = 4350.0
    context.ema50 = 4350.0

    context.rsi14 = 50.0

    context.macd = 0.0
    context.macd_signal = 0.0
    context.macd_histogram = 0.0

    context.trend = "Neutral"
    context.score = 50
    context.signal = "WAIT"

    context.market_regime = "uncertain"
    context.setup = "no_setup"

    return context


def test_engine_returns_eight_brains():
    engine = AdvisoryBrainEngine()

    result = engine.analyze(
        TestContext(),
        bearish_candles(),
    )

    assert len(result.brains) == 8

    names = {
        brain.name
        for brain in result.brains
    }

    expected = {
        "Trend Brain",
        "Momentum Brain",
        "Indicator Brain",
        "Price Action Brain",
        "Volatility Brain",
        "Structure Brain",
        "Entry / Setup Brain",
        "Risk / Regime Brain",
    }

    assert names == expected


def test_bearish_market_produces_bearish_master_bias():
    engine = AdvisoryBrainEngine()

    result = engine.analyze(
        TestContext(),
        bearish_candles(),
    )

    assert result.master_direction == "SELL"

    assert result.sell_votes > result.buy_votes

    assert result.master_confidence >= 50.0

    assert 0.0 <= result.agreement_percent <= 100.0


def test_bullish_market_produces_bullish_master_bias():
    engine = AdvisoryBrainEngine()

    result = engine.analyze(
        bullish_context(),
        [
            {
                "open": 4200.0,
                "high": 4230.0,
                "low": 4190.0,
                "close": 4220.0,
            },
            {
                "open": 4220.0,
                "high": 4250.0,
                "low": 4210.0,
                "close": 4240.0,
            },
            {
                "open": 4240.0,
                "high": 4280.0,
                "low": 4230.0,
                "close": 4270.0,
            },
            {
                "open": 4270.0,
                "high": 4310.0,
                "low": 4260.0,
                "close": 4300.0,
            },
            {
                "open": 4300.0,
                "high": 4350.0,
                "low": 4290.0,
                "close": 4340.0,
            },
            {
                "open": 4340.0,
                "high": 4390.0,
                "low": 4330.0,
                "close": 4380.0,
            },
        ],
    )

    assert result.master_direction == "BUY"

    assert result.buy_votes > result.sell_votes

    assert result.master_confidence >= 50.0


def test_neutral_market_does_not_force_strong_direction():
    engine = AdvisoryBrainEngine()

    result = engine.analyze(
        neutral_context(),
        [],
    )

    assert result.master_direction in {
        "BUY",
        "SELL",
        "WAIT",
    }

    assert 50.0 <= result.master_confidence <= 95.0

    assert (
        result.buy_votes
        + result.sell_votes
        + result.wait_votes
        == 8
    )


def test_each_brain_has_valid_direction():
    engine = AdvisoryBrainEngine()

    result = engine.analyze(
        TestContext(),
        bearish_candles(),
    )

    for brain in result.brains:
        assert brain.direction in {
            "BUY",
            "SELL",
            "WAIT",
        }

        assert 0.0 <= brain.confidence <= 100.0

        assert -100.0 <= brain.score <= 100.0

        assert brain.name

        assert brain.summary


def test_snapshot_serializes_to_json_friendly_dictionary():
    engine = AdvisoryBrainEngine()

    result = engine.analyze(
        TestContext(),
        bearish_candles(),
    )

    data = result.to_dict()

    assert isinstance(data, dict)

    assert "brains" in data

    assert "master" in data

    assert len(data["brains"]) == 8

    assert "direction" in data["master"]

    assert "confidence" in data["master"]

    assert "agreement_percent" in data["master"]


def test_convenience_function_returns_dictionary():
    data = analyze_advisory_brains(
        TestContext(),
        bearish_candles(),
    )

    assert isinstance(data, dict)

    assert "brains" in data

    assert "master" in data

    assert len(data["brains"]) == 8


def test_master_consensus_handles_empty_input():
    result = master_consensus([])

    assert result[0] == "WAIT"

    assert result[1] == 50.0

    assert result[2] == 0.0

    assert result[3] == 0

    assert result[4] == 0

    assert result[5] == 0


def test_advisory_layer_does_not_create_execution_fields():
    """
    Safety test.

    The advisory snapshot must remain analytical.
    """

    engine = AdvisoryBrainEngine()

    result = engine.analyze(
        TestContext(),
        bearish_candles(),
    )

    data = result.to_dict()

    assert "execution" not in data

    assert "order_id" not in data

    assert "broker_order" not in data

    assert "trade_id" not in data


def test_original_context_is_not_modified():
    context = TestContext()

    original = {
        "trend": context.trend,
        "signal": context.signal,
        "score": context.score,
        "market_regime": context.market_regime,
        "setup": context.setup,
    }

    engine = AdvisoryBrainEngine()

    engine.analyze(
        context,
        bearish_candles(),
    )

    assert context.trend == original["trend"]

    assert context.signal == original["signal"]

    assert context.score == original["score"]

    assert (
        context.market_regime
        == original["market_regime"]
    )

    assert context.setup == original["setup"]


if __name__ == "__main__":
    print(
        "RAYMOND v2.8 advisory brain tests "
        "loaded successfully."
    )
