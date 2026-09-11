from __future__ import annotations

import math

import pytest

from app.demo_trading import (
    DemoTradingEngine,
    DemoTradingError,
)


def test_engine_starts_in_demo_mode() -> None:
    engine = DemoTradingEngine()

    status = engine.status()

    assert status["mode"] == "demo"
    assert status["execution_type"] == "paper"
    assert status["live_trading_enabled"] is False
    assert status["real_orders_allowed"] is False


def test_open_buy_trade() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=0.10,
        stop_loss=1990.0,
        take_profit=2020.0,
    )

    assert trade.symbol == "XAUUSD"
    assert trade.direction == "buy"
    assert trade.entry_price == 2000.0
    assert trade.quantity == 0.10
    assert trade.status == "open"
    assert trade.execution_type == "paper"


def test_open_sell_trade() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="sell",
        entry_price=2000.0,
        quantity=0.10,
        stop_loss=2010.0,
        take_profit=1980.0,
    )

    assert trade.direction == "sell"
    assert trade.status == "open"


def test_close_buy_trade_calculates_profit() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    closed = engine.close_trade(
        trade.trade_id,
        2020.0,
    )

    assert closed.status == "closed"
    assert closed.exit_price == 2020.0
    assert closed.pnl == 20.0


def test_close_sell_trade_calculates_profit() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="sell",
        entry_price=2000.0,
        quantity=1.0,
    )

    closed = engine.close_trade(
        trade.trade_id,
        1980.0,
    )

    assert closed.status == "closed"
    assert closed.pnl == 20.0


def test_losing_buy_trade_calculates_loss() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    closed = engine.close_trade(
        trade.trade_id,
        1990.0,
    )

    assert closed.pnl == -10.0


def test_losing_sell_trade_calculates_loss() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="sell",
        entry_price=2000.0,
        quantity=1.0,
    )

    closed = engine.close_trade(
        trade.trade_id,
        2010.0,
    )

    assert closed.pnl == -10.0


def test_performance_metrics() -> None:
    engine = DemoTradingEngine()

    winning_trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    engine.close_trade(
        winning_trade.trade_id,
        2020.0,
    )

    losing_trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    engine.close_trade(
        losing_trade.trade_id,
        1990.0,
    )

    performance = engine.performance()

    assert performance.total_trades == 2
    assert performance.winning_trades == 1
    assert performance.losing_trades == 1
    assert performance.open_trades == 0

    assert performance.win_rate == 50.0
    assert performance.total_pnl == 10.0
    assert performance.gross_profit == 20.0
    assert performance.gross_loss == 10.0
    assert performance.profit_factor == 2.0
    assert performance.expectancy == 5.0
    assert performance.max_drawdown == 10.0


def test_open_trade_limit_is_enforced() -> None:
    engine = DemoTradingEngine(
        max_open_trades=2,
    )

    engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            quantity=1.0,
        )


def test_invalid_direction_is_rejected() -> None:
    engine = DemoTradingEngine()

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="hold",
            entry_price=2000.0,
            quantity=1.0,
        )


def test_invalid_quantity_is_rejected() -> None:
    engine = DemoTradingEngine()

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            quantity=0.0,
        )


def test_invalid_entry_price_is_rejected() -> None:
    engine = DemoTradingEngine()

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="buy",
            entry_price=0.0,
            quantity=1.0,
        )


def test_buy_stop_loss_must_be_below_entry() -> None:
    engine = DemoTradingEngine()

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            quantity=1.0,
            stop_loss=2010.0,
        )


def test_buy_take_profit_must_be_above_entry() -> None:
    engine = DemoTradingEngine()

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            quantity=1.0,
            take_profit=1990.0,
        )


def test_sell_stop_loss_must_be_above_entry() -> None:
    engine = DemoTradingEngine()

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="sell",
            entry_price=2000.0,
            quantity=1.0,
            stop_loss=1990.0,
        )


def test_sell_take_profit_must_be_below_entry() -> None:
    engine = DemoTradingEngine()

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="sell",
            entry_price=2000.0,
            quantity=1.0,
            take_profit=2010.0,
        )


def test_missing_trade_is_rejected() -> None:
    engine = DemoTradingEngine()

    with pytest.raises(DemoTradingError):
        engine.close_trade(
            "does-not-exist",
            2000.0,
        )


def test_trade_cannot_be_closed_twice() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    engine.close_trade(
        trade.trade_id,
        2010.0,
    )

    with pytest.raises(DemoTradingError):
        engine.close_trade(
            trade.trade_id,
            2020.0,
        )


def test_cancel_trade() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    cancelled = engine.cancel_trade(
        trade.trade_id,
    )

    assert cancelled.status == "cancelled"
    assert cancelled.pnl == 0.0


def test_cancelled_trade_is_not_open() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    engine.cancel_trade(trade.trade_id)

    assert len(engine.open_trades) == 0


def test_reset_clears_trades() -> None:
    engine = DemoTradingEngine()

    engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    assert len(engine.trades) == 1

    engine.reset()

    assert len(engine.trades) == 0
    assert len(engine.open_trades) == 0


def test_no_trades_returns_zero_metrics() -> None:
    engine = DemoTradingEngine()

    performance = engine.performance()

    assert performance.total_trades == 0
    assert performance.winning_trades == 0
    assert performance.losing_trades == 0
    assert performance.win_rate == 0.0
    assert performance.total_pnl == 0.0
    assert performance.gross_profit == 0.0
    assert performance.gross_loss == 0.0
    assert performance.profit_factor == 0.0
    assert performance.expectancy == 0.0
    assert performance.max_drawdown == 0.0


def test_all_winning_trades_have_infinite_profit_factor() -> None:
    engine = DemoTradingEngine()

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    engine.close_trade(
        trade.trade_id,
        2010.0,
    )

    performance = engine.performance()

    assert math.isinf(
        performance.profit_factor
    )


def test_daily_loss_limit_is_enforced() -> None:
    engine = DemoTradingEngine(
        max_daily_loss=300.0,
    )

    trade = engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=1.0,
    )

    engine.close_trade(
        trade.trade_id,
        1700.0,
    )

    assert engine.daily_closed_pnl() == -300.0
    assert engine.can_open_trade() is False

    with pytest.raises(DemoTradingError):
        engine.open_trade(
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            quantity=1.0,
        )


def test_zero_daily_loss_limit_is_rejected() -> None:
    with pytest.raises(DemoTradingError):
        DemoTradingEngine(
            max_daily_loss=0.0,
        )


def test_status_reports_demo_risk_limits() -> None:
    engine = DemoTradingEngine(
        max_open_trades=2,
        max_daily_loss=250.0,
    )

    status = engine.status()

    assert status["max_open_trades"] == 2
    assert status["max_daily_loss"] == 250.0
    assert status["live_trading_enabled"] is False
    assert status["real_orders_allowed"] is False
