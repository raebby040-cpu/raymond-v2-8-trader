"""
RAYMOND v2.8 - DEMO Canonical Synchronization Tests

Batch 2.

Verifies that MT5 DEMO broker state becomes persistent Raymond
canonical state and that running XAUUSD P/L is calculated correctly.
"""

from types import SimpleNamespace

import pytest

from app.canonical_state import (
    CanonicalTradingPosition,
    TradingAccountSnapshot,
)
from app.demo_canonical_sync import (
    DemoCanonicalSyncError,
    synchronize_demo_position,
    synchronize_demo_positions,
)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def __init__(
        self,
        *,
        account=None,
        positions=None,
    ):
        self._account = account or {
            "login": 123456,
            "trade_mode": 0,
            "balance": 1000.0,
            "equity": 1010.0,
            "margin": 0.0,
            "margin_free": 1010.0,
            "currency": "USD",
            "server": "Exness-MT5Demo",
            "company": "Exness",
        }

        self._positions = (
            positions
            if positions is not None
            else []
        )

    def account_info(self):
        return SimpleNamespace(
            **self._account
        )

    def positions_get(self):
        return tuple(
            self._positions
        )


def make_position(
    *,
    ticket=1001,
    symbol="XAUUSD",
    side="buy",
    volume=0.02,
    entry=2051.0,
    current=2056.0,
    sl=2046.0,
    tp=2061.0,
):
    position_type = (
        FakeMT5.POSITION_TYPE_BUY
        if side == "buy"
        else FakeMT5.POSITION_TYPE_SELL
    )

    return SimpleNamespace(
        ticket=ticket,
        symbol=symbol,
        type=position_type,
        volume=volume,
        price_open=entry,
        price_current=current,
        sl=sl,
        tp=tp,
        magic=28001703,
        comment="RAYMOND-DEMO-SIGNAL",
    )


@pytest.fixture
def clean_canonical_tables():
    """
    Remove only the test-created canonical rows.

    The existing application schema is preserved.
    """

    from app.database import SessionLocal

    db = SessionLocal()

    try:
        db.query(
            CanonicalTradingPosition
        ).delete(
            synchronize_session=False
        )

        db.query(
            TradingAccountSnapshot
        ).delete(
            synchronize_session=False
        )

        db.commit()

    finally:
        db.close()

    yield

    db = SessionLocal()

    try:
        db.query(
            CanonicalTradingPosition
        ).delete(
            synchronize_session=False
        )

        db.query(
            TradingAccountSnapshot
        ).delete(
            synchronize_session=False
        )

        db.commit()

    finally:
        db.close()


def test_demo_position_is_created_in_canonical_state(
    clean_canonical_tables,
):
    fake_mt5 = FakeMT5(
        positions=[
            make_position(
                ticket=1001,
                entry=2051.0,
                current=2056.0,
                volume=0.02,
            )
        ]
    )

    result = synchronize_demo_positions(
        mt5_module=fake_mt5
    )

    assert result["status"] == "ok"
    assert result["mode"] == "demo"
    assert result["created_positions"] == 1
    assert result["updated_positions"] == 0
    assert result["open_positions"] == 1

    from app.database import SessionLocal
    from app.canonical_state import (
        TradingStateRepository,
    )

    db = SessionLocal()

    try:
        repository = TradingStateRepository(
            db
        )

        position = (
            repository.get_position_by_ticket(
                mode="demo",
                broker_position_ticket="1001",
            )
        )

        assert position is not None
        assert position.symbol == "XAUUSD"
        assert position.side == "buy"
        assert position.volume == pytest.approx(
            0.02
        )
        assert position.entry_price == pytest.approx(
            2051.0
        )
        assert position.current_price == pytest.approx(
            2056.0
        )

        assert position.unrealized_pnl == pytest.approx(
            10.0
        )

        assert position.total_pnl == pytest.approx(
            10.0
        )

        assert position.reconciliation_status == (
            "synchronized"
        )

    finally:
        db.close()


