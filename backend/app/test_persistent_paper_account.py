"""Stage 19 persistent paper-account tests."""

from app.models import Base, PositionStatus, TradeDirection
from app.position_repository import PositionRepository
from app.persistent_paper_account import (
    PAPER_STARTING_BALANCE,
    build_persistent_paper_account,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest


@pytest.fixture()
def persistent_account_db(tmp_path, monkeypatch):
    path = tmp_path / "stage19_account.db"
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(
        "app.persistent_paper_account.SessionLocal",
        Session,
    )
    db = Session()
    try:
        yield db, engine
    finally:
        db.close()
        engine.dispose()


def _position(db, pid, tid):
    return PositionRepository.create(
        db,
        position_id=pid,
        trade_id=tid,
        symbol="XAUUSD",
        direction=TradeDirection.BUY,
        entry_price=4300.0,
        original_quantity=1.0,
        initial_stop_loss=4298.0,
        take_profit_1=4305.0,
        risk_1r=2.0,
    )


def test_persistent_account_uses_closed_position_pnl(
    persistent_account_db,
):
    db, _ = persistent_account_db

    position = _position(db, "ACC-CLOSED", "ACC-TRADE-CLOSED")
    PositionRepository.close(
        db,
        position.position_id,
        exit_price=4305.0,
    )

    account = build_persistent_paper_account()

    assert account["starting_balance"] == PAPER_STARTING_BALANCE
    assert account["realized_pnl"] == 5.0
    assert account["balance"] == 10005.0
    assert account["unrealized_pnl"] == 0.0
    assert account["equity"] == 10005.0


def test_persistent_account_includes_open_pnl_in_equity(
    persistent_account_db,
):
    db, _ = persistent_account_db

    position = _position(db, "ACC-OPEN", "ACC-TRADE-OPEN")
    position.current_price = 4310.0
    position.pnl = 10.0
    db.commit()

    account = build_persistent_paper_account()

    assert account["realized_pnl"] == 0.0
    assert account["unrealized_pnl"] == 10.0
    assert account["balance"] == 10000.0
    assert account["equity"] == 10010.0
    assert account["open_positions"] == 1.0
