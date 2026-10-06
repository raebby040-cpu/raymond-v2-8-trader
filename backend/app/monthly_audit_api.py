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
        description=(
            "Calendar month in YYYY-MM format. "
            "Defaults to current UTC month."
        ),
        pattern=r"^\d{4}-\d{2}$",
    ),
    include_trades: bool = Query(
        False,
        description=(
            "Research-only option to include individual "
            "trade records for price-path forensics."
        ),
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

    Individual trade records are hidden by default.

    They are returned only when explicitly requested with:

        include_trades=true

    This option exists specifically for research-only forensic analysis.
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

    # Individual trade records remain hidden by default.
    #
    # The forensic GitHub Actions workflow explicitly requests
    # include_trades=true so it can reconstruct price paths.
    #
    # This remains read-only and research-only.
    if not include_trades:
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
