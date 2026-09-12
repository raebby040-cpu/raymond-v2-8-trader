"""
RAYMOND v2.8 - MT5 AI Decision Bridge

STEP 11B-4

Purpose:
- Provides a READ-ONLY endpoint for the MT5 EA.
- Reads real MT5 candles and current bid/ask.
- Uses Raymond's existing technical-indicator engine.
- Uses Raymond's existing AITradingDecisionEngine.
- Returns the current AI decision and paper-trade proposal.
- Does NOT place broker orders.
- Does NOT modify positions.
- Does NOT close positions.
- Does NOT authorize live execution.

Safety:
- Step 11B-4 is READ ONLY.
- Live trading remains disabled.
- Risk Engine approval is still required.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

try:
    from .mt5_service import MT5ServiceError, mt5_service
    from .technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
    )
    from .ai_trading_decision import (
        AIDecisionError,
        AITradingDecisionEngine,
        AIDirection,
        TechnicalContext,
    )
except ImportError:
    from mt5_service import MT5ServiceError, mt5_service
    from technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
    )
    from ai_trading_decision import (
        AIDecisionError,
        AITradingDecisionEngine,
        AIDirection,
        TechnicalContext,
    )


router = APIRouter(
    prefix="/api/mt5",
    tags=["MT5 Decision Bridge"],
)


# ------------------------------------------------------------
# EXISTING RAYMOND AI ENGINE
# ------------------------------------------------------------

_ai = AITradingDecisionEngine()


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def utc_timestamp() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def direction_to_action(direction: AIDirection) -> str:
    """
    Convert Raymond's internal AI direction into
    a simple API action.
    """

    if direction == AIDirection.BUY:
        return "BUY"

    if direction == AIDirection.SELL:
        return "SELL"

    return "HOLD/WAIT"


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def proposal_to_dict(proposal):
    """
    Convert the immutable AITradeProposal dataclass
    into a JSON-safe dictionary.
    """

    if proposal is None:
        return None

    data = asdict(proposal)

    direction = data.get("direction")

    if isinstance(direction, AIDirection):
        data["direction"] = direction.value

    return data


def decision_to_response(
    *,
    decision,
    symbol: str,
    timeframe: str,
    bid: float,
    ask: float,
    indicators,
):
    """
    Convert Raymond's AIDecision object into the
    external MT5 bridge response.
    """

    action = direction_to_action(
        decision.direction
    )

    proposal = proposal_to_dict(
        decision.proposal
    )

    return {
        "accepted": True,

        "bridge": {
            "name": "Raymond MT5 AI Decision Bridge",
            "version": "0.1.0",
            "step": "11B-4",
            "mode": "READ_ONLY",
        },

        "safety": {
            "trading_enabled": False,
            "live_trading_enabled": False,
            "execution_authorized": False,
            "execution_allowed": False,

            "risk_engine_required": True,

            "reason": (
                "Step 11B-4 provides AI decision support "
                "only. Broker execution is disabled."
            ),
        },

        "market": {
            "symbol": symbol,
            "timeframe": timeframe,
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
            "close": safe_float(
                indicators.close
            ),
        },

        "indicators": {
            "symbol": indicators.symbol,
            "timeframe": indicators.timeframe,

            "close": safe_float(
                indicators.close
            ),

            "ema20": (
                safe_float(indicators.ema20)
                if indicators.ema20 is not None
                else None
            ),

            "ema50": (
                safe_float(indicators.ema50)
                if indicators.ema50 is not None
                else None
            ),

            "rsi14": (
                safe_float(indicators.rsi14)
                if indicators.rsi14 is not None
                else None
            ),

            "atr14": (
                safe_float(indicators.atr14)
                if indicators.atr14 is not None
                else None
            ),

            "macd": (
                safe_float(indicators.macd)
                if indicators.macd is not None
                else None
            ),

            "macd_signal": (
                safe_float(indicators.macd_signal)
                if indicators.macd_signal is not None
                else None
            ),

            "macd_histogram": (
                safe_float(indicators.macd_histogram)
                if indicators.macd_histogram is not None
                else None
            ),

            "trend": indicators.trend,
            "score": indicators.score,
            "signal": indicators.signal,
            "candles_used": indicators.candles_used,
        },

        "decision": {
            "direction": (
                decision.direction.value
            ),

            "action": action,

            "confidence": safe_float(
                decision.confidence
            ),

            "technical_score": decision.technical_score,

            "trend": decision.trend,

            "signal": decision.signal,

            "reasoning": decision.reasoning,

            "execution_type": (
                decision.execution_type
            ),

            "read_only": (
                decision.read_only
            ),

            "broker_order_required": (
                decision.broker_order_required
            ),

            "risk_engine_required": (
                decision.risk_engine_required
            ),

            "proposal": proposal,
        },

        "timestamp": utc_timestamp(),
    }


# ------------------------------------------------------------
# MT5 AI DECISION ENDPOINT
# ------------------------------------------------------------

@router.get("/decision")
async def get_mt5_decision(
    symbol: str = Query(
        default="XAUUSD",
        min_length=1,
        max_length=32,
    ),

    timeframe: str = Query(
        default="M15",
        min_length=2,
        max_length=4,
    ),

    limit: int = Query(
        default=100,
        ge=60,
        le=500,
    ),
):
    """
    Return Raymond's current AI decision using
    real MT5 market data.

    READ ONLY.

    This endpoint does NOT:

    - open trades
    - close trades
    - modify stop loss
    - modify take profit
    - send broker orders
    - authorize live trading
    - bypass the Risk Engine
    - bypass the Emergency Stop
    """

    # --------------------------------------------------------
    # HARD MT5 CONNECTION CHECK
    # --------------------------------------------------------

    if not mt5_service.connected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "MT5 is not connected",

                "action": "HOLD/WAIT",

                "execution_authorized": False,

                "live_trading_enabled": False,

                "timestamp": utc_timestamp(),
            },
        )

    # --------------------------------------------------------
    # READ MT5 MARKET DATA
    # --------------------------------------------------------

    try:
        candles = await mt5_service.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

        # ----------------------------------------------------
        # REQUIRE SUFFICIENT CANDLE DATA
        # ----------------------------------------------------

        if len(candles) < 60:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": (
                        "Insufficient MT5 candle data"
                    ),

                    "required": 60,

                    "received": len(candles),

                    "action": "HOLD/WAIT",

                    "execution_authorized": False,

                    "live_trading_enabled": False,

                    "timestamp": utc_timestamp(),
                },
            )

        # ----------------------------------------------------
        # CURRENT BID / ASK
        # ----------------------------------------------------

        tick = await mt5_service.get_symbol_tick(
            symbol
        )

        bid = safe_float(
            tick.get("bid", 0.0)
        )

        ask = safe_float(
            tick.get("ask", 0.0)
        )

        # ----------------------------------------------------
        # QUOTE SAFETY CHECK
        # ----------------------------------------------------

        if (
            bid <= 0
            or ask <= 0
            or ask < bid
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": (
                        "Invalid MT5 market quote"
                    ),

                    "bid": bid,

                    "ask": ask,

                    "action": "HOLD/WAIT",

                    "execution_authorized": False,

                    "live_trading_enabled": False,

                    "timestamp": utc_timestamp(),
                },
            )

        # ----------------------------------------------------
        # CALCULATE EXISTING TECHNICAL INDICATORS
        # ----------------------------------------------------

        indicators = calculate_indicators(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
        )

        # ----------------------------------------------------
        # BUILD THE EXISTING RAYMOND TECHNICAL CONTEXT
        # ----------------------------------------------------
        #
        # IMPORTANT:
        # We use Raymond's existing TechnicalContext.
        #
        # We do NOT create a second AI system here.
        #

        context = TechnicalContext(
            symbol=indicators.symbol,

            timeframe=indicators.timeframe,

            close=indicators.close,

            ema20=indicators.ema20,

            ema50=indicators.ema50,

            rsi14=indicators.rsi14,

            atr14=indicators.atr14,

            macd=indicators.macd,

            macd_signal=indicators.macd_signal,

            macd_histogram=(
                indicators.macd_histogram
            ),

            trend=indicators.trend,

            score=indicators.score,

            signal=indicators.signal,

            candles_used=(
                indicators.candles_used
            ),
        )

        # ----------------------------------------------------
        # RUN EXISTING RAYMOND AI ENGINE
        # ----------------------------------------------------

        decision = _ai.evaluate(
            context
        )

        # ----------------------------------------------------
        # RETURN READ-ONLY RESULT
        # ----------------------------------------------------

        return decision_to_response(
            decision=decision,

            symbol=symbol,

            timeframe=timeframe,

            bid=bid,

            ask=ask,

            indicators=indicators,
        )

    # --------------------------------------------------------
    # EXPECTED MT5 / INDICATOR ERRORS
    # --------------------------------------------------------

    except HTTPException:
        raise

    except (
        MT5ServiceError,
        TechnicalIndicatorError,
        AIDecisionError,
    ) as exc:

        raise HTTPException(
            status_code=422,

            detail={
                "error": (
                    "MT5 AI decision pipeline "
                    "failed safely"
                ),

                "message": str(exc),

                "action": "HOLD/WAIT",

                "execution_authorized": False,

                "live_trading_enabled": False,

                "timestamp": utc_timestamp(),
            },
        ) from exc

    # --------------------------------------------------------
    # UNEXPECTED FAILURE
    # --------------------------------------------------------

    except Exception as exc:

        raise HTTPException(
            status_code=500,

            detail={
                "error": (
                    "Unexpected MT5 decision "
                    "bridge error"
                ),

                "message": str(exc),

                "action": "HOLD/WAIT",

                "execution_authorized": False,

                "live_trading_enabled": False,

                "timestamp": utc_timestamp(),
            },
        ) from exc
