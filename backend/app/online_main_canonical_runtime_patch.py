"""
RAYMOND v2.8 - Online Main Canonical Runtime Patch.

Provides a safe bridge for the production online_main.py module.

It updates the already-imported function references used by online_main.py:
- get_paper_equity
- build_persistent_paper_risk_state
- build_paper_risk_state

Canonical paper accounting:
    Starting balance = $1,000
    Balance = starting balance + realized P&L
    Equity = balance + unrealized P&L

Persistent Position records remain the source of truth.

Live broker execution remains disabled.
"""

from __future__ import annotations

from typing import Any, MutableMapping

from .canonical_paper_runtime import (
    canonical_paper_equity,
    canonical_paper_risk_state,
)


def install_into_online_main(
    namespace: MutableMapping[str, Any],
) -> None:
    """
    Patch the online_main.py module namespace in-place.

    Intended usage from online_main.py:

        install_into_online_main(globals())

    This must run after SessionLocal and PaperRiskState are available
    in the online_main.py namespace.
    """

    namespace["get_paper_equity"] = (
        lambda: canonical_paper_equity(namespace)
    )

    canonical_risk_provider = (
        lambda: canonical_paper_risk_state(namespace)
    )

    namespace["build_paper_risk_state"] = (
        canonical_risk_provider
    )

    # online_main.py imports this function directly from
    # persistent_paper_risk, so replace that bound reference too.
    namespace["build_persistent_paper_risk_state"] = (
        canonical_risk_provider
    )


def patch_online_main_module(
    online_main_module: Any,
) -> None:
    """
    Patch an already-loaded online_main module.

    Useful for tests or an external bootstrap.
    """

    namespace = vars(online_main_module)

    install_into_online_main(namespace)


__all__ = [
    "install_into_online_main",
    "patch_online_main_module",
]
