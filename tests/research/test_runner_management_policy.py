from scripts.research.runner_management_policy import (
    Direction,
    RunnerPosition,
    current_r,
    evaluate_runner,
)


def test_original_r_is_immutable():
    """
    Moving the stop must never redefine the original 1R.
    """

    position_a = RunnerPosition(
        direction=Direction.BUY,
        entry=4000.0,
        original_risk_1r=10.0,
        current_price=4025.0,
        current_stop=4000.0,
        remaining_quantity=0.14,
    )

    position_b = RunnerPosition(
        direction=Direction.BUY,
        entry=4000.0,
        original_risk_1r=10.0,
        current_price=4025.0,
        current_stop=4020.0,
        remaining_quantity=0.14,
    )

    assert current_r(position_a) == 2.5
    assert current_r(position_b) == 2.5


def test_minimum_rr_is_runner_milestone():
    """
    Reaching minimum RR must not automatically mean
    full-position closure.
    """

    position = RunnerPosition(
        direction=Direction.BUY,
        entry=4000.0,
        original_risk_1r=10.0,
        current_price=4025.0,
        current_stop=4000.0,
        remaining_quantity=0.14,
    )

    decision = evaluate_runner(position)

    assert decision.target_reached is True

    assert decision.action in {
        "PARTIAL_CLOSE",
        "MOVE_TO_PROTECTION",
        "TRAIL",
    }


def test_runner_continues_beyond_minimum_rr():
    """
    A trade at 6R should still be able to trail.
    """

    position = RunnerPosition(
        direction=Direction.BUY,
        entry=4000.0,
        original_risk_1r=10.0,
        current_price=4060.0,
        current_stop=4025.0,
        remaining_quantity=0.07,
        partial_close_applied=True,
        trailing_active=True,
    )

    decision = evaluate_runner(position)

    assert decision.current_r == 6.0

    assert decision.action == "TRAIL"

    assert decision.new_stop is not None

    assert decision.new_stop > 4025.0


def test_sell_runner_trails_down():
    """
    SELL runners must trail downward as price falls.
    """

    position = RunnerPosition(
        direction=Direction.SELL,
        entry=4000.0,
        original_risk_1r=10.0,
        current_price=3970.0,
        current_stop=3990.0,
        remaining_quantity=0.07,
        partial_close_applied=True,
        trailing_active=True,
    )

    decision = evaluate_runner(position)

    assert decision.action == "TRAIL"

    assert decision.new_stop < 3990.0


def test_partial_close_is_separate_event():
    """
    Partial close must be represented as a distinct
    accounting event.
    """

    position = RunnerPosition(
        direction=Direction.BUY,
        entry=4000.0,
        original_risk_1r=10.0,
        current_price=4020.0,
        current_stop=4000.0,
        remaining_quantity=0.14,
    )

    decision = evaluate_runner(position)

    assert decision.action == "PARTIAL_CLOSE"

    assert decision.partial_close_quantity == 0.07
