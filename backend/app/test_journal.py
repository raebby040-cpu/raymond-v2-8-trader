"""
RAYMOND v2.8 - Trade Journal Tests

Step 10A:
- Tests demo/paper trade persistence.
- Tests journal updates and synchronization.
- Tests pagination and execution-type filtering.
- Confirms live trades are rejected.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.demo_trading import (
    DemoTradingEngine,
    DemoTradingError,
)
from app.journal import (
    TradeJournal,
    TradeJournalError,
)
from app.models import Base


@pytest.fixture
def db_session():
    """Create an isolated in-memory database for each test."""

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(engine)

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
        engine.dispose()


@pytest.fixture
def demo_engine():
    """Create a safe demo-only trading engine."""

    return DemoTradingEngine(
        initial_balance=10_000.0,
        max_open_trades=3,
        max_daily_loss=300.0,
    )


@pytest.fixture
def journal(db_session):
    """Create a journal using the isolated database."""

    return TradeJournal(db_session)


def create_demo_trade(
    demo_engine,
    *,
    trade_id="DEMO-001",
    direction="buy",
    symbol="XAUUSD",
    entry_price=2000.0,
    quantity=0.10,
):
    """Open one demo trade for testing."""

    return demo_engine.open_trade(
        trade_id=trade_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        quantity=quantity,
    )


def test_journal_accepts_paper_trade(
    journal,
    demo_engine,
):
    """A demo trade must be persisted as a paper trade."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-001",
    )

    row = journal.save_demo_trade(trade)

    assert row.trade_id == "DEMO-001"
    assert row.symbol == "XAUUSD"
    assert row.execution_type == "paper"
    assert row.entry_price == 2000.0
    assert row.quantity == 0.10


def test_journal_rejects_non_paper_trade(
    journal,
):
    """The Step 10A journal must reject live execution types."""

    class FakeTrade:
        trade_id = "LIVE-001"
        symbol = "XAUUSD"
        direction = "buy"
        entry_price = 2000.0
        exit_price = None
        quantity = 0.10
        pnl = 0.0
        status = "open"
        execution_type = "live"
        opened_at = datetime.now(timezone.utc)
        closed_at = None
        stop_loss = None
        take_profit = None

    with pytest.raises(TradeJournalError):
        journal.save_demo_trade(
            FakeTrade()
        )


def test_journal_prevents_duplicate_trade(
    journal,
    demo_engine,
):
    """Saving the same trade twice must not create duplicate rows."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-DUPLICATE",
    )

    first = journal.save_demo_trade(trade)
    second = journal.save_demo_trade(trade)

    assert first.trade_id == second.trade_id

    rows, total = journal.list_trades()

    assert total == 1
    assert len(rows) == 1


def test_journal_updates_closed_trade(
    journal,
    demo_engine,
):
    """Closing a demo trade must update the journal entry."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-CLOSE",
        direction="buy",
        entry_price=2000.0,
        quantity=0.10,
    )

    journal.save_demo_trade(trade)

    closed_trade = demo_engine.close_trade(
        trade_id="DEMO-CLOSE",
        exit_price=2010.0,
    )

    row = journal.update_demo_trade(
        closed_trade
    )

    assert row.trade_id == "DEMO-CLOSE"
    assert row.status.value == "closed"
    assert row.exit_price == 2010.0
    assert row.pnl > 0


def test_sync_demo_trade_inserts_missing_trade(
    journal,
    demo_engine,
):
    """sync_demo_trade must insert a missing trade."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-SYNC-NEW",
    )

    row = journal.sync_demo_trade(trade)

    assert row.trade_id == "DEMO-SYNC-NEW"

    rows, total = journal.list_trades()

    assert total == 1
    assert len(rows) == 1


def test_sync_demo_trade_updates_existing_trade(
    journal,
    demo_engine,
):
    """sync_demo_trade must update an existing journal row."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-SYNC-UPDATE",
        entry_price=2000.0,
    )

    journal.sync_demo_trade(trade)

    closed_trade = demo_engine.close_trade(
        trade_id="DEMO-SYNC-UPDATE",
        exit_price=2020.0,
    )

    row = journal.sync_demo_trade(
        closed_trade
    )

    assert row.trade_id == "DEMO-SYNC-UPDATE"
    assert row.status.value == "closed"
    assert row.exit_price == 2020.0
    assert row.pnl > 0

    rows, total = journal.list_trades()

    assert total == 1
    assert len(rows) == 1


