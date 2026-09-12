"""RAYMOND v2.8 public online market-data bridge.

Provides an online, broker-independent market feed for the Android
dashboard while MT5 is offline.

READ-ONLY ONLY:
- No broker orders
- No position modification
- No position closing
- No live trading
- No real-money execution
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

try:
    from .ai_trading_decision import (
        AIDecisionError,
        AIDirection,
        AITradingDecisionEngine,
        TechnicalContext,
    )
    from .technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )
    from .mt5_service import mt5_service
except ImportError:
    from ai_trading_decision import (
        AIDecisionError,
        AIDirection,
        AITradingDecisionEngine,
        TechnicalContext,
    )
    from technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )
    from mt5_service import mt5_service


router = APIRouter(
    prefix="/api/online",
    tags=["Online Market"],
)

_ai = AITradingDecisionEngine()

_YAHOO_BASE = (
    "https://query1.finance.yahoo.com/v8/finance/chart"
)

_INTERVALS = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "1h",
    "D1": "1d",
}

_RANGES = {
    "M1": "1d",
    "M5": "5d",
    "M15": "10d",
    "M30": "1mo",
    "H1": "3mo",
    "H4": "6mo",
    "D1": "2y",
}


def _utc() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _ticker(symbol: str) -> str:
    """Convert a Raymond symbol into the public feed symbol."""
    normalized = symbol.strip().upper()

    if normalized in {
        "XAUUSD",
        "XAU/USD",
        "GOLD",
    }:
        return "XAUUSD=X"

    raise HTTPException(
        status_code=400,
        detail={
            "error": (
                "Online public feed currently "
                "supports XAUUSD only"
            ),
            "symbol": normalized,
        },
    )


async def _fetch_chart(
    symbol: str,
    timeframe: str,
    limit: int,
) -> dict[str, Any]:
    """Fetch public XAUUSD candles."""

    normalized_timeframe = timeframe.strip().upper()

    interval = _INTERVALS.get(normalized_timeframe)

    if interval is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Unsupported timeframe",
                "timeframe": timeframe,
            },
        )

    ticker = _ticker(symbol)

    params = {
        "interval": interval,
        "range": _RANGES[normalized_timeframe],
        "events": "history",
    }

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={
                "User-Agent": (
                    "RAYMOND-v2.8/online-market"
                )
            },
        ) as client:

            response = await client.get(
                f"{_YAHOO_BASE}/{ticker}",
                params=params,
            )

            response.raise_for_status()
            payload = response.json()

    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Online market feed unavailable",
                "message": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    chart = payload.get("chart") or {}

    results = chart.get("result") or []

    result = results[0] if results else None

    if not result:
        raise HTTPException(
            status_code=503,
            detail={
                "error": (
                    "Online market feed returned "
                    "no data"
                ),
                "timestamp": _utc(),
            },
        )

    timestamps = result.get("timestamp") or []

    indicators = result.get("indicators") or {}

    quote_list = indicators.get("quote") or []

    quote = quote_list[0] if quote_list else {}

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    candles: list[dict[str, Any]] = []

    for index, timestamp in enumerate(timestamps):

        open_price = (
            opens[index]
            if index < len(opens)
            else None
        )

        high_price = (
            highs[index]
            if index < len(highs)
            else None
        )

        low_price = (
            lows[index]
            if index < len(lows)
            else None
        )

        close_price = (
            closes[index]
            if index < len(closes)
            else None
        )

        if any(
            value is None
            for value in (
                open_price,
                high_price,
                low_price,
                close_price,
            )
        ):
            continue

        volume = (
            volumes[index]
            if index < len(volumes)
            else 0
        )

        candles.append(
            {
                "time": int(timestamp),
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
                "volume": float(volume or 0),
            }
        )

    candles = candles[-limit:]

    if len(candles) < 60:
        raise HTTPException(
            status_code=422,
            detail={
                "error": (
                    "Insufficient online candle data"
                ),
                "required": 60,
                "received": len(candles),
            },
        )

    meta = result.get("meta") or {}

    price = meta.get("regularMarketPrice")

    if price is None:
        price = candles[-1]["close"]

    return {
        "symbol": "XAUUSD",
        "source_symbol": ticker,
        "timeframe": normalized_timeframe,
        "price": float(price),
        "candles": candles,
        "source": (
            "Yahoo Finance public chart feed"
        ),
        "source_type": "public_reference_feed",
        "timestamp": _utc(),
        "market_timestamp": meta.get(
            "regularMarketTime"
        ),
        "live_trading_allowed": False,
    }


def _context(indicators) -> TechnicalContext:
    """Convert indicator results into AI technical context."""

    return TechnicalContext(
        symbol=indicators.symbol,
        timeframe=indicators.timeframe,
        close=indicators.close,
        ema20=indicators.ema20,
        ema50=indicators.ema50,
        rsi14=indicators.rsi14,
        atr14=indicators.atr14,
        macd=indicators.macd,
        macd_signal=indicators.macd_signal,
        macd_histogram=indicators.macd_histogram,
        trend=indicators.trend,
        score=indicators.score,
        signal=indicators.signal,
        candles_used=indicators.candles_used,
    )


def _decision_payload(decision) -> dict[str, Any]:
    """Serialize the AI decision safely."""

    proposal = (
        None
        if decision.proposal is None
        else asdict(decision.proposal)
    )

    if proposal:
        direction = proposal.get("direction")

        if isinstance(direction, AIDirection):
            proposal["direction"] = direction.value

    return {
        "direction": decision.direction.value,
        "action": (
            decision.direction.value
            if decision.direction != AIDirection.WAIT
            else "HOLD/WAIT"
        ),
        "confidence": float(decision.confidence),
        "technical_score": decision.technical_score,
        "trend": decision.trend,
        "signal": decision.signal,
        "reasoning": decision.reasoning,
        "execution_type": decision.execution_type,
        "read_only": decision.read_only,
        "broker_order_required": (
            decision.broker_order_required
        ),
        "risk_engine_required": (
            decision.risk_engine_required
        ),
        "proposal": proposal,
    }


@router.get("/status")
async def online_status():
    """Return online trading-system permissions."""

    mt5_connected = bool(
        getattr(
            mt5_service,
            "connected",
            False,
        )
    )

    return {
        "online": True,
        "market_feed": True,
        "market_feed_source": (
            "Yahoo Finance public chart feed"
        ),
        "mt5_connected": mt5_connected,
        "paper_trading_enabled": True,
        "demo_trading_enabled": True,

        # Safety lock.
        "live_trading_enabled": False,
        "execution_authorized": False,
        "broker_orders_allowed": False,

        "trading_permissions": {
            "market_read": True,
            "analysis": True,
            "paper": True,
            "mt5_demo": mt5_connected,
            "live": False,
        },

        "timestamp": _utc(),
    }


@router.get("/price")
async def online_price(
    symbol: str = Query(
        "XAUUSD",
        min_length=1,
        max_length=32,
    ),
):
    """Return the latest available online XAUUSD price."""

    data = await _fetch_chart(
        symbol,
        "M15",
        60,
    )

    return {
        "symbol": data["symbol"],
        "price": data["price"],
        "source": data["source"],
        "source_type": data["source_type"],
        "market_timestamp": (
            data["market_timestamp"]
        ),
        "timestamp": data["timestamp"],

        # Safety lock.
        "live_trading_enabled": False,
    }


@router.get("/candlesticks")
async def online_candlesticks(
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
    """Return online XAUUSD candlestick data."""

    return await _fetch_chart(
        symbol,
        timeframe,
        limit,
    )


@router.get("/indicators")
async def online_indicators(
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
    """Calculate technical indicators from online candles."""

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

    except TechnicalIndicatorError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    return {
        "symbol": "XAUUSD",
        "timeframe": data["timeframe"],
        "price": data["price"],
        "source": data["source"],
        "indicators": indicator_result_to_dict(
            indicators
        ),

        # Safety lock.
        "live_trading_enabled": False,

        "timestamp": _utc(),
    }


@router.get("/analysis")
async def online_analysis(
    symbol: str = Query(
        "XAUUSD",
        min_length=1,
        max_length=32,
    ),
    timeframe: str = Query(
        "M15",
        min_length=2,
        max_length=4,
    ),
    limit: int = Query(
        100,
        ge=60,
        le=500,
    ),
):
    """Run technical analysis and the existing AI decision engine."""

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

        decision = _ai.evaluate(
            _context(indicators)
        )

    except (
        TechnicalIndicatorError,
        AIDecisionError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": str(exc),
                "action": "HOLD/WAIT",
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

        "indicators": indicator_result_to_dict(
            indicators
        ),

        "decision": _decision_payload(
            decision
        ),

        "safety": {
            "live_trading_enabled": False,
            "execution_authorized": False,
            "broker_order_allowed": False,
            "read_only": True,
        },

        "timestamp": _utc(),
    }
