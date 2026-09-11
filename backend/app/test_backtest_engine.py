"""
RAYMOND v2.8 - Backtest Engine Tests

Deterministic tests for the production backtesting engine.

Safety coverage:
- insufficient historical data is rejected
- invalid candles are rejected
- symbol mismatch is rejected
- WAIT decisions do not create trades
- BUY/SELL decisions execute only on the next candle open
- stop-loss is preferred when SL and TP are both touched
- Risk Engine rejection prevents entries
- broker-aware position sizing is used
- open positions can be closed at end of data
- no live/paper execution gateway is required
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pytest

from app.ai_trading_decision import (
    AIDirection,
    AIDecision,
    AITradeProposal,
)
from app.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestEngineError,
)
from app.risk_engine import (
    RiskDecision,
    RiskEngine,
    RiskEngineError,
    SymbolSpecification,
)


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
        contract_size=1.0,
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
    timestamps: bool = True,
) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []

    for index in range(count):
        price = start_price + (index * 0.10)

        candle: dict[str, Any] = {
            "open": price,
            "high": price + 0.50,
            "low": price - 0.50,
            "close": price + 0.05,
        }

        if timestamps:
            candle["time"] = (
                f"2026-01-01T{index // 60:02d}:"
                f"{index % 60:02d}:00"
            )

        candles.append(candle)

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
        confidence=50.0,
        technical_score=50,
        trend="Neutral",
        signal="WAIT",
        proposal=None,
        reasoning="test WAIT",
    )


class FakePipeline:
    """
    Minimal deterministic pipeline replacement.

    It allows the backtest tests to isolate simulator behavior
    without depending on market-indicator calculations.
    """

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


class RejectingRiskEngine(RiskEngine):
    """Risk engine that deterministically rejects every entry."""

    def pre_trade_check(
        self,
        *,
        equity: float,
        daily_loss: float,
        open_positions: int,
        current_exposure: float,
        proposed_exposure: float,
        entry_price: float,
        stop_loss_price: float | None,
        take_profit_price: float | None,
        volume: float,
        side: str,
        specification: SymbolSpecification,
        existing_direction_volume: float = 0.0,
    ) -> RiskDecision:
        return RiskDecision(
            allowed=False,
            reason="test risk rejection",
            risk_amount=self.risk_amount(equity),
            daily_loss_limit=self.daily_loss_limit(equity),
            total_exposure_limit=self.total_exposure_limit(
                equity
            ),
            proposed_exposure=proposed_exposure,
            open_positions=open_positions,
        )


class FakePipelineWithRisk(FakePipeline):
    def __init__(
        self,
        decisions: Sequence[AIDecision],
        risk_engine: RiskEngine,
    ) -> None:
        super().__init__(decisions)
        self.risk_engine = risk_engine


def make_engine(
    *,
    decisions: Sequence[AIDecision],
    risk_engine: RiskEngine | None = None,
    starting_balance: float = 10_000.0,
) -> BacktestEngine:
    pipeline = FakePipelineWithRisk(
        decisions,
        risk_engine or RiskEngine(),
    )

    return BacktestEngine(
        config=BacktestConfig(
            symbol="XAUUSD",
            timeframe="H1",
            starting_balance=starting_balance,
            warmup_candles=50,
        ),
        pipeline_service=pipeline,
    )


def test_rejects_insufficient_candles() -> None:
    engine = make_engine(
        decisions=[make_wait_decision()],
    )

    candles = make_candles(50)

    with pytest.raises(BacktestEngineError, match="Insufficient"):
        engine.run(
            candles=candles,
            specification=make_specification(),
        )


def test_rejects_invalid_candle_values() -> None:
    engine = make_engine(
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
    engine = make_engine(
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
    engine = make_engine(
        decisions=[make_wait_decision()],
    )

    candles = make_candles(51)

    with pytest.raises(
        BacktestEngineError,
        match="Symbol specification",
    ):
        engine.run(
            candles=candles,
            specification=make_specification(
                symbol="EURUSD",
            ),
        )


def test_wait_decision_creates_no_trade() -> None:
    engine = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(10)
        ],
    )

    candles = make_candles(60)

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.status == "completed"
    assert result.total_trades == 0
    assert result.winning_trades == 0
    assert result.losing_trades == 0


def test_signal_uses_only_past_and_current_candles() -> None:
    pipeline = FakePipelineWithRisk(
        [
            make_wait_decision()
            for _ in range(20)
        ],
        RiskEngine(),
    )

    engine = BacktestEngine(
        config=BacktestConfig(
            symbol="XAUUSD",
            timeframe="H1",
            starting_balance=10_000.0,
            warmup_candles=50,
        ),
        pipeline_service=pipeline,
    )

    candles = make_candles(55)

    engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert pipeline.calls

    first_call = pipeline.calls[0]

    assert len(first_call) == 51

    assert first_call == candles[:51]


def test_buy_entry_occurs_on_next_candle_open() -> None:
    decisions = [
        make_buy_decision(
            entry=2005.0,
            stop_loss=2004.0,
            take_profit=2007.0,
        )
    ]

    engine = make_engine(
        decisions=decisions,
    )

    candles = make_candles(52)

    # Signal candle.
    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2005.0,
        "low": 1999.0,
        "close": 2005.0,
    }

    # Next candle is deliberately different.
    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2010.0,
        "high": 2011.0,
        "low": 2009.0,
        "close": 2010.5,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    # With only one signal candle and no later candle after the
    # entry candle, the open position is closed at end of data.
    assert result.total_trades == 1
    assert result.trades[0]["entry_price"] == pytest.approx(
        2010.0
    )


def test_buy_stop_loss_is_respected() -> None:
    decisions = [
        make_buy_decision(
            entry=2000.0,
            stop_loss=1999.0,
            take_profit=2002.0,
        )
    ]

    engine = make_engine(
        decisions=decisions,
    )

    candles = make_candles(53)

    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2001.0,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2000.0,
        "high": 2000.5,
        "low": 1998.5,
        "close": 1999.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 1999.0,
        "high": 1999.5,
        "low": 1998.5,
        "close": 1999.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1
    assert result.trades[0]["exit_reason"] == "stop_loss"
    assert result.trades[0]["pnl"] < 0


def test_buy_take_profit_is_respected() -> None:
    decisions = [
        make_buy_decision(
            entry=2000.0,
            stop_loss=1999.0,
            take_profit=2002.0,
        )
    ]

    engine = make_engine(
        decisions=decisions,
    )

    candles = make_candles(53)

    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2000.0,
        "high": 2003.0,
        "low": 1999.5,
        "close": 2002.5,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 2002.5,
        "high": 2003.0,
        "low": 2002.0,
        "close": 2002.5,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1
    assert result.trades[0]["exit_reason"] == "take_profit"
    assert result.trades[0]["pnl"] > 0


def test_stop_loss_wins_when_both_sl_and_tp_are_touched() -> None:
    decisions = [
        make_buy_decision(
            entry=2000.0,
            stop_loss=1999.0,
            take_profit=2002.0,
        )
    ]

    engine = make_engine(
        decisions=decisions,
    )

    candles = make_candles(52)

    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2000.0,
        "high": 2003.0,
        "low": 1998.0,
        "close": 2001.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1
    assert result.trades[0]["exit_reason"] == "stop_loss"
    assert result.trades[0]["pnl"] < 0


def test_risk_rejection_prevents_trade() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1999.0,
                take_profit=2002.0,
            )
        ],
        risk_engine=RejectingRiskEngine(),
    )

    candles = make_candles(55)

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 0


def test_position_size_is_calculated_from_symbol_specification() -> None:
    decisions = [
        make_buy_decision(
            entry=2000.0,
            stop_loss=1999.0,
            take_profit=2002.0,
        )
    ]

    engine = make_engine(
        decisions=decisions,
        starting_balance=10_000.0,
    )

    candles = make_candles(52)

    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2000.0,
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["position_size"] > 0


def test_open_position_can_be_closed_at_end_of_data() -> None:
    decisions = [
        make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        )
    ]

    engine = make_engine(
        decisions=decisions,
    )

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
        "open": 2005.0,
        "high": 2006.0,
        "low": 2004.0,
        "close": 2005.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1
    assert result.trades[0]["exit_reason"] == "end_of_data"


def test_result_contains_equity_curve() -> None:
    engine = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(10)
        ],
    )

    candles = make_candles(60)

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.equity_curve
    assert result.bars_processed == 60
    assert result.starting_balance == pytest.approx(
        10_000.0
    )
    assert result.ending_balance == pytest.approx(
        10_000.0
    )


def test_result_metrics_are_consistent() -> None:
    engine = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(10)
        ],
    )

    candles = make_candles(60)

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.net_profit == pytest.approx(
        result.ending_balance
        - result.starting_balance
    )

    assert result.total_trades == (
        result.winning_trades
        + result.losing_trades
        + result.breakeven_trades
    )

    if result.total_trades == 0:
        assert result.win_rate_percent == 0.0
