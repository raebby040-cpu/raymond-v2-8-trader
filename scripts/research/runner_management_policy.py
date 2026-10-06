"""
RAYMOND v2.8 - Research-only Runner Management Policy

PURPOSE
-------
Research-only management policy for testing a protected runner model.

IMPORTANT
---------
This module:
- does NOT place broker orders
- does NOT modify production positions
- does NOT modify the live strategy
- does NOT contact MT5/Exness
- does NOT promote itself into production

DESIGN
------
1. Original risk_1r remains immutable for the entire trade.
2. Minimum RR is treated as a protection/runner milestone.
3. A trade can continue beyond the minimum RR.
4. Partial close is a separate accounting event.
5. Trailing uses the original 1R.
6. Trailing can continue as price extends.
7. A trailing stop can eventually close the runner on reversal.
"""

from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class RunnerConfig:
    """
    Research configuration.

    minimum_rr:
        Minimum intended RR the strategy wants to achieve.

    protection_rr:
        RR at which the trade receives profit protection.

    trail_start_rr:
        RR at which the runner begins active trailing.

    trailing_distance_r:
        Distance between current price and trailing stop,
        expressed in ORIGINAL R units.

    partial_close_rr:
        RR at which a partial close may occur.

    partial_close_fraction:
        Fraction of the remaining position to close.

    runner_mode:
        If True, the remaining position may continue beyond
        minimum_rr instead of automatically closing at that level.
    """

    minimum_rr: float = 2.5
    protection_rr: float = 1.0
    trail_start_rr: float = 2.5
    trailing_distance_r: float = 1.0

    partial_close_rr: float = 2.0
    partial_close_fraction: float = 0.50

    runner_mode: bool = True

    def validate(self) -> None:
        if self.minimum_rr <= 0:
            raise ValueError(
                "minimum_rr must be greater than zero."
            )

        if self.protection_rr <= 0:
            raise ValueError(
                "protection_rr must be greater than zero."
            )

        if self.trail_start_rr < self.protection_rr:
            raise ValueError(
                "trail_start_rr must be greater than or equal "
                "to protection_rr."
            )

        if self.trailing_distance_r <= 0:
            raise ValueError(
                "trailing_distance_r must be greater than zero."
            )

        if not 0 < self.partial_close_fraction < 1:
            raise ValueError(
                "partial_close_fraction must be between 0 and 1."
            )


@dataclass(frozen=True)
class RunnerPosition:
    """
    Read-only representation of a paper position.

    original_risk_1r MUST remain the original price-distance
    calculated when the position was opened.
    """

    direction: Direction

    entry: float

    original_risk_1r: float

    current_price: float

    current_stop: float

    remaining_quantity: float

    partial_close_applied: bool = False

    trailing_active: bool = False

    def validate(self) -> None:
        if self.entry <= 0:
            raise ValueError(
                "entry must be greater than zero."
            )

        if self.current_price <= 0:
            raise ValueError(
                "current_price must be greater than zero."
            )

        if self.original_risk_1r <= 0:
            raise ValueError(
                "original_risk_1r must be greater than zero."
            )

        if self.remaining_quantity <= 0:
            raise ValueError(
                "remaining_quantity must be greater than zero."
            )


@dataclass(frozen=True)
class RunnerDecision:
    """
    Research management decision.

    No broker execution happens here.
    """

    action: str

    current_r: float

    new_stop: object

    partial_close_quantity: float

    target_reached: bool

    reason: str


def current_r(position: RunnerPosition) -> float:
    """
    Calculate R using ORIGINAL risk_1r.

    IMPORTANT:
    The current stop is deliberately NOT used here.

    This prevents BE/trailing from changing the meaning of 1R.
    """

    position.validate()

    if position.direction == Direction.BUY:
        return (
            position.current_price - position.entry
        ) / position.original_risk_1r

    return (
        position.entry - position.current_price
    ) / position.original_risk_1r


