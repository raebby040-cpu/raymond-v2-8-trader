"""
Raymond v2.8 — MT5 Bridge Integration.

Registers the read-only MT5 Bridge API with FastAPI.

Safety:
- Does not submit broker orders.
- Does not modify or close broker positions.
- Does not enable live trading.
- Does not bypass the Risk Engine or Emergency Stop.
- Registers the router only once per application instance.
"""

from __future__ import annotations

from fastapi import FastAPI

try:
    from .mt5_bridge_api import router as mt5_bridge_router
except ImportError:
    from mt5_bridge_api import router as mt5_bridge_router


def register_mt5_bridge(app: FastAPI) -> None:
    """Register the read-only MT5 Bridge API exactly once."""
    if getattr(app.state, "mt5_bridge_registered", False):
        return

    app.include_router(mt5_bridge_router)
    app.state.mt5_bridge_registered = True
