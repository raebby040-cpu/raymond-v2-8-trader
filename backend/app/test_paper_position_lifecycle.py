"""
Tests for RAYMOND v2.8 Stage 17.4.2.

Automatic paper-position TP/SL lifecycle tests.

These tests use the real Position model with an isolated in-memory
SQLite database. They never contact MT5, a broker, or live execution.
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Position, PositionStatus, TradeDirection
from app.paper_position_lifecycle import (
    PaperPositionLifecycle,
    PaperPositionLifecycleError,
)


@pytest.fixture()
def db():
    """Create one isolated database/session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def make_position(
    db,
    *,
    direction=TradeDirection.BUY,
    entry_price=100.0,
    stop_loss=95.0,
    take_profit_1=110.0,
    take_profit_2=120.0,
    quantity=1.0,
    status=PositionStatus.OPEN,
    position_id="POS-001",
    trade_id="PAPER-001",
):
    """Create a Position using fields present on the current model."""

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
        risk_1r=abs(entry_price - stop_loss),
        current_price=entry_price,
        remaining_quantity=quantity,
        pnl=0.0,
        pnl_percent=0.0,
        regime="trending_down",
        setup="bearish_continuation",
        technical_score=14.0,
        confluence=65.0,
        confidence=77.8,
        trade_thesis="Test paper trade thesis",
        break_even_applied=0,
        partial_close_applied=0,
        trailing_active=0,
        management_status="open",
        max_drawdown=0.0,
        max_profit=0.0,
        status=status,
        opened_at=datetime.utcnow(),
    )

    db.add(position)
    db.commit()
    db.refresh(position)

    return position


# ============================================================
# BUY LIFECYCLE
# ============================================================


