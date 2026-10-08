"""
Raymond v2.8 — MT5 Bridge Integration
=====================================

Registers the read-only MT5 Bridge API router with the existing
FastAPI application.

Safety:
- Does not submit broker orders.
- Does not modify or close broker positions.
- Does not enable live trading.
- Does not bypass the Risk Engine or Emergency Stop.
- Registers the router only once per application instance.
"""

from __future__ import annotations

from fastapi import FastAPI

from .mt5_bridge_api import router as mt5_bridge_router


def register_mt5_bridge(app: FastAPI) -> None:
    """
    Register the read-only MT5 Bridge API with the FastAPI app.

    Call after the FastAPI application has been created.
    Repeated calls will not register the router twice.
    """
    if getattr(app.state, "mt5_bridge_registered", False):
        return

    app.include_router(mt5_bridge_router)
    app.state.mt5_bridge_registered = True