def test_journal_calculates_pnl_percent(
    journal,
    demo_engine,
):
    """Journal should calculate P&L percentage from entry notional."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-PERCENT",
        entry_price=2000.0,
        quantity=1.0,
    )

    closed_trade = demo_engine.close_trade(
        trade_id="DEMO-PERCENT",
        exit_price=2020.0,
    )

    row = journal.save_demo_trade(
        closed_trade
    )

    assert row.pnl == 20.0
    assert row.pnl_percent == pytest.approx(1.0)


def test_journal_lists_trades_with_pagination(
    journal,
    demo_engine,
):
    """Journal listing must support limit and offset."""

    for index in range(5):
        trade = create_demo_trade(
            demo_engine,
            trade_id=f"DEMO-PAGE-{index}",
            entry_price=2000.0 + index,
        )

        journal.save_demo_trade(trade)

    rows, total = journal.list_trades(
        limit=2,
        offset=0,
    )

    assert total == 5
    assert len(rows) == 2

    rows, total = journal.list_trades(
        limit=2,
        offset=2,
    )

    assert total == 5
    assert len(rows) == 2


def test_journal_filters_paper_trades(
    journal,
    demo_engine,
):
    """Execution-type filtering must return paper trades."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-PAPER-FILTER",
    )

    journal.save_demo_trade(trade)

    rows, total = journal.list_trades(
        execution_type="paper",
    )

    assert total == 1
    assert len(rows) == 1
    assert rows[0].execution_type == "paper"


def test_journal_live_filter_returns_no_rows(
    journal,
    demo_engine,
):
    """There should be no live rows during Step 10A."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-NO-LIVE",
    )

    journal.save_demo_trade(trade)

    rows, total = journal.list_trades(
        execution_type="live",
    )

    assert total == 0
    assert rows == []


def test_journal_rejects_invalid_execution_type(
    journal,
):
    """Unknown execution types must fail closed."""

    with pytest.raises(TradeJournalError):
        journal.list_trades(
            execution_type="broker"
        )


def test_journal_rejects_invalid_limit(
    journal,
):
    """Journal pagination limits must be validated."""

    with pytest.raises(TradeJournalError):
        journal.list_trades(
            limit=0
        )

    with pytest.raises(TradeJournalError):
        journal.list_trades(
            limit=501
        )


def test_journal_rejects_negative_offset(
    journal,
):
    """Negative pagination offsets must be rejected."""

    with pytest.raises(TradeJournalError):
        journal.list_trades(
            offset=-1
        )


def test_serialize_trade(
    journal,
    demo_engine,
):
    """Journal rows must serialize into safe API dictionaries."""

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-SERIALIZE",
    )

    row = journal.save_demo_trade(trade)

    payload = journal.serialize_trade(row)

    assert payload["trade_id"] == "DEMO-SERIALIZE"
    assert payload["symbol"] == "XAUUSD"
    assert payload["direction"] == "buy"
    assert payload["execution_type"] == "paper"
    assert payload["status"] == "open"


def test_journal_order_is_newest_first(
    journal,
    demo_engine,
):
    """Journal entries should be returned newest first."""

    first_trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-ORDER-1",
    )

    journal.save_demo_trade(
        first_trade
    )

    second_trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-ORDER-2",
    )

    journal.save_demo_trade(
        second_trade
    )

    rows, total = journal.list_trades()

    assert total == 2
    assert len(rows) == 2

    assert rows[0].trade_id == "DEMO-ORDER-2"
    assert rows[1].trade_id == "DEMO-ORDER-1"


def test_closed_trade_preserves_stop_loss_and_take_profit(
    journal,
    demo_engine,
):
    """SL and TP values must be persisted."""

    trade = demo_engine.open_trade(
        trade_id="DEMO-SLTP",
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        quantity=0.10,
        stop_loss=1990.0,
        take_profit=2020.0,
    )

    closed_trade = demo_engine.close_trade(
        trade_id="DEMO-SLTP",
        exit_price=2010.0,
    )

    row = journal.save_demo_trade(
        closed_trade
    )

    assert row.stop_loss == 1990.0
    assert row.take_profit == 2020.0


def test_journal_does_not_execute_orders(
    journal,
    demo_engine,
):
    """
    Saving a journal entry must only persist data.

    It must not interact with MT5, Exness,
    or any real broker.
    """

    trade = create_demo_trade(
        demo_engine,
        trade_id="DEMO-SAFETY",
    )

    row = journal.save_demo_trade(trade)

    assert row.execution_type == "paper"
    assert trade.execution_type == "paper"


def test_invalid_demo_trade_direction_fails(
    journal,
):
    """Invalid trade directions must be rejected."""

    class FakeTrade:
        trade_id = "BAD-DIRECTION"
        symbol = "XAUUSD"
        direction = "hold"
        entry_price = 2000.0
        exit_price = None
        quantity = 0.10
        pnl = 0.0
        status = "open"
        execution_type = "paper"
        opened_at = datetime.now(timezone.utc)
        closed_at = None
        stop_loss = None
        take_profit = None

    with pytest.raises(TradeJournalError):
        journal.save_demo_trade(
            FakeTrade()
        )


def test_empty_journal_has_zero_total(
    journal,
):
    """A new journal must start empty."""

    rows, total = journal.list_trades()

    assert rows == []
    assert total == 0
