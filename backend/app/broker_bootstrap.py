"""
RAYMOND v2.8 - Broker Bootstrap

Central bootstrap layer for broker functionality.

This module mounts:
- Broker account management
- MT5 broker adapter
- Live execution gateway

IMPORTANT:
Importing this module does NOT enable live trading.

The live execution gateway remains fail-closed and still
requires all independent safety gates before an order can
be sent to a broker.
"""

from fastapi import FastAPI


def mount_broker_integration(app: FastAPI) -> None:
    """
    Mount the complete Raymond broker integration.

    This function is intentionally explicit.

    It keeps broker-specific route registration outside
    main.py while allowing the production entrypoint
    (online_main.py) to activate the broker API layer.

    Live execution remains independently protected by:
    - LIVE_TRADING_ENABLED
    - broker-account selection
    - account verification
    - live authorization
    - emergency stop
    - MT5 health
    - risk validation
    - order validation
    - execution verification
    """

    try:
        from .broker_integration import (
            router as broker_router,
        )
    except ImportError:
        from broker_integration import (
            router as broker_router,
        )

    app.include_router(
        broker_router,
    )
