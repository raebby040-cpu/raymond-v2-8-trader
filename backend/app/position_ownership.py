
"""Ownership checks for RAYMOND paper-trading positions.

This module provides reusable helpers for API and repository code.
It does not alter the trading strategy or execute broker orders.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import Position


def get_owned_position(
    db: Session,
    position_id: int,
    owner_user_id: int,
) -> Optional[Position]:
    """Return a position only when it belongs to the specified user.

    Returns None for both nonexistent positions and positions belonging
    to another user, preventing callers from distinguishing the two.
    """
    if owner_user_id is None:
        return None

    return (
        db.query(Position)
        .filter(
            Position.id == position_id,
            Position.owner_user_id == owner_user_id,
        )
        .first()
    )


def list_owned_positions(
    db: Session,
    owner_user_id: int,
):
    """Return only positions assigned to the specified user."""
    if owner_user_id is None:
        return []

    return (
        db.query(Position)
        .filter(Position.owner_user_id == owner_user_id)
        .all()
    )


def position_belongs_to_user(
    db: Session,
    position_id: int,
    owner_user_id: int,
) -> bool:
    """Check whether a position is assigned to the specified user."""
    return get_owned_position(
        db=db,
        position_id=position_id,
        owner_user_id=owner_user_id,
    ) is not None