def test_existing_demo_position_updates_running_pnl(
    clean_canonical_tables,
):
    fake_mt5_initial = FakeMT5(
        positions=[
            make_position(
                ticket=1002,
                entry=2051.0,
                current=2053.0,
                volume=0.02,
            )
        ]
    )

    first = synchronize_demo_positions(
        mt5_module=fake_mt5_initial
    )

    assert first["created_positions"] == 1

    fake_mt5_updated = FakeMT5(
        positions=[
            make_position(
                ticket=1002,
                entry=2051.0,
                current=2056.0,
                volume=0.02,
            )
        ]
    )

    second = synchronize_demo_positions(
        mt5_module=fake_mt5_updated
    )

    assert second["created_positions"] == 0
    assert second["updated_positions"] == 1

    from app.database import SessionLocal
    from app.canonical_state import (
        TradingStateRepository,
    )

    db = SessionLocal()

    try:
        repository = TradingStateRepository(
            db
        )

        position = (
            repository.get_position_by_ticket(
                mode="demo",
                broker_position_ticket="1002",
            )
        )

        assert position is not None

        assert position.current_price == pytest.approx(
            2056.0
        )

        assert position.unrealized_pnl == pytest.approx(
            10.0
        )

        assert position.total_pnl == pytest.approx(
            10.0
        )

    finally:
        db.close()


def test_demo_account_equity_is_persisted(
    clean_canonical_tables,
):
    fake_mt5 = FakeMT5(
        account={
            "login": 555555,
            "trade_mode": 0,
            "balance": 1000.0,
            "equity": 1010.0,
            "margin": 100.0,
            "margin_free": 910.0,
            "currency": "USD",
            "server": "Exness-MT5Demo",
            "company": "Exness",
        },
        positions=[
            make_position(
                ticket=1003,
                entry=2051.0,
                current=2056.0,
            )
        ],
    )

    result = synchronize_demo_positions(
        mt5_module=fake_mt5
    )

    assert result["balance"] == pytest.approx(
        1000.0
    )

    assert result["equity"] == pytest.approx(
        1010.0
    )

    assert result["floating_pnl"] == pytest.approx(
        10.0
    )

    from app.database import SessionLocal
    from app.canonical_state import (
        TradingStateRepository,
    )

    db = SessionLocal()

    try:
        repository = TradingStateRepository(
            db
        )

        account = (
            repository.get_latest_account(
                mode="demo"
            )
        )

        assert account is not None
        assert account.balance == pytest.approx(
            1000.0
        )
        assert account.equity == pytest.approx(
            1010.0
        )
        assert account.floating_pnl == pytest.approx(
            10.0
        )
        assert account.open_positions == 1

    finally:
        db.close()


def test_real_account_is_rejected(
    clean_canonical_tables,
):
    fake_mt5 = FakeMT5(
        account={
            "login": 999999,
            "trade_mode": 1,
            "balance": 1000.0,
            "equity": 1000.0,
            "margin": 0.0,
            "margin_free": 1000.0,
            "currency": "USD",
            "server": "Real",
            "company": "Exness",
        },
        positions=[],
    )

    with pytest.raises(
        DemoCanonicalSyncError
    ):
        synchronize_demo_positions(
            mt5_module=fake_mt5
        )


def test_single_verified_position_sync(
    clean_canonical_tables,
):
    fake_mt5 = FakeMT5()

    position = make_position(
        ticket=1004,
        entry=2051.0,
        current=2056.0,
        volume=0.02,
    )

    result = synchronize_demo_position(
        position=position,
        account_info=fake_mt5._account,
        mt5_module=fake_mt5,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "demo"
    assert result["broker_position_ticket"] == "1004"
    assert result["unrealized_pnl"] == pytest.approx(
        10.0
    )
    assert result["total_pnl"] == pytest.approx(
        10.0
  )