def improved_stop(
    position: RunnerPosition,
    candidate: float,
) -> bool:
    """
    Confirm that a proposed trailing stop improves protection.

    BUY:
        candidate must be ABOVE existing stop
        and BELOW current price.

    SELL:
        candidate must be BELOW existing stop
        and ABOVE current price.
    """

    if position.direction == Direction.BUY:

        return (
            candidate > position.current_stop
            and candidate < position.current_price
        )

    return (
        candidate < position.current_stop
        and candidate > position.current_price
    )


def evaluate_runner(
    position: RunnerPosition,
    config: RunnerConfig = RunnerConfig(),
) -> RunnerDecision:
    """
    Evaluate research-only runner management.

    Priority:

    1. No action while losing.
    2. Partial close when configured threshold is reached.
    3. Protect profit at protection_rr.
    4. Trail after trail_start_rr.
    5. Otherwise hold.

    The minimum RR is NOT automatically treated as a final
    full-position exit when runner_mode=True.
    """

    config.validate()
    position.validate()

    r = current_r(position)

    target_reached = (
        r >= config.minimum_rr
    )

    # ---------------------------------------------------------
    # LOSING / NON-PROFITABLE POSITION
    # ---------------------------------------------------------

    if r <= 0:

        return RunnerDecision(
            action="HOLD",
            current_r=r,
            new_stop=None,
            partial_close_quantity=0.0,
            target_reached=False,
            reason=(
                "Position is not currently profitable."
            ),
        )

    # ---------------------------------------------------------
    # PARTIAL CLOSE
    # ---------------------------------------------------------

    if (
        not position.partial_close_applied
        and r >= config.partial_close_rr
    ):

        quantity = round(
            position.remaining_quantity
            * config.partial_close_fraction,
            8,
        )

        if (
            quantity > 0
            and quantity < position.remaining_quantity
        ):

            return RunnerDecision(
                action="PARTIAL_CLOSE",
                current_r=r,
                new_stop=None,
                partial_close_quantity=quantity,
                target_reached=target_reached,
                reason=(
                    "Partial-close threshold reached. "
                    "Partial P/L must be recorded separately "
                    "from final runner P/L."
                ),
            )

    # ---------------------------------------------------------
    # PROFIT PROTECTION
    # ---------------------------------------------------------

    if r >= config.protection_rr:

        protection_stop = position.entry

        if position.direction == Direction.BUY:

            valid = (
                protection_stop > position.current_stop
                and protection_stop < position.current_price
            )

        else:

            valid = (
                protection_stop < position.current_stop
                and protection_stop > position.current_price
            )

        if valid:

            return RunnerDecision(
                action="MOVE_TO_PROTECTION",
                current_r=r,
                new_stop=protection_stop,
                partial_close_quantity=0.0,
                target_reached=target_reached,
                reason=(
                    "Minimum profit protection threshold "
                    "has been reached."
                ),
            )

    # ---------------------------------------------------------
    # RUNNER TRAILING
    # ---------------------------------------------------------

    if (
        config.runner_mode
        and r >= config.trail_start_rr
    ):

        trailing_distance = (
            config.trailing_distance_r
            * position.original_risk_1r
        )

        if position.direction == Direction.BUY:

            candidate_stop = (
                position.current_price
                - trailing_distance
            )

        else:

            candidate_stop = (
                position.current_price
                + trailing_distance
            )

        if improved_stop(
            position,
            candidate_stop,
        ):

            return RunnerDecision(
                action="TRAIL",
                current_r=r,
                new_stop=candidate_stop,
                partial_close_quantity=0.0,
                target_reached=target_reached,
                reason=(
                    "Minimum RR has been reached. "
                    "The remaining position is being "
                    "trailed as a runner."
                ),
            )

    # ---------------------------------------------------------
    # HOLD
    # ---------------------------------------------------------

    return RunnerDecision(
        action="HOLD",
        current_r=r,
        new_stop=None,
        partial_close_quantity=0.0,
        target_reached=target_reached,
        reason=(
            "No stronger research management action "
            "is currently required."
        ),
                )
