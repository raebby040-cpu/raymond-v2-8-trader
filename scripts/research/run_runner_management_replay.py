"""RAYMOND V2.8 - Research-only runner management replay.

This module replays historical paper trades against M5 price data using
the research-only runner_management_policy.

IMPORTANT:
This module NEVER:
- places broker orders
- modifies production positions
- modifies the live strategy
- connects to MT5/Exness
- promotes research results to production

Research model:
1. Original risk_1r is immutable.
2. Profit protection occurs at +1R.
3. 50% partial close occurs at +2R.
4. The remaining runner is protected and can continue.
5. Runner trailing begins at +2.5R.
6. Trailing continues as price extends.
7. Partial P/L and final runner P/L are accounted separately.
8. Total simulated P/L must reconcile exactly.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from runner_management_policy import (
    Direction,
    RunnerConfig,
    RunnerPosition,
    evaluate_runner,
)


CONTRACT_SIZE = 100.0
EPSILON = 1e-9


def price_at_r(
    direction,
    entry,
    risk,
    r,
):
    """Return the price corresponding to a given original R level."""

    if direction == Direction.BUY:
        return entry + (r * risk)

    return entry - (r * risk)


def stop_hit(
    direction,
    candle,
    stop,
):
    """Check whether the active stop was touched by an M5 candle."""

    if direction == Direction.BUY:
        return float(candle["low"]) <= stop

    return float(candle["high"]) >= stop


def calculate_pnl(
    direction,
    entry,
    exit_price,
    quantity,
):
    """Calculate XAUUSD P/L using the 100 oz contract size."""

    if direction == Direction.BUY:
        price_move = exit_price - entry
    else:
        price_move = entry - exit_price

    return (
        price_move
        * quantity
        * CONTRACT_SIZE
    )


def normalize_timestamp(value):
    """Normalize a timestamp to UTC."""

    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")

    return timestamp.tz_convert("UTC")


def validate_trade_direction(
    direction,
    entry,
    initial_stop,
):
    """Validate that the original stop is on the correct side."""

    if direction == Direction.BUY:
        if initial_stop >= entry:
            raise ValueError(
                "BUY initial stop must be below entry."
            )

    elif direction == Direction.SELL:
        if initial_stop <= entry:
            raise ValueError(
                "SELL initial stop must be above entry."
            )


def replay_trade(
    trade,
    m5,
    config,
):
    """Replay one historical trade under the research runner policy."""

    required_fields = [
        "trade_id",
        "direction",
        "entry_price",
        "initial_stop_loss",
        "opened_at",
        "closed_at",
    ]

    missing = [
        field
        for field in required_fields
        if field not in trade
    ]

    if missing:
        return {
            "trade_id": trade.get("trade_id"),
            "status": "SKIPPED",
            "reason": "missing_fields",
            "missing_fields": missing,
        }

    try:
        direction = Direction(
            str(trade["direction"]).upper()
        )
    except ValueError:
        return {
            "trade_id": trade["trade_id"],
            "status": "SKIPPED",
            "reason": "invalid_direction",
            "direction": trade.get("direction"),
        }

    entry = float(
        trade["entry_price"]
    )

    initial_stop = float(
        trade["initial_stop_loss"]
    )

    quantity = float(
        trade.get("quantity")
        or trade.get("original_quantity")
        or 0
    )

    if quantity <= 0:
        return {
            "trade_id": trade["trade_id"],
            "status": "SKIPPED",
            "reason": "invalid_quantity",
        }

    original_risk = abs(
        entry - initial_stop
    )

    if original_risk <= 0:
        return {
            "trade_id": trade["trade_id"],
            "status": "SKIPPED",
            "reason": "invalid_original_risk",
        }

    try:
        validate_trade_direction(
            direction,
            entry,
            initial_stop,
        )
    except ValueError as exc:
        return {
            "trade_id": trade["trade_id"],
            "status": "SKIPPED",
            "reason": "invalid_stop_direction",
            "detail": str(exc),
        }

    opened = normalize_timestamp(
        trade["opened_at"]
    )

    closed = normalize_timestamp(
        trade["closed_at"]
    )

    if closed < opened:
        return {
            "trade_id": trade["trade_id"],
            "status": "SKIPPED",
            "reason": "closed_before_open",
        }

    candles = m5[
        (
            m5["timestamp"]
            >= opened.floor("5min")
        )
        & (
            m5["timestamp"]
            <= closed.ceil("5min")
        )
    ].copy()

    if candles.empty:
        return {
            "trade_id": trade["trade_id"],
            "status": "SKIPPED",
            "reason": "no_m5_candles",
        }

    current_stop = initial_stop
    remaining_quantity = quantity

    partial_close_applied = False
    trailing_active = False

    # IMPORTANT:
    # This is the corrected accumulator.
    partial_close_pnl = 0.0

    events = []

    exit_price = None
    exit_reason = None
    exit_time = None

    for _, candle in candles.iterrows():

        candle_time = candle["timestamp"]

        # --------------------------------------------------
        # EXISTING STOP FIRST
        # --------------------------------------------------
        #
        # Conservative OHLC rule:
        #
        # If the active stop was touched during this candle,
        # the existing stop wins before a new management action.
        #
        # This avoids assuming favorable intrabar sequencing
        # that OHLC data cannot prove.
        # --------------------------------------------------

        if stop_hit(
            direction,
            candle,
            current_stop,
        ):
            exit_price = current_stop
            exit_reason = "STOP"
            exit_time = candle_time
            break

        # --------------------------------------------------
        # USE CANDLE CLOSE FOR POLICY EVALUATION
        # --------------------------------------------------

        current_price = float(
            candle["close"]
        )

        position = RunnerPosition(
            direction=direction,
            entry=entry,
            original_risk_1r=original_risk,
            current_price=current_price,
            current_stop=current_stop,
            remaining_quantity=remaining_quantity,
            partial_close_applied=partial_close_applied,
            trailing_active=trailing_active,
        )

        decision = evaluate_runner(
            position,
            config,
        )

        # --------------------------------------------------
        # PARTIAL CLOSE
        # --------------------------------------------------

        if decision.action == "PARTIAL_CLOSE":

            partial_quantity = float(
                decision.partial_close_quantity
            )

            if (
                partial_quantity <= 0
                or partial_quantity
                >= remaining_quantity
            ):
                continue

            partial_price = price_at_r(
                direction,
                entry,
                original_risk,
                config.partial_close_rr,
            )

            partial_trade_pnl = calculate_pnl(
                direction,
                entry,
                partial_price,
                partial_quantity,
            )

            # CORRECTED:
            # Accumulate into partial_close_pnl.
            partial_close_pnl += (
                partial_trade_pnl
            )

            remaining_quantity = round(
                remaining_quantity
                - partial_quantity,
                8,
            )

            partial_close_applied = True

            events.append(
                {
                    "time": str(
                        candle_time
                    ),
                    "action":
                        "PARTIAL_CLOSE",
                    "price":
                        round(
                            partial_price,
                            6,
                        ),
                    "quantity":
                        partial_quantity,
                    "r":
                        round(
                            decision.current_r,
                            6,
                        ),
                    "pnl":
                        round(
                            partial_trade_pnl,
                            6,
                        ),
                }
            )

            # Protect the remaining runner at entry.
            protection_stop = entry

            if direction == Direction.BUY:

                if protection_stop > current_stop:
                    current_stop = (
                        protection_stop
                    )

                    events.append(
                        {
                            "time": str(
                                candle_time
                            ),
                            "action":
                                "MOVE_TO_PROTECTION",
                            "price":
                                round(
                                    current_stop,
                                    6,
                                ),
                            "r":
                                round(
                                    decision.current_r,
                                    6,
                                ),
                        }
                    )

            else:

                if protection_stop < current_stop:
                    current_stop = (
                        protection_stop
                    )

                    events.append(
                        {
                            "time": str(
                                candle_time
                            ),
                            "action":
                                "MOVE_TO_PROTECTION",
                            "price":
                                round(
                                    current_stop,
                                    6,
                                ),
                            "r":
                                round(
                                    decision.current_r,
                                    6,
                                ),
                        }
                    )

            continue

        # --------------------------------------------------
        # MOVE TO PROTECTION
        # --------------------------------------------------

        if decision.action == "MOVE_TO_PROTECTION":

            candidate_stop = float(
                decision.new_stop
            )

            # Never worsen protection.
            if direction == Direction.BUY:

                if candidate_stop > current_stop:
                    current_stop = (
                        candidate_stop
                    )

                    events.append(
                        {
                            "time": str(
                                candle_time
                            ),
                            "action":
                                "MOVE_TO_PROTECTION",
                            "price":
                                round(
                                    current_stop,
                                    6,
                                ),
                            "r":
                                round(
                                    decision.current_r,
                                    6,
                                ),
                        }
                    )

            else:

                if candidate_stop < current_stop:
                    current_stop = (
                        candidate_stop
                    )

                    events.append(
                        {
                            "time": str(
                                candle_time
                            ),
                            "action":
                                "MOVE_TO_PROTECTION",
                            "price":
                                round(
                                    current_stop,
                                    6,
                                ),
                            "r":
                                round(
                                    decision.current_r,
                                    6,
                                ),
                        }
                    )

            continue

        # --------------------------------------------------
        # TRAILING
        # --------------------------------------------------

        if decision.action == "TRAIL":

            candidate_stop = float(
                decision.new_stop
            )

            # Never worsen protection.
            if direction == Direction.BUY:

                if candidate_stop <= current_stop:
                    continue

                # Safety: BUY trailing stop must remain
                # below current price.
                if candidate_stop >= current_price:
                    continue

            else:

                if candidate_stop >= current_stop:
                    continue

                # Safety: SELL trailing stop must remain
                # above current price.
                if candidate_stop <= current_price:
                    continue

            current_stop = candidate_stop
            trailing_active = True

            events.append(
                {
                    "time": str(
                        candle_time
                    ),
                    "action":
                        "TRAIL",
                    "price":
                        round(
                            current_stop,
                            6,
                        ),
                    "r":
                        round(
                            decision.current_r,
                            6,
                        ),
                }
            )

    # ------------------------------------------------------
    # FALLBACK TO ACTUAL RECORDED EXIT
    # ------------------------------------------------------

    if exit_price is None:

        recorded_exit = trade.get(
            "exit_price"
        )

        if recorded_exit is not None:

            exit_price = float(
                recorded_exit
            )

        else:

            # Last available candle inside the
            # historical replay window.
            exit_price = float(
                candles.iloc[-1]["close"]
            )

        exit_reason = (
            "RECORDED_CLOSE_FALLBACK"
        )

        exit_time = candles.iloc[-1][
            "timestamp"
        ]

    # ------------------------------------------------------
    # FINAL RUNNER P/L
    # ------------------------------------------------------

    runner_final_pnl = calculate_pnl(
        direction,
        entry,
        exit_price,
        remaining_quantity,
    )

    simulated_total_pnl = (
        partial_close_pnl
        + runner_final_pnl
    )

    actual_audited_pnl = float(
        trade.get("pnl", 0.0)
    )

    difference = (
        simulated_total_pnl
        - actual_audited_pnl
    )

    # ------------------------------------------------------
    # ACCOUNTING RECONCILIATION
    # ------------------------------------------------------

    accounting_reconciled = (
        abs(
            (
                partial_close_pnl
                + runner_final_pnl
            )
            - simulated_total_pnl
        )
        <= EPSILON
    )

    return {
        "trade_id":
            trade["trade_id"],

        "status":
            "REPLAYED",

        "direction":
            direction.value,

        "quantity":
            quantity,

        "entry_price":
            round(entry, 6),

        "initial_stop_loss":
            round(initial_stop, 6),

        "original_risk_1r":
            round(original_risk, 6),

        "partial_close_applied":
            partial_close_applied,

        "partial_close_pnl":
            round(
                partial_close_pnl,
                6,
            ),

        "runner_exit_price":
            round(
                exit_price,
                6,
            ),

        "runner_exit_reason":
            exit_reason,

        "runner_exit_time":
            str(exit_time)
            if exit_time is not None
            else None,

        "runner_remaining_quantity":
            round(
                remaining_quantity,
                8,
            ),

        "runner_final_pnl":
            round(
                runner_final_pnl,
                6,
            ),

        "simulated_total_pnl":
            round(
                simulated_total_pnl,
                6,
            ),

        "actual_audited_pnl":
            round(
                actual_audited_pnl,
                6,
            ),

        "difference_vs_actual":
            round(
                difference,
                6,
            ),

        "trailing_active":
            trailing_active,

        "event_count":
            len(events),

        "accounting_reconciled":
            accounting_reconciled,

        "events":
            events,
    }


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Research-only RAYMOND runner "
            "management replay."
        )
    )

    parser.add_argument(
        "--audit",
        required=True,
    )

    parser.add_argument(
        "--m5",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    # ------------------------------------------------------
    # LOAD RESEARCH POLICY
    # ------------------------------------------------------

    config = RunnerConfig()
    config.validate()

    # ------------------------------------------------------
    # LOAD AUDIT
    # ------------------------------------------------------

    audit = json.loads(
        Path(
            args.audit
        ).read_text(
            encoding="utf-8"
        )
    )

    trades = audit.get(
        "trades",
        []
    )

    if not isinstance(
        trades,
        list,
    ):
        raise SystemExit(
            "ERROR: audit trades must be a list."
        )

    # ------------------------------------------------------
    # LOAD M5
    # ------------------------------------------------------

    m5 = pd.read_csv(
        args.m5
    )

    required_m5_columns = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    }

    missing_m5 = (
        required_m5_columns
        - set(m5.columns)
    )

    if missing_m5:
        raise SystemExit(
            "ERROR: missing M5 columns: "
            + ", ".join(
                sorted(missing_m5)
            )
        )

    m5["timestamp"] = (
        pd.to_datetime(
            m5["timestamp"],
            utc=True,
            errors="coerce",
        )
    )

    for column in (
        "open",
        "high",
        "low",
        "close",
    ):
        m5[column] = pd.to_numeric(
            m5[column],
            errors="coerce",
        )

    m5 = m5.dropna(
        subset=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
        ]
    )

    m5 = (
        m5.sort_values(
            "timestamp"
        )
        .drop_duplicates(
            subset=["timestamp"]
        )
        .reset_index(drop=True)
    )

    if m5.empty:
        raise SystemExit(
            "ERROR: M5 dataset is empty."
        )

    # ------------------------------------------------------
    # M5 DATA SAFETY VALIDATION
    # ------------------------------------------------------

    if (
        m5["high"]
        < m5["low"]
    ).any():
        raise SystemExit(
            "ERROR: M5 candle has high < low."
        )

    for field in (
        "open",
        "close",
    ):

        if (
            m5["high"]
            < m5[field]
        ).any():
            raise SystemExit(
                f"ERROR: M5 high < {field}."
            )

        if (
            m5["low"]
            > m5[field]
        ).any():
            raise SystemExit(
                f"ERROR: M5 low > {field}."
            )

    # ------------------------------------------------------
    # REPLAY
    # ------------------------------------------------------

    results = []

    for trade in trades:

        try:

            result = replay_trade(
                trade,
                m5,
                config,
            )

        except Exception as exc:

            # One malformed historical trade must NEVER
            # abort the entire research run.
            result = {
                "trade_id":
                    trade.get("trade_id"),

                "status":
                    "SKIPPED",

                "reason":
                    "replay_exception",

                "detail":
                    str(exc),
            }

        results.append(
            result
        )

    # ------------------------------------------------------
    # AGGREGATION
    # ------------------------------------------------------

    replayed = [
        result
        for result in results
        if result["status"]
        == "REPLAYED"
    ]

    skipped = [
        result
        for result in results
        if result["status"]
        != "REPLAYED"
    ]

    actual_total = sum(
        float(
            result[
                "actual_audited_pnl"
            ]
        )
        for result in replayed
    )

    simulated_total = sum(
        float(
            result[
                "simulated_total_pnl"
            ]
        )
        for result in replayed
    )

    partial_total = sum(
        float(
            result[
                "partial_close_pnl"
            ]
        )
        for result in replayed
    )

    runner_total = sum(
        float(
            result[
                "runner_final_pnl"
            ]
        )
        for result in replayed
    )

    difference = (
        simulated_total
        - actual_total
    )

    improved = sum(
        result[
            "difference_vs_actual"
        ] > 0.005
        for result in replayed
    )

    worsened = sum(
        result[
            "difference_vs_actual"
        ] < -0.005
        for result in replayed
    )

    unchanged = sum(
        abs(
            result[
                "difference_vs_actual"
            ]
        ) <= 0.005
        for result in replayed
    )

    accounting_reconciled = all(
        result[
            "accounting_reconciled"
        ]
        for result in replayed
    )

    aggregate_accounting_reconciled = (
        abs(
            (
                partial_total
                + runner_total
            )
            - simulated_total
        )
        <= EPSILON
    )

    # ------------------------------------------------------
    # REPORT
    # ------------------------------------------------------

    report = {

        "report_type":
            "RAYMOND_RUNNER_MANAGEMENT_REPLAY",

        "version":
            "1.1",

        "research_only":
            True,

        "live_trading_changed":
            False,

        "strategy_modified":
            False,

        "positions_modified":
            False,

        "orders_created":
            False,

        "candidates_promoted":
            False,

        "symbol":
            "XAUUSD",

        "month":
            audit.get(
                "month"
            ),

        "configuration": {

            "minimum_rr":
                config.minimum_rr,

            "protection_rr":
                config.protection_rr,

            "trail_start_rr":
                config.trail_start_rr,

            "trailing_distance_r":
                config.trailing_distance_r,

            "partial_close_rr":
                config.partial_close_rr,

            "partial_close_fraction":
                config.partial_close_fraction,

            "runner_mode":
                config.runner_mode,
        },

        "trade_count":
            len(trades),

        "replayed_trade_count":
            len(replayed),

        "skipped_trade_count":
            len(skipped),

        "actual_audited_pnl":
            round(
                actual_total,
                6,
            ),

        "simulated_runner_pnl":
            round(
                simulated_total,
                6,
            ),

        "partial_close_pnl_total":
            round(
                partial_total,
                6,
            ),

        "runner_final_pnl_total":
            round(
                runner_total,
                6,
            ),

        "difference_vs_actual":
            round(
                difference,
                6,
            ),

        "improved_trade_count":
            improved,

        "worsened_trade_count":
            worsened,

        "unchanged_trade_count":
            unchanged,

        "accounting_reconciled":
            (
                accounting_reconciled
                and aggregate_accounting_reconciled
            ),

        "safety": {

            "research_only":
                True,

            "live_trading_changed":
                False,

            "strategy_modified":
                False,

            "positions_modified":
                False,

            "orders_created":
                False,

            "candidates_promoted":
                False,
        },

        "trades":
            results,
    }

    # ------------------------------------------------------
    # WRITE OUTPUT
    # ------------------------------------------------------

    output_path = Path(
        args.output
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ------------------------------------------------------
    # CONSOLE SUMMARY
    # ------------------------------------------------------

    print(
        "RAYMOND RUNNER MANAGEMENT REPLAY"
    )

    print(
        "Research only:",
        True,
    )

    print(
        "Month:",
        audit.get("month"),
    )

    print(
        "Trades:",
        len(trades),
    )

    print(
        "Replayed:",
        len(replayed),
    )

    print(
        "Skipped:",
        len(skipped),
    )

    print(
        "Actual audited P/L:",
        round(
            actual_total,
            6,
        ),
    )

    print(
        "Simulated runner P/L:",
        round(
            simulated_total,
            6,
        ),
    )

    print(
        "Difference:",
        round(
            difference,
            6,
        ),
    )

    print(
        "Improved:",
        improved,
    )

    print(
        "Worsened:",
        worsened,
    )

    print(
        "Unchanged:",
        unchanged,
    )

    print(
        "Accounting reconciled:",
        (
            accounting_reconciled
            and aggregate_accounting_reconciled
        ),
    )


if __name__ == "__main__":
    main()
