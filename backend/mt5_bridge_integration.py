"""
Raymond v2.8 — MT5 Bridge Integration
=====================================

Registers the read-only MT5 Bridge API router with a FastAPI application.

Safety:
- Does not submit broker orders.
- Does not modify or close positions.
- Does not enable live trading.
- Keeps the MT5 Bridge API separate from main.py.
"""

from __future__ import annotations

from fastapi import FastAPI

from .mt5_bridge_api import router as mt5_bridge_router


def register_mt5_bridge(app: FastAPI) -> None:
    """
    Register the MT5 Bridge API exactly once.

    Call this function from the existing FastAPI application's
    startup/module configuration after the app has been created.
    """
    if getattr(app.state, "mt5_bridge_registered", False):
        return

    app.include_router(mt5_bridge_router)
    app.state.mt5_bridge_registered = True
