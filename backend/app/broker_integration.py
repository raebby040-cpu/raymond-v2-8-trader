"""
RAYMOND v2.8 - Broker Integration

Central integration point for Step 17 broker functionality.

Provides:

- Broker account management
- MT5 broker adapter
- Live execution gateway
- Live reconciliation
- Live position monitoring
- Live position protection
- Live protection worker status
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

    from .live_position_monitor import (
        router as live_position_monitor_router,
    )

    from .live_position_protection import (
        router as live_position_protection_router,
    )

    from .live_position_protection_worker_api import (
        router as live_position_protection_worker_router,
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

    from live_position_monitor import (
        router as live_position_monitor_router,
    )

    from live_position_protection import (
        router as live_position_protection_router,
    )

    from live_position_protection_worker_api import (
        router as live_position_protection_worker_router,
    )


router = APIRouter()


# ---------------------------------------------------------------------------
# BROKER ACCOUNT MANAGEMENT
# ---------------------------------------------------------------------------

router.include_router(
    broker_accounts_router
)


# ---------------------------------------------------------------------------
# MT5 BROKER ADAPTER
# ---------------------------------------------------------------------------

router.include_router(
    mt5_adapter_router
)


# ---------------------------------------------------------------------------
# LIVE RECONCILIATION
# ---------------------------------------------------------------------------

router.include_router(
    live_reconciliation_router
)


# ---------------------------------------------------------------------------
# LIVE POSITION MONITOR
# ---------------------------------------------------------------------------

router.include_router(
    live_position_monitor_router
)


# ---------------------------------------------------------------------------
# LIVE POSITION PROTECTION
# ---------------------------------------------------------------------------

router.include_router(
    live_position_protection_router
)


# ---------------------------------------------------------------------------
# CONTINUOUS PROTECTION WORKER API
# ---------------------------------------------------------------------------

router.include_router(
    live_position_protection_worker_router
)


# ---------------------------------------------------------------------------
# LIVE EXECUTION
# ---------------------------------------------------------------------------

router.include_router(
    live_execution_router
)
