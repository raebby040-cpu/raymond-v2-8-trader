"""
RAYMOND v2.8 - Advisory Brain Analysis API

PURPOSE
-------
Expose the independent 8-brain advisory ensemble alongside the
existing RAYMOND Step 13 decision.

SAFETY
------
This endpoint is READ-ONLY.

It does NOT:
- place orders
- modify positions
- close positions
- contact MT5 for execution
- contact a broker
- bypass Step 14 Risk Engine
- replace Step 13
- enable live trading

The existing RAYMOND Step 13 decision remains the official
strategy decision.

This endpoint only compares:

    RAYMOND Step 13
            +
    8 independent advisory brains
            =
    advisory comparison

Possible comparison statuses:

    AGREE
    DISAGREE
    WEAK_ENTRY
    RAYMOND_WAIT
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

try:
    from .advisory_comparison import (
        analyze_and_compare,
    )
    from .ai_trading_decision import (
        AIDecisionError,
        AITradingDecisionEngine,
    )
    from .online_market_api import (
        _context,
        _decision_payload,
        _fetch_chart,
    )
    from .technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )
except ImportError:
    from advisory_comparison import (
        analyze_and_compare,
    )
    from ai_trading_decision import (
        AIDecisionError,
        AITradingDecisionEngine,
    )
    from online_market_api import (
        _context,
        _decision_payload,
        _fetch_chart,
    )
    from technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )


router = APIRouter(
    prefix="/api/online",
    tags=["Advisory Analysis"],
)

_ai = AITradingDecisionEngine()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/advisory-analysis")
async def advisory_analysis(
    symbol: str = Query(
        "XAUUSD",
        min_length=1,
        max_length=32,
    ),
    timeframe: str = Query(
        "H1",
        min_length=2,
        max_length=4,
    ),
    limit: int = Query(
        100,
        ge=60,
        le=500,
    ),
):
    """
    Run RAYMOND Step 13 and the independent 8-brain
    advisory ensemble, then compare their results.

    This endpoint is analysis-only.
    """

    data = await _fetch_chart(
        symbol,
        timeframe,
        limit,
    )

    try:
        indicators = calculate_indicators(
            symbol="XAUUSD",
            timeframe=data["timeframe"],
            candles=data["candles"],
        )

        context = _context(indicators)

        # --------------------------------------------------------
        # IMPORTANT:
        # This is the existing RAYMOND Step 13 decision.
        # It remains authoritative.
        # --------------------------------------------------------
        decision = _ai.evaluate(context)

        comparison = analyze_and_compare(
            decision=decision,
            context=context,
            candles=data["candles"],
        )

    except (
        TechnicalIndicatorError,
        AIDecisionError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    return {
        "accepted": True,

        "market": {
            "symbol": "XAUUSD",
            "timeframe": data["timeframe"],
            "price": data["price"],
        },

        "source": data["source"],
        "source_type": data.get(
            "source_type",
            "public_reference_feed",
        ),

        # Existing technical evidence.
        "indicators": indicator_result_to_dict(
            indicators
        ),

        # --------------------------------------------------------
        # OFFICIAL RAYMOND STEP 13 DECISION
        # --------------------------------------------------------
        "raymond": _decision_payload(
            decision
        ),

        # --------------------------------------------------------
        # 8-BRAIN ADVISORY COMPARISON
        # --------------------------------------------------------
        "advisory_comparison": comparison,

        # --------------------------------------------------------
        # HARD SAFETY FLAGS
        # --------------------------------------------------------
        "safety": {
            "read_only": True,
            "advisory_only": True,
            "paper_trading_enabled": True,
            "live_trading_enabled": False,
            "execution_authorized": False,
            "broker_orders_allowed": False,
            "risk_engine_bypass": False,
            "step13_replaced": False,
        },

        "timestamp": _utc(),
    }


__all__ = [
    "router",
]


