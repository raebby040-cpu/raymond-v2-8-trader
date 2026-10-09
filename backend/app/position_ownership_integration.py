
"""RAYMOND V2.8 position ownership integration helpers.

Provides a separate integration layer for authenticated, user-scoped
paper-position access without modifying the existing position repository.

This module does not place broker orders or change trading decisions.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import Position, PositionStatus
from .position_ownership import get_owned_position


def get_user_position(
    db: Session,
    position_id: str,
    owner_user_id: str,
) -> Optional[Position]:
    """Retrieve a position only if it belongs to the authenticated user."""
    if not owner_user_id or not position_id:
        return None

    return get_owned_position(
        db=db,
        position_id=position_id,
        owner_user_id=owner_user_id,
    )


def get_user_open_positions(
    db: Session,
    owner_user_id: str,
) -> list[Position]:
    """Retrieve open positions belonging to one user only."""
    if not owner_user_id:
        return []

    return (
        db.query(Position)
        .filter(
            Position.owner_user_id == owner_user_id,
            Position.status == PositionStatus.OPEN,
        )
        .order_by(Position.opened_at.asc())
        .all()
    )


def get_user_positions(
    db: Session,
    owner_user_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[Position]:
    """Retrieve a paginated list of one user's positions."""
    if not owner_user_id:
        return []

    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))

    return (
        db.query(Position)
        .filter(Position.owner_user_id == owner_user_id)
        .order_by(Position.opened_at.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )


def user_owns_position(
    db: Session,
    position_id: str,
    owner_user_id: str,
) -> bool:
    """Return whether the requested position belongs to this user."""
    return get_user_position(
        db=db,
        position_id=position_id,
        owner_user_id=owner_user_id,
    ) is not None
