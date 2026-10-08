"""
RAYMOND v2.8 - Live Protection Worker API

STEP 17.6F

Read-only API for the continuous live-position protection worker.

This module:

- exposes worker status;
- exposes protection configuration;
- allows a manual dry-run cycle;
- never opens trades;
- never enables live trading;
- never changes broker positions through the status endpoints.

Actual automatic execution remains controlled by the worker and
its independent environment gates.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

try:
    from .live_position_protection_worker import (
        get_live_position_protection_worker,
        protection_worker_status,
    )
    from .live_position_protection import (
        LivePositionProtectionError,
        protect_live_positions,
        protection_config,
    )
except ImportError:
    from live_position_protection_worker import (
        get_live_position_protection_worker,
        protection_worker_status,
    )
    from live_position_protection import (
        LivePositionProtectionError,
        protect_live_positions,
        protection_config,
    )


router = APIRouter(
    prefix="/api/live-protection-worker",
    tags=["Live Protection Worker"],
)


@router.get("/status")
async def get_worker_status():
    """
    Return complete worker and protection configuration status.

    READ ONLY.

    This endpoint does not modify MT5.
    """

    worker = (
        get_live_position_protection_worker()
    )

    return {
        "status": "ok",

        "worker": worker.status(),

        "protection": protection_config(),

        "safety": {
            "fail_closed": True,
            "opens_orders": False,
            "enables_live_trading": False,
            "modifies_positions": False,
            "status_endpoint_read_only": True,
        },
    }


@router.get("/health")
async def get_worker_health():
    """
    Lightweight health view.

    A worker that is not configured to run is reported as
    disabled rather than unhealthy.

    If configured to run but has failed cycles, the health
    response exposes that condition without attempting
    broker remediation.
    """

    worker = (
        get_live_position_protection_worker()
    )

    status = worker.status()

    configured = bool(
        status.get(
            "protection_enabled",
            False,
        )
    )

    running = bool(
        status.get(
            "running",
            False,
        )
    )

    failed_cycles = int(
        status.get(
            "failed_cycles",
            0,
        )
        or 0
    )

    if not configured:
        worker_state = "disabled"

    elif not running:
        worker_state = "stopped"

    elif failed_cycles > 0:
        worker_state = "degraded"

    else:
        worker_state = "healthy"

    return {
        "status": worker_state,

        "worker_running": running,

        "protection_enabled": configured,

        "failed_cycles": failed_cycles,

        "last_error": status.get(
            "last_error"
        ),

        "fail_closed": True,

        "timestamp": status.get(
            "timestamp"
        ),
    }


@router.post("/dry-run")
async def run_protection_dry_run():
    """
    Execute ONE protection evaluation in dry-run mode.

    This endpoint NEVER modifies the broker.

    It is intended for demo/testing and validation of
    break-even/trailing calculations.
    """

    worker = (
        get_live_position_protection_worker()
    )

    try:

        result = await protect_live_positions(
            symbol=worker.symbol,
            magic=worker.magic,
            dry_run=True,
        )

        return {
            "status": "completed",

            "dry_run": True,

            "broker_modified": False,

            "protection": result,

            "safety": {
                "fail_closed": True,
                "orders_created": False,
                "positions_modified": False,
                "live_trading_enabled": False,
            },
        }

    except LivePositionProtectionError as exc:

        raise HTTPException(
            status_code=503,

            detail={
                "error": (
                    "LIVE_PROTECTION_DRY_RUN_FAILED"
                ),

                "message": str(exc),

                "dry_run": True,

                "broker_modified": False,

                "fail_closed": True,
            },
        ) from exc


@router.get("/configuration")
async def get_worker_configuration():
    """
    Return the effective protection configuration.

    READ ONLY.
    """

    worker = (
        get_live_position_protection_worker()
    )

    return {
        "status": "ok",

        "worker": {
            "symbol": worker.symbol,
            "magic": worker.magic,
            "interval_seconds": (
                worker.interval_seconds
            ),
        },

        "protection": protection_config(),

        "safety": {
            "fail_closed": True,
            "read_only": True,
        },
    }
