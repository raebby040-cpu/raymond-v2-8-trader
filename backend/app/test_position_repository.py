"""
RAYMOND v2.8 - Stage 16.2 Persistent Position Tests

These tests verify the persistent position state independently of the
live application database and without contacting MT5 or a broker.
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

try:
    from .database_migration import migrate_stage_16_2
    from .models import Base, PositionStatus, TradeDirection
    from .position_repository import PositionRepository
    from . import database_migration
except ImportError:
    from database_migration import migrate_stage_16_2
    from models import Base, PositionStatus, TradeDirection
    from position_repository import PositionRepository
    import database_migration


@pytest.fixture()
def db_session():
    """
    Create an isolated in-memory SQLite database for each test.
    """

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_create_persistent_position_persists_core_state(db_session):
    """A paper execution can become one persistent open position."""

    position = PositionRepository.create(
        db_session,
        position_id="POS-TEST-001",
        trade_id="PAPER-TEST-001",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=4300.0,
        original_quantity=0.50,
        initial_stop_loss=4290.0,
        take_profit_1=4315.0,
        take_profit_2=4330.0,
        risk_1r=10.0,
        regime="trending_up",
        setup="bullish_continuation",
        technical_score=78.0,
        confluence=82.0,
        confidence=86.0,
    )

    loaded = PositionRepository.get_by_trade_id(
        db_session,
        "PAPER-TEST-001",
    )

    assert loaded is not None
    assert loaded.position_id == "POS-TEST-001"
    assert loaded.trade_id == "PAPER-TEST-001"
    assert loaded.symbol == "XAUUSD"
    assert loaded.direction == TradeDirection.BUY
    assert loaded.entry_price == 4300.0
    assert loaded.original_quantity == 0.50
    assert loaded.remaining_quantity == 0.50
    assert loaded.initial_stop_loss == 4290.0
    assert loaded.current_stop_loss == 4290.0
    assert loaded.take_profit_1 == 4315.0
    assert loaded.take_profit_2 == 4330.0
    assert loaded.risk_1r == 10.0
    assert loaded.management_status == "open"
    assert loaded.break_even_applied == 0
    assert loaded.partial_close_applied == 0
    assert loaded.trailing_active == 0
    assert loaded.status == PositionStatus.OPEN
    assert isinstance(loaded.opened_at, datetime)


def test_duplicate_trade_id_is_idempotent(db_session):
    """The same paper execution must not create a second position."""

    first = PositionRepository.create(
        db_session,
        position_id="POS-TEST-002",
        trade_id="PAPER-DUPLICATE-001",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=4300.0,
        original_quantity=0.25,
        initial_stop_loss=4310.0,
        take_profit_1=4285.0,
    )

    second = PositionRepository.create(
        db_session,
        position_id="POS-TEST-002-RETRY",
        trade_id="PAPER-DUPLICATE-001",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=9999.0,
        original_quantity=99.0,
        initial_stop_loss=10000.0,
        take_profit_1=9000.0,
    )

    assert second.position_id == first.position_id
    assert second.entry_price == first.entry_price
    assert second.original_quantity == first.original_quantity

    positions = PositionRepository.get_all(
        db_session,
        limit=100,
    )

    matching = [
        position
        for position in positions
        if position.trade_id == "PAPER-DUPLICATE-001"
    ]

    assert len(matching) == 1


def test_original_stop_is_preserved_when_current_stop_moves(db_session):
    """Moving SL must never overwrite the original trade risk."""

    position = PositionRepository.create(
        db_session,
        position_id="POS-TEST-003",
        trade_id="PAPER-SL-001",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=4300.0,
        original_quantity=1.0,
        initial_stop_loss=4290.0,
        take_profit_1=4320.0,
        risk_1r=10.0,
    )

    updated = PositionRepository.update_stop_loss(
        db_session,
        position.position_id,
        4300.0,
        management_action="MOVE_TO_BREAK_EVEN",
        management_status="protected",
    )

    assert updated is not None
    assert updated.initial_stop_loss == 4290.0
    assert updated.current_stop_loss == 4300.0
    assert updated.stop_loss == 4300.0
    assert updated.risk_1r == 10.0
    assert updated.management_status == "protected"
    assert updated.last_management_action == "MOVE_TO_BREAK_EVEN"


def test_price_update_persists_pnl_and_extremes(db_session):
    """Price updates persist current price, PnL, and profit extremes."""

    position = PositionRepository.create(
        db_session,
        position_id="POS-TEST-004",
        trade_id="PAPER-PNL-001",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=4300.0,
        original_quantity=1.0,
        initial_stop_loss=4290.0,
        take_profit_1=4320.0,
    )

    updated = PositionRepository.update_price(
        db_session,
        position.position_id,
        4310.0,
    )

    assert updated is not None
    assert updated.current_price == 4310.0
    assert updated.pnl == 10.0
    assert updated.max_profit == 10.0
    assert updated.max_drawdown == 0.0

    updated = PositionRepository.update_price(
        db_session,
        position.position_id,
        4295.0,
    )

    assert updated.pnl == -5.0
    assert updated.max_profit == 10.0
    assert updated.max_drawdown == 5.0


def test_break_even_and_partial_close_state_persist(db_session):
    """Management flags survive reload and prevent state loss on restart."""

    position = PositionRepository.create(
        db_session,
        position_id="POS-TEST-005",
        trade_id="PAPER-MANAGEMENT-001",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=4300.0,
        original_quantity=1.0,
        initial_stop_loss=4290.0,
        take_profit_1=4310.0,
    )

    protected = PositionRepository.mark_break_even(
        db_session,
        position.position_id,
        4300.0,
    )

    assert protected is not None
    assert protected.break_even_applied == 1
    assert protected.current_stop_loss == 4300.0
    assert protected.management_status == "protected"

    reduced = PositionRepository.mark_partial_close(
        db_session,
        position.position_id,
        0.50,
    )

    assert reduced is not None
    assert reduced.partial_close_applied == 1
    assert reduced.remaining_quantity == 0.50
    assert reduced.quantity == 0.50

    reloaded = PositionRepository.get_by_position_id(
        db_session,
        position.position_id,
    )

    assert reloaded is not None
    assert reloaded.break_even_applied == 1
    assert reloaded.partial_close_applied == 1
    assert reloaded.remaining_quantity == 0.50
    assert reloaded.current_stop_loss == 4300.0


def test_stage_16_2_migration_is_idempotent(monkeypatch, db_session):
    """Running the migration repeatedly must leave a stable schema."""

    connection = db_session.get_bind()

    monkeypatch.setattr(
        database_migration,
        "engine",
        connection,
    )

    first = migrate_stage_16_2()
    second = migrate_stage_16_2()

    assert first["status"] == "completed"
    assert second["status"] == "completed"

    columns = {
        column["name"]
        for column in inspect(connection).get_columns("positions")
    }

    required = {
        "trade_id",
        "original_quantity",
        "initial_stop_loss",
        "take_profit_1",
        "take_profit_2",
        "risk_1r",
        "current_price",
        "current_stop_loss",
        "remaining_quantity",
        "break_even_applied",
        "partial_close_applied",
        "trailing_active",
        "management_status",
        "last_management_action",
        "last_management_time",
    }

    assert required.issubset(columns)

    indexes = inspect(connection).get_indexes("positions")

    assert any(
        index["name"] == "ix_positions_trade_id_unique"
        for index in indexes
    )
