"""
RAYMOND v2.8 - Technical Indicator Engine

Calculates technical indicators from OHLC candle data.

Indicators:
- EMA 20
- EMA 50
- RSI 14
- ATR 14
- MACD 12/26/9

Also provides:
- trend direction
- technical score
- human-readable analysis

This module is READ ONLY.
It does not connect to MT5.
It does not place trades.
It does not modify positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence


class TechnicalIndicatorError(ValueError):
    """Raised when indicator input is invalid."""


@dataclass(frozen=True)
class IndicatorResult:
    """Calculated technical indicators."""

    symbol: str
    timeframe: str
    close: float

    ema20: Optional[float]
    ema50: Optional[float]

    rsi14: Optional[float]
    atr14: Optional[float]

    macd: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]

    trend: str
    score: int
    signal: str

    candles_used: int


# ============================================================
# INPUT NORMALIZATION
# ============================================================


def _number(
    value: Any,
    field: str,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TechnicalIndicatorError(
            f"Invalid numeric value for {field}."
        ) from exc

    if number != number:
        raise TechnicalIndicatorError(
            f"{field} cannot be NaN."
        )

    if number in (float("inf"), float("-inf")):
        raise TechnicalIndicatorError(
            f"{field} must be finite."
        )

    return number


def _extract_ohlc(
    candles: Sequence[Mapping[str, Any]],
) -> tuple[
    List[float],
    List[float],
    List[float],
    List[float],
]:
    if not candles:
        raise TechnicalIndicatorError(
            "At least one candle is required."
        )

    opens: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []

    for index, candle in enumerate(candles):
        try:
            high = _number(
                candle["high"],
                f"candle[{index}].high",
            )
            low = _number(
                candle["low"],
                f"candle[{index}].low",
            )
            close = _number(
                candle["close"],
                f"candle[{index}].close",
            )

            open_value = _number(
                candle.get("open", close),
                f"candle[{index}].open",
            )
        except KeyError as exc:
            raise TechnicalIndicatorError(
                f"Missing candle field: {exc.args[0]}."
            ) from exc

        if high < low:
            raise TechnicalIndicatorError(
                f"candle[{index}] high is below low."
            )

        if not (
            low <= open_value <= high
        ):
            raise TechnicalIndicatorError(
                f"candle[{index}] open is outside "
                "the high/low range."
            )

        if not (
            low <= close <= high
        ):
            raise TechnicalIndicatorError(
                f"candle[{index}] close is outside "
                "the high/low range."
            )

        opens.append(open_value)
        highs.append(high)
        lows.append(low)
        closes.append(close)

    return opens, highs, lows, closes


# ============================================================
# EMA
# ============================================================


def ema(
    values: Sequence[float],
    period: int,
) -> List[float]:
    """
    Calculate exponential moving average.

    The first EMA value is seeded with the SMA
    of the first `period` observations.
    """

    if period <= 0:
        raise TechnicalIndicatorError(
            "EMA period must be greater than zero."
        )

    if len(values) < period:
        return []

    numeric = [
        _number(value, "EMA input")
        for value in values
    ]

    multiplier = 2.0 / (period + 1.0)

    seed = sum(
        numeric[:period]
    ) / period

    result = [seed]

    previous = seed

    for value in numeric[period:]:
        current = (
            (value - previous) * multiplier
            + previous
        )

        result.append(current)
        previous = current

    return result


def latest_ema(
    values: Sequence[float],
    period: int,
) -> Optional[float]:
    result = ema(values, period)

    if not result:
        return None

    return result[-1]


# ============================================================
# RSI
# ============================================================


def rsi(
    closes: Sequence[float],
    period: int = 14,
) -> List[float]:
    """
    Calculate Wilder RSI.
    """

    if period <= 0:
        raise TechnicalIndicatorError(
            "RSI period must be greater than zero."
        )

    if len(closes) <= period:
        return []

    numeric = [
        _number(value, "RSI close")
        for value in closes
    ]

    gains: List[float] = []
    losses: List[float] = []

    for index in range(1, len(numeric)):
        change = (
            numeric[index]
            - numeric[index - 1]
        )

        gains.append(
            max(change, 0.0)
        )

        losses.append(
            max(-change, 0.0)
        )

    average_gain = (
        sum(gains[:period])
        / period
    )

    average_loss = (
        sum(losses[:period])
        / period
    )

    result: List[float] = []

    def calculate_rsi(
        gain: float,
        loss: float,
    ) -> float:
        if loss == 0:
            if gain == 0:
                return 50.0

            return 100.0

        relative_strength = gain / loss

        return 100.0 - (
            100.0
            / (1.0 + relative_strength)
        )

    result.append(
        calculate_rsi(
            average_gain,
            average_loss,
        )
    )

    for index in range(
        period,
        len(gains),
    ):
        average_gain = (
            (
                average_gain
                * (period - 1)
            )
            + gains[index]
        ) / period

        average_loss = (
            (
                average_loss
                * (period - 1)
            )
            + losses[index]
        ) / period

        result.append(
            calculate_rsi(
                average_gain,
                average_loss,
            )
        )

    return result


def latest_rsi(
    closes: Sequence[float],
    period: int = 14,
) -> Optional[float]:
    result = rsi(
        closes,
        period,
    )

    if not result:
        return None

    return result[-1]


# ============================================================
# ATR
# ============================================================


def true_ranges(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> List[float]:
    if not (
        len(highs)
        == len(lows)
        == len(closes)
    ):
        raise TechnicalIndicatorError(
            "OHLC arrays must have equal length."
        )

    if not highs:
        return []

    numeric_highs = [
        _number(value, "high")
        for value in highs
    ]

    numeric_lows = [
        _number(value, "low")
        for value in lows
    ]

    numeric_closes = [
        _number(value, "close")
        for value in closes
    ]

    ranges: List[float] = []

    first_range = (
        numeric_highs[0]
        - numeric_lows[0]
    )

    ranges.append(first_range)

    for index in range(
        1,
        len(numeric_highs),
    ):
        high = numeric_highs[index]
        low = numeric_lows[index]
        previous_close = numeric_closes[
            index - 1
        ]

        ranges.append(
            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )

    return ranges


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> List[float]:
    """
    Calculate Wilder ATR.
    """

    if period <= 0:
        raise TechnicalIndicatorError(
            "ATR period must be greater than zero."
        )

    ranges = true_ranges(
        highs,
        lows,
        closes,
    )

    if len(ranges) < period:
        return []

    average = (
        sum(ranges[:period])
        / period
    )

    result = [average]

    for value in ranges[period:]:
        average = (
            (
                average
                * (period - 1)
            )
            + value
        ) / period

        result.append(average)

    return result


def latest_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Optional[float]:
    result = atr(
        highs,
        lows,
        closes,
        period,
    )

    if not result:
        return None

    return result[-1]


# ============================================================
# MACD
# ============================================================


def macd(
    closes: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> Dict[str, Optional[float]]:
    """
    Calculate MACD.

    MACD line:
        EMA(12) - EMA(26)

    Signal:
        EMA(9) of the MACD line

    Histogram:
        MACD - signal
    """

    if (
        fast_period <= 0
        or slow_period <= 0
        or signal_period <= 0
    ):
        raise TechnicalIndicatorError(
            "MACD periods must be greater than zero."
        )

    if fast_period >= slow_period:
        raise TechnicalIndicatorError(
            "MACD fast period must be "
            "smaller than slow period."
        )

    numeric = [
        _number(value, "MACD close")
        for value in closes
    ]

    slow_values = ema(
        numeric,
        slow_period,
    )

    fast_values = ema(
        numeric,
        fast_period,
    )

    if not slow_values or not fast_values:
        return {
            "macd": None,
            "signal": None,
            "histogram": None,
        }

    # Align both EMA series to the slow EMA.
    offset = (
        slow_period
        - fast_period
    )

    if offset < 0:
        raise TechnicalIndicatorError(
            "Invalid MACD EMA alignment."
        )

    if len(fast_values) <= offset:
        return {
            "macd": None,
            "signal": None,
            "histogram": None,
        }

    fast_aligned = fast_values[
        offset:
    ]

    length = min(
        len(fast_aligned),
        len(slow_values),
    )

    macd_values = [
        fast_aligned[index]
        - slow_values[index]
        for index in range(length)
    ]

    if not macd_values:
        return {
            "macd": None,
            "signal": None,
            "histogram": None,
        }

    signal_values = ema(
        macd_values,
        signal_period,
    )

    if not signal_values:
        return {
            "macd": macd_values[-1],
            "signal": None,
            "histogram": None,
        }

    signal_value = signal_values[-1]

    macd_value = macd_values[-1]

    return {
        "macd": macd_value,
        "signal": signal_value,
        "histogram": (
            macd_value - signal_value
        ),
    }


# ============================================================
# TREND / SCORE
# ============================================================


def _clamp_score(
    value: int,
) -> int:
    return max(
        0,
        min(100, value),
    )


def determine_trend(
    *,
    close: float,
    ema20_value: Optional[float],
    ema50_value: Optional[float],
    rsi_value: Optional[float],
    macd_value: Optional[float],
    macd_signal_value: Optional[float],
) -> tuple[str, int, str]:
    """
    Produce a conservative technical assessment.

    The score is NOT a probability.

    It is a normalized technical-strength score
    intended for dashboard display and decision support.

    Signal is deliberately conservative:
    - BUY
    - SELL
    - WAIT
    """

    score = 50

    bullish_points = 0
    bearish_points = 0

    # --------------------------------------------------------
    # Price vs EMA20
    # --------------------------------------------------------

    if ema20_value is not None:
        if close > ema20_value:
            bullish_points += 1
            score += 8
        elif close < ema20_value:
            bearish_points += 1
            score -= 8

    # --------------------------------------------------------
    # EMA20 vs EMA50
    # --------------------------------------------------------

    if (
        ema20_value is not None
        and ema50_value is not None
    ):
        if ema20_value > ema50_value:
            bullish_points += 2
            score += 12
        elif ema20_value < ema50_value:
            bearish_points += 2
            score -= 12

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if rsi_value is not None:
        if 50.0 < rsi_value < 70.0:
            bullish_points += 1
            score += 8
        elif 30.0 < rsi_value < 50.0:
            bearish_points += 1
            score -= 8
        elif rsi_value >= 70.0:
            # Overbought is not automatically bearish,
            # therefore only a small penalty.
            score -= 3
        elif rsi_value <= 30.0:
            # Oversold is not automatically bullish,
            # therefore only a small positive adjustment.
            score += 3

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    if (
        macd_value is not None
        and macd_signal_value is not None
    ):
        if macd_value > macd_signal_value:
            bullish_points += 1
            score += 8
        elif macd_value < macd_signal_value:
            bearish_points += 1
            score -= 8

    score = _clamp_score(score)

    # --------------------------------------------------------
    # Direction
    # --------------------------------------------------------

    if (
        bullish_points >= 3
        and bullish_points > bearish_points
    ):
        trend = "BULLISH"
    elif (
        bearish_points >= 3
        and bearish_points > bullish_points
    ):
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    # --------------------------------------------------------
    # Conservative signal
    # --------------------------------------------------------

    if trend == "BULLISH" and score >= 65:
        signal = "BUY"
    elif trend == "BEARISH" and score <= 35:
        signal = "SELL"
    else:
        signal = "WAIT"

    return trend, score, signal


# ============================================================
# COMPLETE ANALYSIS
# ============================================================


def calculate_indicators(
    *,
    symbol: str,
    timeframe: str,
    candles: Sequence[Mapping[str, Any]],
) -> IndicatorResult:
    """
    Calculate all dashboard indicators.

    Requires enough candles for:
    - EMA50
    - RSI14
    - ATR14
    - MACD12/26/9
    """

    normalized_symbol = (
        str(symbol).strip()
    )

    normalized_timeframe = (
        str(timeframe).strip().upper()
    )

    if not normalized_symbol:
        raise TechnicalIndicatorError(
            "Symbol cannot be empty."
        )

    if not normalized_timeframe:
        raise TechnicalIndicatorError(
            "Timeframe cannot be empty."
        )

    _, highs, lows, closes = (
        _extract_ohlc(candles)
    )

    if len(closes) < 50:
        raise TechnicalIndicatorError(
            "At least 50 candles are required "
            "for the complete indicator set."
        )

    close_value = closes[-1]

    ema20_value = latest_ema(
        closes,
        20,
    )

    ema50_value = latest_ema(
        closes,
        50,
    )

    rsi_value = latest_rsi(
        closes,
        14,
    )

    atr_value = latest_atr(
        highs,
        lows,
        closes,
        14,
    )

    macd_values = macd(
        closes,
        12,
        26,
        9,
    )

    trend, score, signal = (
        determine_trend(
            close=close_value,
            ema20_value=ema20_value,
            ema50_value=ema50_value,
            rsi_value=rsi_value,
            macd_value=macd_values["macd"],
            macd_signal_value=(
                macd_values["signal"]
            ),
        )
    )

    return IndicatorResult(
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        close=close_value,
        ema20=ema20_value,
        ema50=ema50_value,
        rsi14=rsi_value,
        atr14=atr_value,
        macd=macd_values["macd"],
        macd_signal=macd_values["signal"],
        macd_histogram=(
            macd_values["histogram"]
        ),
        trend=trend,
        score=score,
        signal=signal,
        candles_used=len(closes),
    )


# ============================================================
# API SERIALIZATION
# ============================================================


def indicator_result_to_dict(
    result: IndicatorResult,
) -> Dict[str, Any]:
    """
    Convert IndicatorResult into a JSON-safe
    response structure.
    """

    return {
        "status": "ok",
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "close": result.close,
        "indicators": {
            "ema20": result.ema20,
            "ema50": result.ema50,
            "rsi14": result.rsi14,
            "atr14": result.atr14,
            "macd": result.macd,
            "macd_signal": result.macd_signal,
            "macd_histogram": result.macd_histogram,
        },
        "analysis": {
            "trend": result.trend,
            "score": result.score,
            "signal": result.signal,
        },
        "candles_used": result.candles_used,
        "read_only": True,
    }
