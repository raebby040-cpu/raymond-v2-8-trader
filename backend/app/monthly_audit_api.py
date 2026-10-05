"""
RAYMOND V2.8 - Read-only monthly audit API.

This endpoint exposes the Phase 1 audit report for research review.
It performs database reads only and never changes positions, strategy,
or execution state.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .database import get_db
from scripts.monthly_trade_audit import (
    DEFAULT_SYMBOL,
    build_report,
    load_closed_positions,
    month_bounds,
)

router = APIRouter(
    prefix="/api/research",
    tags=["Research Audit"],
)


@router.get("/monthly-audit")
def monthly_audit(
    month: str | None = Query(
        None,
        description="Calendar month in YYYY-MM format. Defaults to current UTC month.",
        pattern=r"^\d{4}-\d{2}$",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Return the Phase 1 monthly audit using closed PAPER positions.

    READ-ONLY:
    - no position updates
    - no broker/MT5 calls
    - no strategy changes
    - no candidate promotion
    """

    start, end, label = month_bounds(month)

    # Keep the database dependency active so the endpoint verifies
    # database availability for the request.
    _ = db

    trades = load_closed_positions(
        start=start,
        end=end,
        symbol=DEFAULT_SYMBOL,
    )

    report = build_report(
        trades=trades,
        month=label,
        symbol=DEFAULT_SYMBOL,
    )

    # Do not expose individual trade records through this endpoint.
    report.pop("trades", None)
    report.pop("loss_trade_ids", None)

    return {
        **report,
        "safety": {
            "research_only": True,
            "read_only": True,
            "live_trading_changed": False,
            "positions_modified": False,
            "strategy_modified": False,
            "orders_created": False,
            "candidates_promoted": False,
        },
    }


__all__ = ["router"]
