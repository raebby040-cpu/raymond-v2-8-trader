"""
RAYMOND v2.8 - Stage 20.6B Persistent Equity Startup Bridge

Keeps backend/app/main.py unchanged.

This startup bridge replaces the paper-equity provider used by
online_main.py with the persistent PostgreSQL paper-account provider.

Safety:
- Paper trading only.
- No broker orders.
- No MT5 execution.
- Does not change strategy or position management.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("raymond.persistent_equity_bridge")


def _persistent_paper_equity() -> float:
    """Return authoritative equity from persisted paper positions."""
    from app.persistent_paper_account import get_persistent_paper_equity

    return float(get_persistent_paper_equity())


try:
    # Load the existing application module first, then replace only
    # its paper-equity provider. online_main.py imports this provider
    # after app.main has loaded.
    import app.main as _raymond_main

    _raymond_main.get_paper_equity = _persistent_paper_equity

    logger.info(
        "Stage 20.6B: persistent paper-equity provider installed."
    )

except Exception:
    logger.exception(
        "Stage 20.6B: failed to install persistent paper-equity provider."
    )
    raise
