"""
RAYMOND v2.8 - Canonical Paper Runtime Bridge.

Connects the existing online_main.py runtime to the canonical
persistent paper-trading account without replacing online_main.py.

Canonical accounting:

    Starting balance = $1,000
    Balance = starting balance + realized P&L
    Equity = balance + unrealized P&L

Persistent Position records are the source of truth.

Live broker execution remains disabled.
"""

from __future__ import annotations

from typing import Any, MutableMapping

from .persistent_paper_account import (
    build_persistent_paper_account,
    get_persistent_paper_equity,
)

from .position_repository import PositionRepository


def canonical_paper_equity(
    namespace: MutableMapping[str, Any],
) -> float:
    """
    Return canonical persistent paper equity.

    Equity includes unrealized P&L from open positions.
    """

    session_local = namespace.get(
        "SessionLocal"
    )

    if session_local is None:
        raise RuntimeError(
            "SessionLocal is required for canonical "
            "paper equity."
        )

    db = session_local()

    try:
        equity = float(
            get_persistent_paper_equity(db)
        )

        if equity <= 0:
            raise RuntimeError(
                "Canonical paper equity is not greater "
                "than zero."
            )

        return equity

    finally:
        db.close()


def canonical_paper_risk_state(
    namespace: MutableMapping[str, Any],
) -> Any:
    """
    Build the paper risk state from persistent Position records.

    The old demo_engine is deliberately excluded.
    """

    session_local = namespace.get(
        "SessionLocal"
    )

    risk_state_class = namespace.get(
        "PaperRiskState"
    )

    if session_local is None:
        raise RuntimeError(
            "SessionLocal is required for canonical "
            "paper risk state."
        )

    if risk_state_class is None:
        raise RuntimeError(
            "PaperRiskState is required for canonical "
            "paper risk state."
        )

    db = session_local()

    try:
        account = build_persistent_paper_account(
            db
        )

        positions = (
            PositionRepository.get_open_positions(
                db
            )
        )

        total_exposure = 0.0

        for position in positions:
            entry_price = float(
                getattr(
                    position,
                    "entry_price",
                    0.0,
                )
                or 0.0
            )

            quantity = float(
                getattr(
                    position,
                    "remaining_quantity",
                    0.0,
                )
                or getattr(
                    position,
                    "quantity",
                    0.0,
                )
                or 0.0
            )

            if entry_price <= 0:
                raise RuntimeError(
                    "Persistent paper position has "
                    "an invalid entry price."
                )

            if quantity <= 0:
                raise RuntimeError(
                    "Persistent paper position has "
                    "an invalid quantity."
                )

            total_exposure += (
                entry_price * quantity
            )

        return risk_state_class(
            daily_loss=float(
                account.get(
                    "daily_loss",
                    0.0,
                )
                or 0.0
            ),
            open_positions=len(
                positions
            ),
            total_exposure=total_exposure,
        )

    finally:
        db.close()


def install_canonical_paper_runtime(
    namespace: MutableMapping[str, Any],
) -> None:
    """
    Replace paper-account functions inside the running application
    namespace with canonical persistent implementations.

    This is designed for online_main.py.

    It also updates the imported function references used by
    automatic paper-entry workers.
    """

    namespace[
        "get_paper_equity"
    ] = lambda: canonical_paper_equity(
        namespace
    )

    namespace[
        "build_paper_risk_state"
    ] = lambda: canonical_paper_risk_state(
        namespace
    )

    # The existing online_main.py uses the persistent risk function
    # directly for Stage 17.6. Replace that reference as well.
    namespace[
        "build_persistent_paper_risk_state"
    ] = lambda: canonical_paper_risk_state(
        namespace
    )


__all__ = [
    "canonical_paper_equity",
    "canonical_paper_risk_state",
    "install_canonical_paper_runtime",
]
