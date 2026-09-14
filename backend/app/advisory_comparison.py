"""
RAYMOND v2.8 - Advisory Comparison Layer

PURPOSE
-------
Compare the existing RAYMOND Step 13 decision against the
independent 8-brain advisory ensemble.

IMPORTANT SAFETY RULES
----------------------
- Advisory only.
- Does NOT place trades.
- Does NOT modify positions.
- Does NOT contact MT5.
- Does NOT contact a broker.
- Does NOT bypass Step 14 Risk Engine.
- Does NOT replace Step 13.
- Does NOT change execution behaviour.

The existing RAYMOND Step 13 decision remains the official
strategy decision.

This module only answers:

    Do the independent advisory brains agree with RAYMOND?

Possible comparison statuses:

    AGREE
    DISAGREE
    WEAK_ENTRY
    RAYMOND_WAIT

The comparison can therefore be displayed by the application
without changing trading behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from app.advisory_brains import (
    AdvisoryBrainEngine,
    AdvisorySnapshot,
)


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

BUY = "BUY"
SELL = "SELL"
WAIT = "WAIT"

AGREE = "AGREE"
DISAGREE = "DISAGREE"
WEAK_ENTRY = "WEAK_ENTRY"
RAYMOND_WAIT = "RAYMOND_WAIT"


# ---------------------------------------------------------------------------
# DATA MODEL
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdvisoryComparison:
    """
    Comparison between the official RAYMOND decision and
    the independent advisory ensemble.
    """

    raymond_direction: str

    advisory_direction: str
    advisory_confidence: float
    advisory_score: float

    buy_votes: int
    sell_votes: int
    wait_votes: int

    agreement_percent: float

    comparison: str
    entry_quality: str

    summary: str
    warning: str

    advisory: AdvisorySnapshot

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the comparison into an API-safe dictionary.
        """

        return {
            "raymond": {
                "direction": self.raymond_direction,
            },
            "advisory": {
                "direction": self.advisory_direction,
                "confidence": round(
                    self.advisory_confidence,
                    2,
                ),
                "score": round(
                    self.advisory_score,
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
            },
            "comparison": {
                "status": self.comparison,
                "summary": self.summary,
                "warning": self.warning,
            },
            "brains": [
                brain.to_dict()
                for brain in self.advisory.brains
            ],
        }


# ---------------------------------------------------------------------------
# SAFE HELPERS
# ---------------------------------------------------------------------------


def _direction_value(
    value: Any,
    default: str = WAIT,
) -> str:
    """
    Convert enums/strings into BUY, SELL or WAIT.
    """

    if value is None:
        return default

    candidate = getattr(
        value,
        "value",
        value,
    )

    text = str(candidate).strip().upper()

    if text in {
        BUY,
        SELL,
        WAIT,
    }:
        return text

    return default


def _float_value(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Safely convert a value to float.
    """

    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def _int_value(
    value: Any,
    default: int = 0,
) -> int:
    """
    Safely convert a value to int.
    """

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def _value(
    source: Any,
    name: str,
    default: Any = None,
) -> Any:
    """
    Safely read a dictionary key or object attribute.
    """

    if source is None:
        return default

    if isinstance(source, Mapping):
        return source.get(
            name,
            default,
        )

    return getattr(
        source,
        name,
        default,
    )


# ---------------------------------------------------------------------------
# COMPARISON LOGIC
# ---------------------------------------------------------------------------


def _determine_comparison(
    raymond_direction: str,
    advisory_direction: str,
    agreement_percent: float,
    advisory_confidence: float,
) -> tuple[str, str, str]:
    """
    Determine comparison status, entry quality and summary.

    Conservative rules:

    1. RAYMOND WAIT
       -> RAYMOND_WAIT

    2. RAYMOND BUY/SELL and advisory opposite
       -> DISAGREE

    3. RAYMOND BUY/SELL and advisory WAIT
       -> WEAK_ENTRY

    4. Same direction with strong agreement
       -> AGREE

    5. Same direction but weak agreement/confidence
       -> WEAK_ENTRY
    """

    raymond_direction = _direction_value(
        raymond_direction
    )

    advisory_direction = _direction_value(
        advisory_direction
    )

    if raymond_direction == WAIT:
        return (
            RAYMOND_WAIT,
            "WAIT",
            (
                "RAYMOND Step 13 is currently WAIT, "
                "so no directional agreement is treated "
                "as a trade confirmation."
            ),
        )

    if (
        advisory_direction in {
            BUY,
            SELL,
        }
        and advisory_direction != raymond_direction
    ):
        return (
            DISAGREE,
            "CONFLICT",
            (
                "The advisory ensemble disagrees with "
                "the official RAYMOND direction."
            ),
        )

    if advisory_direction == WAIT:
        return (
            WEAK_ENTRY,
            "WEAK",
            (
                "RAYMOND has a directional signal, but "
                "the independent advisory ensemble does "
                "not have enough directional agreement."
            ),
        )

    strong_agreement = (
        agreement_percent >= 75.0
        and advisory_confidence >= 60.0
    )

    if strong_agreement:
        return (
            AGREE,
            "STRONG",
            (
                "The advisory ensemble agrees with "
                "RAYMOND and has strong internal "
                "directional agreement."
            ),
        )

    return (
        WEAK_ENTRY,
        "WEAK",
        (
            "The advisory ensemble agrees with "
            "RAYMOND, but internal agreement or "
            "confidence is not strong enough for "
            "a high-quality entry classification."
        ),
    )


# ---------------------------------------------------------------------------
# PUBLIC COMPARISON FUNCTION
# ---------------------------------------------------------------------------


def compare_decision_with_advisory(
    decision: Any,
    advisory: AdvisorySnapshot,
) -> AdvisoryComparison:
    """
    Compare an existing RAYMOND Step 13 decision against
    an already-calculated advisory snapshot.

    This function does not modify either object.
    """

    raymond_direction = _direction_value(
        _value(
            decision,
            "direction",
            WAIT,
        )
    )

    advisory_direction = _direction_value(
        advisory.master_direction,
        WAIT,
    )

    advisory_confidence = _float_value(
        advisory.master_confidence
    )

    advisory_score = _float_value(
        advisory.master_score
    )

    agreement_percent = _float_value(
        advisory.agreement_percent
    )

    (
        comparison,
        entry_quality,
        summary,
    ) = _determine_comparison(
        raymond_direction,
        advisory_direction,
        agreement_percent,
        advisory_confidence,
    )

    warning = str(
        advisory.warning or ""
    ).strip()

    return AdvisoryComparison(
        raymond_direction=raymond_direction,
        advisory_direction=advisory_direction,
        advisory_confidence=advisory_confidence,
        advisory_score=advisory_score,
        buy_votes=_int_value(
            advisory.buy_votes
        ),
        sell_votes=_int_value(
            advisory.sell_votes
        ),
        wait_votes=_int_value(
            advisory.wait_votes
        ),
        agreement_percent=agreement_percent,
        comparison=comparison,
        entry_quality=entry_quality,
        summary=summary,
        warning=warning,
        advisory=advisory,
    )


# ---------------------------------------------------------------------------
# ONE-STEP CONVENIENCE FUNCTION
# ---------------------------------------------------------------------------


def analyze_and_compare(
    decision: Any,
    context: Any,
    candles: Optional[Sequence[Any]] = None,
) -> dict[str, Any]:
    """
    Run the complete advisory comparison.

    IMPORTANT:
    The advisory engine is kept as an AdvisorySnapshot object
    until the comparison has finished.

    The old implementation incorrectly used the serialized
    dictionary returned by analyze_advisory_brains(), which
    caused:

        AttributeError:
        'dict' object has no attribute 'master_direction'

    This implementation deliberately uses the object-level
    AdvisoryBrainEngine().analyze() method.

    Flow:

        existing RAYMOND decision
                    +
        market/technical context
                    +
        candles
                    |
                    v
        8 advisory brains
                    |
                    v
        Master Consensus
                    |
                    v
        Comparison
                    |
                    v
        API-safe dictionary

    This remains advisory-only.
    """

    advisory = AdvisoryBrainEngine().analyze(
        context,
        candles,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    return result.to_dict()


# ---------------------------------------------------------------------------
# OBJECT-LEVEL CONVENIENCE FUNCTION
# ---------------------------------------------------------------------------


def build_advisory_comparison(
    decision: Any,
    context: Any,
    candles: Optional[Sequence[Any]] = None,
) -> AdvisoryComparison:
    """
    Return the full AdvisoryComparison object.

    Useful for backend code that needs structured access
    rather than a serialized dictionary.
    """

    advisory = AdvisoryBrainEngine().analyze(
        context,
        candles,
    )

    return compare_decision_with_advisory(
        decision,
        advisory,
    )


# ---------------------------------------------------------------------------
# PUBLIC EXPORTS
# ---------------------------------------------------------------------------


__all__ = [
    "AGREE",
    "DISAGREE",
    "WEAK_ENTRY",
    "RAYMOND_WAIT",
    "AdvisoryComparison",
    "analyze_and_compare",
    "build_advisory_comparison",
    "compare_decision_with_advisory",
]
