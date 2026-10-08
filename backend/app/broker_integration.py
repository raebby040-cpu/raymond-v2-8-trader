"""
RAYMOND v2.8 - Broker Integration

Central integration point for Step 17 broker functionality.

Provides:

- Broker account management
- MT5 broker adapter
- Live execution gateway
- Live position reconciliation

IMPORTANT:

Importing this module does NOT enable live trading.

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

    from .live_reconciliation import (
        router as live_reconciliation_router,
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

    from live_reconciliation import (
        router as live_reconciliation_router,
    )


router = APIRouter()


# ============================================================
# BROKER ACCOUNTS
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


# ============================================================
# LIVE RECONCILIATION
# ============================================================

router.include_router(
    live_reconciliation_router,
)
