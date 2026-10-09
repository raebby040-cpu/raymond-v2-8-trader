
"""Ownership checks for RAYMOND paper-trading positions.

These helpers support user-scoped position access.
They do not change trading decisions or execute broker orders.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import Position


def get_owned_position(
    db: Session,
    position_id: str,
    owner_user_id: str,
) -> Optional[Position]:
    """Return a position only if it belongs to the specified user."""
    if not position_id or not owner_user_id:
        return None

    return (
        db.query(Position)
        .filter(
            Position.position_id == position_id,
            Position.owner_user_id == owner_user_id,
        )
        .first()
    )


def list_owned_positions(
    db: Session,
    owner_user_id: str,
) -> list[Position]:
    """Return only positions assigned to the specified user."""
    if not owner_user_id:
        return []

    return (
        db.query(Position)
        .filter(Position.owner_user_id == owner_user_id)
        .order_by(Position.opened_at.desc())
        .all()
    )


def position_belongs_to_user(
    db: Session,
    position_id: str,
    owner_user_id: str,
) -> bool:
    """Check whether a position belongs to the specified user."""
    return (
        get_owned_position(
            db=db,
            position_id=position_id,
            owner_user_id=owner_user_id,
        )
        is not None
    )
