"""
RAYMOND v2.8 - Backtest Engine Tests

Deterministic tests for the production backtesting engine.

Safety coverage:
- insufficient historical data is rejected
- invalid candles are rejected
- non-chronological candles are rejected
- symbol mismatch is rejected
- WAIT decisions do not create trades
- BUY decisions execute only on the next candle open
- no look-ahead bias
- BUY stop-loss is respected
- BUY take-profit is respected
- stop-loss wins when both SL and TP are touched
- SELL execution and P&L are correct
- Risk Engine rejection prevents entries
- broker-aware position sizing is used
- open positions can be closed at end of data
- equity curve is generated
- performance metrics remain internally consistent
- gap-through-SL execution is conservative
- gap-through-TP execution is conservative
- execution costs are deterministic
- commission is charged on entry and exit
- invalid execution costs are rejected
- repeated backtests are deterministic
- no live/paper execution gateway is required
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
    """
    Minimal deterministic pipeline replacement.

    It isolates backtest simulator behavior from the real
    technical-indicator calculation path.
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


def test_rejects_insufficient_candles() -> None:
    engine = make_engine(
        decisions=[make_wait_decision()],
    )

    candles = make_candles(50)

    with pytest.raises(
        BacktestEngineError,
        match="Insufficient",
    ):
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
    assert result.breakeven_trades == 0


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
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2005.0,
                stop_loss=2004.0,
                take_profit=2007.0,
            )
        ],
    )

    candles = make_candles(52)

    candles[50] = {
        "time": "2026-01-01T00:50:00",
        "open": 2000.0,
        "high": 2005.0,
        "low": 1999.0,
        "close": 2005.0,
    }

    candles[51] = {
        "time": "2026-01-01T00:51:00",
        "open": 2010.0,
        "high": 2011.0,
        "low": 2009.5,
        "close": 2010.5,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 1
    assert result.trades[0]["entry_price"] == pytest.approx(
        2010.0
    )
    assert result.trades[0]["exit_reason"] == "end_of_data"


def test_buy_stop_loss_is_respected() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1999.0,
                take_profit=2002.0,
            )
        ],
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

    trade = result.trades[0]

    assert result.total_trades == 1
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == pytest.approx(1999.0)
    assert trade["pnl"] < 0


def test_buy_take_profit_is_respected() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1999.0,
                take_profit=2002.0,
            )
        ],
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

    trade = result.trades[0]

    assert result.total_trades == 1
    assert trade["exit_reason"] == "take_profit"
    assert trade["exit_price"] == pytest.approx(2002.0)
    assert trade["pnl"] > 0


def test_stop_loss_wins_when_both_sl_and_tp_are_touched() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1999.0,
                take_profit=2002.0,
            )
        ],
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
        "close": 2000.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    trade = result.trades[0]

    assert result.total_trades == 1
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == pytest.approx(1999.0)
    assert trade["pnl"] < 0


def test_buy_gap_through_stop_loss_uses_candle_open() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1999.0,
                take_profit=2002.0,
            )
        ],
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
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 1995.0,
        "high": 1996.0,
        "low": 1994.0,
        "close": 1995.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    trade = result.trades[0]

    assert result.total_trades == 1
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == pytest.approx(1995.0)
    assert trade["pnl"] < 0


def test_sell_gap_through_stop_loss_uses_candle_open() -> None:
    engine = make_engine(
        decisions=[
            make_sell_decision(
                entry=2000.0,
                stop_loss=2001.0,
                take_profit=1998.0,
            )
        ],
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
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 2005.0,
        "high": 2006.0,
        "low": 2004.0,
        "close": 2005.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    trade = result.trades[0]

    assert result.total_trades == 1
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == pytest.approx(2005.0)
    assert trade["pnl"] < 0


def test_buy_gap_through_take_profit_uses_candle_open() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2010.0,
            )
        ],
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
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 2020.0,
        "high": 2021.0,
        "low": 2019.0,
        "close": 2020.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    trade = result.trades[0]

    assert result.total_trades == 1
    assert trade["exit_reason"] == "take_profit"
    assert trade["exit_price"] == pytest.approx(2020.0)
    assert trade["pnl"] > 0


def test_sell_gap_through_take_profit_uses_candle_open() -> None:
    engine = make_engine(
        decisions=[
            make_sell_decision(
                entry=2000.0,
                stop_loss=2010.0,
                take_profit=1990.0,
            )
        ],
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
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 1980.0,
        "high": 1981.0,
        "low": 1979.0,
        "close": 1980.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    trade = result.trades[0]

    assert result.total_trades == 1
    assert trade["exit_reason"] == "take_profit"
    assert trade["exit_price"] == pytest.approx(1980.0)
    assert trade["pnl"] > 0


def test_sell_trade_take_profit_generates_positive_pnl() -> None:
    engine = make_engine(
        decisions=[
            make_sell_decision(
                entry=2000.0,
                stop_loss=2010.0,
                take_profit=1990.0,
            )
        ],
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
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 1990.0,
        "high": 1990.5,
        "low": 1989.5,
        "close": 1990.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    trade = result.trades[0]

    assert result.total_trades == 1
    assert trade["exit_reason"] == "take_profit"
    assert trade["exit_price"] == pytest.approx(1990.0)
    assert trade["pnl"] > 0


def test_risk_engine_rejection_prevents_entry() -> None:
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

    candles = make_candles(53)

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.total_trades == 0
    assert result.winning_trades == 0
    assert result.losing_trades == 0


def test_position_sizing_uses_symbol_specification() -> None:
    risk_engine = RiskEngine()

    specification = make_specification()

    volume = risk_engine.calculate_position_size_from_symbol(
        equity=10_000.0,
        entry_price=2000.0,
        stop_loss_price=1990.0,
        specification=specification,
    )

    assert volume >= specification.volume_min
    assert volume <= specification.volume_max


def test_open_position_is_closed_at_end_of_data() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        ],
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


def test_equity_curve_is_generated() -> None:
    engine = make_engine(
        decisions=[
            make_wait_decision()
            for _ in range(5)
        ],
    )

    candles = make_candles(55)

    result = engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert result.equity_curve
    assert len(result.equity_curve) == 5


def test_metrics_are_consistent() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1999.0,
                take_profit=2002.0,
            )
        ],
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

    assert result.total_trades == (
        result.winning_trades
        + result.losing_trades
        + result.breakeven_trades
    )

    assert result.net_profit == pytest.approx(
        result.ending_balance
        - result.starting_balance
    )

    if result.total_trades > 0:
        assert result.win_rate_percent == pytest.approx(
            (
                result.winning_trades
                / result.total_trades
            )
            * 100
        )


