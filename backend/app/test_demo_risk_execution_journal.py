"""Step 11D - Demo -> Risk -> Execution -> Journal validation."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.demo_trading import DemoTradingEngine
from app.execution_gateway import (
    OrderRequest,
    OrderSide,
    OrderType,
    PaperExecutionGateway,
)
from app.journal import TradeJournal
from app.models import Base
from app.risk_engine import (
    RiskConfig,
    RiskEngine,
    SymbolSpecification,
)


def _symbol_specification():
    return SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        volume_limit=100.0,
        trade_mode=4,
        trade_execution_mode=0,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="USD",
        spread=10,
        spread_float=True,
    )


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    return SessionLocal()


def test_full_demo_risk_execution_journal_flow():
    """A valid paper trade must pass every layer in order."""

    equity = 10_000.0
    entry_price = 2300.00
    stop_loss = 2290.00
    take_profit = 2320.00
    quantity = 0.10

    risk_engine = RiskEngine(
        RiskConfig(
            risk_per_trade_percent=1.0,
            max_daily_loss_percent=3.0,
            max_open_positions=3,
            max_total_exposure_percent=5.0,
            require_stop_loss=True,
            min_risk_reward=1.5,
        )
    )

    specification = _symbol_specification()

    proposed_exposure = (
        entry_price * quantity
    )

    decision = risk_engine.pre_trade_check(
        equity=equity,
        daily_loss=0.0,
        open_positions=0,
        current_exposure=0.0,
        proposed_exposure=proposed_exposure,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        take_profit_price=take_profit,
        volume=quantity,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is True
    assert decision.reason == "Risk checks passed."

    gateway = PaperExecutionGateway(
        live_trading_enabled=False,
    )

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=quantity,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    import asyncio

    execution = asyncio.run(
        gateway.execute(order)
    )

    assert execution.status.value == "accepted"
    assert execution.execution_type == "paper"
    assert execution.broker == "paper"
    assert execution.symbol == "XAUUSD"
    assert execution.side == "buy"
    assert execution.volume == quantity
    assert execution.order_id.startswith("PAPER-")

    demo_engine = DemoTradingEngine(
        initial_balance=equity,
        max_open_trades=3,
        max_daily_loss=300.0,
    )

    trade = demo_engine.open_trade(
        symbol="XAUUSD",
        direction="buy",
        entry_price=entry_price,
        quantity=quantity,
        stop_loss=stop_loss,
        take_profit=take_profit,
        trade_id=execution.order_id,
    )

    assert trade.trade_id == execution.order_id
    assert trade.symbol == "XAUUSD"
    assert trade.direction == "buy"
    assert trade.execution_type == "paper"
    assert trade.status == "open"

    session = _session()

    try:
        journal = TradeJournal(session)

        journal_row = journal.save_demo_trade(
            trade
        )

        assert journal_row.trade_id == execution.order_id
        assert journal_row.symbol == "XAUUSD"
        assert journal_row.execution_type == "paper"
        assert journal_row.status.value == "open"

        closed_trade = demo_engine.close_trade(
            execution.order_id,
            2310.00,
        )

        assert closed_trade.status == "closed"
        assert closed_trade.pnl == 1.0

        updated_row = journal.sync_demo_trade(
            closed_trade
        )

        assert updated_row.trade_id == execution.order_id
        assert updated_row.status.value == "closed"
        assert updated_row.exit_price == 2310.00
        assert updated_row.pnl == 1.0
        assert updated_row.execution_type == "paper"

        rows, total = journal.list_trades(
            execution_type="paper"
        )

        assert total == 1
        assert len(rows) == 1
        assert rows[0].trade_id == execution.order_id
        assert rows[0].status.value == "closed"

    finally:
        session.close()


def test_risk_rejection_stops_before_execution():
    """A rejected risk decision must never reach the execution gateway."""

    risk_engine = RiskEngine()

    specification = _symbol_specification()

    decision = risk_engine.pre_trade_check(
        equity=10_000.0,
        daily_loss=500.0,
        open_positions=0,
        current_exposure=0.0,
        proposed_exposure=1_000.0,
        entry_price=2300.00,
        stop_loss_price=2290.00,
        take_profit_price=2320.00,
        volume=0.10,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is False
    assert "daily loss" in decision.reason.lower()


def test_execution_is_paper_only():
    """The execution gateway must never turn a paper request into live execution."""

    gateway = PaperExecutionGateway(
        live_trading_enabled=False,
    )

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.10,
        stop_loss=2290.00,
        take_profit=2320.00,
    )

    import asyncio

    result = asyncio.run(
        gateway.execute(order)
    )

    assert result.status.value == "accepted"
    assert result.execution_type == "paper"
    assert result.broker == "paper"
    assert result.order_id.startswith("PAPER-")


def test_journal_rejects_non_paper_trade():
    """The journal must refuse a trade marked as live."""

    from app.demo_trading import DemoTrade
    from app.journal import TradeJournalError

    session = _session()

    try:
        journal = TradeJournal(session)

        trade = DemoTrade(
            trade_id="LIVE-TEST-001",
            symbol="XAUUSD",
            direction="buy",
            entry_price=2300.00,
            quantity=0.10,
            execution_type="live",
        )

        try:
            journal.save_demo_trade(trade)
        except TradeJournalError as exc:
            assert "only accepts paper trades" in str(
                exc
            ).lower()
        else:
            raise AssertionError(
                "Live trade was incorrectly accepted by the journal."
            )

    finally:
        session.close()


def test_demo_trade_remains_paper():
    """Demo trades must explicitly remain paper trades."""

    demo_engine = DemoTradingEngine(
        initial_balance=10_000.0,
        max_open_trades=3,
        max_daily_loss=300.0,
    )

    trade = demo_engine.open_trade(
        symbol="XAUUSD",
        direction="sell",
        entry_price=2300.00,
        quantity=0.10,
        stop_loss=2310.00,
        take_profit=2280.00,
        trade_id="PAPER-11D-001",
    )

    assert trade.execution_type == "paper"
    assert trade.status == "open"

    closed = demo_engine.close_trade(
        "PAPER-11D-001",
        2290.00,
    )

    assert closed.execution_type == "paper"
    assert closed.status == "closed"
    assert closed.pnl == 1.0
