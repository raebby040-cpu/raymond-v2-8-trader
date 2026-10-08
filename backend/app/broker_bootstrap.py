"""
RAYMOND v2.8 - Broker Bootstrap

Central bootstrap layer for broker functionality.

Live remains fail-closed.

DEMO worker:
    Disabled unless explicitly enabled with
    RAYMOND_MT5_DEMO_WORKER_ENABLED=true.

LIVE protection worker:
    Disabled unless explicitly enabled with
    RAYMOND_LIVE_PROTECTION_WORKER_ENABLED=true.

LIVE authorization:
    Mounted as an API route, but disabled by default.

Canonical trading state:
    Mounted as a read-only API route.

The canonical state does not place orders.
"""

from fastapi import FastAPI


_worker_registered = False


def mount_broker_integration(
    app: FastAPI,
) -> None:
    """
    Mount broker APIs, canonical state APIs and register
    broker worker lifecycles.
    """

    global _worker_registered

    try:
        from .broker_integration import (
            router as broker_router,
        )

        from .live_authorization import (
            router as live_authorization_router,
        )

        from .canonical_state import (
            router as canonical_state_router,
        )

        from .live_position_protection_worker import (
            start_live_position_protection_worker,
            stop_live_position_protection_worker,
        )

        from .demo_execution_worker import (
            start_demo_execution_worker,
            stop_demo_execution_worker,
        )

    except ImportError:
        from broker_integration import (
            router as broker_router,
        )

        from live_authorization import (
            router as live_authorization_router,
        )

        from canonical_state import (
            router as canonical_state_router,
        )

        from live_position_protection_worker import (
            start_live_position_protection_worker,
            stop_live_position_protection_worker,
        )

        from demo_execution_worker import (
            start_demo_execution_worker,
            stop_demo_execution_worker,
        )

    # ----------------------------------------------------------
    # API ROUTES
    # ----------------------------------------------------------

    app.include_router(
        broker_router,
    )

    app.include_router(
        live_authorization_router,
    )

    app.include_router(
        canonical_state_router,
    )

    # ----------------------------------------------------------
    # WORKER LIFECYCLE
    # ----------------------------------------------------------

    if _worker_registered:
        return

    @app.on_event(
        "startup"
    )
    async def _start_raymond_live_protection_worker():
        await start_live_position_protection_worker()

    @app.on_event(
        "shutdown"
    )
    async def _stop_raymond_live_protection_worker():
        await stop_live_position_protection_worker()

    @app.on_event(
        "startup"
    )
    async def _start_raymond_demo_execution_worker():
        await start_demo_execution_worker()

    @app.on_event(
        "shutdown"
    )
    async def _stop_raymond_demo_execution_worker():
        await stop_demo_execution_worker()

    _worker_registered = True
