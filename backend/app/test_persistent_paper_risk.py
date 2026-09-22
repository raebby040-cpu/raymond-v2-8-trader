"""Stage 18 persistent paper-risk tests."""
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, PositionStatus, TradeDirection
from app.position_repository import PositionRepository
from app.persistent_paper_risk import build_persistent_paper_risk_state
from app.risk_engine import RiskConfig, RiskEngine, SymbolSpecification

@pytest.fixture()
def persistent_risk_db(tmp_path, monkeypatch):
    path = tmp_path / "stage18.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("app.persistent_paper_risk.SessionLocal", Session)
    db = Session()
    try: yield db, engine
    finally: db.close(); engine.dispose()

def pos(db, pid, tid, entry=4300.0, sl=4298.0, qty=1.0):
    return PositionRepository.create(db, position_id=pid, trade_id=tid, symbol="XAUUSD", direction=TradeDirection.BUY, entry_price=entry, original_quantity=qty, initial_stop_loss=sl, take_profit_1=4305.0, risk_1r=abs(entry-sl))

def spec():
    return SymbolSpecification(symbol="XAUUSD", digits=2, point=.01, tick_size=.01, tick_value=1., tick_value_profit=1., tick_value_loss=1., contract_size=100., volume_min=.01, volume_max=100., volume_step=.01, volume_limit=100., trade_mode=4, trade_execution_mode=0, trade_stops_level=0, trade_freeze_level=0, currency_base="XAU", currency_profit="USD", currency_margin="USD", spread=30, spread_float=True)

def engine():
    return RiskEngine(RiskConfig(risk_per_trade_percent=1., max_daily_loss_percent=3., max_open_positions=3, max_total_exposure_percent=5., require_stop_loss=True, min_risk_reward=1.5))

def check(risk, state, proposed=1.):
    return engine().pre_trade_check(equity=10000., daily_loss=state.daily_loss, open_positions=state.open_positions, current_exposure=state.total_exposure, proposed_exposure=proposed, entry_price=4300., stop_loss_price=4298., take_profit_price=4305., volume=.01, side="BUY", specification=spec())

def test_counts_only_open(persistent_risk_db):
    db,_=persistent_risk_db
    pos(db,"OPEN1","T1"); pos(db,"OPEN2","T2"); closed=pos(db,"CLOSED","T3"); PositionRepository.close(db,closed.position_id,exit_price=4299.)
    state=build_persistent_paper_risk_state()
    assert state.open_positions==2

def test_exposure_from_original_risk(persistent_risk_db):
    db,_=persistent_risk_db
    pos(db,"E1","T1"); pos(db,"E2","T2")
    assert build_persistent_paper_risk_state().total_exposure==pytest.approx(400.)

def test_daily_loss_from_closed_persistent_position(persistent_risk_db):
    db,_=persistent_risk_db
    p=pos(db,"L1","T1"); p=PositionRepository.close(db,p.position_id,exit_price=4000.)
    assert p.pnl==-300.; assert build_persistent_paper_risk_state().daily_loss==pytest.approx(300.)

def test_max_open_positions_enforced(persistent_risk_db):
    db,_=persistent_risk_db
    for i in range(3): pos(db,f"M{i}",f"TM{i}")
    state=build_persistent_paper_risk_state(); decision=check(None,state)
    assert decision.allowed is False and decision.reason=="maximum open positions reached"

def test_total_exposure_enforced(persistent_risk_db):
    db,_=persistent_risk_db
    pos(db,"X1","TX1"); pos(db,"X2","TX2")
    state=build_persistent_paper_risk_state(); decision=check(None,state,101.)
    assert decision.allowed is False and decision.reason=="maximum total exposure exceeded"

def test_daily_loss_enforced(persistent_risk_db):
    db,_=persistent_risk_db
    p=pos(db,"D1","TD1"); PositionRepository.close(db,p.position_id,exit_price=4000.)
    state=build_persistent_paper_risk_state(); decision=check(None,state)
    assert decision.allowed is False and decision.reason=="maximum daily loss reached"

def test_invalid_open_risk_fails_closed(persistent_risk_db):
    db,_=persistent_risk_db
    p=pos(db,"BAD","TBAD"); p.risk_1r=0.; db.commit()
    with pytest.raises(Exception, match="invalid 1R risk"): build_persistent_paper_risk_state()

def test_old_closed_loss_is_ignored(persistent_risk_db):
    db,_=persistent_risk_db
    p=pos(db,"OLD","TOLD"); p=PositionRepository.close(db,p.position_id,exit_price=4000.); p.closed_at=datetime(2000,1,1); db.commit()
    assert build_persistent_paper_risk_state().daily_loss==0.
