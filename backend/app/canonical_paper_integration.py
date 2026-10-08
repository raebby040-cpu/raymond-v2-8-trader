"""
Canonical persistent paper-trading integration for Raymond v2.8.

This module allows main.py to adopt the persistent paper account without
replacing the existing large main.py file.

After importing this module in main.py, call:

    install_canonical_paper_integration(
        app,
        globals(),
    )

Persistent database Position records remain the single source of truth.

Paper accounting:

    Balance = $1,000 + realized P&L
    Equity  = Balance + unrealized P&L

Live broker/MT5 execution remains disabled.
"""

from __future__ import annotations

from typing import Any, MutableMapping

from fastapi import FastAPI

from .paper_position_management_api import (
    router as paper_position_management_router,
)

from .persistent_paper_account import (
    build_persistent_paper_account,
    get_persistent_paper_equity,
)

from .position_repository import PositionRepository


def _require_main_symbol(
    main_namespace: MutableMapping[str, Any],
    name: str,
) -> Any:
    value = main_namespace.get(name)

    if value is None:
        raise RuntimeError(
            "Canonical paper integration requires "
            f"{name} to already exist in main.py."
        )

    return value


def build_canonical_paper_risk_state(
    main_namespace: MutableMapping[str, Any],
) -> Any:
    """
    Build PaperRiskState from persistent database positions.

    This deliberately does not use demo_engine.open_trades.
    """

    session_local = _require_main_symbol(
        main_namespace,
        "SessionLocal",
    )

    paper_risk_state = _require_main_symbol(
        main_namespace,
        "PaperRiskState",
    )

    pipeline_error = _require_main_symbol(
        main_namespace,
        "TradingPipelineServiceError",
    )

    db = session_local()

    try:
        account = build_persistent_paper_account(db)

        positions = PositionRepository.get_open_positions(
            db
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
                    getattr(
                        position,
                        "quantity",
                        0.0,
                    ),
                )
                or 0.0
            )

            if entry_price < 0:
                raise pipeline_error(
                    "Persistent paper position has "
                    "an invalid entry price."
                )

            if quantity < 0:
                raise pipeline_error(
                    "Persistent paper position has "
                    "an invalid quantity."
                )

            total_exposure += (
                entry_price * quantity
            )

        return paper_risk_state(
            daily_loss=float(
                account.get(
                    "daily_loss",
                    0.0,
                )
            ),
            open_positions=int(
                account.get(
                    "open_positions",
                    len(positions),
                )
            ),
            total_exposure=total_exposure,
        )

    except pipeline_error:
        raise

    except Exception as exc:
        raise pipeline_error(
            "Unable to build canonical persistent "
            f"paper risk state: {exc}"
        ) from exc

    finally:
        db.close()


def get_canonical_paper_equity(
    main_namespace: MutableMapping[str, Any],
) -> float:
    """
    Return current canonical persistent paper equity.

    The persistent account calculates:

        $1,000 starting balance
        + realized P&L
        + unrealized P&L
        = equity
    """

    session_local = _require_main_symbol(
        main_namespace,
        "SessionLocal",
    )

    pipeline_error = _require_main_symbol(
        main_namespace,
        "TradingPipelineServiceError",
    )

    db = session_local()

    try:
        equity = float(
            get_persistent_paper_equity(db)
        )

        if equity <= 0:
            raise pipeline_error(
                "Canonical paper equity is not "
                "greater than zero."
            )

        return equity

    except pipeline_error:
        raise

    except Exception as exc:
        raise pipeline_error(
            "Unable to determine canonical persistent "
            f"paper equity: {exc}"
        ) from exc

    finally:
        db.close()


def install_canonical_paper_integration(
    app: FastAPI,
    main_namespace: MutableMapping[str, Any],
) -> None:
    """
    Install the canonical paper system into the existing FastAPI app.

    This function is called once from main.py after the application's
    existing globals have been initialized.
    """

    if not isinstance(app, FastAPI):
        raise TypeError(
            "install_canonical_paper_integration requires "
            "the existing FastAPI application."
        )

    # Replace the old demo_engine-based paper calculations.
    main_namespace[
        "build_paper_risk_state"
    ] = lambda: build_canonical_paper_risk_state(
        main_namespace
    )

    main_namespace[
        "get_paper_equity"
    ] = lambda: get_canonical_paper_equity(
        main_namespace
    )

    # Register the persistent paper-position management API
    # only if it is not already registered.
    management_path = (
        "/api/online/manage-paper-positions"
    )

    already_registered = any(
        getattr(route, "path", None)
        == management_path
        for route in getattr(
            app,
            "routes",
            [],
        )
    )

    if not already_registered:
        app.include_router(
            paper_position_management_router
        )


__all__ = [
    "build_canonical_paper_risk_state",
    "get_canonical_paper_equity",
    "install_canonical_paper_integration",
          ]
