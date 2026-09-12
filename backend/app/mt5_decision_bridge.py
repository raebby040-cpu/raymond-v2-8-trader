"""
RAYMOND v2.8 - MT5 AI Decision Bridge

STEP 11B-4:
- Provides a read-only endpoint for the MT5 EA to retrieve
  Raymond's current AI trading decision.
- Uses the existing MT5 market-data service.
- Uses the existing technical-indicator layer.
- Uses the existing AI trading decision layer.
- Does NOT place, modify, or close broker orders.
- Live trading remains disabled.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

try:
    from .mt5_service import MT5ServiceError, mt5_service
    from .technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )
    from .ai_trading_decision import AIDecisionLayer
except ImportError:
    from mt5_service import MT5ServiceError, mt5_service
    from technical_indicators import (
        TechnicalIndicatorError,
        calculate_indicators,
        indicator_result_to_dict,
    )
    from ai_trading_decision import AIDecisionLayer


router = APIRouter(
    prefix="/api/mt5",
    tags=["MT5 Decision Bridge"],
)


_ai = AIDecisionLayer()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_action(decision: dict) -> str:
    recommendation = decision.get("recommendation", {})

    if not isinstance(recommendation, dict):
        return "HOLD/WAIT"

    action = str(
        recommendation.get(
            "action",
            "HOLD/WAIT",
        )
    ).upper()

    allowed_actions = {
        "BUY",
        "SELL",
        "HOLD",
        "HOLD/WAIT",
    }

    if action not in allowed_actions:
        return "HOLD/WAIT"

    if action == "HOLD":
        return "HOLD/WAIT"

    return action


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
    Return Raymond's current AI decision for MT5.

    IMPORTANT:
    This endpoint is READ ONLY.

    It does not:
    - open trades
    - close trades
    - modify SL
    - modify TP
    - authorize live trading

    It only delivers the current Raymond AI decision.
    """

    # ---------------------------------------------------------
    # HARD SAFETY LOCK
    # ---------------------------------------------------------

    if not mt5_service.connected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "MT5 is not connected",
                "action": "HOLD/WAIT",
                "execution_authorized": False,
                "timestamp": utc_timestamp(),
            },
        )

    try:
        # -----------------------------------------------------
        # 1. READ REAL MT5 CANDLES
        # -----------------------------------------------------

        candles = await mt5_service.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

        if len(candles) < 60:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Insufficient MT5 candle data",
                    "required": 60,
                    "received": len(candles),
                    "action": "HOLD/WAIT",
                    "execution_authorized": False,
                    "timestamp": utc_timestamp(),
                },
            )

        # -----------------------------------------------------
        # 2. READ CURRENT MT5 BID / ASK
        # -----------------------------------------------------

        tick = await mt5_service.get_symbol_tick(symbol)

        bid = float(
            tick.get(
                "bid",
                0.0,
            )
        )

        ask = float(
            tick.get(
                "ask",
                0.0,
            )
        )

        if bid <= 0 or ask <= 0 or ask < bid:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Invalid MT5 quote",
                    "action": "HOLD/WAIT",
                    "execution_authorized": False,
                    "timestamp": utc_timestamp(),
                },
            )

        # -----------------------------------------------------
        # 3. CALCULATE TECHNICAL INDICATORS
        # -----------------------------------------------------

        indicators = calculate_indicators(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
        )

        indicator_data = indicator_result_to_dict(
            indicators
        )

        # -----------------------------------------------------
        # 4. BUILD MARKET DATA FOR AI
        # -----------------------------------------------------

        closes = [
            float(candle["close"])
            for candle in candles
        ]

        market_data = {
            "current_price": float(
                indicators.close
            ),
            "bid": bid,
            "ask": ask,
            "price_history": closes,
            "indicators": {
                "ema20": (
                    indicators.ema20
                    if indicators.ema20 is not None
                    else indicators.close
                ),
                "ema50": (
                    indicators.ema50
                    if indicators.ema50 is not None
                    else indicators.close
                ),
                "rsi": (
                    indicators.rsi14
                    if indicators.rsi14 is not None
                    else 50.0
                ),
                "atr": (
                    indicators.atr14
                    if indicators.atr14 is not None
                    else 0.0
                ),
            },
        }

        # -----------------------------------------------------
        # 5. RUN EXISTING RAYMOND AI DECISION ENGINE
        # -----------------------------------------------------

        decision = _ai.make_decision(
            market_data
        )

        if not isinstance(decision, dict):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "AI decision engine returned invalid data",
                    "action": "HOLD/WAIT",
                    "execution_authorized": False,
                    "timestamp": utc_timestamp(),
                },
            )

        recommendation = decision.get(
            "recommendation",
            {},
        )

        action = normalize_action(
            decision
        )

        # -----------------------------------------------------
        # 6. HARD EXECUTION LOCK
        # -----------------------------------------------------
        #
        # Even if AI says BUY or SELL, this endpoint does NOT
        # authorize execution.
        #
        # Step 11B-4 is decision delivery only.
        #

        execution_authorized = False

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
                "execution_authorized": execution_authorized,
                "execution_allowed": False,
                "reason": (
                    "Step 11B-4 provides AI decisions only. "
                    "Broker execution is disabled."
                ),
            },

            "market": {
                "symbol": symbol,
                "timeframe": timeframe,
                "bid": bid,
                "ask": ask,
                "spread": ask - bid,
                "close": float(
                    indicators.close
                ),
            },

            "indicators": indicator_data,

            "decision": {
                "final_decision": str(
                    decision.get(
                        "final_decision",
                        "hold",
                    )
                ),
                "action": action,
                "confidence": float(
                    decision.get(
                        "confidence",
                        0.0,
                    )
                ),
                "risk_level": str(
                    decision.get(
                        "risk_level",
                        "UNKNOWN",
                    )
                ),
                "scores": decision.get(
                    "scores",
                    {},
                ),
                "recommendation": recommendation,
            },

            "timestamp": utc_timestamp(),
        }

    except HTTPException:
        raise

    except (
        MT5ServiceError,
        TechnicalIndicatorError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": (
                    "MT5 AI decision pipeline failed"
                ),
                "message": str(exc),
                "action": "HOLD/WAIT",
                "execution_authorized": False,
                "timestamp": utc_timestamp(),
            },
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": (
                    "Unexpected MT5 decision bridge error"
                ),
                "message": str(exc),
                "action": "HOLD/WAIT",
                "execution_authorized": False,
                "timestamp": utc_timestamp(),
            },
        ) from exc
