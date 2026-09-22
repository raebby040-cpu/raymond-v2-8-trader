"""
RAYMOND v2.8 - Persistent Paper Equity Provider

Stage 20.6B

Provides the authoritative paper-account equity directly from
the PostgreSQL-persisted paper positions.

Safety:
- Paper trading only.
- No broker orders.
- No MT5 execution.
- Does not alter strategy logic.
- Does not alter position-management logic.
"""

from __future__ import annotations

from .persistent_paper_account import get_persistent_paper_equity


def get_paper_equity() -> float:
    """
    Return the authoritative persistent paper equity.

    The value comes from the persistent paper-account calculation,
    not from the in-memory DemoTradingEngine.
    """
    return float(get_persistent_paper_equity())


__all__ = ["get_paper_equity"]
