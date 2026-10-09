
"""Authenticated, read-only API for user-owned paper positions.

This router only returns positions belonging to the authenticated user.
It does not create, modify, or close positions.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .database import get_db
from .models import Position
from .position_ownership_integration import (
    get_user_position,
    get_user_positions,
)
from .user_auth import User, get_current_user


router = APIRouter(
    prefix="/api/user-paper-positions",
    tags=["User Paper Positions"],
)


def _serialize_position(position: Position) -> dict:
    """Serialize position data without exposing ownership internals."""
    return {
        "position_id": position.position_id,
        "trade_id": position.trade_id,
        "symbol": position.symbol,
        "direction": (
            position.direction.value
            if hasattr(position.direction, "value")
            else position.direction
        ),
        "status": (
            position.status.value
            if hasattr(position.status, "value")
            else position.status
        ),
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "stop_loss": position.stop_loss,
        "take_profit": position.take_profit,
        "volume": position.volume,
        "realized_pnl": position.realized_pnl,
        "unrealized_pnl": position.unrealized_pnl,
        "opened_at": (
            position.opened_at.isoformat()
            if position.opened_at
            else None
        ),
        "closed_at": (
            position.closed_at.isoformat()
            if position.closed_at
            else None
        ),
        "paper_only": True,
        "live_trading_enabled": False,
        "broker_orders_allowed": False,
    }


@router.get("")
def list_my_positions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List positions belonging to the authenticated user."""
    positions = get_user_positions(
        db=db,
        owner_user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )

    return {
        "count": len(positions),
        "positions": [
            _serialize_position(position)
            for position in positions
        ],
        "paper_only": True,
        "live_trading_enabled": False,
        "broker_orders_allowed": False,
    }


@router.get("/{position_id}")
def get_my_position(
    position_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve one position only if it belongs to the current user."""
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

    return _serialize_position(position)
