"""
RAYMOND v2.8 - Broker Bootstrap

Central bootstrap layer for broker functionality.

Mounts:

- Broker account management
- MT5 broker adapter
- Live execution gateway
- Live reconciliation
- Live position monitoring
- Live position protection
- Continuous live protection worker

IMPORTANT:

Importing this module does NOT enable live trading.

Live execution remains fail-closed.

The continuous protection worker is independently disabled
unless RAYMOND_LIVE_PROTECTION_WORKER_ENABLED=true.

Actual SL modification is independently disabled unless:

RAYMOND_POSITION_PROTECTION_ENABLED=true
"""

from fastapi import FastAPI


_worker_registered = False


def mount_broker_integration(
    app: FastAPI,
) -> None:
    """
    Mount the complete Raymond broker API and protection layer.

    main.py is intentionally untouched.

    Live trading remains protected by independent gates.
    """

    global _worker_registered

    try:

        from .broker_integration import (
            router as broker_router,
        )

        from .live_position_protection_worker import (
            start_live_position_protection_worker,
            stop_live_position_protection_worker,
        )

    except ImportError:

        from broker_integration import (
            router as broker_router,
        )

        from live_position_protection_worker import (
            start_live_position_protection_worker,
            stop_live_position_protection_worker,
        )

    # --------------------------------------------------------------
    # API routes
    # --------------------------------------------------------------

    app.include_router(
        broker_router,
    )

    # --------------------------------------------------------------
    # Protection worker lifecycle
    #
    # This is registered once per FastAPI application instance.
    #
    # The worker itself remains disabled unless explicitly enabled
    # by environment configuration.
    # --------------------------------------------------------------

    if not _worker_registered:

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

        _worker_registered = True