def test_buy_stop_loss_closes_and_persists(db):
    position = make_position(
        db,
        position_id="BUY-SL",
        trade_id="PAPER-BUY-SL",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        95.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "STOP_LOSS_HIT"
    assert result.closed is True
    assert result.persisted is True

    assert position.status == PositionStatus.CLOSED
    assert position.closed_at is not None
    assert position.current_price == 95.0
    assert position.pnl == -5.0
    assert position.quantity == 0.0
    assert position.remaining_quantity == 0.0


def test_buy_tp1_closes_and_persists(db):
    position = make_position(
        db,
        position_id="BUY-TP1",
        trade_id="PAPER-BUY-TP1",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        110.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "TAKE_PROFIT_1_HIT"
    assert result.closed is True
    assert result.persisted is True

    assert position.status == PositionStatus.CLOSED
    assert position.pnl == 10.0


def test_buy_tp2_closes_and_persists(db):
    position = make_position(
        db,
        position_id="BUY-TP2",
        trade_id="PAPER-BUY-TP2",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        120.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "TAKE_PROFIT_2_HIT"
    assert result.closed is True
    assert result.persisted is True

    assert position.status == PositionStatus.CLOSED
    assert position.pnl == 20.0


def test_buy_holds_and_persists_mark_to_market(db):
    position = make_position(
        db,
        position_id="BUY-HOLD",
        trade_id="PAPER-BUY-HOLD",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        105.0,
    )

    assert result.action == "HOLD"
    assert result.close_reason is None
    assert result.closed is False
    assert result.persisted is True

    assert position.status == PositionStatus.OPEN
    assert position.current_price == 105.0
    assert position.pnl == 5.0
    assert position.remaining_quantity == 1.0


# ============================================================
# SELL LIFECYCLE
# ============================================================


def test_sell_stop_loss_closes_and_persists(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=90.0,
        take_profit_2=80.0,
        position_id="SELL-SL",
        trade_id="PAPER-SELL-SL",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        105.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "STOP_LOSS_HIT"
    assert result.closed is True
    assert result.persisted is True

    assert position.status == PositionStatus.CLOSED
    assert position.pnl == -5.0
    assert position.closed_at is not None


def test_sell_tp1_closes_and_persists(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=90.0,
        take_profit_2=80.0,
        position_id="SELL-TP1",
        trade_id="PAPER-SELL-TP1",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        90.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "TAKE_PROFIT_1_HIT"
    assert result.closed is True
    assert result.persisted is True

    assert position.status == PositionStatus.CLOSED
    assert position.pnl == 10.0


def test_sell_tp2_closes_and_persists(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=90.0,
        take_profit_2=80.0,
        position_id="SELL-TP2",
        trade_id="PAPER-SELL-TP2",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        80.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "TAKE_PROFIT_2_HIT"
    assert result.closed is True
    assert result.persisted is True

    assert position.status == PositionStatus.CLOSED
    assert position.pnl == 20.0


def test_sell_holds_and_marks_to_market(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=90.0,
        take_profit_2=80.0,
        position_id="SELL-HOLD",
        trade_id="PAPER-SELL-HOLD",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        95.0,
    )

    assert result.action == "HOLD"
    assert result.close_reason is None
    assert result.closed is False
    assert result.persisted is True

    assert position.status == PositionStatus.OPEN
    assert position.current_price == 95.0
    assert position.pnl == 5.0


# ============================================================
# CLOSED POSITION
# ============================================================


def test_closed_position_is_not_processed_again(db):
    position = make_position(
        db,
        status=PositionStatus.CLOSED,
        position_id="ALREADY-CLOSED",
        trade_id="PAPER-ALREADY-CLOSED",
    )

    position.closed_at = datetime.utcnow()
    position.last_management_action = "STOP_LOSS_HIT"
    position.current_price = 95.0
    position.pnl = -5.0
    position.pnl_percent = -5.0
    position.quantity = 0.0
    position.remaining_quantity = 0.0

    db.commit()
    db.refresh(position)

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        120.0,
    )

    assert result.action == "ALREADY_CLOSED"
    assert result.closed is True
    assert result.persisted is False
    assert result.quantity == 0.0

    assert position.status == PositionStatus.CLOSED
    assert position.current_price == 95.0
    assert position.pnl == -5.0


# ============================================================
# VALIDATION
# ============================================================


@pytest.mark.parametrize(
    "bad_price",
    [
        0,
        -1,
        -100,
        "abc",
        None,
    ],
)
def test_invalid_current_price_is_rejected(
    db,
    bad_price,
):
    position = make_position(
        db,
        position_id=f"BAD-{str(bad_price)}",
        trade_id=f"PAPER-BAD-{str(bad_price)}",
    )

    lifecycle = PaperPositionLifecycle(db)

    with pytest.raises(
        PaperPositionLifecycleError
    ):
        lifecycle.evaluate_position(
            position,
            bad_price,
        )


def test_empty_symbol_is_rejected(db):
    lifecycle = PaperPositionLifecycle(db)

    with pytest.raises(
        PaperPositionLifecycleError
    ):
        lifecycle.evaluate_symbol(
            "",
            100.0,
        )


def test_symbol_is_normalized_and_open_position_is_processed(db):
    position = make_position(
        db,
        position_id="SYMBOL-NORMALIZE",
        trade_id="PAPER-SYMBOL-NORMALIZE",
    )

    results = PaperPositionLifecycle(db).evaluate_symbol(
        "xauusd",
        105.0,
    )

    assert len(results) == 1
    assert results[0].symbol == "XAUUSD"
    assert position.current_price == 105.0


# ============================================================
# MULTIPLE POSITIONS
# ============================================================


def test_evaluate_symbol_processes_all_open_positions(db):
    first = make_position(
        db,
        position_id="MULTI-1",
        trade_id="PAPER-MULTI-1",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
    )

    second = make_position(
        db,
        position_id="MULTI-2",
        trade_id="PAPER-MULTI-2",
        entry_price=200.0,
        stop_loss=190.0,
        take_profit_1=220.0,
        take_profit_2=240.0,
    )

    results = PaperPositionLifecycle(db).evaluate_symbol(
        "XAUUSD",
        110.0,
    )

    assert len(results) == 2

    assert first.status == PositionStatus.CLOSED
    assert first.pnl == 10.0

    assert second.status == PositionStatus.OPEN
    assert second.current_price == 110.0
    assert second.pnl == -90.0


# ============================================================
# PNL
# ============================================================


def test_pnl_percent_uses_entry_notional(db):
    position = make_position(
        db,
        entry_price=100.0,
        stop_loss=90.0,
        take_profit_1=120.0,
        take_profit_2=130.0,
        quantity=2.0,
        position_id="PNL-PERCENT",
        trade_id="PAPER-PNL-PERCENT",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        105.0,
    )

    assert result.action == "HOLD"
    assert position.pnl == 10.0
    assert position.pnl_percent == 5.0


# ============================================================
# THESIS PRESERVATION
# ============================================================


def test_trade_thesis_is_preserved_on_close(db):
    position = make_position(
        db,
        position_id="THESIS",
        trade_id="PAPER-THESIS",
    )

    thesis = position.trade_thesis

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        95.0,
    )

    assert result.closed is True
    assert position.trade_thesis == thesis


# ============================================================
# SERIALIZATION
# ============================================================


def test_result_serializes_paper_safety_flags(db):
    position = make_position(
        db,
        position_id="SERIALIZE",
        trade_id="PAPER-SERIALIZE",
    )

    result = PaperPositionLifecycle(db).evaluate_position(
        position,
        105.0,
    )

    payload = result.to_dict()

    assert payload["execution_type"] == "paper"
    assert payload["read_only"] is True
    assert payload["broker_order_required"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["broker_orders_allowed"] is False


# ============================================================
# LIVE EXECUTION SAFETY
# ============================================================


def test_lifecycle_has_no_live_execution_surface(db):
    lifecycle = PaperPositionLifecycle(db)

    assert not hasattr(
        lifecycle,
        "mt5",
    )

    assert not hasattr(
        lifecycle,
        "broker",
    )

    assert not hasattr(
        lifecycle,
        "execute_live",
    )

    assert not hasattr(
        lifecycle,
        "send_order",
    )
