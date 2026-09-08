from typing import Any, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from backend.db import SessionLocal
from backend.models import EmergencyStop, JournalEntry, BrokerReceipt, Position
from datetime import datetime


def _get_session() -> Session:
    return SessionLocal()


def get_emergency_stop() -> EmergencyStop | None:
    with _get_session() as db:
        stmt = select(EmergencyStop).limit(1)
        res = db.execute(stmt).scalars().first()
        return res


def set_emergency_stop(activated: bool, reason: str | None = None, activated_by: str | None = None) -> EmergencyStop:
    with _get_session() as db:
        obj = db.query(EmergencyStop).first()
        if not obj:
            obj = EmergencyStop(activated=activated, activated_at=(datetime.utcnow() if activated else None), reason=reason, activated_by=activated_by)
            db.add(obj)
        else:
            obj.activated = activated
            obj.activated_at = (datetime.utcnow() if activated else None)
            obj.reason = reason
            obj.activated_by = activated_by
        db.commit()
        db.refresh(obj)
        return obj


def write_journal_entry(entry_type: str, payload: Dict[str, Any]) -> JournalEntry:
    with _get_session() as db:
        je = JournalEntry(type=entry_type, payload=payload)
        db.add(je)
        db.commit()
        db.refresh(je)
        return je


def write_broker_receipt(journal_entry_id: int, broker_order_id: str | None, status: str | None, raw: Dict[str, Any] | None) -> BrokerReceipt:
    with _get_session() as db:
        br = BrokerReceipt(journal_entry_id=journal_entry_id, broker_order_id=broker_order_id, status=status, raw=raw)
        db.add(br)
        db.commit()
        db.refresh(br)
        return br


def list_open_positions() -> List[Position]:
    with _get_session() as db:
        stmt = select(Position).where(Position.status == "open")
        res = db.execute(stmt).scalars().all()
        return res


def close_position(position_id: int, reason: str | None = None) -> JournalEntry:
    with _get_session() as db:
        pos = db.get(Position, position_id)
        if not pos or pos.status != "open":
            return None
        pos.status = "closed"
        pos.closed_at = datetime.utcnow()
        db.add(pos)
        # create a journal entry recording the close
        je = JournalEntry(type="position_close", payload={"position_id": pos.id, "reason": reason})
        db.add(je)
        db.commit()
        db.refresh(je)
        return je


def close_all_positions(reason: str | None = None) -> Dict[str, Any]:
    with _get_session() as db:
        open_positions = db.query(Position).filter(Position.status == "open").all()
        closed = 0
        created_journal_ids = []
        for p in open_positions:
            p.status = "closed"
            p.closed_at = datetime.utcnow()
            db.add(p)
            je = JournalEntry(type="position_close", payload={"position_id": p.id, "reason": reason})
            db.add(je)
            db.flush()
            created_journal_ids.append(je.id)
            closed += 1
        db.commit()
        return {"positions_found": len(open_positions), "positions_closed": closed, "journal_ids": created_journal_ids}
