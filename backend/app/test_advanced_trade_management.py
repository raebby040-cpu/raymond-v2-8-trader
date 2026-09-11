"""Step 12 - Advanced trade-management validation."""

import pytest

from app.advanced_trade_management import (
    AdvancedTradeManager,
    ManagementAction,
    PositionSnapshot,
    TradeDirection,
    TradeManagementConfig,
    TradeManagementError,
    management_decision_to_dict,
)


def _manager():
    return AdvancedTradeManager(
        TradeManagementConfig(
            break_even_trigger_r=1.0,
            break_even_offset=0.0,
            trailing_enabled=True,
            trailing_distance=5.0,
            trailing_step=1.0,
            partial_close_enabled=True,
            partial_close_percent=50.0,
            partial_close_trigger_r=2.0,
        )
    )


def test_buy_break_even_trigger():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-001",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2310.0,
        quantity=0.10,
        stop_loss=2290.0,
        take_profit=2320.0,
    )

    decision = manager.evaluate(position)

    assert decision.action == (
        ManagementAction.MOVE_TO_BREAK_EVEN
    )
    assert decision.new_stop_loss == 2300.0
    assert decision.partial_close_quantity == 0.0
    assert decision.execution_type == "paper"
    assert decision.read_only is True
    assert decision.broker_order_required is False


def test_sell_break_even_trigger():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-002",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=2300.0,
        current_price=2290.0,
        quantity=0.10,
        stop_loss=2310.0,
        take_profit=2280.0,
    )

    decision = manager.evaluate(position)

    assert decision.action == (
        ManagementAction.MOVE_TO_BREAK_EVEN
    )
    assert decision.new_stop_loss == 2300.0


def test_buy_trailing_stop_improves_protection():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-003",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2320.0,
        quantity=0.10,
        stop_loss=2305.0,
        take_profit=2340.0,
        break_even_applied=True,
    )

    decision = manager.evaluate(position)

    assert decision.action == (
        ManagementAction.TRAIL_STOP
    )
    assert decision.new_stop_loss == 2315.0


def test_sell_trailing_stop_improves_protection():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-004",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=2300.0,
        current_price=2280.0,
        quantity=0.10,
        stop_loss=2290.0,
        take_profit=2260.0,
        break_even_applied=True,
    )

    decision = manager.evaluate(position)

    assert decision.action == (
        ManagementAction.TRAIL_STOP
    )
    assert decision.new_stop_loss == 2285.0


def test_trailing_stop_never_worsens_buy_stop():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-005",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2308.0,
        quantity=0.10,
        stop_loss=2305.0,
        take_profit=2320.0,
        break_even_applied=True,
    )

    decision = manager.evaluate(position)

    assert decision.action == ManagementAction.HOLD
    assert decision.new_stop_loss is None


def test_trailing_stop_never_worsens_sell_stop():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-006",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=2300.0,
        current_price=2292.0,
        quantity=0.10,
        stop_loss=2295.0,
        take_profit=2270.0,
        break_even_applied=True,
    )

    decision = manager.evaluate(position)

    assert decision.action == ManagementAction.HOLD
    assert decision.new_stop_loss is None


def test_partial_close_trigger():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-007",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2320.0,
        quantity=0.10,
        stop_loss=2290.0,
        take_profit=2340.0,
        break_even_applied=True,
    )

    decision = manager.evaluate(position)

    assert decision.action == (
        ManagementAction.PARTIAL_CLOSE
    )
    assert decision.partial_close_quantity == 0.05
    assert decision.new_stop_loss is None


def test_partial_close_only_happens_once():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-008",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2320.0,
        quantity=0.10,
        stop_loss=2300.0,
        take_profit=2340.0,
        break_even_applied=True,
        partial_close_applied=True,
    )

    decision = manager.evaluate(position)

    assert decision.action == (
        ManagementAction.TRAIL_STOP
    )
    assert decision.partial_close_quantity == 0.0


def test_no_management_action_when_position_is_flat():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-009",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2300.0,
        quantity=0.10,
        stop_loss=2290.0,
        take_profit=2320.0,
    )

    decision = manager.evaluate(position)

    assert decision.action == ManagementAction.HOLD
    assert decision.new_stop_loss is None
    assert decision.partial_close_quantity == 0.0
    assert decision.profit_r == 0.0


