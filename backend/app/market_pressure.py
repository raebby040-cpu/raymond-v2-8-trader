"""
RAYMOND v2.8 - Market Pressure Engine
Estimates directional market pressure from OHLC + volume data.
IMPORTANT:
- This is NOT a global buyer/seller count.
- XAUUSD spot volume is fragmented across brokers.
- Volume is treated as activity/tick-volume information.
- Positive pressure = buy-side candle pressure.
- Negative pressure = sell-side candle pressure.
- The engine is read-only.
- It never places, modifies, or closes trades.
- It never enables live trading.
Designed to plug into Raymond's existing strategy as an
ADVISORY confluence layer. It does not replace EMA, RSI,
MACD, trend, technical score, Risk Engine, or execution
controls.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence
class MarketPressureError(ValueError):
    """Raised when market-pressure input is invalid."""
@dataclass(frozen=True)
class MarketPressureResult:
    """
    Result produced by the Market Pressure Engine.
    score:
        -100 = strongest observed sell pressure
           0 = neutral
        +100 = strongest observed buy pressure
    The score is NOT a probability and must not be interpreted
    as a guaranteed likelihood of price movement.
    """
    score: int
    label: str
    latest_volume: float
    average_volume: Optional[float]
    relative_volume: Optional[float]
    candle_pressure: float
    volume_spike: bool
    available: bool
    candles_used: int
    reason: str
# ============================================================
# CONSTANTS
# ============================================================
DEFAULT_LOOKBACK = 20
DEFAULT_SPIKE_MULTIPLIER = 1.5
MIN_PRESSURE_LABEL = 25
# ============================================================
# NUMERIC VALIDATION
# ============================================================
def _number(
    value: Any,
    field: str,
) -> float:
    """
    Convert a value to a finite float.
    """
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MarketPressureError(
            f"Invalid numeric value for {field}."
        ) from exc
    if number != number:
        raise MarketPressureError(
            f"{field} cannot be NaN."
        )
    if number in (
        float("inf"),
        float("-inf"),
    ):
        raise MarketPressureError(
            f"{field} must be finite."
        )
    return number
# ============================================================
# VOLUME
# ============================================================
def _extract_volume(
    candle: Mapping[str, Any],
    index: int,
) -> float:
    """
    Extract volume using the naming conventions used by
    Raymond's market-data layer.
    Supported:
    - volume
    - tickVolume
    - tick_volume
    Missing volume is treated as zero so that the pressure
    engine can safely report UNAVAILABLE rather than crashing
    the entire trading pipeline.
    """
    value = candle.get("volume")
    if value is None:
        value = candle.get("tickVolume")
    if value is None:
        value = candle.get("tick_volume")
    if value is None:
        return 0.0
    volume = _number(
        value,
        f"candle[{index}].volume",
    )
    if volume < 0:
        raise MarketPressureError(
            f"candle[{index}].volume cannot be negative."
        )
    return volume
# ============================================================
# OHLC
# ============================================================
def _extract_ohlc(
    candle: Mapping[str, Any],
    index: int,
) -> tuple[float, float, float]:
    """
    Extract and validate high, low and close.
    """
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
    except KeyError as exc:
        raise MarketPressureError(
            f"Missing candle field: {exc.args[0]}."
        ) from exc
    if high < low:
        raise MarketPressureError(
            f"candle[{index}] high is below low."
        )
    if not (
        low <= close <= high
    ):
        raise MarketPressureError(
            f"candle[{index}] close is outside "
            "the high/low range."
        )
    return high, low, close
# ============================================================
# CANDLE PRESSURE
# ============================================================
def _candle_pressure(
    candle: Mapping[str, Any],
    index: int,
) -> float:
    """
    Calculate directional pressure for one candle.
    Close Location Value:
        +1.0 = close at the high
         0.0 = close at the midpoint
        -1.0 = close at the low
    This measures where the candle finished inside its range.
    It does NOT claim to know the actual number of buyers or
    sellers.
    """
    high, low, close = _extract_ohlc(
        candle,
        index,
    )
    candle_range = high - low
    if candle_range <= 0:
        return 0.0
    pressure = (
        (
            (close - low)
            - (high - close)
        )
        / candle_range
    )
    return max(
        -1.0,
        min(
            1.0,
            pressure,
        ),
    )
# ============================================================
# LABEL
# ============================================================
def _pressure_label(
    score: int,
) -> str:
    """
    Convert the numerical pressure score into a conservative
    label.
    """
    if score >= MIN_PRESSURE_LABEL:
        return "BUY_PRESSURE"
    if score <= -MIN_PRESSURE_LABEL:
        return "SELL_PRESSURE"
    return "NEUTRAL"
# ============================================================
# MAIN ENGINE
# ============================================================
def calculate_market_pressure(
    candles: Sequence[Mapping[str, Any]],
    *,
    lookback: int = DEFAULT_LOOKBACK,
    spike_multiplier: float = DEFAULT_SPIKE_MULTIPLIER,
) -> MarketPressureResult:
    """
    Calculate current market pressure.
    Only the supplied candle history is used.
    The latest candle is treated as the current observation.
    No future candle is accessed.
    Parameters
    ----------
    candles:
        Chronological OHLC candle data.
    lookback:
        Number of latest candles used for the pressure window.
    spike_multiplier:
        Current volume / average volume required to classify
        the latest candle as a volume spike.
    Returns
    -------
    MarketPressureResult
    """
    if not candles:
        raise MarketPressureError(
            "At least one candle is required."
        )
    if lookback < 2:
        raise MarketPressureError(
            "lookback must be at least 2."
        )
    if spike_multiplier <= 0:
        raise MarketPressureError(
            "spike_multiplier must be greater than zero."
        )
    # --------------------------------------------------------
    # Use only the latest lookback candles.
    # --------------------------------------------------------
    recent = list(
        candles[-lookback:]
    )
    volumes = [
        _extract_volume(
            candle,
            index,
        )
        for index, candle in enumerate(recent)
    ]
    latest_volume = volumes[-1]
    # --------------------------------------------------------
    # Establish the recent baseline.
    #
    # The latest candle is excluded from the average so that
    # a volume spike does not artificially raise its own
    # comparison baseline.
    # --------------------------------------------------------
    historical_volumes = volumes[:-1]
    positive_historical_volumes = [
        volume
        for volume in historical_volumes
        if volume > 0
    ]
    # --------------------------------------------------------
    # No usable volume.
    # --------------------------------------------------------
    if (
        latest_volume <= 0
        and not positive_historical_volumes
    ):
        return MarketPressureResult(
            score=0,
            label="UNAVAILABLE",
            latest_volume=latest_volume,
            average_volume=None,
            relative_volume=None,
            candle_pressure=0.0,
            volume_spike=False,
            available=False,
            candles_used=len(recent),
            reason=(
                "Volume data is unavailable or zero "
                "throughout the pressure window."
            ),
        )
    # --------------------------------------------------------
    # Calculate average volume.
    # --------------------------------------------------------
    if positive_historical_volumes:
        average_volume = (
            sum(
                positive_historical_volumes
            )
            / len(
                positive_historical_volumes
            )
        )
    else:
        # With no historical positive volume, the latest
        # volume cannot be meaningfully classified as a spike.
        average_volume = (
            latest_volume
            if latest_volume > 0
            else None
        )
    # --------------------------------------------------------
    # Relative volume.
    # --------------------------------------------------------
    if (
        average_volume is not None
        and average_volume > 0
    ):
        relative_volume = (
            latest_volume
            / average_volume
        )
    else:
        relative_volume = None
    volume_spike = (
        relative_volume is not None
        and relative_volume >= spike_multiplier
    )
    # --------------------------------------------------------
    # Calculate volume-weighted directional pressure.
    #
    # Recent candles matter more when their volume is higher.
    #
    # The relative-volume weight is deliberately capped so a
    # single abnormal candle cannot completely dominate the
    # result.
    # --------------------------------------------------------
    weighted_pressure = 0.0
    total_weight = 0.0
    for index, candle in enumerate(recent):
        volume = volumes[index]
        if volume <= 0:
            continue
        candle_pressure = _candle_pressure(
            candle,
            index,
        )
        if (
            average_volume is not None
            and average_volume > 0
        ):
            relative = (
                volume
                / average_volume
            )
        else:
            relative = 1.0
        # Prevent extreme volume from completely dominating
        # the pressure calculation.
        weight = min(
            max(
                relative,
                0.25,
            ),
            3.0,
        )
        weighted_pressure += (
            candle_pressure
            * weight
        )
        total_weight += weight
    # --------------------------------------------------------
    # No usable pressure.
    # --------------------------------------------------------
    if total_weight <= 0:
        return MarketPressureResult(
            score=0,
            label="UNAVAILABLE",
            latest_volume=latest_volume,
            average_volume=average_volume,
            relative_volume=relative_volume,
            candle_pressure=0.0,
            volume_spike=volume_spike,
            available=False,
            candles_used=len(recent),
            reason=(
                "No positive-volume candles were "
                "available for pressure calculation."
            ),
        )
    # --------------------------------------------------------
    # Normalize pressure to -1 ... +1.
    # --------------------------------------------------------
    normalized_pressure = (
        weighted_pressure
        / total_weight
    )
    normalized_pressure = max(
        -1.0,
        min(
            1.0,
            normalized_pressure,
        ),
    )
    # --------------------------------------------------------
    # Convert to -100 ... +100.
    # --------------------------------------------------------
    score = int(
        round(
            normalized_pressure
            * 100.0
        )
    )
    score = max(
        -100,
        min(
            100,
            score,
        ),
    )
    label = _pressure_label(
        score
    )
    # --------------------------------------------------------
    # Human-readable reason.
    # --------------------------------------------------------
    if (
        relative_volume is not None
        and volume_spike
    ):
        reason = (
            f"{label}: pressure score "
            f"{score}/100 with latest volume "
            f"{relative_volume:.2f}x the recent average."
        )
    elif relative_volume is not None:
        reason = (
            f"{label}: pressure score "
            f"{score}/100; latest volume is "
            f"{relative_volume:.2f}x the recent average."
        )
    else:
        reason = (
            f"{label}: pressure score "
            f"{score}/100."
        )
    return MarketPressureResult(
        score=score,
        label=label,
        latest_volume=latest_volume,
        average_volume=average_volume,
        relative_volume=relative_volume,
        candle_pressure=normalized_pressure,
        volume_spike=volume_spike,
        available=True,
        candles_used=len(recent),
        reason=reason,
    )
# ============================================================
# CONVENIENCE ALIASES
# ============================================================
def analyze_market_pressure(
    candles: Sequence[Mapping[str, Any]],
    *,
    lookback: int = DEFAULT_LOOKBACK,
    spike_multiplier: float = DEFAULT_SPIKE_MULTIPLIER,
) -> MarketPressureResult:
    """
    Public alias for callers that prefer an 'analyze' name.
    """
    return calculate_market_pressure(
        candles,
        lookback=lookback,
        spike_multiplier=spike_multiplier,
    )
__all__ = [
    "MarketPressureError",
    "MarketPressureResult",
    "DEFAULT_LOOKBACK",
    "DEFAULT_SPIKE_MULTIPLIER",
    "calculate_market_pressure",
    "analyze_market_pressure",
]
