"""
RAYMOND v2.8 - Advisory Comparison Tests

These tests verify that the 8-brain advisory ensemble can be
compared with the official RAYMOND Step 13 decision safely.

Safety:
- No broker connection.
- No MT5 connection.
- No live trading.
- No order execution.
- Step 13 remains authoritative.
- Step 14 is not bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.advisory_brains import (
    AdvisorySnapshot,
    BrainVote,
)

from app.advisory_comparison import (
    AGREE,
    DISAGREE,
    RAYMOND_WAIT,
    WEAK_ENTRY,
    compare_decision_with_advisory,
)


@dataclass
class FakeDecision:
    direction: str


def make_advisory(
    direction: str,
    confidence: float = 80.0,
    agreement: float = 87.5,
    buy_votes: int = 0,
    sell_votes: int = 0,
    wait_votes: int = 0,
) -> AdvisorySnapshot:
    """
    Build a deterministic advisory snapshot without running
    any execution or broker code.
    """

    brains = tuple(
        BrainVote(
            name=f"Test Brain {index}",
            direction=direction,
            confidence=confidence,
            score=(
                70.0
                if direction == "BUY"
                else -70.0
            ),
            summary="Test advisory vote.",
        )
        for index in range(1, 9)
    )

    return AdvisorySnapshot(
        brains=brains,
        master_direction=direction,
        master_confidence=confidence,
        master_score=(
            70.0
            if direction == "BUY"
            else -70.0
        ),
        buy_votes=buy_votes,
        sell_votes=sell_votes,
        wait_votes=wait_votes,
        agreement_percent=agreement,
        entry_quality="STRONG",
        warning="",
    )


def test_buy_and_buy_produces_agree():
    decision = FakeDecision(direction="BUY")

    advisory = make_advisory(
        direction="BUY",
        confidence=80.0,
        agreement=87.5,
        buy_votes=7,
        sell_votes=1,
        wait_votes=0,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert result.raymond_direction == "BUY"
    assert result.advisory_direction == "BUY"
    assert result.comparison == AGREE
    assert result.entry_quality == "STRONG"


def test_sell_and_sell_produces_agree():
    decision = FakeDecision(direction="SELL")

    advisory = make_advisory(
        direction="SELL",
        confidence=82.0,
        agreement=87.5,
        buy_votes=1,
        sell_votes=7,
        wait_votes=0,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert result.raymond_direction == "SELL"
    assert result.advisory_direction == "SELL"
    assert result.comparison == AGREE
    assert result.entry_quality == "STRONG"


def test_buy_and_sell_produces_disagree():
    decision = FakeDecision(direction="BUY")

    advisory = make_advisory(
        direction="SELL",
        confidence=82.0,
        agreement=87.5,
        buy_votes=1,
        sell_votes=7,
        wait_votes=0,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert result.raymond_direction == "BUY"
    assert result.advisory_direction == "SELL"
    assert result.comparison == DISAGREE
    assert result.entry_quality == "CONFLICT"


def test_sell_and_buy_produces_disagree():
    decision = FakeDecision(direction="SELL")

    advisory = make_advisory(
        direction="BUY",
        confidence=82.0,
        agreement=87.5,
        buy_votes=7,
        sell_votes=1,
        wait_votes=0,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert result.raymond_direction == "SELL"
    assert result.advisory_direction == "BUY"
    assert result.comparison == DISAGREE
    assert result.entry_quality == "CONFLICT"


def test_directional_signal_with_advisory_wait_is_weak_entry():
    decision = FakeDecision(direction="BUY")

    advisory = make_advisory(
        direction="WAIT",
        confidence=50.0,
        agreement=50.0,
        buy_votes=3,
        sell_votes=3,
        wait_votes=2,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert result.raymond_direction == "BUY"
    assert result.advisory_direction == "WAIT"
    assert result.comparison == WEAK_ENTRY
    assert result.entry_quality == "WEAK"


def test_sell_signal_with_advisory_wait_is_weak_entry():
    decision = FakeDecision(direction="SELL")

    advisory = make_advisory(
        direction="WAIT",
        confidence=50.0,
        agreement=50.0,
        buy_votes=3,
        sell_votes=3,
        wait_votes=2,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert result.raymond_direction == "SELL"
    assert result.advisory_direction == "WAIT"
    assert result.comparison == WEAK_ENTRY
    assert result.entry_quality == "WEAK"


def test_raymond_wait_does_not_become_trade_confirmation():
    decision = FakeDecision(direction="WAIT")

    advisory = make_advisory(
        direction="BUY",
        confidence=90.0,
        agreement=100.0,
        buy_votes=8,
        sell_votes=0,
        wait_votes=0,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert result.raymond_direction == "WAIT"
    assert result.advisory_direction == "BUY"
    assert result.comparison == RAYMOND_WAIT
    assert result.entry_quality == "WAIT"


def test_same_direction_but_weak_consensus_is_weak_entry():
    decision = FakeDecision(direction="BUY")

    advisory = make_advisory(
        direction="BUY",
        confidence=55.0,
        agreement=62.5,
        buy_votes=5,
        sell_votes=2,
        wait_votes=1,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert result.raymond_direction == "BUY"
    assert result.advisory_direction == "BUY"
    assert result.comparison == WEAK_ENTRY
    assert result.entry_quality == "WEAK"


def test_comparison_serializes_safely():
    decision = FakeDecision(direction="SELL")

    advisory = make_advisory(
        direction="SELL",
        confidence=82.0,
        agreement=87.5,
        buy_votes=1,
        sell_votes=7,
        wait_votes=0,
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    data = result.to_dict()

    assert isinstance(data, dict)

    assert "raymond" in data
    assert "advisory" in data
    assert "comparison" in data
    assert "brains" in data

    assert data["raymond"]["direction"] == "SELL"
    assert data["advisory"]["direction"] == "SELL"
    assert data["comparison"]["status"] == AGREE

    assert len(data["brains"]) == 8


def test_comparison_contains_no_execution_fields():
    decision = FakeDecision(direction="BUY")

    advisory = make_advisory(
        direction="BUY",
    )

    result = compare_decision_with_advisory(
        decision,
        advisory,
    )

    data = result.to_dict()

    assert "order_id" not in data
    assert "trade_id" not in data
    assert "broker_order" not in data
    assert "execution" not in data
    assert "position_id" not in data


def test_comparison_does_not_modify_raymond_decision():
    decision = FakeDecision(direction="SELL")

    advisory = make_advisory(
        direction="SELL",
    )

    original_direction = decision.direction

    compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert decision.direction == original_direction
    assert decision.direction == "SELL"


def test_comparison_does_not_modify_advisory_snapshot():
    decision = FakeDecision(direction="BUY")

    advisory = make_advisory(
        direction="BUY",
    )

    original_direction = advisory.master_direction
    original_confidence = advisory.master_confidence
    original_agreement = advisory.agreement_percent

    compare_decision_with_advisory(
        decision,
        advisory,
    )

    assert advisory.master_direction == original_direction
    assert advisory.master_confidence == original_confidence
    assert advisory.agreement_percent == original_agreement
