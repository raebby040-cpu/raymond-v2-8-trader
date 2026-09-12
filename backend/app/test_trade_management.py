from app.trade_management import (
    TradeManagementConfig,
    TradeManagementError,
    TradeManager,
)


def test_break_even_buy_triggers_at_one_r():
    manager = TradeManager()

    result = manager.calculate_break_even(
        side="BUY",
        entry_price=2300.0,
        current_price=2310.0,
        original_stop_loss=2290.0,
    )

    assert result.triggered is True
    assert result.new_stop_loss == 2300.0


def test_break_even_sell_triggers_at_one_r():
    manager = TradeManager()

    result = manager.calculate_break_even(
        side="SELL",
        entry_price=2300.0,
        current_price=2290.0,
        original_stop_loss=2310.0,
    )

    assert result.triggered is True
    assert result.new_stop_loss == 2300.0


def test_break_even_does_not_trigger_before_one_r():
    manager = TradeManager()

    result = manager.calculate_break_even(
        side="BUY",
        entry_price=2300.0,
        current_price=2305.0,
        original_stop_loss=2290.0,
    )

    assert result.triggered is False
    assert result.new_stop_loss is None


def test_break_even_rejects_invalid_buy_stop():
    manager = TradeManager()

    try:
        manager.calculate_break_even(
            side="BUY",
            entry_price=2300.0,
            current_price=2310.0,
            original_stop_loss=2310.0,
        )
    except TradeManagementError as exc:
        assert "BUY stop-loss" in str(exc)
    else:
        raise AssertionError("Expected TradeManagementError")


def test_trailing_buy_only_tightens_stop():
    manager = TradeManager(
        TradeManagementConfig(trailing_distance=5.0)
    )

    result = manager.calculate_trailing_stop(
        side="BUY",
        current_price=2310.0,
        current_stop_loss=2300.0,
    )

    assert result.triggered is True
    assert result.new_stop_loss == 2305.0


def test_trailing_sell_only_tightens_stop():
    manager = TradeManager(
        TradeManagementConfig(trailing_distance=5.0)
    )

    result = manager.calculate_trailing_stop(
        side="SELL",
        current_price=2290.0,
        current_stop_loss=2300.0,
    )

    assert result.triggered is True
    assert result.new_stop_loss == 2295.0


def test_trailing_does_not_worsen_buy_stop():
    manager = TradeManager(
        TradeManagementConfig(trailing_distance=5.0)
    )

    result = manager.calculate_trailing_stop(
        side="BUY",
        current_price=2302.0,
        current_stop_loss=2300.0,
    )

    assert result.triggered is False
    assert result.new_stop_loss is None


def test_partial_close_calculates_configured_percentage():
    manager = TradeManager(
        TradeManagementConfig(partial_close_percent=50.0)
    )

    result = manager.calculate_partial_close(
        current_volume=0.20,
    )

    assert result.triggered is True
    assert result.close_volume == 0.10
    assert result.remaining_volume == 0.10


def test_disabled_features_do_not_trigger():
    manager = TradeManager(
        TradeManagementConfig(
            break_even_enabled=False,
            trailing_enabled=False,
            partial_close_enabled=False,
        )
    )

    break_even = manager.calculate_break_even(
        side="BUY",
        entry_price=2300.0,
        current_price=2310.0,
        original_stop_loss=2290.0,
    )

    trailing = manager.calculate_trailing_stop(
        side="BUY",
        current_price=2310.0,
        current_stop_loss=2300.0,
    )

    partial = manager.calculate_partial_close(
        current_volume=0.20,
    )

    assert break_even.triggered is False
    assert trailing.triggered is False
    assert partial.triggered is False
    assert partial.close_volume == 0.0
    assert partial.remaining_volume == 0.20


def test_invalid_config_is_rejected():
    try:
        TradeManager(
            TradeManagementConfig(partial_close_percent=0.0)
        )
    except TradeManagementError as exc:
        assert "partial_close_percent" in str(exc)
    else:
        raise AssertionError("Expected TradeManagementError")
