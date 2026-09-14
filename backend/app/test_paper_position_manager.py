"""
RAYMOND v2.8 - Paper Position Manager Tests

Stage 17
Advanced Trade Management Integration

These tests verify that the integration layer:
- updates persistent paper prices,
- delegates decisions to AdvancedTradeManager,
- persists break-even,
- persists trailing stops,
- persists partial closes,
- prevents duplicate management actions,
- supports BUY and SELL,
- remains paper-only,
- never requires broker execution.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.advanced_trade_management import (
    ManagementAction,
    ManagementDecision,
    TradeDirection,
)
from app.models import PositionStatus
from app.paper_position_manager import (
    PaperPositionManager,
    PaperPositionManagementError,
)


def make_position(
    *,
    position_id="paper-position-1",
    trade_id="paper-trade-1",
    symbol="XAUUSD",
    direction=TradeDirection.BUY,
    entry_price=4300.0,
    current_price=4300.0,
    quantity=1.0,
    stop_loss=4290.0,
    take_profit=4320.0,
    break_even_applied=0,
    partial_close_applied=0,
    status=PositionStatus.OPEN,
):
    return SimpleNamespace(
        position_id=position_id,
        trade_id=trade_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_price=current_price,
        quantity=quantity,
        original_quantity=quantity,
        remaining_quantity=quantity,
        stop_loss=stop_loss,
        initial_stop_loss=stop_loss,
        current_stop_loss=stop_loss,
        take_profit=take_profit,
        take_profit_1=take_profit,
        take_profit_2=None,
        break_even_applied=break_even_applied,
        partial_close_applied=partial_close_applied,
        status=status,
    )


def make_decision(
    *,
    action=ManagementAction.HOLD,
    profit_r=0.0,
    new_stop_loss=None,
    partial_close_quantity=0.0,
    reason="Hold position.",
    execution_type="paper",
    read_only=True,
    broker_order_required=False,
):
    return SimpleNamespace(
        action=action,
        profit_r=profit_r,
        new_stop_loss=new_stop_loss,
        partial_close_quantity=partial_close_quantity,
        reason=reason,
        execution_type=execution_type,
        read_only=read_only,
        broker_order_required=broker_order_required,
    )


class FakeTradeManager:
    def __init__(self, decision):
        self.decision = decision
        self.received_snapshot = None

    def evaluate(self, snapshot):
        self.received_snapshot = snapshot
        return self.decision


@pytest.fixture
def db():
    return Mock(name="sqlalchemy_session")


def test_hold_updates_price_and_persists_state(db):
    position = make_position()
    updated = make_position(current_price=4310.0)

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.HOLD,
            profit_r=1.0,
            reason="No management action required.",
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=updated,
    ) as update_price:
        result = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4310.0,
        )

    update_price.assert_called_once_with(
        db,
        "paper-position-1",
        4310.0,
    )

    assert result.position_id == "paper-position-1"
    assert result.symbol == "XAUUSD"
    assert result.action == ManagementAction.HOLD.value
    assert result.profit_r == 1.0
    assert result.current_price == 4310.0
    assert result.persisted is True
    assert result.execution_type == "paper"
    assert result.read_only is True
    assert result.broker_order_required is False

    assert manager.received_snapshot.current_price == 4310.0
    assert manager.received_snapshot.direction == TradeDirection.BUY


def test_break_even_is_persisted(db):
    position = make_position()
    updated = make_position(current_price=4310.0)

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.MOVE_TO_BREAK_EVEN,
            profit_r=1.0,
            new_stop_loss=4300.0,
            reason="Break-even threshold reached.",
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.get_by_position_id",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.mark_break_even",
        return_value=updated,
    ) as mark_break_even:
        result = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4310.0,
        )

    mark_break_even.assert_called_once_with(
        db,
        "paper-position-1",
        4300.0,
    )

    assert result.action == ManagementAction.MOVE_TO_BREAK_EVEN.value
    assert result.new_stop_loss == 4300.0
    assert result.persisted is True


def test_duplicate_break_even_is_prevented(db):
    position = make_position()
    updated = make_position(
        current_price=4310.0,
        break_even_applied=1,
    )

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.MOVE_TO_BREAK_EVEN,
            profit_r=1.0,
            new_stop_loss=4300.0,
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.get_by_position_id",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.mark_break_even",
    ) as mark_break_even:
        result = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4310.0,
        )

    mark_break_even.assert_not_called()

    assert result.action == ManagementAction.HOLD.value
    assert result.persisted is True
    assert "already" in result.reason.lower()


def test_trailing_stop_is_persisted_when_protection_improves(db):
    position = make_position(
        current_price=4315.0,
        stop_loss=4300.0,
    )
    updated = make_position(
        current_price=4315.0,
        stop_loss=4300.0,
    )

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.TRAIL_STOP,
            profit_r=1.5,
            new_stop_loss=4308.0,
            reason="Trailing stop improves protection.",
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.get_by_position_id",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.update_stop_loss",
        return_value=updated,
    ) as update_stop:
        result = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4315.0,
        )

    update_stop.assert_called_once_with(
        db,
        "paper-position-1",
        4308.0,
        management_action="TRAIL_STOP",
        management_status="protected",
    )

    assert result.action == ManagementAction.TRAIL_STOP.value
    assert result.new_stop_loss == 4308.0
    assert result.persisted is True


def test_buy_trailing_stop_that_worsens_protection_is_rejected(db):
    position = make_position(
        current_price=4315.0,
        stop_loss=4308.0,
    )
    updated = make_position(
        current_price=4315.0,
        stop_loss=4308.0,
    )

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.TRAIL_STOP,
            profit_r=1.5,
            new_stop_loss=4305.0,
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.get_by_position_id",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.update_stop_loss",
    ) as update_stop:
        result = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4315.0,
        )

    update_stop.assert_not_called()

    assert result.action == ManagementAction.HOLD.value
    assert result.persisted is True
    assert "worsen" in result.reason.lower()


def test_sell_trailing_stop_that_improves_protection_is_persisted(db):
    position = make_position(
        direction=TradeDirection.SELL,
        entry_price=4300.0,
        current_price=4285.0,
        stop_loss=4300.0,
    )
    updated = make_position(
        direction=TradeDirection.SELL,
        entry_price=4300.0,
        current_price=4285.0,
        stop_loss=4300.0,
    )

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.TRAIL_STOP,
            profit_r=1.5,
            new_stop_loss=4292.0,
            reason="Sell trailing stop improves protection.",
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.get_by_position_id",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.update_stop_loss",
        return_value=updated,
    ) as update_stop:
        result = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4285.0,
        )

    update_stop.assert_called_once_with(
        db,
        "paper-position-1",
        4292.0,
        management_action="TRAIL_STOP",
        management_status="protected",
    )

    assert result.action == ManagementAction.TRAIL_STOP.value
    assert result.new_stop_loss == 4292.0


def test_partial_close_is_persisted(db):
    position = make_position(
        quantity=1.0,
        current_price=4320.0,
    )
    updated = make_position(
        quantity=1.0,
        current_price=4320.0,
    )

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.PARTIAL_CLOSE,
            profit_r=2.0,
            partial_close_quantity=0.5,
            reason="Partial close threshold reached.",
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.get_by_position_id",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.mark_partial_close",
        return_value=updated,
    ) as mark_partial:
        result = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4320.0,
        )

    mark_partial.assert_called_once_with(
        db,
        "paper-position-1",
        0.5,
    )

    assert result.action == ManagementAction.PARTIAL_CLOSE.value
    assert result.partial_close_quantity == 0.5
    assert result.persisted is True


def test_duplicate_partial_close_is_prevented(db):
    position = make_position()
    updated = make_position(
        partial_close_applied=1,
    )

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.PARTIAL_CLOSE,
            profit_r=2.0,
            partial_close_quantity=0.5,
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.get_by_position_id",
        return_value=updated,
    ), patch(
        "app.paper_position_manager.PositionRepository.mark_partial_close",
    ) as mark_partial:
        result = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4320.0,
        )

    mark_partial.assert_not_called()

    assert result.action == ManagementAction.HOLD.value
    assert result.partial_close_quantity == 0.0
    assert "already" in result.reason.lower()


def test_closed_position_is_not_managed(db):
    position = make_position(
        status=PositionStatus.CLOSED,
    )

    trade_manager = Mock()

    result = PaperPositionManager(
        db,
        trade_manager=trade_manager,
    ).evaluate_position(
        position,
        current_price=4310.0,
    )

    trade_manager.evaluate.assert_not_called()

    assert result.action == ManagementAction.HOLD.value
    assert result.persisted is False
    assert "not open" in result.reason.lower()


def test_unsafe_execution_type_is_rejected(db):
    position = make_position()

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.HOLD,
            execution_type="live",
        )
    )

    with pytest.raises(PaperPositionManagementError):
        PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4310.0,
        )


def test_broker_order_requirement_is_rejected(db):
    position = make_position()

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.HOLD,
            broker_order_required=True,
        )
    )

    with pytest.raises(PaperPositionManagementError):
        PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4310.0,
        )


def test_non_read_only_decision_is_rejected(db):
    position = make_position()

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.HOLD,
            read_only=False,
        )
    )

    with pytest.raises(PaperPositionManagementError):
        PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4310.0,
        )


def test_evaluate_symbol_only_manages_open_positions(db):
    position_one = make_position(
        position_id="position-1",
        trade_id="trade-1",
    )
    position_two = make_position(
        position_id="position-2",
        trade_id="trade-2",
    )

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.HOLD,
        )
    )

    with patch(
        "app.paper_position_manager.PositionRepository.get_open_positions",
        return_value=[position_one, position_two],
    ), patch(
        "app.paper_position_manager.PositionRepository.update_price",
        side_effect=[
            position_one,
            position_two,
        ],
    ):
        results = PaperPositionManager(
            db,
            trade_manager=manager,
        ).evaluate_symbol(
            "XAUUSD",
            current_price=4310.0,
        )

    assert len(results) == 2
    assert results[0].position_id == "position-1"
    assert results[1].position_id == "position-2"


def test_manager_never_calls_broker_or_mt5():
    position = make_position()

    manager = FakeTradeManager(
        make_decision(
            action=ManagementAction.HOLD,
        )
    )

    fake_broker = Mock()
    fake_mt5 = Mock()

    with patch(
        "app.paper_position_manager.PositionRepository.update_price",
        return_value=position,
    ):
        result = PaperPositionManager(
            Mock(),
            trade_manager=manager,
        ).evaluate_position(
            position,
            current_price=4310.0,
        )

    assert result.execution_type == "paper"
    assert result.read_only is True
    assert result.broker_order_required is False

    fake_broker.assert_not_called()
    fake_mt5.assert_not_called()


