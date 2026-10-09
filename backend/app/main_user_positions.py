"""RAYMOND V2.8 application entry point with user-owned positions.

Keeps the existing main application and trading engine unchanged.
Adds read-only, authenticated access to positions owned by the
currently authenticated user.
"""

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .main import app
from .database import get_db
from .models import Position
from .position_ownership_integration import (
    get_user_position,
    get_user_positions,
)
from .user_auth import User, get_current_user


def serialize_user_position(position: Position) -> dict:
    """Return fields that actually exist on the Position model."""
    direction = position.direction
    status = position.status

    return {
        "position_id": position.position_id,
        "trade_id": position.trade_id,
        "symbol": position.symbol,
        "direction": (
            direction.value if hasattr(direction, "value") else direction
        ),
        "status": status.value if hasattr(status, "value") else status,
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "stop_loss": position.current_stop_loss or position.stop_loss,
        "take_profit": position.take_profit,
        "quantity": position.quantity,
        "remaining_quantity": position.remaining_quantity,
        "pnl": position.pnl,
        "partial_close_quantity": position.partial_close_quantity,
        "partial_close_price": position.partial_close_price,
        "partial_close_pnl": position.partial_close_pnl,
        "opened_at": (
            position.opened_at.isoformat()
            if position.opened_at else None
        ),
        "closed_at": (
            position.closed_at.isoformat()
            if position.closed_at else None
        ),
        "paper_only": True,
        "live_trading_enabled": False,
        "broker_orders_allowed": False,
    }


@app.get("/api/user-paper-positions", tags=["User Paper Positions"])
def list_my_paper_positions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List only paper positions owned by the authenticated user."""
    positions = get_user_positions(
        db=db,
        owner_user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )

    return {
        "count": len(positions),
        "positions": [
            serialize_user_position(position)
            for position in positions
        ],
        "paper_only": True,
        "live_trading_enabled": False,
        "broker_orders_allowed": False,
    }


@app.get(
    "/api/user-paper-positions/{position_id}",
    tags=["User Paper Positions"],
)
def get_my_paper_position(
    position_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a position only when it belongs to the signed-in user."""
    position = get_user_position(
        db=db,
        position_id=position_id,
        owner_user_id=current_user.user_id,
    )

    if position is None:
        raise HTTPException(
            status_code=404,
            detail="Position not found.",
        )

    return serialize_user_position(position)
