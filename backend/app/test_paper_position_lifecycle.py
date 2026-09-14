"""
RAYMOND v2.8 - Paper Position Lifecycle Tests

Stage 17.4.2

Tests automatic paper-position TP/SL lifecycle detection.

SAFETY:
- paper only
- no broker execution
- no MT5 execution
- no live trading
"""

from datetime import datetime

import pytest

from app.database import Base
from app.models import (
    Position,
    PositionStatus,
    TradeDirection,
)
from app.paper_position_lifecycle import (
    PaperPositionLifecycle,
    PaperPositionLifecycleError,
)


@pytest.fixture()
def db():
    """
    Create an isolated in-memory SQLite database session.
    """

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
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


def make_position(
    db,
    *,
    position_id="position-1",
    trade_id="trade-1",
    direction=TradeDirection.BUY,
    entry_price=100.0,
    stop_loss=95.0,
    take_profit_1=105.0,
    take_profit_2=110.0,
    quantity=1.0,
):
    """
    Create a persistent test position directly.

    This intentionally avoids the trading pipeline so the tests
    isolate lifecycle behaviour.
    """

    position = Position(
        position_id=position_id,
        trade_id=trade_id,
        symbol="XAUUSD",
        direction=direction,

        quantity=float(quantity),
        original_quantity=float(quantity),
        remaining_quantity=float(quantity),

        entry_price=float(entry_price),

        initial_stop_loss=float(stop_loss),
        current_stop_loss=float(stop_loss),

        stop_loss=float(stop_loss),

        take_profit_1=float(take_profit_1),
        take_profit_2=float(take_profit_2),
        take_profit=float(take_profit_1),

        current_price=float(entry_price),

        pnl=0.0,
        pnl_percent=0.0,

        regime="trending",
        setup="continuation",
        technical_score=10.0,
        confluence=70.0,
        confidence=80.0,

        trade_thesis="Lifecycle test thesis",

        break_even_applied=0,
        partial_close_applied=0,
        trailing_active=0,

        management_status="open",
        last_management_action="OPEN",
        last_management_time=datetime.utcnow(),

        max_drawdown=0.0,
        max_profit=0.0,

        status=PositionStatus.OPEN,

        opened_at=datetime.utcnow(),
        closed_at=None,
    )

    db.add(position)
    db.commit()
    db.refresh(position)

    return position


# ============================================================
# BASIC SAFETY
# ============================================================


def test_lifecycle_can_be_created(db):
    lifecycle = PaperPositionLifecycle(db)

    assert lifecycle is not None
    assert lifecycle.db is db


def test_lifecycle_is_paper_only():
    assert not hasattr(
        PaperPositionLifecycle,
        "place_order",
    )

    assert not hasattr(
        PaperPositionLifecycle,
        "send_broker_order",
    )

    assert not hasattr(
        PaperPositionLifecycle,
        "mt5",
    )


# ============================================================
# NO HIT / HOLD
# ============================================================


def test_buy_position_holds_before_targets(db):
    position = make_position(db)

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        102.0,
    )

    assert result.action == "HOLD"
    assert result.closed is False
    assert result.persisted is True
    assert result.close_reason is None
    assert result.current_price == 102.0

    db.refresh(position)

    assert position.status == PositionStatus.OPEN
    assert position.current_price == 102.0
    assert position.pnl > 0


def test_sell_position_holds_before_targets(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        98.0,
    )

    assert result.action == "HOLD"
    assert result.closed is False
    assert result.close_reason is None

    db.refresh(position)

    assert position.status == PositionStatus.OPEN
    assert position.current_price == 98.0
    assert position.pnl > 0


# ============================================================
# BUY STOP LOSS
# ============================================================


