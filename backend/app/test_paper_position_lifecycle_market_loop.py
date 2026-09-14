"""
RAYMOND v2.8 - Lifecycle-Aware Paper Position Market Loop Tests

Stage 17.4.3

Verifies that:
1. SL/TP lifecycle processing runs before advanced management.
2. A position closed by SL/TP is not managed afterward.
3. Positions that remain open are still passed to management.
4. The loop remains paper-only and cannot authorize broker/MT5 execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models import Position, PositionStatus, TradeDirection
from app.paper_position_lifecycle_market_loop import (
    LifecycleAwarePaperPositionMarketLoop,
)
from app.paper_position_market_loop import (
    PaperPositionMarketLoopConfig,
)


def make_position(
    db,
    *,
    position_id: str,
    trade_id: str,
    direction: TradeDirection,
    entry_price: float,
    stop_loss: float,
    take_profit_1: float,
    take_profit_2: float | None = None,
    quantity: float = 1.0,
):
    """
    Create and persist a paper position using the real Position model.
    """

    position = Position(
        position_id=position_id,
        trade_id=trade_id,
        symbol="XAUUSD",
        direction=direction,
        quantity=quantity,
        original_quantity=quantity,
        entry_price=entry_price,
        initial_stop_loss=stop_loss,
        current_stop_loss=stop_loss,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        take_profit=take_profit_1,
        current_price=entry_price,
        pnl=0.0,
        pnl_percent=0.0,
        status=PositionStatus.OPEN,
        management_status="open",
        opened_at=datetime.now(timezone.utc),
    )

    db.add(position)
    db.commit()
    db.refresh(position)

    return position


class FakeLifecycle:
    """
    Controlled lifecycle engine for testing loop ordering.
    """

    def __init__(self):
        self.calls = []

    def evaluate_symbol(self, symbol: str, price: float):
        self.calls.append((symbol, price))

        return (
            SimpleNamespace(
                position_id="PAPER-CLOSED",
                trade_id="TRADE-CLOSED",
                symbol=symbol,
                action="CLOSE_POSITION",
                close_reason="TAKE_PROFIT_1",
                entry_price=100.0,
                current_price=price,
                quantity=1.0,
                stop_loss=90.0,
                take_profit_1=110.0,
                take_profit_2=None,
                pnl=10.0,
                pnl_percent=10.0,
                closed=True,
                persisted=True,
                execution_type="paper",
                read_only=True,
                broker_order_required=False,
                live_trading_enabled=False,
                broker_orders_allowed=False,
            ),
        )


class FakeManager:
    """
    Controlled management engine for testing ordering.
    """

    def __init__(self):
        self.calls = []

    def evaluate_symbol(self, symbol: str, price: float):
        self.calls.append((symbol, price))

        return (
            SimpleNamespace(
                position_id="PAPER-OPEN",
                trade_id="TRADE-OPEN",
                symbol=symbol,
                action="HOLD",
                reason="Position remains open",
                current_price=price,
                execution_type="paper",
                read_only=True,
                broker_order_required=False,
                live_trading_enabled=False,
                broker_orders_allowed=False,
            ),
        )


class FakeLifecycleEmpty:
    """
    Lifecycle engine that closes nothing.
    """

    def __init__(self):
        self.calls = []

    def evaluate_symbol(self, symbol: str, price: float):
        self.calls.append((symbol, price))
        return ()


def test_lifecycle_runs_before_management(db):
    """
    Lifecycle processing must happen before advanced management.
    """

    lifecycle = FakeLifecycle()
    manager = FakeManager()

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
        manager=manager,
        lifecycle=lifecycle,
    )

    result = loop.evaluate_price(110.0)

    assert result.symbol == "XAUUSD"
    assert result.current_price == 110.0
    assert result.count == 2

    assert lifecycle.calls == [
        ("XAUUSD", 110.0),
    ]

    assert manager.calls == [
        ("XAUUSD", 110.0),
    ]

    assert result.results[0]["phase"] == "lifecycle"
    assert result.results[1]["phase"] == "management"


def test_lifecycle_closure_is_reported_as_lifecycle_phase(db):
    """
    A lifecycle close result must be clearly marked as lifecycle processing.
    """

    lifecycle = FakeLifecycle()
    manager = FakeManager()

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
        manager=manager,
        lifecycle=lifecycle,
    )

    result = loop.evaluate_price(110.0)

    lifecycle_result = result.results[0]

    assert lifecycle_result["phase"] == "lifecycle"
    assert lifecycle_result["action"] == "CLOSE_POSITION"
    assert lifecycle_result["close_reason"] == "TAKE_PROFIT_1"
    assert lifecycle_result["closed"] is True
    assert lifecycle_result["persisted"] is True


def test_open_position_management_is_reported_separately(db):
    """
    Management results must remain separate from lifecycle results.
    """

    lifecycle = FakeLifecycleEmpty()
    manager = FakeManager()

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
        manager=manager,
        lifecycle=lifecycle,
    )

    result = loop.evaluate_price(105.0)

    assert result.count == 1
    assert result.results[0]["phase"] == "management"
    assert result.results[0]["action"] == "HOLD"


def test_loop_uses_real_lifecycle_engine_for_take_profit(db):
    """
    Integration test using the actual PaperPositionLifecycle engine.

    BUY position:
        entry = 100
        TP1   = 110

    Price reaches 110, therefore the position must close.
    """

    position = make_position(
        db,
        position_id="LIFECYCLE-TP-1",
        trade_id="TRADE-LIFECYCLE-TP-1",
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=90.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
        quantity=1.0,
    )

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
    )

    result = loop.evaluate_price(110.0)

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.quantity == 0
    assert position.current_price == 110.0
    assert position.pnl == pytest.approx(10.0)
    assert position.management_status == "closed"

    lifecycle_results = [
        item
        for item in result.results
        if item.get("phase") == "lifecycle"
    ]

    assert lifecycle_results

    close_result = lifecycle_results[0]

    assert close_result["position_id"] == "LIFECYCLE-TP-1"
    assert close_result["action"] == "CLOSE_POSITION"
    assert close_result["closed"] is True
    assert close_result["persisted"] is True


def test_loop_uses_real_lifecycle_engine_for_stop_loss(db):
    """
    Integration test using the actual lifecycle engine.

    BUY position:
        entry = 100
        SL    = 90

    Price reaches 90, therefore the position must close.
    """

    position = make_position(
        db,
        position_id="LIFECYCLE-SL-1",
        trade_id="TRADE-LIFECYCLE-SL-1",
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=90.0,
        take_profit_1=120.0,
        take_profit_2=130.0,
        quantity=1.0,
    )

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
    )

    result = loop.evaluate_price(90.0)

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.quantity == 0
    assert position.current_price == 90.0
    assert position.pnl == pytest.approx(-10.0)
    assert position.management_status == "closed"

    lifecycle_results = [
        item
        for item in result.results
        if item.get("phase") == "lifecycle"
    ]

    assert lifecycle_results

    close_result = lifecycle_results[0]

    assert close_result["position_id"] == "LIFECYCLE-SL-1"
    assert close_result["action"] == "CLOSE_POSITION"
    assert close_result["closed"] is True
    assert close_result["persisted"] is True


def test_loop_keeps_non_triggered_position_open(db):
    """
    A price that hits neither SL nor TP must leave the position open.
    """

    position = make_position(
        db,
        position_id="LIFECYCLE-HOLD-1",
        trade_id="TRADE-LIFECYCLE-HOLD-1",
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=90.0,
        take_profit_1=120.0,
        take_profit_2=130.0,
        quantity=1.0,
    )

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
    )

    result = loop.evaluate_price(105.0)

    db.refresh(position)

    assert position.status == PositionStatus.OPEN
    assert position.quantity == pytest.approx(1.0)
    assert position.current_price == pytest.approx(105.0)
    assert position.pnl == pytest.approx(5.0)

    assert result.current_price == pytest.approx(105.0)


def test_closed_position_is_not_processed_again(db):
    """
    Once a position is closed, a later market-loop evaluation must not
    generate another lifecycle close for that position.
    """

    position = make_position(
        db,
        position_id="LIFECYCLE-ONCE-1",
        trade_id="TRADE-LIFECYCLE-ONCE-1",
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=90.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
        quantity=1.0,
    )

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
    )

    first_result = loop.evaluate_price(110.0)

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED

    second_result = loop.evaluate_price(115.0)

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.quantity == 0

    first_closes = [
        item
        for item in first_result.results
        if item.get("phase") == "lifecycle"
        and item.get("position_id") == "LIFECYCLE-ONCE-1"
        and item.get("action") == "CLOSE_POSITION"
    ]

    second_closes = [
        item
        for item in second_result.results
        if item.get("phase") == "lifecycle"
        and item.get("position_id") == "LIFECYCLE-ONCE-1"
        and item.get("action") == "CLOSE_POSITION"
    ]

    assert len(first_closes) == 1
    assert len(second_closes) == 0


def test_loop_safety_flags_remain_paper_only(db):
    """
    Every lifecycle-aware loop result must remain paper-only.
    """

    lifecycle = FakeLifecycle()
    manager = FakeManager()

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
        manager=manager,
        lifecycle=lifecycle,
    )

    result = loop.evaluate_price(110.0)

    assert result.to_dict()["execution_type"] == "paper"
    assert result.to_dict()["read_only"] is True
    assert result.to_dict()["broker_order_required"] is False
    assert result.to_dict()["live_trading_enabled"] is False
    assert result.to_dict()["broker_orders_allowed"] is False


def test_loop_rejects_invalid_market_price(db):
    """
    Invalid prices must be rejected before lifecycle or management processing.
    """

    lifecycle = FakeLifecycle()
    manager = FakeManager()

    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    loop = LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
        manager=manager,
        lifecycle=lifecycle,
    )

    with pytest.raises(ValueError):
        loop.evaluate_price(0.0)

    assert lifecycle.calls == []
    assert manager.calls == []
