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

# ---------------------------------------------------------------------------
# BiQuote public market-data API
# ---------------------------------------------------------------------------

_BIQUOTE_BASE = "https://biquote.io/api"

_INTERVALS = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}


def _utc() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _ticker(symbol: str) -> str:
    """Convert a Raymond symbol into the BiQuote symbol."""
    normalized = symbol.strip().upper()

    if normalized in {
        "XAUUSD",
        "XAU/USD",
        "GOLD",
    }:
        return "XAUUSD"

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


def _bar_timestamp(value: Any) -> int:
    """Convert an ISO timestamp into Unix seconds."""
    if isinstance(value, (int, float)):
        return int(value)

    if not isinstance(value, str):
        raise ValueError("Invalid candle timestamp")

    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return int(parsed.timestamp())


async def _fetch_price(symbol: str) -> dict[str, Any]:
    """Fetch the latest XAUUSD price from BiQuote."""

    ticker = _ticker(symbol)

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={
                "User-Agent": "RAYMOND-v2.8/online-market",
                "Accept": "application/json",
            },
        ) as client:
            response = await client.get(
                f"{_BIQUOTE_BASE}/{ticker}",
            )

            response.raise_for_status()
            payload = response.json()

    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Online market price unavailable",
                "message": str(exc),
                "timestamp": _utc(),
            },
        ) from exc

    price = payload.get("mid")

    if price is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Online market feed returned no price",
                "timestamp": _utc(),
            },
        )

    return {
        "symbol": "XAUUSD",
        "price": float(price),
        "source": "BiQuote public MT5 reference feed",
        "source_type": "public_reference_feed",
        "market_timestamp": payload.get("timestamp"),
        "market_state": payload.get("marketState"),
        "stale": bool(payload.get("stale", False)),
        "quote_age_seconds": payload.get("quoteAgeSeconds"),
        "timestamp": _utc(),
        "live_trading_enabled": False,
    }


async def _fetch_chart(
    symbol: str,
    timeframe: str,
    limit: int,
) -> dict[str, Any]:
    """Fetch public XAUUSD candles from BiQuote."""

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

    # Request enough bars for technical calculations.
    request_limit = max(limit, 100)

    params = {
        "interval": interval,
        "limit": min(request_limit, 1000),
    }

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={
                "User-Agent": "RAYMOND-v2.8/online-market",
                "Accept": "application/json",
            },
        ) as client:

            response = await client.get(
                f"{_BIQUOTE_BASE}/{ticker}/ohlc",
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

    bars = payload.get("bars") or []

    if not bars:
        raise HTTPException(
            status_code=503,
            detail={
                "error": (
                    "Online market feed returned "
                    "no candle data"
                ),
                "timestamp": _utc(),
            },
        )

    candles: list[dict[str, Any]] = []

    for bar in bars:
        try:
            open_price = bar.get("open")
            high_price = bar.get("high")
            low_price = bar.get("low")
            close_price = bar.get("close")

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

            candles.append(
                {
                    "time": _bar_timestamp(
                        bar.get("openTime")
                    ),
                    "open": float(open_price),
                    "high": float(high_price),
                    "low": float(low_price),
                    "close": float(close_price),
                    "volume": float(
                        bar.get("volume")
                        or bar.get("tickVolume")
                        or 0
                    ),
                }
            )

        except (TypeError, ValueError):
            continue

    # BiQuote returns newest-first.
    # Raymond's indicator engine expects chronological order.
    candles.sort(key=lambda candle: candle["time"])

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

    # The latest candle close is the fallback price.
    price = candles[-1]["close"]

    return {
        "symbol": "XAUUSD",
        "source_symbol": ticker,
        "timeframe": normalized_timeframe,
        "price": float(price),
        "candles": candles,
        "source": "BiQuote public MT5 reference feed",
        "source_type": "public_reference_feed",
        "timestamp": _utc(),
        "market_timestamp": None,
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
            "BiQuote public MT5 reference feed"
        ),
        "mt5_connected": mt5_connected,
        "paper_trading_enabled": True,
        "demo_trading_enabled": True,

        # ---------------------------------------------------------------
        # SAFETY LOCK — LIVE TRADING IS PERMANENTLY DISABLED HERE.
        # ---------------------------------------------------------------
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

    data = await _fetch_price(symbol)

    return {
        "symbol": data["symbol"],
        "price": data["price"],
        "source": data["source"],
        "source_type": data["source_type"],
        "market_timestamp": data["market_timestamp"],
        "market_state": data["market_state"],
        "stale": data["stale"],
        "quote_age_seconds": data[
            "quote_age_seconds"
        ],
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
