"""
RAYMOND v2.8 - Backtest Engine Tests

Deterministic tests for the production backtesting engine.
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
from app.risk_engine import (
    RiskDecision,
    RiskEngine,
    SymbolSpecification,
)


def make_specification(
    *,
    symbol: str = "XAUUSD",
    trade_mode: int | None = None,
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
        trade_mode=(
            RiskEngine.TRADE_MODE_FULL
            if trade_mode is None
            else trade_mode
        ),
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
    """Minimal deterministic pipeline replacement."""

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
            total_exposure_limit=self.total_exposure_limit(equity),
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
    spread: float = 0.0,
    slippage: float = 0.0,
    commission_per_unit: float = 0.0,
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
            spread=spread,
            slippage=slippage,
            commission_per_unit=commission_per_unit,
        ),
        pipeline_service=pipeline,
    )


def run_single_buy(
    *,
    candles: list[dict[str, Any]],
    decision: AIDecision,
    risk_engine: RiskEngine | None = None,
    spread: float = 0.0,
    slippage: float = 0.0,
    commission_per_unit: float = 0.0,
):
    engine = make_engine(
        decisions=[decision],
        risk_engine=risk_engine,
        spread=spread,
        slippage=slippage,
        commission_per_unit=commission_per_unit,
    )

    return engine.run(
        candles=candles,
        specification=make_specification(),
    )


def run_single_sell(
    *,
    candles: list[dict[str, Any]],
    decision: AIDecision,
    risk_engine: RiskEngine | None = None,
    spread: float = 0.0,
    slippage: float = 0.0,
    commission_per_unit: float = 0.0,
):
    engine = make_engine(
        decisions=[decision],
        risk_engine=risk_engine,
        spread=spread,
        slippage=slippage,
        commission_per_unit=commission_per_unit,
    )

    return engine.run(
        candles=candles,
        specification=make_specification(),
    )


def test_rejects_insufficient_candles() -> None:
    engine = make_engine(
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
    engine = make_engine(
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
    assert pipeline.calls[0] == candles[:51]
    assert len(pipeline.calls[0]) == 51

    for call_index, call in enumerate(pipeline.calls):
        assert len(call) == 51 + call_index
        assert call == candles[: 51 + call_index]


def test_buy_entry_occurs_on_next_candle_open() -> None:
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

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
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

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
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

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["exit_reason"] == "take_profit"
    assert trade["exit_price"] == pytest.approx(2020.0)
    assert trade["pnl"] > 0


def test_buy_stop_loss_has_priority_when_both_levels_are_hit() -> None:
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
        "low": 1989.0,
        "close": 2000.0,
    }

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
    )

    assert result.total_trades == 1
    assert result.trades[0]["exit_reason"] == "stop_loss"


def test_sell_stop_loss_is_respected() -> None:
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
        "high": 2011.0,
        "low": 1989.0,
        "close": 2010.0,
    }

    result = run_single_sell(
        candles=candles,
        decision=make_sell_decision(
            entry=2000.0,
            stop_loss=2010.0,
            take_profit=1980.0,
        ),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == pytest.approx(2010.0)
    assert trade["pnl"] < 0


def test_sell_take_profit_is_respected() -> None:
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
        "low": 1979.0,
        "close": 1980.0,
    }

    result = run_single_sell(
        candles=candles,
        decision=make_sell_decision(
            entry=2000.0,
            stop_loss=2010.0,
            take_profit=1980.0,
        ),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["exit_reason"] == "take_profit"
    assert trade["exit_price"] == pytest.approx(1980.0)
    assert trade["pnl"] > 0


def test_sell_trade_take_profit_generates_positive_pnl() -> None:
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
        "low": 1979.0,
        "close": 1980.0,
    }

    result = run_single_sell(
        candles=candles,
        decision=make_sell_decision(
            entry=2000.0,
            stop_loss=2010.0,
            take_profit=1980.0,
        ),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["direction"] == "sell"
    assert trade["exit_reason"] == "take_profit"
    assert trade["exit_price"] == pytest.approx(1980.0)
    assert trade["pnl"] > 0


def test_buy_gap_through_stop_loss_is_respected() -> None:
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
        "open": 1980.0,
        "high": 1981.0,
        "low": 1979.0,
        "close": 1980.0,
    }

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
    )

    trade = result.trades[0]

    assert trade["exit_reason"] == "stop_loss_gap"
    assert trade["exit_price"] == pytest.approx(1980.0)
    assert trade["pnl"] < 0


def test_sell_gap_through_stop_loss_is_respected() -> None:
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
        "open": 2020.0,
        "high": 2021.0,
        "low": 2019.0,
        "close": 2020.0,
    }

    result = run_single_sell(
        candles=candles,
        decision=make_sell_decision(
            entry=2000.0,
            stop_loss=2010.0,
            take_profit=1980.0,
        ),
    )

    trade = result.trades[0]

    assert trade["exit_reason"] == "stop_loss_gap"
    assert trade["exit_price"] == pytest.approx(2020.0)
    assert trade["pnl"] < 0


def test_buy_gap_through_take_profit_is_respected() -> None:
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
        "open": 2025.0,
        "high": 2026.0,
        "low": 2024.0,
        "close": 2025.0,
    }

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
    )

    trade = result.trades[0]

    assert trade["exit_reason"] == "take_profit_gap"
    assert trade["exit_price"] == pytest.approx(2025.0)
    assert trade["pnl"] > 0


def test_sell_gap_through_take_profit_is_respected() -> None:
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
        "open": 1975.0,
        "high": 1976.0,
        "low": 1974.0,
        "close": 1975.0,
    }

    result = run_single_sell(
        candles=candles,
        decision=make_sell_decision(
            entry=2000.0,
            stop_loss=2010.0,
            take_profit=1980.0,
        ),
    )

    trade = result.trades[0]

    assert trade["exit_reason"] == "take_profit_gap"
    assert trade["exit_price"] == pytest.approx(1975.0)
    assert trade["pnl"] > 0


def test_risk_engine_rejection_prevents_entry() -> None:
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

    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        ],
        risk_engine=RejectingRiskEngine(),
    )

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 0


def test_position_sizing_is_positive_and_within_symbol_limits() -> None:
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

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
    )

    assert result.total_trades == 1

    trade = result.trades[0]

    assert trade["position_size"] > 0
    assert trade["position_size"] <= 100.0


def test_open_trade_is_closed_at_end_of_data() -> None:
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
        "open": 2000.0,
        "high": 2001.0,
        "low": 1999.0,
        "close": 2000.0,
    }

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
    )

    assert result.total_trades == 1
    assert result.trades[0]["exit_reason"] == "end_of_data"


def test_equity_curve_is_recorded() -> None:
    engine = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(10)
        ],
    )

    result = engine.run(
        candles=make_candles(60),
        specification=make_specification(),
    )

    assert result.equity_curve
    assert result.equity_curve[0]["equity"] == pytest.approx(10_000.0)


def test_metrics_are_consistent_for_no_trade_run() -> None:
    engine = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(20)
        ],
    )

    result = engine.run(
        candles=make_candles(70),
        specification=make_specification(),
    )

    assert result.total_trades == 0
    assert result.net_profit == pytest.approx(0.0)
    assert result.starting_balance == pytest.approx(10_000.0)
    assert result.ending_balance == pytest.approx(10_000.0)


def test_negative_execution_cost_reduces_profit() -> None:
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

    free_result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
        commission_per_unit=0.0,
    )

    costly_result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
        commission_per_unit=1.0,
    )

    assert costly_result.net_profit < free_result.net_profit


def test_commission_is_recorded_as_execution_cost() -> None:
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

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
        commission_per_unit=1.0,
    )

    assert result.total_trades == 1
    assert result.total_execution_cost > 0
    assert result.trades[0]["execution_cost"] > 0


def test_spread_and_slippage_are_reflected_in_result() -> None:
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

    result = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
        spread=0.10,
        slippage=0.10,
    )

    assert result.total_trades == 1
    assert result.total_execution_cost >= 0


def test_backtest_is_deterministic() -> None:
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

    decision1 = make_buy_decision(
        entry=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
    )

    decision2 = make_buy_decision(
        entry=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
    )

    result1 = run_single_buy(
        candles=candles,
        decision=decision1,
    )

    result2 = run_single_buy(
        candles=candles,
        decision=decision2,
    )

    assert result1.total_trades == result2.total_trades
    assert result1.net_profit == pytest.approx(result2.net_profit)
    assert result1.ending_balance == pytest.approx(
        result2.ending_balance
    )


def test_buy_trade_mode_long_only_is_allowed() -> None:
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
        "low": 1989.0,
        "close": 2020.0,
    }

    engine = make_engine(
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
        specification=make_specification(
            trade_mode=RiskEngine.TRADE_MODE_LONGONLY,
        ),
    )

    assert result.total_trades == 1
    assert result.trades[0]["direction"] == "buy"


def test_sell_trade_mode_short_only_is_allowed() -> None:
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
        "low": 1979.0,
        "close": 1980.0,
    }

    engine = make_engine(
        decisions=[
            make_sell_decision(
                entry=2000.0,
                stop_loss=2010.0,
                take_profit=1980.0,
            )
        ],
    )

    result = engine.run(
        candles=candles,
        specification=make_specification(
            trade_mode=RiskEngine.TRADE_MODE_SHORTONLY,
        ),
    )

    assert result.total_trades == 1
    assert result.trades[0]["direction"] == "sell"
