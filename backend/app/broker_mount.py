"""
RAYMOND v2.8 - Broker Route Mount

Central FastAPI mounting layer for all broker functionality.

Mounted functionality:
- Broker account management
- MT5 broker adapter
- Live execution gateway

This module does NOT enable live trading.
Live execution remains fail-closed and is controlled by
the independent safety gates in the execution gateway.
"""

from fastapi import FastAPI


def mount_broker_routes(app: FastAPI) -> None:
    """
    Mount all Raymond broker-related API routes.

    Keeping this in a separate module prevents main.py from
    becoming tightly coupled to every broker implementation.

    The function is intentionally explicit and idempotent:
    calling it once is expected during application startup.
    """

    try:
        from .broker_integration import (
            router as broker_integration_router,
        )
    except ImportError:
        from broker_integration import (
            router as broker_integration_router,
        )

    app.include_router(
        broker_integration_router,
    )
