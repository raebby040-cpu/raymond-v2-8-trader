"""
RAYMOND v2.8 - Broker Integration

Central integration point for Step 17 broker functionality.

Provides:
- Broker account management
- MT5 broker adapter
- Live execution gateway

IMPORTANT:
Live execution remains fail-closed and requires every
independent safety gate.
"""

from fastapi import APIRouter

try:
    from .broker_accounts import (
        router as broker_accounts_router,
    )

    from .mt5_broker_adapter import (
        router as mt5_adapter_router,
    )

    from .live_execution_gateway import (
        router as live_execution_router,
    )

except ImportError:
    from broker_accounts import (
        router as broker_accounts_router,
    )

    from mt5_broker_adapter import (
        router as mt5_adapter_router,
    )

    from live_execution_gateway import (
        router as live_execution_router,
    )


# ============================================================
# CENTRAL BROKER ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# BROKER ACCOUNT MANAGEMENT
# ============================================================

router.include_router(
    broker_accounts_router,
)


# ============================================================
# MT5 BROKER ADAPTER
# ============================================================

router.include_router(
    mt5_adapter_router,
)


# ============================================================
# LIVE EXECUTION
# ============================================================

router.include_router(
    live_execution_router,
)