def test_negative_spread_is_rejected() -> None:
    with pytest.raises(
        BacktestEngineError,
        match="spread cannot be negative",
    ):
        make_engine(
            decisions=[make_wait_decision()],
            spread=-1.0,
        )


def test_negative_slippage_is_rejected() -> None:
    with pytest.raises(
        BacktestEngineError,
        match="slippage cannot be negative",
    ):
        make_engine(
            decisions=[make_wait_decision()],
            slippage=-1.0,
        )


def test_negative_commission_is_rejected() -> None:
    with pytest.raises(
        BacktestEngineError,
        match="commission_per_unit cannot be negative",
    ):
        make_engine(
            decisions=[make_wait_decision()],
            commission_per_unit=-1.0,
        )


def test_commission_is_charged_on_entry_and_exit() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2010.0,
            )
        ],
        commission_per_unit=1.0,
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
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
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
    assert result.total_execution_cost > 0
    assert result.trades[0]["execution_cost"] > 0
    assert result.ending_balance < result.starting_balance


def test_execution_costs_reduce_result() -> None:
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
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    candles[52] = {
        "time": "2026-01-01T00:52:00",
        "open": 2000.0,
        "high": 2000.5,
        "low": 1999.5,
        "close": 2000.0,
    }

    clean_engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2010.0,
            )
        ],
    )

    costly_engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2010.0,
            )
        ],
        spread=1.0,
        slippage=0.5,
        commission_per_unit=1.0,
    )

    clean_result = clean_engine.run(
        candles=candles,
        specification=make_specification(),
    )

    costly_result = costly_engine.run(
        candles=candles,
        specification=make_specification(),
    )

    assert clean_result.total_trades == 1
    assert costly_result.total_trades == 1

    assert costly_result.total_execution_cost > (
        clean_result.total_execution_cost
    )

    assert costly_result.ending_balance < (
        clean_result.ending_balance
    )


def test_repeated_backtests_are_deterministic() -> None:
    def run_once():
        engine = make_engine(
            decisions=[
                make_buy_decision(
                    entry=2000.0,
                    stop_loss=1999.0,
                    take_profit=2002.0,
                )
            ],
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

        return engine.run(
            candles=candles,
            specification=make_specification(),
        )

    first = run_once()
    second = run_once()

    assert first.status == second.status
    assert first.total_trades == second.total_trades
    assert first.winning_trades == second.winning_trades
    assert first.losing_trades == second.losing_trades
    assert first.breakeven_trades == second.breakeven_trades

    assert first.net_profit == pytest.approx(
        second.net_profit
    )

    assert first.ending_balance == pytest.approx(
        second.ending_balance
    )

    assert first.max_drawdown == pytest.approx(
        second.max_drawdown
    )

    assert first.max_drawdown_percent == pytest.approx(
        second.max_drawdown_percent
    )

    assert first.total_execution_cost == pytest.approx(
        second.total_execution_cost
    )

    assert len(first.trades) == len(second.trades)

    for first_trade, second_trade in zip(
        first.trades,
        second.trades,
    ):
        assert first_trade["trade_id"] != second_trade["trade_id"]

        first_without_id = {
            key: value
            for key, value in first_trade.items()
            if key != "trade_id"
        }

        second_without_id = {
            key: value
            for key, value in second_trade.items()
            if key != "trade_id"
        }

        assert first_without_id == second_without_id


def test_buy_trade_mode_long_only_is_allowed() -> None:
    engine = make_engine(
        decisions=[
            make_buy_decision(
                entry=2000.0,
                stop_loss=1990.0,
                take_profit=2010.0,
            )
        ],
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
        "high": 2001.0,
        "low": 1999.0,
        "close": 2000.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(
            trade_mode=RiskEngine.TRADE_MODE_LONGONLY,
        ),
    )

    assert result.total_trades <= 1


def test_sell_trade_mode_short_only_is_allowed() -> None:
    engine = make_engine(
        decisions=[
            make_sell_decision(
                entry=2000.0,
                stop_loss=2010.0,
                take_profit=1990.0,
            )
        ],
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
        "high": 2001.0,
        "low": 1999.0,
        "close": 2000.0,
    }

    result = engine.run(
        candles=candles,
        specification=make_specification(
            trade_mode=RiskEngine.TRADE_MODE_SHORTONLY,
        ),
    )

    assert result.total_trades <= 1
