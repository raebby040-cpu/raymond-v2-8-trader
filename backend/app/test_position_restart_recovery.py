"""
RAYMOND v2.8 - Stage 16.2 Restart / Recovery Tests

These tests verify that persistent position state survives the
lifecycle of a database session.

The test intentionally closes the original SQLAlchemy session and
creates a completely new session against the same SQLite database.

This simulates the persistence boundary required after an application
restart without contacting MT5, a broker, or live trading services.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

try:
    from .models import Base, PositionStatus, TradeDirection
    from .position_repository import PositionRepository
except ImportError:
    from models import Base, PositionStatus, TradeDirection
    from position_repository import PositionRepository


@pytest.fixture()
def persistent_db(tmp_path: Path):
    """
    Create a file-backed SQLite database.

    A file-backed database is intentional here. An in-memory database
    would disappear when the original database connection/session is
    closed and therefore would not test restart persistence.
    """

    database_path = tmp_path / "raymond_restart_test.db"

    engine = create_engine(
        f"sqlite:///{database_path}",
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
        yield database_path, engine, SessionLocal, db
    finally:
        db.close()
        engine.dispose()


def test_position_survives_database_session_restart(
    persistent_db,
):
    """
    A persistent open position must remain recoverable after the
    original database session is closed and a new session is created.
    """

    (
        database_path,
        engine,
        SessionLocal,
        db,
    ) = persistent_db

    position = PositionRepository.create(
        db,
        position_id="POS-RESTART-001",
        trade_id="PAPER-RESTART-001",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=4300.0,
        original_quantity=1.0,
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

    assert position.status == PositionStatus.OPEN

    # Simulate normal position management before restart.
    PositionRepository.mark_break_even(
        db,
        position.position_id,
        4300.0,
    )

    PositionRepository.mark_partial_close(
        db,
        position.position_id,
        0.50,
    )

    PositionRepository.update_price(
        db,
        position.position_id,
        4310.0,
    )

    # Capture the persistent database path before closing everything.
    assert database_path.exists()

    # Simulate application/database shutdown.
    db.close()
    engine.dispose()

    # Simulate a fresh application/database startup.
    recovery_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    RecoverySession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=recovery_engine,
    )

    recovered_db = RecoverySession()

    try:
        recovered = PositionRepository.get_by_position_id(
            recovered_db,
            "POS-RESTART-001",
        )

        assert recovered is not None

        assert recovered.position_id == "POS-RESTART-001"
        assert recovered.trade_id == "PAPER-RESTART-001"
        assert recovered.symbol == "XAUUSD"

        assert recovered.direction == TradeDirection.BUY
        assert recovered.status == PositionStatus.OPEN

        assert recovered.entry_price == 4300.0
        assert recovered.original_quantity == 1.0
        assert recovered.remaining_quantity == 0.50

        # Original risk must survive restart.
        assert recovered.initial_stop_loss == 4290.0
        assert recovered.risk_1r == 10.0

        # Current management state must survive restart.
        assert recovered.current_stop_loss == 4300.0
        assert recovered.stop_loss == 4300.0
        assert recovered.break_even_applied == 1
        assert recovered.partial_close_applied == 1

        # Current market state must survive restart.
        assert recovered.current_price == 4310.0

        # After the 50% partial close, only 0.50 quantity remains.
        # Therefore:
        # (4310 - 4300) * 0.50 = 5.0
        assert recovered.pnl == 5.0
        assert recovered.max_profit == 5.0

        # Strategy context must survive restart.
        assert recovered.regime == "trending_up"
        assert recovered.setup == "bullish_continuation"
        assert recovered.technical_score == 78.0
        assert recovered.confluence == 82.0
        assert recovered.confidence == 86.0

    finally:
        recovered_db.close()
        recovery_engine.dispose()


def test_open_position_recovery_returns_only_open_positions(
    persistent_db,
):
    """
    Recovery must distinguish open positions from closed positions.
    """

    (
        database_path,
        engine,
        SessionLocal,
        db,
    ) = persistent_db

    open_position = PositionRepository.create(
        db,
        position_id="POS-RECOVERY-OPEN",
        trade_id="PAPER-RECOVERY-OPEN",
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=4300.0,
        original_quantity=0.50,
        initial_stop_loss=4290.0,
        take_profit_1=4315.0,
    )

    closed_position = PositionRepository.create(
        db,
        position_id="POS-RECOVERY-CLOSED",
        trade_id="PAPER-RECOVERY-CLOSED",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=4300.0,
        original_quantity=0.50,
        initial_stop_loss=4310.0,
        take_profit_1=4285.0,
    )

    # Close one position through the repository.
    closed = PositionRepository.close(
        db,
        closed_position.position_id,
        exit_price=4290.0,
        reason="TEST_RESTART_RECOVERY",
    )

    assert closed is not None
    assert closed.status == PositionStatus.CLOSED

    # Close the first session.
    db.close()
    engine.dispose()

    # Start a completely new session.
    recovery_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    RecoverySession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=recovery_engine,
    )

    recovered_db = RecoverySession()

    try:
        open_positions = PositionRepository.get_open_positions(
            recovered_db,
        )

        recovered_ids = {
            position.position_id
            for position in open_positions
        }

        assert open_position.position_id in recovered_ids
        assert closed_position.position_id not in recovered_ids

        recovered_open = next(
            position
            for position in open_positions
            if position.position_id
            == open_position.position_id
        )

        assert recovered_open.status == PositionStatus.OPEN
        assert recovered_open.trade_id == "PAPER-RECOVERY-OPEN"

    finally:
        recovered_db.close()
        recovery_engine.dispose()


def test_restart_recovery_does_not_create_duplicate_position(
    persistent_db,
):
    """
    Recovery must load the existing position rather than create a
    second position for the same paper trade.
    """

    (
        database_path,
        engine,
        SessionLocal,
        db,
    ) = persistent_db

    original = PositionRepository.create(
        db,
        position_id="POS-IDEMPOTENT-RESTART",
        trade_id="PAPER-IDEMPOTENT-RESTART",
        symbol="XAUUSD",
        direction=TradeDirection.SELL,
        entry_price=4300.0,
        original_quantity=0.25,
        initial_stop_loss=4310.0,
        take_profit_1=4285.0,
    )

    original_id = original.position_id

    db.close()
    engine.dispose()

    recovery_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    RecoverySession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=recovery_engine,
    )

    recovered_db = RecoverySession()

    try:
        recovered = PositionRepository.get_by_trade_id(
            recovered_db,
            "PAPER-IDEMPOTENT-RESTART",
        )

        assert recovered is not None
        assert recovered.position_id == original_id

        # Retry the same creation after the simulated restart.
        retry = PositionRepository.create(
            recovered_db,
            position_id="POS-IDEMPOTENT-RESTART-RETRY",
            trade_id="PAPER-IDEMPOTENT-RESTART",
            symbol="XAUUSD",
            direction=TradeDirection.SELL,
            entry_price=9999.0,
            original_quantity=99.0,
            initial_stop_loss=10000.0,
            take_profit_1=9000.0,
        )

        assert retry.position_id == original_id
        assert retry.entry_price == 4300.0
        assert retry.original_quantity == 0.25

        positions = PositionRepository.get_all(
            recovered_db,
            limit=100,
        )

        matching = [
            position
            for position in positions
            if position.trade_id
            == "PAPER-IDEMPOTENT-RESTART"
        ]

        assert len(matching) == 1

    finally:
        recovered_db.close()
        recovery_engine.dispose()
