"""
RAYMOND v2.8 - Lifecycle-Aware Paper Position Market Loop Tests

Stage 17.4.3

Verifies:
1. SL/TP lifecycle processing runs before advanced management.
2. Lifecycle and management results are serialized correctly.
3. Real SL/TP closure persists correctly.
4. Open positions remain open when no level is hit.
5. Closed positions are not processed again.
6. The loop remains paper-only.
7. Invalid prices are rejected before processing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.models import Position, PositionStatus, TradeDirection
from app.paper_position_lifecycle_market_loop import (
    LifecycleAwarePaperPositionMarketLoop,
)
from app.paper_position_market_loop import (
    PaperPositionMarketLoopConfig,
)


@dataclass(frozen=True)
class FakeResult:
    position_id: str
    trade_id: str
    symbol: str
    action: str
    reason: str | None = None
    close_reason: str | None = None
    entry_price: float | None = None
    current_price: float | None = None
    quantity: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    closed: bool = False
    persisted: bool = False
    execution_type: str = "paper"
    read_only: bool = True
    broker_order_required: bool = False
    live_trading_enabled: bool = False
    broker_orders_allowed: bool = False

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "action": self.action,
            "reason": self.reason,
            "close_reason": self.close_reason,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "quantity": self.quantity,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "closed": self.closed,
            "persisted": self.persisted,
            "execution_type": self.execution_type,
            "read_only": self.read_only,
            "broker_order_required": self.broker_order_required,
            "live_trading_enabled": self.live_trading_enabled,
            "broker_orders_allowed": self.broker_orders_allowed,
        }


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
    def __init__(self):
        self.calls = []

    def evaluate_symbol(self, symbol: str, price: float):
        self.calls.append((symbol, price))

        return (
            FakeResult(
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
                pnl=10.0,
                pnl_percent=10.0,
                closed=True,
                persisted=True,
            ),
        )


class FakeManager:
    def __init__(self):
        self.calls = []

    def evaluate_symbol(self, symbol: str, price: float):
        self.calls.append((symbol, price))

        return (
            FakeResult(
                position_id="PAPER-OPEN",
                trade_id="TRADE-OPEN",
                symbol=symbol,
                action="HOLD",
                reason="Position remains open",
                current_price=price,
            ),
        )


class FakeLifecycleEmpty:
    def __init__(self):
        self.calls = []

    def evaluate_symbol(self, symbol: str, price: float):
        self.calls.append((symbol, price))
        return ()


def make_loop(
    db,
    *,
    lifecycle=None,
    manager=None,
):
    config = PaperPositionMarketLoopConfig.from_values(
        symbol="XAUUSD",
        interval_seconds=30.0,
        enabled=True,
    )

    return LifecycleAwarePaperPositionMarketLoop(
        db=db,
        price_provider=None,
        config=config,
        manager=manager,
        lifecycle=lifecycle,
    )


def test_lifecycle_runs_before_management(db):
    lifecycle = FakeLifecycle()
    manager = FakeManager()

    loop = make_loop(
        db,
        lifecycle=lifecycle,
        manager=manager,
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
    lifecycle = FakeLifecycle()
    manager = FakeManager()

    loop = make_loop(
        db,
        lifecycle=lifecycle,
        manager=manager,
    )

    result = loop.evaluate_price(110.0)

    lifecycle_result = result.results[0]

    assert lifecycle_result["phase"] == "lifecycle"
    assert lifecycle_result["action"] == "CLOSE_POSITION"
    assert lifecycle_result["close_reason"] == "TAKE_PROFIT_1"
    assert lifecycle_result["closed"] is True
    assert lifecycle_result["persisted"] is True


def test_open_position_management_is_reported_separately(db):
    lifecycle = FakeLifecycleEmpty()
    manager = FakeManager()

    loop = make_loop(
        db,
        lifecycle=lifecycle,
        manager=manager,
    )

    result = loop.evaluate_price(105.0)

    assert result.count == 1
    assert result.results[0]["phase"] == "management"
    assert result.results[0]["action"] == "HOLD"


def test_loop_uses_real_lifecycle_engine_for_take_profit(db):
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

    loop = make_loop(db)

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

    loop = make_loop(db)

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

    loop = make_loop(db)

    result = loop.evaluate_price(105.0)

    db.refresh(position)

    assert position.status == PositionStatus.OPEN
    assert position.quantity == pytest.approx(1.0)
    assert position.current_price == pytest.approx(105.0)
    assert position.pnl == pytest.approx(5.0)

    assert result.current_price == pytest.approx(105.0)


def test_closed_position_is_not_processed_again(db):
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

    loop = make_loop(db)

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
    lifecycle = FakeLifecycle()
    manager = FakeManager()

    loop = make_loop(
        db,
        lifecycle=lifecycle,
        manager=manager,
    )

    result = loop.evaluate_price(110.0)
    safety = result.to_dict()

    assert safety["execution_type"] == "paper"
    assert safety["read_only"] is True
    assert safety["broker_order_required"] is False
    assert safety["live_trading_enabled"] is False
    assert safety["broker_orders_allowed"] is False


def test_loop_rejects_invalid_market_price(db):
    lifecycle = FakeLifecycle()
    manager = FakeManager()

    loop = make_loop(
        db,
        lifecycle=lifecycle,
        manager=manager,
    )

    with pytest.raises(ValueError):
        loop.evaluate_price(0.0)

    assert lifecycle.calls == []
    assert manager.calls == []
