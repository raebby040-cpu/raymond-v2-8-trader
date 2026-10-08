"""
RAYMOND v2.8 - Canonical Persistent Paper Runtime.

This module is the authoritative bridge between the production
online runtime and the persistent paper-trading account.

Canonical accounting:

    Starting balance = $1,000
    Balance = $1,000 + realized P&L
    Equity = Balance + unrealized P&L

Persistent Position records are the source of truth.

This module is PAPER ONLY.

It does not:
    - send broker orders
    - modify MT5 positions
    - connect to Exness for execution
    - enable live trading
    - bypass the Risk Engine
    - bypass Emergency Stop
"""

from __future__ import annotations

from typing import Any, MutableMapping

from .database import SessionLocal
from .models import PositionStatus
from .persistent_paper_account import (
    build_persistent_paper_account,
    get_persistent_paper_equity,
)
from .trading_pipeline_service import PaperRiskState
from .position_repository import PositionRepository


def _as_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Safely convert a value to float.
    """
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def canonical_paper_equity(
    namespace: MutableMapping[str, Any] | None = None,
) -> float:
    """
    Return the authoritative persistent paper equity.

    Balance contains realized P&L only.

    Equity contains:

        balance + unrealized P&L

    Persistent database positions are the source of truth.
    """

    del namespace

    db = SessionLocal()

    try:
        equity = get_persistent_paper_equity(db)

        equity = _as_float(equity)

        if equity <= 0:
            raise RuntimeError(
                "Canonical persistent paper equity is invalid."
            )

        return equity

    finally:
        db.close()


def canonical_paper_risk_state(
    namespace: MutableMapping[str, Any] | None = None,
) -> PaperRiskState:
    """
    Build the authoritative paper risk state directly from the
    persistent paper account.

    This implementation intentionally imports PaperRiskState
    directly instead of requiring it to exist inside the
    online_main.py namespace.

    Open positions are loaded from the persistent Position table.

    Exposure is calculated from:

        entry_price × remaining_quantity

    when available, with quantity/original quantity as a fallback.

    No broker state is consulted.
    """

    del namespace

    db = SessionLocal()

    try:
        account = build_persistent_paper_account(db)

        positions = PositionRepository.get_open_positions(db)

        total_exposure = 0.0

        for position in positions:
            status = getattr(
                position,
                "status",
                None,
            )

            if status is not None:
                if status != PositionStatus.OPEN:
                    continue

            remaining_quantity = _as_float(
                getattr(
                    position,
                    "remaining_quantity",
                    None,
                )
            )

            if remaining_quantity <= 0:
                remaining_quantity = _as_float(
                    getattr(
                        position,
                        "quantity",
                        None,
                    )
                )

            if remaining_quantity <= 0:
                remaining_quantity = _as_float(
                    getattr(
                        position,
                        "original_quantity",
                        None,
                    )
                )

            entry_price = _as_float(
                getattr(
                    position,
                    "entry_price",
                    None,
                )
            )

            if remaining_quantity <= 0:
                continue

            if entry_price > 0:
                total_exposure += (
                    entry_price
                    * remaining_quantity
                )
            else:
                # If an older persisted record has no entry price,
                # keep the risk state usable without inventing price
                # information.
                total_exposure += remaining_quantity

        daily_loss = max(
            0.0,
            _as_float(
                account.get(
                    "daily_loss",
                    0.0,
                )
            ),
        )

        return PaperRiskState(
            daily_loss=daily_loss,
            open_positions=len(positions),
            total_exposure=total_exposure,
        )

    finally:
        db.close()


def install_canonical_paper_runtime(
    namespace: MutableMapping[str, Any],
) -> None:
    """
    Install canonical paper providers into a runtime namespace.

    This updates the actual function references used by the
    production online runtime.
    """

    namespace["get_paper_equity"] = (
        lambda: canonical_paper_equity(namespace)
    )

    canonical_risk_provider = (
        lambda: canonical_paper_risk_state(namespace)
    )

    namespace["build_paper_risk_state"] = (
        canonical_risk_provider
    )

    namespace["build_persistent_paper_risk_state"] = (
        canonical_risk_provider
    )


__all__ = [
    "canonical_paper_equity",
    "canonical_paper_risk_state",
    "install_canonical_paper_runtime",
]
