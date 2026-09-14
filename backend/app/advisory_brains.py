"""
RAYMOND v2.8 - Advisory AI Brain Ensemble

ADVISORY ONLY.

This module provides 8 independent analytical "brains" plus
a Master Consensus Brain.

IMPORTANT SAFETY RULES:
- Does NOT place trades.
- Does NOT modify positions.
- Does NOT close positions.
- Does NOT contact MT5.
- Does NOT contact a broker.
- Does NOT enable live trading.
- Does NOT replace Step 13.
- Does NOT bypass Step 14 Risk Engine.

The existing RAYMOND strategy remains the final trading decision.

The purpose of this module is to provide an independent analytical
comparison layer so the application can show WHY the market is being
classified as BUY, SELL, or WAIT.

Brains:
1. Trend Brain
2. Momentum Brain
3. Indicator Brain
4. Price Action Brain
5. Volatility Brain
6. Structure Brain
7. Entry / Setup Brain
8. Risk / Regime Brain

9. Master Consensus Brain
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

BUY = "BUY"
SELL = "SELL"
WAIT = "WAIT"

BULLISH = "Bullish"
BEARISH = "Bearish"
NEUTRAL = "Neutral"


# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrainVote:
    """
    Result produced by one advisory brain.
    """

    name: str
    direction: str
    confidence: float
    score: float
    summary: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "confidence": round(self.confidence, 2),
            "score": round(self.score, 2),
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class AdvisorySnapshot:
    """
    Complete advisory ensemble result.
    """

    brains: tuple[BrainVote, ...]

    master_direction: str
    master_confidence: float
    master_score: float

    buy_votes: int
    sell_votes: int
    wait_votes: int

    agreement_percent: float

    entry_quality: str
    warning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "brains": [
                brain.to_dict()
                for brain in self.brains
            ],
            "master": {
                "direction": self.master_direction,
                "confidence": round(
                    self.master_confidence,
                    2,
                ),
                "score": round(
                    self.master_score,
                    2,
                ),
                "buy_votes": self.buy_votes,
                "sell_votes": self.sell_votes,
                "wait_votes": self.wait_votes,
                "agreement_percent": round(
                    self.agreement_percent,
                    2,
                ),
                "entry_quality": self.entry_quality,
                "warning": self.warning,
            },
        }


# ---------------------------------------------------------------------------
# SAFE VALUE HELPERS
# ---------------------------------------------------------------------------


def _value(
    source: Any,
    name: str,
    default: Any = None,
) -> Any:
    """
    Safely read either an object attribute or dictionary key.
    """

    if source is None:
        return default

    if isinstance(source, Mapping):
        return source.get(name, default)

    return getattr(
        source,
        name,
        default,
    )


def _float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:
    """
    Safely convert a value to finite float.
    """

    if value is None:
        return default

    try:
        result = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default

    if not isfinite(result):
        return default

    return result


def _int(
    value: Any,
    default: int = 0,
) -> int:
    """
    Safely convert a value to int.
    """

    if value is None:
        return default

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def _text(
    value: Any,
    default: str = "",
) -> str:
    """
    Safely convert a value to text.
    """

    if value is None:
        return default

    return str(value).strip()


def _clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def _direction_from_score(
    score: float,
) -> str:
    if score >= 20:
        return BUY

    if score <= -20:
        return SELL

    return WAIT


def _confidence_from_score(
    score: float,
) -> float:
    """
    Converts a -100..100 score into a useful 50..95 confidence.
    """

    magnitude = abs(score)

    return _clamp(
        50.0 + magnitude * 0.45,
        50.0,
        95.0,
    )


# ---------------------------------------------------------------------------
# CANDLE HELPERS
# ---------------------------------------------------------------------------


def _candle_value(
    candle: Any,
    name: str,
) -> Optional[float]:
    """
    Read OHLC values from either dictionaries or objects.
    """

    return _float(
        _value(
            candle,
            name,
            None,
        )
    )


def _normalise_candles(
    candles: Optional[Sequence[Any]],
) -> list[Any]:
    if candles is None:
        return []

    try:
        return list(candles)
    except TypeError:
        return []


def _recent_closes(
    candles: Sequence[Any],
    count: int = 20,
) -> list[float]:
    values: list[float] = []

    for candle in list(candles)[-count:]:
        close = _candle_value(
            candle,
            "close",
        )

        if close is not None:
            values.append(close)

    return values


def _recent_ranges(
    candles: Sequence[Any],
    count: int = 20,
) -> list[float]:
    values: list[float] = []

    for candle in list(candles)[-count:]:
        high = _candle_value(
            candle,
            "high",
        )

        low = _candle_value(
            candle,
            "low",
        )

        if (
            high is not None
            and low is not None
            and high >= low
        ):
            values.append(
                high - low
            )

    return values


# ---------------------------------------------------------------------------
# BRAIN 1 - TREND
# ---------------------------------------------------------------------------


def trend_brain(
    context: Any,
) -> BrainVote:
    ema20 = _float(
        _value(
            context,
            "ema20",
        )
    )

    ema50 = _float(
        _value(
            context,
            "ema50",
        )
    )

    trend = _text(
        _value(
            context,
            "trend",
        )
    )

    if (
        ema20 is not None
        and ema50 is not None
    ):
        if ema20 > ema50:
            score = 75.0
            direction = BUY
            summary = (
                "EMA20 is above EMA50, "
                "indicating bullish trend alignment."
            )
            evidence = (
                "EMA20 > EMA50",
            )

        elif ema20 < ema50:
            score = -75.0
            direction = SELL
            summary = (
                "EMA20 is below EMA50, "
                "indicating bearish trend alignment."
            )
            evidence = (
                "EMA20 < EMA50",
            )

        else:
            score = 0.0
            direction = WAIT
            summary = (
                "EMA20 and EMA50 are aligned, "
                "so trend direction is unclear."
            )
            evidence = (
                "EMA20 ~= EMA50",
            )

    else:
        if trend == BULLISH:
            score = 65.0
            direction = BUY
            summary = (
                "Existing technical trend is bullish."
            )
            evidence = (
                "Trend = Bullish",
            )

        elif trend == BEARISH:
            score = -65.0
            direction = SELL
            summary = (
                "Existing technical trend is bearish."
            )
            evidence = (
                "Trend = Bearish",
            )

        else:
            score = 0.0
            direction = WAIT
            summary = (
                "Trend data is neutral or incomplete."
            )
            evidence = (
                "Trend = Neutral",
            )

    return BrainVote(
        name="Trend Brain",
        direction=direction,
        confidence=_confidence_from_score(
            score
        ),
        score=score,
        summary=summary,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# BRAIN 2 - MOMENTUM
# ---------------------------------------------------------------------------


def momentum_brain(
    context: Any,
) -> BrainVote:
    rsi = _float(
        _value(
            context,
            "rsi14",
        )
    )

    histogram = _float(
        _value(
            context,
            "macd_histogram",
        )
    )

    macd = _float(
        _value(
            context,
            "macd",
        )
    )

    signal = _float(
        _value(
            context,
            "macd_signal",
        )
    )

    score = 0.0
    evidence: list[str] = []

    if rsi is not None:
        if rsi >= 70:
            score -= 15.0
            evidence.append(
                "RSI is overbought"
            )

        elif rsi <= 30:
            score += 15.0
            evidence.append(
                "RSI is oversold"
            )

        elif rsi > 55:
            score += 30.0
            evidence.append(
                "RSI supports bullish momentum"
            )

        elif rsi < 45:
            score -= 30.0
            evidence.append(
                "RSI supports bearish momentum"
            )

    if histogram is not None:
        if histogram > 0:
            score += 35.0
            evidence.append(
                "MACD histogram positive"
            )

        elif histogram < 0:
            score -= 35.0
            evidence.append(
                "MACD histogram negative"
            )

    elif (
        macd is not None
        and signal is not None
    ):
        if macd > signal:
            score += 30.0
            evidence.append(
                "MACD above signal"
            )

        elif macd < signal:
            score -= 30.0
            evidence.append(
                "MACD below signal"
            )

    score = _clamp(
        score,
        -100.0,
        100.0,
    )

    direction = _direction_from_score(
        score
    )

    if direction == BUY:
        summary = (
            "Momentum currently favours buyers."
        )

    elif direction == SELL:
        summary = (
            "Momentum currently favours sellers."
        )

    else:
        summary = (
            "Momentum is mixed and does not "
            "provide a strong directional edge."
        )

    return BrainVote(
        name="Momentum Brain",
        direction=direction,
        confidence=_confidence_from_score(
            score
        ),
        score=score,
        summary=summary,
        evidence=tuple(evidence)
        if evidence
        else (
            "Insufficient momentum evidence",
        ),
    )


# ---------------------------------------------------------------------------
# BRAIN 3 - INDICATOR
# ---------------------------------------------------------------------------


def indicator_brain(
    context: Any,
) -> BrainVote:
    score = _float(
        _value(
            context,
            "score",
            50,
        ),
        50.0,
    )

    signal = _text(
        _value(
            context,
            "signal",
        )
    ).upper()

    trend = _text(
        _value(
            context,
            "trend",
        )
    )

    indicator_score = (
        (score - 50.0) * 1.5
    )

    if signal == BUY:
        indicator_score += 20.0

    elif signal == SELL:
        indicator_score -= 20.0

    if trend == BULLISH:
        indicator_score += 15.0

    elif trend == BEARISH:
        indicator_score -= 15.0

    indicator_score = _clamp(
        indicator_score,
        -100.0,
        100.0,
    )

    direction = _direction_from_score(
        indicator_score
    )

    if direction == BUY:
        summary = (
            "The existing technical indicator "
            "stack favours BUY."
        )

    elif direction == SELL:
        summary = (
            "The existing technical indicator "
            "stack favours SELL."
        )

    else:
        summary = (
            "The technical indicator stack "
            "does not show a strong edge."
        )

    return BrainVote(
        name="Indicator Brain",
        direction=direction,
        confidence=_confidence_from_score(
            indicator_score
        ),
        score=indicator_score,
        summary=summary,
        evidence=(
            f"Technical score={score:.1f}",
            f"Signal={signal or 'unknown'}",
            f"Trend={trend or 'unknown'}",
        ),
    )


# ---------------------------------------------------------------------------
# BRAIN 4 - PRICE ACTION
# ---------------------------------------------------------------------------


def price_action_brain(
    context: Any,
    candles: Sequence[Any],
) -> BrainVote:
    if len(candles) < 3:
        return BrainVote(
            name="Price Action Brain",
            direction=WAIT,
            confidence=50.0,
            score=0.0,
            summary=(
                "Not enough candle data for "
                "reliable price-action analysis."
            ),
            evidence=(
                "Fewer than 3 candles available",
            ),
        )

    recent = list(candles)[-5:]

    bullish = 0
    bearish = 0

    for candle in recent:
        open_price = _candle_value(
            candle,
            "open",
        )

        close = _candle_value(
            candle,
            "close",
        )

        if (
            open_price is None
            or close is None
        ):
            continue

        if close > open_price:
            bullish += 1

        elif close < open_price:
            bearish += 1

    score = (
        bullish - bearish
    ) * 20.0

    closes = _recent_closes(
        candles,
        20,
    )

    if len(closes) >= 2:
        if closes[-1] > closes[0]:
            score += 20.0

        elif closes[-1] < closes[0]:
            score -= 20.0

    score = _clamp(
        score,
        -100.0,
        100.0,
    )

    direction = _direction_from_score(
        score
    )

    if direction == BUY:
        summary = (
            "Recent candle behaviour favours "
            "bullish price action."
        )

    elif direction == SELL:
        summary = (
            "Recent candle behaviour favours "
            "bearish price action."
        )

    else:
        summary = (
            "Recent price action is mixed."
        )

    return BrainVote(
        name="Price Action Brain",
        direction=direction,
        confidence=_confidence_from_score(
            score
        ),
        score=score,
        summary=summary,
        evidence=(
            f"Recent bullish candles={bullish}",
            f"Recent bearish candles={bearish}",
        ),
    )


# ---------------------------------------------------------------------------
# BRAIN 5 - VOLATILITY
# ---------------------------------------------------------------------------


def volatility_brain(
    context: Any,
    candles: Sequence[Any],
) -> BrainVote:
    atr = _float(
        _value(
            context,
            "atr14",
        )
    )

    ranges = _recent_ranges(
        candles,
        20,
    )

    average_range = (
        sum(ranges) / len(ranges)
        if ranges
        else None
    )

    if (
        atr is None
        or atr <= 0
    ):
        return BrainVote(
            name="Volatility Brain",
            direction=WAIT,
            confidence=50.0,
            score=0.0,
            summary=(
                "Volatility data is incomplete."
            ),
            evidence=(
                "ATR unavailable",
            ),
        )

    score = 0.0
    evidence: list[str] = []

    if (
        average_range is not None
        and average_range > 0
    ):
        ratio = atr / average_range

        if ratio > 1.50:
            evidence.append(
                "Volatility is elevated"
            )
            score -= 15.0

        elif ratio < 0.70:
            evidence.append(
                "Volatility is compressed"
            )
            score -= 5.0

        else:
            evidence.append(
                "Volatility is within normal range"
            )

    if atr > 0:
        evidence.append(
            f"ATR={atr:.5f}"
        )

    # Volatility Brain is deliberately conservative.
    # It confirms direction only when volatility
    # does not look dangerously abnormal.
    trend = _text(
        _value(
            context,
            "trend",
        )
    )

    if trend == BULLISH:
        score += 25.0

    elif trend == BEARISH:
        score -= 25.0

    score = _clamp(
        score,
        -100.0,
        100.0,
    )

    direction = _direction_from_score(
        score
    )

    if direction == BUY:
        summary = (
            "Volatility conditions are compatible "
            "with a bullish setup."
        )

    elif direction == SELL:
        summary = (
            "Volatility conditions are compatible "
            "with a bearish setup."
        )

    else:
        summary = (
            "Volatility requires caution before "
            "committing to direction."
        )

    return BrainVote(
        name="Volatility Brain",
        direction=direction,
        confidence=_confidence_from_score(
            score
        ),
        score=score,
        summary=summary,
        evidence=tuple(evidence),
    )


# ---------------------------------------------------------------------------
# BRAIN 6 - STRUCTURE
# ---------------------------------------------------------------------------


def structure_brain(
    context: Any,
    candles: Sequence[Any],
) -> BrainVote:
    if len(candles) < 6:
        trend = _text(
            _value(
                context,
                "trend",
            )
        )

        if trend == BULLISH:
            score = 45.0

        elif trend == BEARISH:
            score = -45.0

        else:
            score = 0.0

        direction = _direction_from_score(
            score
        )

        return BrainVote(
            name="Structure Brain",
            direction=direction,
            confidence=_confidence_from_score(
                score
            ),
            score=score,
            summary=(
                "Limited candle structure; "
                "using the existing trend as fallback."
            ),
            evidence=(
                "Insufficient swing data",
            ),
        )

    data = list(candles)

    recent = data[-6:]

    highs: list[float] = []
    lows: list[float] = []

    for candle in recent:
        high = _candle_value(
            candle,
            "high",
        )

        low = _candle_value(
            candle,
            "low",
        )

        if high is not None:
            highs.append(high)

        if low is not None:
            lows.append(low)

    if len(highs) < 3 or len(lows) < 3:
        return BrainVote(
            name="Structure Brain",
            direction=WAIT,
            confidence=50.0,
            score=0.0,
            summary=(
                "Unable to establish reliable "
                "market structure."
            ),
            evidence=(
                "Incomplete high/low sequence",
            ),
        )

    higher_highs = 0
    lower_highs = 0
    higher_lows = 0
    lower_lows = 0

    for index in range(1, len(highs)):
        if highs[index] > highs[index - 1]:
            higher_highs += 1

        elif highs[index] < highs[index - 1]:
            lower_highs += 1

    for index in range(1, len(lows)):
        if lows[index] > lows[index - 1]:
            higher_lows += 1

        elif lows[index] < lows[index - 1]:
            lower_lows += 1

    score = 0.0

    score += (
        higher_highs * 20.0
    )

    score -= (
        lower_highs * 20.0
    )

    score += (
        higher_lows * 20.0
    )

    score -= (
        lower_lows * 20.0
    )

    score = _clamp(
        score,
        -100.0,
        100.0,
    )

    direction = _direction_from_score(
        score
    )

    if direction == BUY:
        summary = (
            "Recent swing structure favours "
            "higher highs and/or higher lows."
        )

    elif direction == SELL:
        summary = (
            "Recent swing structure favours "
            "lower highs and/or lower lows."
        )

    else:
        summary = (
            "Recent swing structure is mixed."
        )

    return BrainVote(
        name="Structure Brain",
        direction=direction,
        confidence=_confidence_from_score(
            score
        ),
        score=score,
        summary=summary,
        evidence=(
            f"Higher highs={higher_highs}",
            f"Lower highs={lower_highs}",
            f"Higher lows={higher_lows}",
            f"Lower lows={lower_lows}",
        ),
    )


# ---------------------------------------------------------------------------
# BRAIN 7 - ENTRY / SETUP
# ---------------------------------------------------------------------------


def entry_setup_brain(
    context: Any,
    candles: Sequence[Any],
) -> BrainVote:
    trend = _text(
        _value(
            context,
            "trend",
        )
    )

    signal = _text(
        _value(
            context,
            "signal",
        )
    ).upper()

    rsi = _float(
        _value(
            context,
            "rsi14",
        )
    )

    score = 0.0
    evidence: list[str] = []

    if signal == BUY:
        score += 35.0
        evidence.append(
            "Existing signal is BUY"
        )

    elif signal == SELL:
        score -= 35.0
        evidence.append(
            "Existing signal is SELL"
        )

    if trend == BULLISH:
        score += 35.0
        evidence.append(
            "Trend is bullish"
        )

    elif trend == BEARISH:
        score -= 35.0
        evidence.append(
            "Trend is bearish"
        )

    # Entry brain becomes cautious when RSI is already extreme.
    if rsi is not None:
        if rsi >= 75:
            score -= 25.0
            evidence.append(
                "BUY entry may be extended"
            )

        elif rsi <= 25:
            score += 25.0
            evidence.append(
                "SELL entry may be extended"
            )

    closes = _recent_closes(
        candles,
        5,
    )

    if len(closes) >= 2:
        recent_change = (
            closes[-1] - closes[-2]
        )

        if recent_change > 0:
            score += 10.0

        elif recent_change < 0:
            score -= 10.0

    score = _clamp(
        score,
        -100.0,
        100.0,
    )

    direction = _direction_from_score(
        score
    )

    if direction == BUY:
        summary = (
            "The setup currently provides a "
            "bullish entry bias."
        )

    elif direction == SELL:
        summary = (
            "The setup currently provides a "
            "bearish entry bias."
        )

    else:
        summary = (
            "The setup needs more confirmation "
            "before entry."
        )

    return BrainVote(
        name="Entry / Setup Brain",
        direction=direction,
        confidence=_confidence_from_score(
            score
        ),
        score=score,
        summary=summary,
        evidence=tuple(evidence)
        if evidence
        else (
            "No strong entry confirmation",
        ),
    )


# ---------------------------------------------------------------------------
# BRAIN 8 - RISK / REGIME
# ---------------------------------------------------------------------------


def risk_regime_brain(
    context: Any,
) -> BrainVote:
    regime = _text(
        _value(
            context,
            "market_regime",
            _value(
                context,
                "regime",
                "",
            ),
        )
    ).lower()

    setup = _text(
        _value(
            context,
            "setup",
            "",
        )
    ).lower()

    trend = _text(
        _value(
            context,
            "trend",
        )
    )

    score = 0.0
    evidence: list[str] = []

    if "up" in regime or "bull" in regime:
        score += 45.0
        evidence.append(
            f"Regime={regime}"
        )

    elif (
        "down" in regime
        or "bear" in regime
    ):
        score -= 45.0
        evidence.append(
            f"Regime={regime}"
        )

    elif regime:
        evidence.append(
            f"Regime={regime}"
        )

    if "bull" in setup or "continuation_up" in setup:
        score += 25.0
        evidence.append(
            f"Setup={setup}"
        )

    elif (
        "bear" in setup
        or "continuation_down" in setup
    ):
        score -= 25.0
        evidence.append(
            f"Setup={setup}"
        )

    if trend == BULLISH:
        score += 20.0

    elif trend == BEARISH:
        score -= 20.0

    score = _clamp(
        score,
        -100.0,
        100.0,
    )

    direction = _direction_from_score(
        score
    )

    if direction == BUY:
        summary = (
            "Market regime and setup conditions "
            "support a bullish bias."
        )

    elif direction == SELL:
        summary = (
            "Market regime and setup conditions "
            "support a bearish bias."
        )

    else:
        summary = (
            "Regime information is insufficient "
            "for a strong directional bias."
        )

    return BrainVote(
        name="Risk / Regime Brain",
        direction=direction,
        confidence=_confidence_from_score(
            score
        ),
        score=score,
        summary=summary,
        evidence=tuple(evidence)
        if evidence
        else (
            "No explicit regime/setup data",
        ),
    )


# ---------------------------------------------------------------------------
# MASTER CONSENSUS
# ---------------------------------------------------------------------------


def master_consensus(
    brains: Sequence[BrainVote],
) -> tuple[
    str,
    float,
    float,
    int,
    int,
    int,
    float,
    str,
    str,
]:
    """
    Combine the 8 advisory brains.

    This does NOT change the existing RAYMOND strategy.

    The Master Brain only describes ensemble agreement.
    """

    if not brains:
        return (
            WAIT,
            50.0,
            0.0,
            0,
            0,
            0,
            0.0,
            "UNKNOWN",
            "No advisory brains available.",
        )

    buy_votes = sum(
        1
        for brain in brains
        if brain.direction == BUY
    )

    sell_votes = sum(
        1
        for brain in brains
        if brain.direction == SELL
    )

    wait_votes = sum(
        1
        for brain in brains
        if brain.direction == WAIT
    )

    total = len(brains)

    buy_score = sum(
        max(
            0.0,
            brain.score,
        )
        for brain in brains
    )

    sell_score = sum(
        max(
            0.0,
            -brain.score,
        )
        for brain in brains
    )

    if buy_score > sell_score:
        master_score = _clamp(
            buy_score / total,
            0.0,
            100.0,
        )

        direction = BUY

    elif sell_score > buy_score:
        master_score = _clamp(
            -(sell_score / total),
            -100.0,
            0.0,
        )

        direction = SELL

    else:
        master_score = 0.0
        direction = WAIT

    winning_votes = max(
        buy_votes,
        sell_votes,
    )

    agreement_percent = (
        winning_votes / total * 100.0
    )

    # Strong majority.
    if winning_votes >= 6:
        entry_quality = "STRONG"

    # Reasonable majority.
    elif winning_votes >= 5:
        entry_quality = "MODERATE"

    # Split decision.
    elif winning_votes >= 4:
        entry_quality = "WEAK"

    else:
        entry_quality = "CONFLICTED"

    if direction == BUY:
        master_confidence = (
            50.0
            + agreement_percent * 0.40
            + max(
                0.0,
                master_score,
            ) * 0.15
        )

    elif direction == SELL:
        master_confidence = (
            50.0
            + agreement_percent * 0.40
            + abs(master_score) * 0.15
        )

    else:
        master_confidence = 50.0

    master_confidence = _clamp(
        master_confidence,
        50.0,
        95.0,
    )

    if wait_votes >= 4:
        warning = (
            "Advisory brains are cautious. "
            "Wait for stronger confirmation."
        )

    elif entry_quality == "CONFLICTED":
        warning = (
            "The advisory ensemble is conflicted. "
            "Do not treat the Master Brain as a trade trigger."
        )

    elif entry_quality == "WEAK":
        warning = (
            "Direction exists, but agreement is weak. "
            "Entry quality is limited."
        )

    else:
        warning = (
            "Advisory consensus is aligned. "
            "Step 14 Risk Engine must still approve any trade."
        )

    return (
        direction,
        master_confidence,
        master_score,
        buy_votes,
        sell_votes,
        wait_votes,
        agreement_percent,
        entry_quality,
        warning,
    )


# ---------------------------------------------------------------------------
# MAIN ADVISORY ENGINE
# ---------------------------------------------------------------------------


class AdvisoryBrainEngine:
    """
    Advisory-only 8-brain analysis engine.

    The engine accepts the existing RAYMOND TechnicalContext or
    any compatible object/dictionary containing equivalent fields.
    """

    def analyze(
        self,
        context: Any,
        candles: Optional[Sequence[Any]] = None,
    ) -> AdvisorySnapshot:
        """
        Run all advisory brains.

        This method never executes a trade.
        """

        candle_data = _normalise_candles(
            candles
        )

        brains = (
            trend_brain(
                context
            ),
            momentum_brain(
                context
            ),
            indicator_brain(
                context
            ),
            price_action_brain(
                context,
                candle_data,
            ),
            volatility_brain(
                context,
                candle_data,
            ),
            structure_brain(
                context,
                candle_data,
            ),
            entry_setup_brain(
                context,
                candle_data,
            ),
            risk_regime_brain(
                context
            ),
        )

        (
            master_direction,
            master_confidence,
            master_score,
            buy_votes,
            sell_votes,
            wait_votes,
            agreement_percent,
            entry_quality,
            warning,
        ) = master_consensus(
            brains
        )

        return AdvisorySnapshot(
            brains=brains,
            master_direction=master_direction,
            master_confidence=master_confidence,
            master_score=master_score,
            buy_votes=buy_votes,
            sell_votes=sell_votes,
            wait_votes=wait_votes,
            agreement_percent=agreement_percent,
            entry_quality=entry_quality,
            warning=warning,
        )


# ---------------------------------------------------------------------------
# SIMPLE PUBLIC FUNCTION
# ---------------------------------------------------------------------------


def analyze_advisory_brains(
    context: Any,
    candles: Optional[Sequence[Any]] = None,
) -> dict[str, Any]:
    """
    Convenience function for future API integration.

    Example:

        result = analyze_advisory_brains(
            technical_context,
            candles,
        )

    Returns a JSON-friendly dictionary.
    """

    engine = AdvisoryBrainEngine()

    snapshot = engine.analyze(
        context,
        candles,
    )

    return snapshot.to_dict()


__all__ = [
    "AdvisoryBrainEngine",
    "AdvisorySnapshot",
    "BrainVote",
    "analyze_advisory_brains",
    "trend_brain",
    "momentum_brain",
    "indicator_brain",
    "price_action_brain",
    "volatility_brain",
    "structure_brain",
    "entry_setup_brain",
    "risk_regime_brain",
    "master_consensus",
]
