"""
RAYMOND v2.8 - Canonical Paper Trading Main Patch

This module provides a small integration layer for main.py.

Purpose:
- Keep persistent Position records as the canonical paper positions.
- Keep persistent paper accounting as the canonical Balance/Equity source.
- Replace demo_engine-based risk/equity calculations at runtime.
- Register persistent paper-position management routes.
- Avoid editing the large main.py implementation directly.

Paper accounting:
    Starting balance = $1,000
    Balance = $1,000 + realized P&L
    Equity = Balance + unrealized P&L

Live broker execution remains disabled.
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


MANAGEMENT_ROUTE = (
    "/api/online/manage-paper-positions"
)


def _get_required(
    namespace: MutableMapping[str, Any],
    name: str,
) -> Any:
    value = namespace.get(name)

    if value is None:
        raise RuntimeError(
            "Canonical paper main patch requires "
            f"'{name}' to exist in main.py."
        )

    return value


def canonical_build_paper_risk_state(
    namespace: MutableMapping[str, Any],
) -> Any:
    """
    Build the application's PaperRiskState from
    persistent database positions.

    demo_engine.open_trades is deliberately not used.
    """

    session_local = _get_required(
        namespace,
        "SessionLocal",
    )

    paper_risk_state_class = _get_required(
        namespace,
        "PaperRiskState",
    )

    pipeline_error = _get_required(
        namespace,
        "TradingPipelineServiceError",
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
                    None,
                )
                or getattr(
                    position,
                    "quantity",
                    0.0,
                )
                or 0.0
            )

            if entry_price <= 0:
                raise pipeline_error(
                    "Persistent paper position has "
                    "an invalid entry price."
                )

            if quantity <= 0:
                raise pipeline_error(
                    "Persistent paper position has "
                    "an invalid quantity."
                )

            total_exposure += (
                entry_price * quantity
            )

        return paper_risk_state_class(
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

    except pipeline_error:
        raise

    except Exception as exc:
        raise pipeline_error(
            "Unable to build canonical paper "
            f"risk state: {exc}"
        ) from exc

    finally:
        db.close()


def canonical_get_paper_equity(
    namespace: MutableMapping[str, Any],
) -> float:
    """
    Return canonical persistent paper equity.

    Equity includes unrealized P&L from currently
    open persistent positions.
    """

    session_local = _get_required(
        namespace,
        "SessionLocal",
    )

    pipeline_error = _get_required(
        namespace,
        "TradingPipelineServiceError",
    )

    db = session_local()

    try:
        equity = float(
            get_persistent_paper_equity(
                db
            )
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
            "Unable to determine canonical "
            f"paper equity: {exc}"
        ) from exc

    finally:
        db.close()


def install_canonical_paper_main_patch(
    app: FastAPI,
    namespace: MutableMapping[str, Any],
) -> None:
    """
    Attach the canonical paper trading system to
    the already-created FastAPI application.

    The existing main.py remains untouched.
    """

    if not isinstance(
        app,
        FastAPI,
    ):
        raise TypeError(
            "Expected the existing FastAPI app."
        )

    # Replace the old demo_engine-based risk state.
    namespace[
        "build_paper_risk_state"
    ] = lambda: (
        canonical_build_paper_risk_state(
            namespace
        )
    )

    # Replace the old demo_engine-based equity.
    namespace[
        "get_paper_equity"
    ] = lambda: (
        canonical_get_paper_equity(
            namespace
        )
    )

    # Add persistent position management API
    # if main.py has not already registered it.
    already_registered = any(
        getattr(
            route,
            "path",
            None,
        )
        == MANAGEMENT_ROUTE
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


def patch_existing_main(
    app: FastAPI,
    namespace: MutableMapping[str, Any],
) -> FastAPI:
    """
    Convenience wrapper.

    Returns the same FastAPI application after
    installing the canonical paper system.
    """

    install_canonical_paper_main_patch(
        app,
        namespace,
    )

    return app


__all__ = [
    "MANAGEMENT_ROUTE",
    "canonical_build_paper_risk_state",
    "canonical_get_paper_equity",
    "install_canonical_paper_main_patch",
    "patch_existing_main",
]
