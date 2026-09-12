"""
RAYMOND v2.8 - Backtest Engine Tests

Deterministic tests for the production backtesting engine.

These tests deliberately use a fake TradingPipelineService so the
backtest engine can be tested without invoking live broker services.

Safety coverage:
- insufficient historical data is rejected
- invalid candle values are rejected
- non-chronological candles are rejected
- symbol mismatch is rejected
- WAIT decisions do not create trades
- BUY decisions execute on the next candle open
- no look-ahead bias
- BUY stop-loss is respected
- BUY take-profit is respected
- stop-loss wins when both SL and TP are touched
- SELL stop-loss is respected
- SELL take-profit is respected
- SELL trades can produce positive P&L
- gap-through-SL execution uses the achievable candle open
- gap-through-TP execution uses the achievable candle open
- Risk Engine rejection prevents entry
- broker-aware position sizing is used
- open positions can be closed at end of data
- equity curve is generated
- performance metrics remain internally consistent
- invalid execution costs are rejected
- commission is charged on entry and exit
- execution costs reduce the result
- repeated backtests remain logically deterministic
- long-only trade mode permits BUY
- short-only trade mode permits SELL
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
):
    engine = make_engine(
        decisions=[decision],
        risk_engine=risk_engine,
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

    # Open below TP; TP is reached intrabar.
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


def test_stop_loss_wins_when_both_sl_and_tp_are_touched() -> None:
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

    trade = result.trades[0]

    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == pytest.approx(1990.0)
    assert trade["pnl"] < 0


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
        "low": 1999.0,
        "close": 2000.0,
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

    # Open above TP; TP is reached intrabar.
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

    trade = result.trades[0]

    assert trade["direction"] == "sell"
    assert trade["exit_reason"] == "take_profit"
    assert trade["pnl"] > 0


def test_buy_gap_through_stop_loss_uses_candle_open() -> None:
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
        "low": 1975.0,
        "close": 1978.0,
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
    assert trade["exit_price"] != pytest.approx(1990.0)


def test_sell_gap_through_stop_loss_uses_candle_open() -> None:
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
        "high": 2025.0,
        "low": 2019.0,
        "close": 2022.0,
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
    assert trade["exit_price"] != pytest.approx(2010.0)


def test_buy_gap_through_take_profit_uses_candle_open() -> None:
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
        "high": 2030.0,
        "low": 2024.0,
        "close": 2026.0,
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
    assert trade["exit_price"] != pytest.approx(2020.0)


def test_sell_gap_through_take_profit_uses_candle_open() -> None:
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
        "low": 1970.0,
        "close": 1974.0,
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
    assert trade["exit_price"] != pytest.approx(1980.0)


def test_risk_engine_rejection_prevents_entry() -> None:
    rejecting_engine = RejectingRiskEngine()

    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        ],
        risk_engine=rejecting_engine,
    )

    result = engine.run(
        candles=make_candles(55),
        specification=make_specification(),
    )

    assert result.status == "completed"
    assert result.total_trades == 0
    assert result.ending_balance == pytest.approx(10_000.0)


def test_position_sizing_uses_symbol_specification() -> None:
    risk_engine = RiskEngine()

    volume = risk_engine.calculate_position_size_from_symbol(
        equity=10_000.0,
        entry_price=2000.0,
        stop_loss_price=1990.0,
        specification=make_specification(),
    )

    assert volume > 0
    assert volume >= 0.01
    assert volume <= 100.0

    step_multiple = round(volume / 0.01)

    assert volume == pytest.approx(
        step_multiple * 0.01
    )


def test_open_position_is_closed_at_end_of_data() -> None:
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
        "high": 2005.0,
        "low": 1995.0,
        "close": 2003.0,
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
    assert result.trades[0]["exit_time"] == (
        "2026-01-01T00:51:00"
    )


def test_equity_curve_is_generated() -> None:
    engine = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(10)
        ],
    )

    result = engine.run(
        candles=make_candles(55),
        specification=make_specification(),
    )

    assert result.equity_curve
    assert len(result.equity_curve) >= 1

    for point in result.equity_curve:
        assert "balance" in point
        assert "equity" in point
        assert "drawdown" in point
        assert "drawdown_percent" in point


def test_metrics_are_consistent() -> None:
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

    assert result.total_trades == len(result.trades)

    assert (
        result.winning_trades
        + result.losing_trades
        + result.breakeven_trades
        == result.total_trades
    )

    if result.total_trades:
        expected_win_rate = (
            result.winning_trades
            / result.total_trades
            * 100
        )

        assert result.win_rate_percent == pytest.approx(
            expected_win_rate
        )

    assert result.net_profit == pytest.approx(
        result.ending_balance
        - result.starting_balance
    )

    if result.total_trades:
        expected_average = (
            sum(
                trade["pnl"]
                for trade in result.trades
            )
            / result.total_trades
        )

        assert result.average_trade == pytest.approx(
            expected_average
        )


def test_negative_spread_is_rejected() -> None:
    with pytest.raises(
        BacktestEngineError,
        match="spread",
    ):
        make_engine(
            decisions=[make_wait_decision()],
            spread=-0.01,
        )


def test_negative_slippage_is_rejected() -> None:
    with pytest.raises(
        BacktestEngineError,
        match="slippage",
    ):
        make_engine(
            decisions=[make_wait_decision()],
            slippage=-0.01,
        )


def test_negative_commission_is_rejected() -> None:
    with pytest.raises(
        BacktestEngineError,
        match="commission",
    ):
        make_engine(
            decisions=[make_wait_decision()],
            commission_per_unit=-0.01,
        )


def test_commission_is_charged_on_entry_and_exit() -> None:
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
        "high": 2005.0,
        "low": 1995.0,
        "close": 2003.0,
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

    trade = result.trades[0]

    assert trade["execution_cost"] > 0
    assert result.total_execution_cost == pytest.approx(
        trade["execution_cost"]
    )


def test_execution_costs_reduce_result() -> None:
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
        "high": 2005.0,
        "low": 1995.0,
        "close": 2003.0,
    }

    decision = make_buy_decision(
        entry=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
    )

    clean = run_single_buy(
        candles=candles,
        decision=decision,
    )

    costly = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
        spread=0.50,
        slippage=0.50,
        commission_per_unit=1.0,
    )

    assert clean.total_trades == 1
    assert costly.total_trades == 1

    assert costly.total_execution_cost > (
        clean.total_execution_cost
    )

    assert costly.ending_balance < (
        clean.ending_balance
    )


def test_repeated_backtests_are_deterministic() -> None:
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

    result_one = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
    )

    result_two = run_single_buy(
        candles=candles,
        decision=make_buy_decision(
            entry=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
        ),
    )

    assert result_one.status == result_two.status
    assert result_one.start_time == result_two.start_time
    assert result_one.end_time == result_two.end_time
    assert result_one.starting_balance == pytest.approx(
        result_two.starting_balance
    )
    assert result_one.ending_balance == pytest.approx(
        result_two.ending_balance
    )
    assert result_one.net_profit == pytest.approx(
        result_two.net_profit
    )
    assert result_one.net_profit_percent == pytest.approx(
        result_two.net_profit_percent
    )
    assert result_one.total_trades == result_two.total_trades
    assert result_one.winning_trades == result_two.winning_trades
    assert result_one.losing_trades == result_two.losing_trades
    assert result_one.breakeven_trades == (
        result_two.breakeven_trades
    )
    assert result_one.win_rate_percent == pytest.approx(
        result_two.win_rate_percent
    )
    assert result_one.gross_profit == pytest.approx(
        result_two.gross_profit
    )
    assert result_one.gross_loss == pytest.approx(
        result_two.gross_loss
    )
    assert result_one.total_execution_cost == pytest.approx(
        result_two.total_execution_cost
    )
    assert result_one.max_drawdown == pytest.approx(
        result_two.max_drawdown
    )
    assert result_one.max_drawdown_percent == pytest.approx(
        result_two.max_drawdown_percent
    )

    assert len(result_one.trades) == len(result_two.trades)

    for first, second in zip(
        result_one.trades,
        result_two.trades,
    ):
        first_without_id = dict(first)
        second_without_id = dict(second)

        first_without_id.pop("trade_id", None)
        second_without_id.pop("trade_id", None)

        assert first_without_id == second_without_id

    if result_one.trades:
        assert result_one.trades[0]["trade_id"] != (
            result_two.trades[0]["trade_id"]
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
        "low": 2019.0,
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
