from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.monthly_trade_audit import build_monthly_trade_audit


router = APIRouter(
    prefix="/api/research",
    tags=["research"],
)


def _open_database_session() -> Session:
    """Create a database session for the research-only audit."""
    return SessionLocal()


@router.get("/monthly-audit")
def get_monthly_trade_audit(
    month: str = Query(
        ...,
        description="Audit month in YYYY-MM format.",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    include_trades: bool = Query(
        False,
        description=(
            "Include individual closed-trade records in the response. "
            "Required by the price-path forensic research workflow."
        ),
    ),
) -> Dict[str, Any]:
    """
    Generate a research-only monthly trade audit.

    IMPORTANT SAFETY BOUNDARY
    -------------------------
    This endpoint is strictly for historical research.

    It:
      - reads completed PAPER/RESEARCH positions;
      - calculates historical audit statistics;
      - does not create broker orders;
      - does not modify open positions;
      - does not modify the active strategy;
      - does not promote research candidates;
      - does not execute live trading.

    Normal requests omit detailed trade records.

    The forensic workflow requests:

        /api/research/monthly-audit
            ?month=2026-09
            &include_trades=true

    When include_trades=true, the complete trade records are returned so
    the forensic engine can reconstruct the price path against historical
    M5 market data.
    """

    db = _open_database_session()

    try:
        # --------------------------------------------------------------
        # Build the historical monthly audit.
        # --------------------------------------------------------------
        try:
            report = build_monthly_trade_audit(
                db=db,
                month=month,
            )
        except TypeError:
            # Compatibility fallback for older builder signatures.
            report = build_monthly_trade_audit(
                db,
                month,
            )

        if report is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No monthly audit report was produced for "
                    f"{month}."
                ),
            )

        if not isinstance(report, dict):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Monthly audit builder returned an invalid "
                    "report object."
                ),
            )

        # Never mutate the original report object.
        response: Dict[str, Any] = dict(report)

        # --------------------------------------------------------------
        # Research-only safety flags.
        # --------------------------------------------------------------
        response["research_only"] = True
        response["live_trading_changed"] = False
        response["strategy_modified"] = False
        response["positions_modified"] = False
        response["orders_created"] = False
        response["candidates_promoted"] = False

        # --------------------------------------------------------------
        # Validate report identity.
        # --------------------------------------------------------------
        if response.get("report_type") != "RAYMOND_MONTHLY_TRADE_AUDIT":
            raise HTTPException(
                status_code=500,
                detail=(
                    "Unexpected monthly audit report type: "
                    f"{response.get('report_type')!r}"
                ),
            )

        if response.get("month") != month:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Monthly audit month mismatch. "
                    f"Requested {month}, received "
                    f"{response.get('month')}."
                ),
            )

        if response.get("research_only") is not True:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Monthly audit is not marked "
                    "research_only=true."
                ),
            )

        if response.get("live_trading_changed") is not False:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Monthly audit reports that live trading "
                    "was changed."
                ),
            )

        # --------------------------------------------------------------
        # Validate accounting reconciliation.
        # --------------------------------------------------------------
        accounting = response.get("accounting")

        if not isinstance(accounting, dict):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Monthly audit accounting section is "
                    "missing or invalid."
                ),
            )

        if accounting.get("accounting_reconciled") is not True:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Historical monthly audit accounting "
                    "is not reconciled."
                ),
            )

        # --------------------------------------------------------------
        # Trade records.
        # --------------------------------------------------------------
        trades = response.get("trades")

        if include_trades:
            # ----------------------------------------------------------
            # CRITICAL FIX
            #
            # When the forensic workflow explicitly requests
            # include_trades=true, the trade records MUST remain in
            # the response.
            # ----------------------------------------------------------
            if trades is None:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "include_trades=true was requested, "
                        "but the audit builder returned no "
                        "'trades' field."
                    ),
                )

            if not isinstance(trades, list):
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "include_trades=true was requested, "
                        "but the 'trades' field is not a list."
                    ),
                )

            performance = response.get("performance")

            if isinstance(performance, dict):
                expected_trade_count = performance.get(
                    "total_trades"
                )

                if (
                    isinstance(expected_trade_count, int)
                    and expected_trade_count != len(trades)
                ):
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Trade record count does not match "
                            "performance.total_trades. "
                            f"Records={len(trades)}, "
                            f"Expected={expected_trade_count}."
                        ),
                    )

        else:
            # ----------------------------------------------------------
            # Preserve the normal lightweight API behavior.
            #
            # Detailed trades are only exposed when explicitly
            # requested by the research workflow.
            # ----------------------------------------------------------
            response.pop("trades", None)
            response.pop("loss_trade_ids", None)

        # --------------------------------------------------------------
        # Explicit metadata describing the response.
        # --------------------------------------------------------------
        response["trade_records_included"] = include_trades

        if include_trades:
            response["trade_record_count"] = len(
                response.get("trades", [])
            )
        else:
            response["trade_record_count"] = 0

        return response

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Monthly audit generation failed: "
                f"{exc}"
            ),
        ) from exc

    finally:
        db.close()
