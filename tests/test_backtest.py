"""
RAYMOND v2.8 - Production Backtest Engine Tests

Tests the canonical app.backtest_engine implementation.

Safety contract:
- historical candles only
- deterministic simulated execution
- AI decisions remain paper/read-only
- Risk Engine remains authoritative
- no MT5 broker orders
- no live trading
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pytest

from app.ai_trading_decision import (
    AIDecision,
    AIDirection,
    AITradeProposal,
)
from app.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestEngineError,
)
from app.risk_engine import RiskEngine, SymbolSpecification


def make_specification(
    *,
    symbol: str = "XAUUSD",
) -> SymbolSpecification:
    return SymbolSpecification(
        symbol=symbol,
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=0.1,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        volume_limit=100.0,
        trade_mode=RiskEngine.TRADE_MODE_FULL,
        trade_execution_mode=0,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="USD",
        spread=0,
        spread_float=True,
    )


def make_candles(
    count: int,
    *,
    start_price: float = 2000.0,
) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []

    for index in range(count):
        price = start_price + (index * 0.10)

        candles.append(
            {
                "time": (
                    f"2026-01-01T{index // 60:02d}:"
                    f"{index % 60:02d}:00"
                ),
                "open": price,
                "high": price + 0.50,
                "low": price - 0.50,
                "close": price + 0.05,
            }
        )

    return candles


def make_buy_decision(
    *,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> AIDecision:
    proposal = AITradeProposal(
        direction=AIDirection.BUY,
        symbol="XAUUSD",
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=(
            abs(take_profit - entry)
            / abs(entry - stop_loss)
        ),
        confidence=80.0,
        reason="test BUY",
        execution_type="paper",
        read_only=True,
        broker_order_required=False,
        risk_engine_required=True,
    )

    return AIDecision(
        direction=AIDirection.BUY,
        symbol="XAUUSD",
        timeframe="H1",
        confidence=80.0,
        technical_score=80,
        trend="Bullish",
        signal="BUY",
        proposal=proposal,
        reasoning="test BUY",
    )


def make_sell_decision(
    *,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> AIDecision:
    proposal = AITradeProposal(
        direction=AIDirection.SELL,
        symbol="XAUUSD",
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=(
            abs(take_profit - entry)
            / abs(entry - stop_loss)
        ),
        confidence=80.0,
        reason="test SELL",
        execution_type="paper",
        read_only=True,
        broker_order_required=False,
        risk_engine_required=True,
    )

    return AIDecision(
        direction=AIDirection.SELL,
        symbol="XAUUSD",
        timeframe="H1",
        confidence=80.0,
        technical_score=20,
        trend="Bearish",
        signal="SELL",
        proposal=proposal,
        reasoning="test SELL",
    )


def make_wait_decision() -> AIDecision:
    return AIDecision(
        direction=AIDirection.WAIT,
        symbol="XAUUSD",
        timeframe="H1",
        confidence=50.0,
        technical_score=50,
        trend="Neutral",
        signal="WAIT",
        proposal=None,
        reasoning="test WAIT",
    )


class FakePipeline:
    """Minimal deterministic replacement for the production pipeline."""

    def __init__(
        self,
        decisions: Sequence[AIDecision],
    ) -> None:
        self.ai_engine = object()
        self.risk_engine = RiskEngine()
        self.decisions = list(decisions)
        self.calls: list[list[Mapping[str, Any]]] = []

    def evaluate_decision(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: Sequence[Mapping[str, Any]],
    ) -> AIDecision:
        self.calls.append(list(candles))

        if not self.decisions:
            return make_wait_decision()

        return self.decisions.pop(0)


def make_engine(
    *,
    decisions: Sequence[AIDecision],
    starting_balance: float = 10_000.0,
    spread: float = 0.0,
    slippage: float = 0.0,
    commission_per_unit: float = 0.0,
) -> tuple[BacktestEngine, FakePipeline]:
    pipeline = FakePipeline(decisions)

    engine = BacktestEngine(
        config=BacktestConfig(
            symbol="XAUUSD",
            timeframe="H1",
            starting_balance=starting_balance,
            warmup_candles=50,
            spread=spread,
            slippage=slippage,
            commission_per_unit=commission_per_unit,
        ),
        pipeline_service=pipeline,
    )

    return engine, pipeline


def test_rejects_insufficient_candles() -> None:
    engine, _ = make_engine(
        decisions=[make_wait_decision()],
    )

    with pytest.raises(
        BacktestEngineError,
        match="Insufficient",
    ):
        engine.run(
            candles=make_candles(50),
            specification=make_specification(),
        )


def test_rejects_invalid_candle_values() -> None:
    engine, _ = make_engine(
        decisions=[make_wait_decision()],
    )

    candles = make_candles(51)
    candles[10]["high"] = float("nan")

    with pytest.raises(BacktestEngineError):
        engine.run(
            candles=candles,
            specification=make_specification(),
        )


def test_rejects_non_chronological_candles() -> None:
    engine, _ = make_engine(
        decisions=[make_wait_decision()],
    )

    candles = make_candles(51)
    candles[25]["time"] = candles[24]["time"]

    with pytest.raises(BacktestEngineError):
        engine.run(
            candles=candles,
            specification=make_specification(),
        )


def test_rejects_symbol_specification_mismatch() -> None:
    engine, _ = make_engine(
        decisions=[make_wait_decision()],
    )

    with pytest.raises(
        BacktestEngineError,
        match="Symbol specification",
    ):
        engine.run(
            candles=make_candles(51),
            specification=make_specification(
                symbol="EURUSD",
            ),
        )


def test_wait_decision_creates_no_trade() -> None:
    engine, _ = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(20)
        ],
    )

    result = engine.run(
        candles=make_candles(70),
        specification=make_specification(),
    )

    assert result.status == "completed"
    assert result.total_trades == 0
    assert result.winning_trades == 0
    assert result.losing_trades == 0
    assert result.breakeven_trades == 0
    assert result.net_profit == pytest.approx(0.0)


def test_pipeline_receives_only_available_history() -> None:
    engine, pipeline = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(20)
        ],
    )

    candles = make_candles(55)

    engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert pipeline.calls

    for index, call in enumerate(pipeline.calls):
        expected_length = 51 + index

        assert len(call) == expected_length
        assert call == candles[:expected_length]


def test_buy_entry_uses_next_candle_open() -> None:
    candles = make_candles(52)

    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2001.0,
        "low": 1999.0,
        "close": 2000.0,
    }

    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2010.0,
        "high": 2011.0,
        "low": 2009.0,
        "close": 2010.0,
    }

    engine, _ = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        ],
    )

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["entry_price"] == pytest.approx(2010.0)
    assert trade["signal_price"] == pytest.approx(2000.0)
    assert trade["entry_time"] == "2026-01-01T00:51:00"
    assert trade["exit_reason"] == "end_of_data"


def test_buy_stop_loss_is_respected() -> None:
    candles = make_candles(53)

    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2001.0,
        "low": 1999.0,
        "close": 2000.0,
    }

    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2000.0,
        "high": 2001.0,
        "low": 1999.0,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 2000.0,
        "high": 2001.0,
        "low": 1989.0,
        "close": 1990.0,
    }

    engine, _ = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        ],
    )

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == pytest.approx(1990.0)
    assert trade["pnl"] < 0


def test_buy_take_profit_is_respected() -> None:
    candles = make_candles(53)

    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2001.0,
        "low": 1999.0,
        "close": 2000.0,
    }

    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2000.0,
        "high": 2001.0,
        "low": 1999.0,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 2000.0,
        "high": 2021.0,
        "low": 1999.0,
        "close": 2020.0,
    }

    engine, _ = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        ],
    )

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["exit_reason"] == "take_profit"
    assert trade["exit_price"] == pytest.approx(2020.0)
    assert trade["pnl"] > 0


def test_backtest_has_no_live_execution_permissions() -> None:
    engine, _ = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        ],
    )

    result = engine.run(
        candles=make_candles(55),
        specification=make_specification(),
    )

    assert result.status == "completed"

    for trade in result.trades:
        assert trade["execution_type"] == "paper"
        assert trade["live_trading_enabled"] is False
        assert trade["broker_order_required"] is False
        assert trade["read_only"] is True
