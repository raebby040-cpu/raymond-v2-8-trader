"""
RAYMOND v2.8 - Automatic Trade Management Persistence

Stage 17.5.x

ADDITIVE ONLY.

This module persists decisions produced by
AutomaticTradeManager.

It does NOT:
- create trades
- open positions
- contact MT5
- contact a live broker
- bypass the Risk Engine
- replace PositionRepository
- replace the existing lifecycle manager
- replace Stage 12 advanced management

Responsibilities:
- Persist automatic TP modifications.
- Persist automatic SL modifications.
- Persist combined SL + TP modifications.
- Keep Stage 16.2 compatibility fields synchronized.
- Preserve initial_stop_loss and risk_1r.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

try:
    from .models import Position, PositionStatus
except ImportError:
    from models import Position, PositionStatus


class AutomaticTradeManagementPersistence:
    """
    Persistence adapter for Stage 17.5 automatic management.

    This class changes only the persistent state of an already-open
    Position.

    It never creates a position and never sends an order.
    """

    @staticmethod
    def get_open_position(
        db: Session,
        position_id: str,
    ) -> Optional[Position]:
        """
        Load an open persistent position.
        """

        position = (
            db.query(Position)
            .filter(
                Position.position_id == position_id,
            )
            .first()
        )

        if position is None:
            return None

        if position.status != PositionStatus.OPEN:
            return None

        return position

    @staticmethod
    def update_take_profit(
        db: Session,
        position_id: str,
        new_take_profit: float,
        *,
        management_action: str = "MODIFY_TP",
        management_status: str = "tp_modified",
    ) -> Optional[Position]:
        """
        Persist a new primary take-profit.

        Both fields are updated:

        take_profit_1
            Authoritative Stage 16.2 primary TP.

        take_profit
            Legacy compatibility field used by older consumers.

        take_profit_2 is deliberately NOT changed.

        This method never changes:
        - initial_stop_loss
        - current_stop_loss
        - risk_1r
        - original_quantity
        - remaining_quantity
        """

        position = (
            AutomaticTradeManagementPersistence
            .get_open_position(
                db,
                position_id,
            )
        )

        if position is None:
            return None

        new_tp = float(new_take_profit)

        if new_tp <= 0:
            raise ValueError(
                "new_take_profit must be greater than zero"
            )

        position.take_profit_1 = new_tp

        # Keep the legacy field synchronized.
        position.take_profit = new_tp

        position.last_management_action = (
            management_action
        )

        position.last_management_time = (
            datetime.utcnow()
        )

        position.management_status = (
            management_status
        )

        try:
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def update_stop_loss_and_take_profit(
        db: Session,
        position_id: str,
        *,
        new_stop_loss: Optional[float] = None,
        new_take_profit: Optional[float] = None,
        management_action: str = "MODIFY_SL_TP",
        management_status: str = "protected",
    ) -> Optional[Position]:
        """
        Atomically persist a new SL and/or TP.

        This is specifically for the
        MODIFY_SL_TP automatic-management decision.

        At least one of new_stop_loss or new_take_profit must
        be supplied.

        Initial trade risk is never overwritten.
        """

        if (
            new_stop_loss is None
            and new_take_profit is None
        ):
            raise ValueError(
                "At least one of new_stop_loss or "
                "new_take_profit is required"
            )

        position = (
            AutomaticTradeManagementPersistence
            .get_open_position(
                db,
                position_id,
            )
        )

        if position is None:
            return None

        if new_stop_loss is not None:
            new_sl = float(new_stop_loss)

            if new_sl <= 0:
                raise ValueError(
                    "new_stop_loss must be greater than zero"
                )

            position.current_stop_loss = new_sl

            # Keep the legacy field synchronized.
            position.stop_loss = new_sl

        if new_take_profit is not None:
            new_tp = float(new_take_profit)

            if new_tp <= 0:
                raise ValueError(
                    "new_take_profit must be greater than zero"
                )

            position.take_profit_1 = new_tp

            # Keep the legacy field synchronized.
            position.take_profit = new_tp

        position.last_management_action = (
            management_action
        )

        position.last_management_time = (
            datetime.utcnow()
        )

        position.management_status = (
            management_status
        )

        try:
            # One commit means SL + TP are persisted together.
            db.commit()
            db.refresh(position)

            return position

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def persist_decision(
        db: Session,
        *,
        position_id: str,
        action: str,
        new_stop_loss: Optional[float] = None,
        new_take_profit: Optional[float] = None,
    ) -> Optional[Position]:
        """
        Persist a decision from AutomaticTradeManager.

        Supported modification actions:

        MODIFY_SL
        MODIFY_TP
        MODIFY_SL_TP

        HOLD requires no database mutation.

        CLOSE is intentionally NOT handled here yet.
        Existing lifecycle/persistence closure remains authoritative
        until the CLOSE integration stage is added.
        """

        normalized_action = str(action).lower()

        if normalized_action == "hold":
            return (
                AutomaticTradeManagementPersistence
                .get_open_position(
                    db,
                    position_id,
                )
            )

        if normalized_action == "modify_sl":
            return (
                AutomaticTradeManagementPersistence
                .update_stop_loss_and_take_profit(
                    db,
                    position_id,
                    new_stop_loss=new_stop_loss,
                    management_action="MODIFY_SL",
                    management_status="protected",
                )
            )

        if normalized_action == "modify_tp":
            return (
                AutomaticTradeManagementPersistence
                .update_take_profit(
                    db,
                    position_id,
                    float(new_take_profit),
                    management_action="MODIFY_TP",
                    management_status="tp_modified",
                )
            )

        if normalized_action == "modify_sl_tp":
            return (
                AutomaticTradeManagementPersistence
                .update_stop_loss_and_take_profit(
                    db,
                    position_id,
                    new_stop_loss=new_stop_loss,
                    new_take_profit=new_take_profit,
                    management_action="MODIFY_SL_TP",
                    management_status="protected",
                )
            )

        if normalized_action == "close":
            raise ValueError(
                "CLOSE persistence is intentionally handled "
                "by the existing position/lifecycle closure path."
            )

        raise ValueError(
            f"Unsupported automatic management action: {action}"
        )


def persist_automatic_management_decision(
    db: Session,
    *,
    position_id: str,
    action: str,
    new_stop_loss: Optional[float] = None,
    new_take_profit: Optional[float] = None,
) -> Optional[Position]:
    """
    Convenience function for integration with the
    automatic trade-management service.
    """

    return (
        AutomaticTradeManagementPersistence
        .persist_decision(
            db,
            position_id=position_id,
            action=action,
            new_stop_loss=new_stop_loss,
            new_take_profit=new_take_profit,
        )
    )
