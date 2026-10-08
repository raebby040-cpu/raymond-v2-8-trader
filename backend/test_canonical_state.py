"""
RAYMOND v2.8 - Canonical Trading State Tests

Batch 1.

These tests verify:

- XAUUSD canonical P/L math.
- BUY and SELL accounting.
- Persistent position creation.
- Running/floating P/L updates.
- Account equity snapshots.
- Partial-close accounting.
- Final position closure.
"""

import pytest

from app.canonical_state import (
    TradingStateRepository,
    calculate_current_r,
    calculate_pnl_percent,
    calculate_unrealized_pnl,
)
from app.database import Base, SessionLocal, engine


@pytest.fixture
def db():
    Base.metadata.create_all(
        bind=engine
    )

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


def test_xauusd_buy_pnl():
    pnl = calculate_unrealized_pnl(
        symbol="XAUUSD",
        side="buy",
        entry_price=2051.0,
        current_price=2056.0,
        volume=0.02,
    )

    assert pnl == pytest.approx(
        10.0
    )


def test_xauusd_sell_pnl():
    pnl = calculate_unrealized_pnl(
        symbol="XAUUSD",
        side="sell",
        entry_price=2056.0,
        current_price=2051.0,
        volume=0.02,
    )

    assert pnl == pytest.approx(
        10.0
    )


def test_xauusd_losing_buy():
    pnl = calculate_unrealized_pnl(
        symbol="XAUUSD",
        side="buy",
        entry_price=2056.0,
        current_price=2051.0,
        volume=0.02,
    )

    assert pnl == pytest.approx(
        -10.0
    )


def test_current_r():
    current_r = calculate_current_r(
        side="buy",
        entry_price=2051.0,
        current_price=2056.0,
        risk_1r=2.5,
    )

    assert current_r == pytest.approx(
        2.0
    )


def test_pnl_percent():
    pnl_percent = calculate_pnl_percent(
        symbol="XAUUSD",
        entry_price=2000.0,
        volume=0.01,
        total_pnl=10.0,
    )

    assert pnl_percent == pytest.approx(
        0.5
    )


def test_create_position_and_update_running_pnl(db):
    repository = TradingStateRepository(
        db
    )

    position = repository.create_position(
        mode="demo",
        symbol="XAUUSD",
        side="buy",
        volume=0.02,
        entry_price=2051.0,
        stop_loss=2046.0,
        take_profit=2061.0,
        risk_1r=5.0,
        broker_position_ticket="12345",
    )

    assert position.status == "open"
    assert position.volume == pytest.approx(
        0.02
    )

    updated = repository.update_market(
        position,
        current_price=2056.0,
        broker_sync=True,
    )

    assert updated.current_price == pytest.approx(
        2056.0
    )

    assert updated.unrealized_pnl == pytest.approx(
        10.0
    )

    assert updated.total_pnl == pytest.approx(
        10.0
    )

    assert updated.current_r == pytest.approx(
        1.0
    )

    assert updated.last_broker_sync is not None


def test_equity_snapshot(db):
    repository = TradingStateRepository(
        db
    )

    snapshot = repository.upsert_account_snapshot(
        mode="demo",
        balance=1000.0,
        equity=1010.0,
        floating_pnl=10.0,
        realized_pnl=0.0,
        available_balance=1010.0,
        open_positions=1,
    )

    assert snapshot.balance == pytest.approx(
        1000.0
    )

    assert snapshot.equity == pytest.approx(
        1010.0
    )

    assert snapshot.floating_pnl == pytest.approx(
        10.0
    )

    assert snapshot.open_positions == 1

    latest = repository.get_latest_account(
        mode="demo"
    )

    assert latest is not None

    assert latest.equity == pytest.approx(
        1010.0
    )


def test_partial_close_moves_pnl_to_realized(db):
    repository = TradingStateRepository(
        db
    )

    position = repository.create_position(
        mode="paper",
        symbol="XAUUSD",
        side="buy",
        volume=0.02,
        entry_price=2051.0,
        stop_loss=2046.0,
        take_profit=2061.0,
        risk_1r=5.0,
    )

    repository.update_market(
        position,
        current_price=2056.0,
    )

    updated = repository.apply_partial_close(
        position,
        close_volume=0.01,
        execution_price=2056.0,
    )

    assert updated.volume == pytest.approx(
        0.01
    )

    assert updated.realized_pnl == pytest.approx(
        5.0
    )

    assert updated.partial_close_applied == 1

    assert updated.partial_close_quantity == pytest.approx(
        0.01
    )

    assert updated.partial_close_price == pytest.approx(
        2056.0
    )


def test_full_close_persists_realized_result(db):
    repository = TradingStateRepository(
        db
    )

    position = repository.create_position(
        mode="paper",
        symbol="XAUUSD",
        side="buy",
        volume=0.02,
        entry_price=2051.0,
        stop_loss=2046.0,
        take_profit=2061.0,
        risk_1r=5.0,
    )

    closed = repository.close_position(
        position,
        execution_price=2056.0,
    )

    assert closed.status == "closed"

    assert closed.volume == pytest.approx(
        0.0
    )

    assert closed.unrealized_pnl == pytest.approx(
        0.0
    )

    assert closed.realized_pnl == pytest.approx(
        10.0
    )

    assert closed.total_pnl == pytest.approx(
        10.0
    )

    assert closed.closed_at is not None
