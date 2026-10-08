"""
RAYMOND v2.8 - Canonical Online Main Entrypoint.

Loads the existing online_main application, then patches its bound
paper-account providers so the production runtime uses the canonical
persistent paper trading system.

Canonical accounting:
    Starting balance = $1,000
    Balance = starting balance + realized P&L
    Equity = balance + unrealized P&L

Persistent Position records are the source of truth.

Live broker execution remains disabled.
"""

from __future__ import annotations

import online_main as _online_main

from app.online_main_canonical_runtime_patch import (
    install_into_online_main,
)


# Patch the already-loaded online_main module namespace.
#
# This replaces the function references actually used by the
# automatic entry worker and other runtime components.
install_into_online_main(vars(_online_main))


# Re-export the existing FastAPI application.
#
# Uvicorn will load this module instead of loading online_main:app
# directly. The underlying application object remains unchanged.
app = _online_main.app


__all__ = ["app"]
