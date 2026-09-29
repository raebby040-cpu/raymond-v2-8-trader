"""
RAYMOND v2.8 - Automatic Paper Entry Telemetry

Read-only runtime telemetry for Stage 17.6.

This module does not create, modify, or close trades.
It only exposes the current state recorded by the automatic
paper-entry worker.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/online",
    tags=["Automatic Paper Entry"],
)


@router.get("/automatic-entry-status")
async def automatic_entry_status():
    """
    Return the current Stage 17.6 automatic-entry worker status.

    Safety:
    - Read-only.
    - Paper trading only.
    - Never creates an order.
    - Never sends a broker order.
    """

    try:
        from . import automatic_entry_worker

        worker = getattr(
            automatic_entry_worker,
            "_ACTIVE_WORKER",
            None,
        )

        if worker is None:
            return {
                "status": "not_initialized",
                "enabled": True,
                "running": False,
                "symbol": "XAUUSD",
                "timeframe": "M15",
                "interval_seconds": 30.0,
                "paper_only": True,
                "execution_authorized": False,
                "broker_orders_allowed": False,
                "live_trading_enabled": False,
            }

        telemetry = worker.status()

        telemetry.update(
            {
                "status": (
                    "running"
                    if worker.running
                    else "stopped"
                ),
                "execution_authorized": False,
                "broker_orders_allowed": False,
                "live_trading_enabled": False,
            }
        )

        return telemetry

    except Exception as exc:
        return {
            "status": "telemetry_error",
            "enabled": True,
            "running": False,
            "paper_only": True,
            "execution_authorized": False,
            "broker_orders_allowed": False,
            "live_trading_enabled": False,
            "error": str(exc),
        }
