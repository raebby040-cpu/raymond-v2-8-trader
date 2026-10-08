"""
RAYMOND v2.8 - Broker Integration

Central integration point for broker functionality.
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

    from .unified_execution_api import (
        router as unified_execution_router,
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

    from unified_execution_api import (
        router as unified_execution_router,
    )


router = APIRouter()


router.include_router(
    broker_accounts_router
)

router.include_router(
    mt5_adapter_router
)

router.include_router(
    live_reconciliation_router
)

router.include_router(
    live_position_monitor_router
)

router.include_router(
    live_position_protection_router
)

router.include_router(
    live_position_protection_worker_router
)

router.include_router(
    live_execution_router
)

# ---------------------------------------------------------------------------
# UNIFIED DEMO/LIVE EXECUTION
# ---------------------------------------------------------------------------

router.include_router(
    unified_execution_router
)
