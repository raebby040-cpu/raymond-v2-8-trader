"""Canonical RAYMOND entry point with authenticated position reads.

Preserves the canonical online runtime and adds read-only,
user-owned paper-position endpoints.
"""

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

import canonical_online_main as canonical
from app.database import get_db
from app.models import Position
from app.position_ownership_integration import (
    get_user_position,
    get_user_positions,
)
from app.user_auth import User, get_current_user

app = canonical.app


def serialize_position(position: Position) -> dict:
    direction = position.direction
    status = position.status

    return {
        "position_id": position.position_id,
        "trade_id": position.trade_id,
        "symbol": position.symbol,
        "direction": direction.value if hasattr(direction, "value") else direction,
        "status": status.value if hasattr(status, "value") else status,
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "stop_loss": (
            position.current_stop_loss
            if position.current_stop_loss is not None
            else position.stop_loss
        ),
        "take_profit": position.take_profit,
        "quantity": position.quantity,
        "remaining_quantity": position.remaining_quantity,
        "pnl": position.pnl,
        "partial_close_quantity": position.partial_close_quantity,
        "partial_close_price": position.partial_close_price,
        "partial_close_pnl": position.partial_close_pnl,
        "opened_at": position.opened_at.isoformat() if position.opened_at else None,
        "closed_at": position.closed_at.isoformat() if position.closed_at else None,
        "paper_only": True,
        "live_trading_enabled": False,
        "broker_orders_allowed": False,
    }


@app.get("/api/user-paper-positions", tags=["User Paper Positions"])
def list_user_positions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    positions = get_user_positions(
        db=db,
        owner_user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )
    return {
        "count": len(positions),
        "positions": [serialize_position(p) for p in positions],
        "paper_only": True,
        "live_trading_enabled": False,
        "broker_orders_allowed": False,
    }


@app.get(
    "/api/user-paper-positions/{position_id}",
    tags=["User Paper Positions"],
)
def get_user_position_by_id(
    position_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    position = get_user_position(
        db=db,
        position_id=position_id,
        owner_user_id=current_user.user_id,
    )
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found.")
    return serialize_position(position)
