"""
RAYMOND v2.8 - Broker Integration

Central integration point for Step 17 broker functionality.

This module combines:
- Broker account management
- MT5 broker adapter

The main FastAPI application only needs to mount this
single router.

IMPORTANT:
This integration layer does NOT enable live trading.
"""

from fastapi import APIRouter

try:
    from .broker_accounts import router as broker_accounts_router
    from .mt5_broker_adapter import router as mt5_adapter_router
except ImportError:
    from broker_accounts import router as broker_accounts_router
    from mt5_broker_adapter import router as mt5_adapter_router


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