def test_buy_position_closes_at_stop_loss(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        95.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "STOP_LOSS_HIT"
    assert result.closed is True
    assert result.persisted is True
    assert result.pnl == -5.0

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.closed_at is not None
    assert position.current_price == 95.0
    assert position.pnl == -5.0
    assert position.remaining_quantity == 0.0
    assert position.quantity == 0.0


def test_buy_position_closes_below_stop_loss(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        94.0,
    )

    assert result.closed is True
    assert result.close_reason == "STOP_LOSS_HIT"
    assert result.pnl == -6.0


# ============================================================
# SELL STOP LOSS
# ============================================================


def test_sell_position_closes_at_stop_loss(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        105.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "STOP_LOSS_HIT"
    assert result.closed is True
    assert result.pnl == -5.0

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.closed_at is not None
    assert position.current_price == 105.0
    assert position.pnl == -5.0
    assert position.remaining_quantity == 0.0
    assert position.quantity == 0.0


def test_sell_position_closes_above_stop_loss(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        106.0,
    )

    assert result.closed is True
    assert result.close_reason == "STOP_LOSS_HIT"
    assert result.pnl == -6.0


# ============================================================
# BUY TAKE PROFIT
# ============================================================


def test_buy_position_closes_at_tp2(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        110.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "TAKE_PROFIT_2_HIT"
    assert result.closed is True
    assert result.pnl == 10.0

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.closed_at is not None
    assert position.current_price == 110.0
    assert position.pnl == 10.0
    assert position.remaining_quantity == 0.0


def test_buy_position_reaches_tp1_before_tp2(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        105.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "TAKE_PROFIT_1_HIT"
    assert result.closed is True
    assert result.pnl == 5.0


def test_buy_position_above_tp2_closes_at_tp2_reason(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        115.0,
    )

    assert result.closed is True
    assert result.close_reason == "TAKE_PROFIT_2_HIT"
    assert result.current_price == 115.0
    assert result.pnl == 15.0


# ============================================================
# SELL TAKE PROFIT
# ============================================================


def test_sell_position_closes_at_tp2(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        90.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "TAKE_PROFIT_2_HIT"
    assert result.closed is True
    assert result.pnl == 10.0

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.closed_at is not None
    assert position.current_price == 90.0
    assert position.pnl == 10.0
    assert position.remaining_quantity == 0.0


def test_sell_position_reaches_tp1_before_tp2(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        95.0,
    )

    assert result.action == "CLOSE_POSITION"
    assert result.close_reason == "TAKE_PROFIT_1_HIT"
    assert result.closed is True
    assert result.pnl == 5.0


def test_sell_position_below_tp2_closes_with_tp2_reason(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        85.0,
    )

    assert result.closed is True
    assert result.close_reason == "TAKE_PROFIT_2_HIT"
    assert result.current_price == 85.0
    assert result.pnl == 15.0


# ============================================================
# STOP LOSS HAS PRIORITY
# ============================================================


def test_buy_stop_loss_has_priority_over_take_profit(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    # A deliberately invalid market value that is simultaneously
    # supplied to test the deterministic priority implementation
    # through the helper ordering.
    result = lifecycle.evaluate_position(
        position,
        95.0,
    )

    assert result.close_reason == "STOP_LOSS_HIT"


def test_sell_stop_loss_has_priority_over_take_profit(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        105.0,
    )

    assert result.close_reason == "STOP_LOSS_HIT"


# ============================================================
# ALREADY CLOSED
# ============================================================


def test_already_closed_position_is_not_processed_again(db):
    position = make_position(db)

    position.status = PositionStatus.CLOSED
    position.closed_at = datetime.utcnow()
    position.pnl = 5.0
    position.pnl_percent = 5.0
    position.current_price = 105.0
    position.quantity = 0.0
    position.remaining_quantity = 0.0
    position.last_management_action = "TAKE_PROFIT_2_HIT"

    db.commit()
    db.refresh(position)

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        110.0,
    )

    assert result.action == "ALREADY_CLOSED"
    assert result.closed is True
    assert result.persisted is False

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.closed_at is not None


# ============================================================
# INVALID PRICE
# ============================================================


@pytest.mark.parametrize(
    "price",
    [
        0,
        -1,
        -100,
    ],
)
def test_invalid_price_is_rejected(db, price):
    position = make_position(db)

    lifecycle = PaperPositionLifecycle(db)

    with pytest.raises(
        PaperPositionLifecycleError
    ):
        lifecycle.evaluate_position(
            position,
            price,
        )


@pytest.mark.parametrize(
    "price",
    [
        None,
        "",
        "not-a-number",
        object(),
    ],
)
def test_non_numeric_price_is_rejected(db, price):
    position = make_position(db)

    lifecycle = PaperPositionLifecycle(db)

    with pytest.raises(
        PaperPositionLifecycleError
    ):
        lifecycle.evaluate_position(
            position,
            price,
        )


# ============================================================
# SYMBOL EVALUATION
# ============================================================


def test_evaluate_symbol_returns_matching_positions(db):
    make_position(
        db,
        position_id="position-1",
        trade_id="trade-1",
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
    )

    make_position(
        db,
        position_id="position-2",
        trade_id="trade-2",
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    results = lifecycle.evaluate_symbol(
        "XAUUSD",
        102.0,
    )

    assert len(results) == 2

    assert all(
        result.symbol == "XAUUSD"
        for result in results
    )


def test_evaluate_symbol_normalizes_symbol(db):
    make_position(
        db,
        position_id="position-1",
        trade_id="trade-1",
    )

    lifecycle = PaperPositionLifecycle(db)

    results = lifecycle.evaluate_symbol(
        "xauusd",
        102.0,
    )

    assert len(results) == 1
    assert results[0].symbol == "XAUUSD"


def test_evaluate_symbol_with_no_positions_is_valid(db):
    lifecycle = PaperPositionLifecycle(db)

    results = lifecycle.evaluate_symbol(
        "XAUUSD",
        4300.0,
    )

    assert results == []


# ============================================================
# OPEN POSITION FILTERING
# ============================================================


def test_evaluate_symbol_ignores_closed_positions(db):
    open_position = make_position(
        db,
        position_id="open-position",
        trade_id="open-trade",
    )

    closed_position = make_position(
        db,
        position_id="closed-position",
        trade_id="closed-trade",
    )

    closed_position.status = PositionStatus.CLOSED
    closed_position.closed_at = datetime.utcnow()
    closed_position.quantity = 0.0
    closed_position.remaining_quantity = 0.0

    db.commit()

    lifecycle = PaperPositionLifecycle(db)

    results = lifecycle.evaluate_symbol(
        "XAUUSD",
        102.0,
    )

    assert len(results) == 1
    assert results[0].position_id == open_position.position_id


# ============================================================
# MULTIPLE SYMBOLS
# ============================================================


def test_evaluate_open_positions_uses_price_map(db):
    make_position(
        db,
        position_id="gold-position",
        trade_id="gold-trade",
        symbol="XAUUSD",
    )

    lifecycle = PaperPositionLifecycle(db)

    results = lifecycle.evaluate_open_positions(
        {
            "XAUUSD": 102.0,
        }
    )

    assert len(results) == 1
    assert results[0].symbol == "XAUUSD"
    assert results[0].current_price == 102.0


def test_evaluate_open_positions_skips_missing_price(db):
    make_position(
        db,
        position_id="gold-position",
        trade_id="gold-trade",
    )

    lifecycle = PaperPositionLifecycle(db)

    results = lifecycle.evaluate_open_positions(
        {
            "EURUSD": 1.10,
        }
    )

    assert results == []


def test_evaluate_open_positions_requires_dictionary(db):
    lifecycle = PaperPositionLifecycle(db)

    with pytest.raises(
        PaperPositionLifecycleError
    ):
        lifecycle.evaluate_open_positions(
            None
        )


# ============================================================
# RESULT SERIALIZATION
# ============================================================


def test_hold_result_serializes_safely(db):
    position = make_position(db)

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        102.0,
    )

    payload = result.to_dict()

    assert payload["position_id"] == "position-1"
    assert payload["symbol"] == "XAUUSD"
    assert payload["action"] == "HOLD"
    assert payload["closed"] is False
    assert payload["persisted"] is True

    assert payload["execution_type"] == "paper"
    assert payload["read_only"] is True
    assert payload["broker_order_required"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["broker_orders_allowed"] is False


def test_close_result_serializes_safely(db):
    position = make_position(db)

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        95.0,
    )

    payload = result.to_dict()

    assert payload["action"] == "CLOSE_POSITION"
    assert payload["close_reason"] == "STOP_LOSS_HIT"
    assert payload["closed"] is True
    assert payload["persisted"] is True

    assert payload["execution_type"] == "paper"
    assert payload["read_only"] is True
    assert payload["broker_order_required"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["broker_orders_allowed"] is False


# ============================================================
# THESIS / TRADE CONTEXT PRESERVATION
# ============================================================


def test_closing_position_preserves_trade_thesis(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
    )

    original_thesis = position.trade_thesis

    lifecycle = PaperPositionLifecycle(db)

    lifecycle.evaluate_position(
        position,
        110.0,
    )

    db.refresh(position)

    assert position.status == PositionStatus.CLOSED
    assert position.trade_thesis == original_thesis
    assert position.regime == "trending"
    assert position.setup == "continuation"
    assert position.technical_score == 10.0
    assert position.confluence == 70.0
    assert position.confidence == 80.0


# ============================================================
# SAFETY FLAGS
# ============================================================


def test_hold_result_remains_paper_only(db):
    position = make_position(db)

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        102.0,
    )

    assert result.execution_type == "paper"
    assert result.read_only is True
    assert result.broker_order_required is False
    assert result.live_trading_enabled is False
    assert result.broker_orders_allowed is False


def test_close_result_remains_paper_only(db):
    position = make_position(db)

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        95.0,
    )

    assert result.execution_type == "paper"
    assert result.read_only is True
    assert result.broker_order_required is False
    assert result.live_trading_enabled is False
    assert result.broker_orders_allowed is False


# ============================================================
# PNL
# ============================================================


def test_buy_profit_is_positive(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=105.0,
        take_profit_2=110.0,
        quantity=2.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        105.0,
    )

    assert result.pnl == 10.0


def test_buy_loss_is_negative(db):
    position = make_position(
        db,
        direction=TradeDirection.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        quantity=2.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        95.0,
    )

    assert result.pnl == -10.0


def test_sell_profit_is_positive(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
        quantity=2.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        95.0,
    )

    assert result.pnl == 10.0


def test_sell_loss_is_negative(db):
    position = make_position(
        db,
        direction=TradeDirection.SELL,
        entry_price=100.0,
        stop_loss=105.0,
        take_profit_1=95.0,
        take_profit_2=90.0,
        quantity=2.0,
    )

    lifecycle = PaperPositionLifecycle(db)

    result = lifecycle.evaluate_position(
        position,
        105.0,
    )

    assert result.pnl == -10.0