def test_no_management_action_when_position_is_losing():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-010",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2295.0,
        quantity=0.10,
        stop_loss=2290.0,
        take_profit=2320.0,
    )

    decision = manager.evaluate(position)

    assert decision.action == ManagementAction.HOLD
    assert decision.new_stop_loss is None


def test_profit_r_buy():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-011",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2320.0,
        quantity=0.10,
        stop_loss=2290.0,
    )

    assert manager.profit_r(position) == 2.0


def test_profit_r_sell():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-012",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=2300.0,
        current_price=2280.0,
        quantity=0.10,
        stop_loss=2310.0,
    )

    assert manager.profit_r(position) == 2.0


def test_break_even_offset_buy():
    manager = AdvancedTradeManager(
        TradeManagementConfig(
            break_even_trigger_r=1.0,
            break_even_offset=1.0,
            trailing_enabled=False,
            trailing_distance=5.0,
            trailing_step=1.0,
            partial_close_enabled=False,
            partial_close_percent=50.0,
            partial_close_trigger_r=2.0,
        )
    )

    position = PositionSnapshot(
        trade_id="PAPER-12-013",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2310.0,
        quantity=0.10,
        stop_loss=2290.0,
    )

    decision = manager.evaluate(position)

    assert decision.action == (
        ManagementAction.MOVE_TO_BREAK_EVEN
    )
    assert decision.new_stop_loss == 2301.0


def test_break_even_offset_sell():
    manager = AdvancedTradeManager(
        TradeManagementConfig(
            break_even_trigger_r=1.0,
            break_even_offset=1.0,
            trailing_enabled=False,
            trailing_distance=5.0,
            trailing_step=1.0,
            partial_close_enabled=False,
            partial_close_percent=50.0,
            partial_close_trigger_r=2.0,
        )
    )

    position = PositionSnapshot(
        trade_id="PAPER-12-014",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=2300.0,
        current_price=2290.0,
        quantity=0.10,
        stop_loss=2310.0,
    )

    decision = manager.evaluate(position)

    assert decision.action == (
        ManagementAction.MOVE_TO_BREAK_EVEN
    )
    assert decision.new_stop_loss == 2299.0


def test_management_decision_serialization():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-015",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2310.0,
        quantity=0.10,
        stop_loss=2290.0,
    )

    decision = manager.evaluate(position)

    data = management_decision_to_dict(
        decision
    )

    assert data["action"] == "move_to_break_even"
    assert data["trade_id"] == "PAPER-12-015"
    assert data["new_stop_loss"] == 2300.0
    assert data["execution_type"] == "paper"
    assert data["read_only"] is True
    assert data["broker_order_required"] is False


def test_invalid_configuration_is_rejected():
    with pytest.raises(TradeManagementError):
        AdvancedTradeManager(
            TradeManagementConfig(
                break_even_trigger_r=0.0,
            )
        )


def test_invalid_position_is_rejected():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2310.0,
        quantity=0.10,
        stop_loss=2290.0,
    )

    with pytest.raises(TradeManagementError):
        manager.evaluate(position)


def test_buy_invalid_stop_loss_is_rejected():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-016",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2310.0,
        quantity=0.10,
        stop_loss=2310.0,
    )

    with pytest.raises(TradeManagementError):
        manager.evaluate(position)


def test_sell_invalid_stop_loss_is_rejected():
    manager = _manager()

    position = PositionSnapshot(
        trade_id="PAPER-12-017",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=2300.0,
        current_price=2290.0,
        quantity=0.10,
        stop_loss=2290.0,
    )

    with pytest.raises(TradeManagementError):
        manager.evaluate(position)


def test_partial_close_never_closes_entire_position():
    manager = AdvancedTradeManager(
        TradeManagementConfig(
            break_even_trigger_r=1.0,
            break_even_offset=0.0,
            trailing_enabled=False,
            trailing_distance=5.0,
            trailing_step=1.0,
            partial_close_enabled=True,
            partial_close_percent=99.99,
            partial_close_trigger_r=2.0,
        )
    )

    position = PositionSnapshot(
        trade_id="PAPER-12-018",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=2300.0,
        current_price=2320.0,
        quantity=0.10,
        stop_loss=2290.0,
    )

    decision = manager.evaluate(position)

    assert decision.action == ManagementAction.HOLD
    assert decision.partial_close_quantity == 0.0
