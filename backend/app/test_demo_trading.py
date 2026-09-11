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
