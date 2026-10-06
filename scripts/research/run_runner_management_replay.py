"""RAYMOND V2.8 - Research-only runner management replay.

This module replays historical paper trades against M5 price data using
the research-only runner_management_policy.

It NEVER:
- places broker orders
- modifies production positions
- modifies the live strategy
- connects to MT5/Exness
- promotes research results to production
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


def price_at_r(direction, entry, risk, r):
    if direction == Direction.BUY:
        return entry + (r * risk)

    return entry - (r * risk)


def stop_hit(direction, candle, stop):
    if direction == Direction.BUY:
        return float(candle["low"]) <= stop

    return float(candle["high"]) >= stop


def calculate_pnl(direction, entry, exit_price, quantity):
    if direction == Direction.BUY:
        price_move = exit_price - entry
    else:
        price_move = entry - exit_price

    return price_move * quantity * CONTRACT_SIZE


def normalize_timestamp(value):
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")

    return timestamp.tz_convert("UTC")


def replay_trade(trade, m5, config):
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

    direction = Direction(
        str(trade["direction"]).upper()
    )

    entry = float(trade["entry_price"])
    initial_stop = float(trade["initial_stop_loss"])

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

    opened = normalize_timestamp(
        trade["opened_at"]
    )

    closed = normalize_timestamp(
        trade["closed_at"]
    )

    candles = m5[
        (m5["timestamp"] >= opened.floor("5min"))
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

    partial_close_pnl = 0.0

    events = []

    exit_price = None
    exit_reason = None

    for _, candle in candles.iterrows():

        # --------------------------------------------------
        # EXISTING STOP FIRST
        # --------------------------------------------------
        #
        # This is intentionally conservative.
        #
        # If the candle touches an already-active stop,
        # the stop is considered hit before a new management
        # action is allowed to use that candle.
        # --------------------------------------------------

        if stop_hit(
            direction,
            candle,
            current_stop,
        ):
            exit_price = current_stop
            exit_reason = "STOP"
            break

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

            partial_price = price_at_r(
                direction,
                entry,
                original_risk,
                config.partial_close_rr,
            )

            partial_quantity = (
                decision.partial_close_quantity
            )

            partial_pnl += calculate_pnl(
                direction,
                entry,
                partial_price,
                partial_quantity,
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
                        candle["timestamp"]
                    ),
                    "action": "PARTIAL_CLOSE",
                    "price": partial_price,
                    "quantity": partial_quantity,
                    "r": decision.current_r,
                    "pnl": calculate_pnl(
                        direction,
                        entry,
                        partial_price,
                        partial_quantity,
                    ),
                }
            )

            # The research model protects the remaining
            # runner at entry after the partial threshold.
            if (
                config.protection_rr
                <= config.partial_close_rr
            ):
                protection_stop = entry

                if (
                    direction == Direction.BUY
                    and protection_stop
                    > current_stop
                ) or (
                    direction == Direction.SELL
                    and protection_stop
                    < current_stop
                ):
                    current_stop = protection_stop

                    events.append(
                        {
                            "time": str(
                                candle["timestamp"]
                            ),
                            "action":
                                "MOVE_TO_PROTECTION",
                            "price": current_stop,
                            "r": decision.current_r,
                        }
                    )

            continue

        # --------------------------------------------------
        # MOVE TO PROTECTION
        # --------------------------------------------------

        if decision.action == "MOVE_TO_PROTECTION":

            current_stop = float(
                decision.new_stop
            )

            events.append(
                {
                    "time": str(
                        candle["timestamp"]
                    ),
                    "action":
                        "MOVE_TO_PROTECTION",
                    "price": current_stop,
                    "r": decision.current_r,
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

            else:
                if candidate_stop >= current_stop:
                    continue

            current_stop = candidate_stop
            trailing_active = True

            events.append(
                {
                    "time": str(
                        candle["timestamp"]
                    ),
                    "action": "TRAIL",
                    "price": current_stop,
                    "r": decision.current_r,
                }
            )

    # ------------------------------------------------------
    # FALLBACK
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
            exit_price = float(
                m5.iloc[-1]["close"]
            )

        exit_reason = (
            "RECORDED_CLOSE_FALLBACK"
        )

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

    return {
        "trade_id": trade["trade_id"],
        "status": "REPLAYED",
        "direction": direction.value,
        "quantity": quantity,
        "entry_price": entry,
        "initial_stop_loss": initial_stop,
        "original_risk_1r": original_risk,
        "partial_close_applied":
            partial_close_applied,
        "partial_close_pnl":
            round(partial_close_pnl, 6),
        "runner_exit_price":
            round(exit_price, 6),
        "runner_exit_reason":
            exit_reason,
        "runner_remaining_quantity":
            remaining_quantity,
        "runner_final_pnl":
            round(runner_final_pnl, 6),
        "simulated_total_pnl":
            round(simulated_total_pnl, 6),
        "actual_audited_pnl":
            round(actual_audited_pnl, 6),
        "difference_vs_actual":
            round(difference, 6),
        "trailing_active":
            trailing_active,
        "event_count":
            len(events),
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

    config = RunnerConfig()
    config.validate()

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

    m5 = pd.read_csv(
        args.m5
    )

    m5["timestamp"] = pd.to_datetime(
        m5["timestamp"],
        utc=True,
    )

    results = []

    for trade in trades:

        results.append(
            replay_trade(
                trade,
                m5,
                config,
            )
        )

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

    report = {
        "report_type":
            "RAYMOND_RUNNER_MANAGEMENT_REPLAY",

        "version":
            "1.0",

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
            audit.get("month"),

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
            all(
                abs(
                    (
                        result[
                            "partial_close_pnl"
                        ]
                        + result[
                            "runner_final_pnl"
                        ]
                    )
                    - result[
                        "simulated_total_pnl"
                    ]
                )
                < 0.000001
                for result in replayed
            ),

        "trades":
            results,
    }

    Path(
        args.output
    ).write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
