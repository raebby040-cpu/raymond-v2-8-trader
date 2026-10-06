from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExitReason(str, Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    NO_EXIT = "NO_EXIT"


@dataclass(frozen=True)
class OHLC:
    timestamp: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class PositionCase:
    trade_id: str
    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float


@dataclass(frozen=True)
class IntrabarResult:
    trade_id: str
    timestamp: str
    reason: ExitReason
    trigger_price: float
    crossed_stop: bool
    crossed_take_profit: bool
    valid: bool
    error: str | None = None


@dataclass(frozen=True)
class ReplaySummary:
    total_positions: int
    valid_positions: int
    invalid_positions: int
    tp_exits: int
    sl_exits: int
    no_exit: int
    isolated_errors: tuple[str, ...]


def validate_position(position: PositionCase) -> None:
    """
    Validate the directional relationship between entry, SL and TP.

    BUY:
        SL < Entry < TP

    SELL:
        TP < Entry < SL
    """

    if not position.trade_id.strip():
        raise ValueError("trade_id is required")

    if (
        position.entry <= 0
        or position.stop_loss <= 0
        or position.take_profit <= 0
    ):
        raise ValueError("prices must be positive")

    if position.direction is Direction.BUY:
        if position.stop_loss >= position.entry:
            raise ValueError(
                "BUY stop_loss must be below entry"
            )

        if position.take_profit <= position.entry:
            raise ValueError(
                "BUY take_profit must be above entry"
            )

    elif position.direction is Direction.SELL:
        if position.stop_loss <= position.entry:
            raise ValueError(
                "SELL stop_loss must be above entry"
            )

        if position.take_profit >= position.entry:
            raise ValueError(
                "SELL take_profit must be below entry"
            )

    else:
        raise ValueError(
            f"unsupported direction: {position.direction}"
        )


def validate_candle(candle: OHLC) -> None:
    if candle.high < candle.low:
        raise ValueError(
            "candle high must be greater than or equal to low"
        )

    if (
        candle.open <= 0
        or candle.high <= 0
        or candle.low <= 0
        or candle.close <= 0
    ):
        raise ValueError("candle prices must be positive")


def candle_exit(
    position: PositionCase,
    candle: OHLC,
) -> IntrabarResult:
    """
    Determine whether an OHLC candle crossed the position SL or TP.

    Conservative same-candle rule:
        If both SL and TP were touched inside the same candle,
        STOP_LOSS wins.

    This avoids assuming a favorable intrabar sequence that
    cannot be proven from OHLC data alone.
    """

    try:
        validate_position(position)
        validate_candle(candle)

        if position.direction is Direction.BUY:
            hit_sl = candle.low <= position.stop_loss
            hit_tp = candle.high >= position.take_profit

        elif position.direction is Direction.SELL:
            hit_sl = candle.high >= position.stop_loss
            hit_tp = candle.low <= position.take_profit

        else:
            raise ValueError(
                f"unsupported direction: {position.direction}"
            )

        # Conservative priority:
        # if both were touched during the same candle,
        # assume the stop was hit first.
        if hit_sl:
            return IntrabarResult(
                trade_id=position.trade_id,
                timestamp=candle.timestamp,
                reason=ExitReason.STOP_LOSS,
                trigger_price=position.stop_loss,
                crossed_stop=True,
                crossed_take_profit=hit_tp,
                valid=True,
            )

        if hit_tp:
            return IntrabarResult(
                trade_id=position.trade_id,
                timestamp=candle.timestamp,
                reason=ExitReason.TAKE_PROFIT,
                trigger_price=position.take_profit,
                crossed_stop=False,
                crossed_take_profit=True,
                valid=True,
            )

        return IntrabarResult(
            trade_id=position.trade_id,
            timestamp=candle.timestamp,
            reason=ExitReason.NO_EXIT,
            trigger_price=candle.close,
            crossed_stop=False,
            crossed_take_profit=False,
            valid=True,
        )

    except Exception as exc:
        return IntrabarResult(
            trade_id=position.trade_id,
            timestamp=candle.timestamp,
            reason=ExitReason.NO_EXIT,
            trigger_price=candle.close,
            crossed_stop=False,
            crossed_take_profit=False,
            valid=False,
            error=str(exc),
        )


def replay_position(
    position: PositionCase,
    candles: Iterable[OHLC],
) -> IntrabarResult:
    """
    Replay one position against its chronological candle sequence.

    The first confirmed SL/TP event ends the position.
    """

    last_result: IntrabarResult | None = None

    for candle in candles:
        result = candle_exit(position, candle)

        if not result.valid:
            return result

        if result.reason is not ExitReason.NO_EXIT:
            return result

        last_result = result

    if last_result is not None:
        return last_result

    return IntrabarResult(
        trade_id=position.trade_id,
        timestamp="",
        reason=ExitReason.NO_EXIT,
        trigger_price=position.entry,
        crossed_stop=False,
        crossed_take_profit=False,
        valid=True,
    )


def replay_isolated(
    positions: Sequence[PositionCase],
    candles_by_trade: Mapping[str, Sequence[OHLC]],
) -> tuple[list[IntrabarResult], ReplaySummary]:
    """
    Replay every position independently.

    IMPORTANT:
    A malformed position must NOT terminate the entire replay.

    This directly tests the failure mode discovered in the
    production paper-position market loop where one invalid
    SELL position raised:

        SELL stop_loss must be above entry_price

    and caused the market-loop cycle to fail.
    """

    results: list[IntrabarResult] = []
    isolated_errors: list[str] = []

    for position in positions:
        candles = candles_by_trade.get(position.trade_id, ())

        result = replay_position(
            position=position,
            candles=candles,
        )

        results.append(result)

        if not result.valid:
            isolated_errors.append(
                f"{position.trade_id}: {result.error}"
            )

    summary = ReplaySummary(
        total_positions=len(results),
        valid_positions=sum(
            result.valid for result in results
        ),
        invalid_positions=sum(
            not result.valid for result in results
        ),
        tp_exits=sum(
            result.reason is ExitReason.TAKE_PROFIT
            for result in results
        ),
        sl_exits=sum(
            result.reason is ExitReason.STOP_LOSS
            for result in results
        ),
        no_exit=sum(
            result.reason is ExitReason.NO_EXIT
            for result in results
        ),
        isolated_errors=tuple(isolated_errors),
    )

    return results, summary


def september_2026_regression_fixture() -> tuple[
    list[PositionCase],
    dict[str, list[OHLC]],
]:
    """
    Regression fixture for the three September 2026 BUY positions
    identified by the forensic audit as having market price cross
    their TP levels before eventually closing as losses.

    This fixture is intentionally research-only.
    It does NOT access the production database and does NOT modify
    any live or paper positions.
    """

    positions = [
        PositionCase(
            trade_id="PAPER-2AD9E5C7FDA04948A4EE38F5EF0044A6",
            direction=Direction.BUY,
            entry=4177.788,
            stop_loss=4170.848409574364,
            take_profit=4195.136976064088,
        ),
        PositionCase(
            trade_id="PAPER-3E1F711E436D42FF8F9630B63218F81C",
            direction=Direction.BUY,
            entry=4177.207,
            stop_loss=4170.239266717222,
            take_profit=4194.626333206947,
        ),
        PositionCase(
            trade_id="PAPER-A2EB60FB37B4448D9A4CB63C7388A808",
            direction=Direction.BUY,
            entry=4177.207,
            stop_loss=4170.239266717222,
            take_profit=4194.626333206947,
        ),
    ]

    candles_by_trade: dict[str, list[OHLC]] = {}

    for index, position in enumerate(positions):
        if index == 0:
            candle = OHLC(
                timestamp="2026-09-30T07:05:00Z",
                open=4193.0,
                high=4197.875,
                low=4192.0,
                close=4194.0,
            )
        else:
            candle = OHLC(
                timestamp="2026-09-30T06:55:00Z",
                open=4192.0,
                high=4194.845,
                low=4191.5,
                close=4193.0,
            )

        candles_by_trade[position.trade_id] = [candle]

    return positions, candles_by_trade


def run_september_regression() -> ReplaySummary:
    """
    Run the three known September TP-crossing regression cases.
    """

    positions, candles_by_trade = (
        september_2026_regression_fixture()
    )

    results, summary = replay_isolated(
        positions=positions,
        candles_by_trade=candles_by_trade,
    )

    for result in results:
        print(
            f"{result.trade_id}: "
            f"{result.reason.value} "
            f"valid={result.valid} "
            f"trigger={result.trigger_price}"
        )

    print()
    print("September 2026 regression summary:")
    print(f"  positions: {summary.total_positions}")
    print(f"  valid: {summary.valid_positions}")
    print(f"  invalid: {summary.invalid_positions}")
    print(f"  TP exits: {summary.tp_exits}")
    print(f"  SL exits: {summary.sl_exits}")
    print(f"  no exit: {summary.no_exit}")

    if summary.isolated_errors:
        print("  isolated errors:")
        for error in summary.isolated_errors:
            print(f"    - {error}")

    return summary


if __name__ == "__main__":
    run_september_regression()
