#!/usr/bin/env python3

"""
RAYMOND v2.8 - WEEKLY GROWTH V3 RESEARCH

RESEARCH ONLY.

This version tests:
- Risk/reward
- Signal threshold
- Weekly trade cap
- ATR stop multiplier
- Profit protection

Profit protection modes:
- none
- be_1r
- lock_0_5r
- trail_1r

Data split:
- 2024 = development
- 2025 = parameter-selection validation
- 2026+ = completely unseen final holdout

IMPORTANT:
This file does NOT place live trades.
It does NOT modify the live/paper trading engine.
"""

from __future__ import annotations

import itertools
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


HERE = Path(__file__).resolve().parent

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


from run_weekly_growth_backtest import (
    StrategyConfig,
    Position,
    Trade,
    load_data,
    calculate_indicators,
    score_signal,
    calculate_volume_for_risk,
    get_entry_price,
    get_exit_price,
    calculate_pnl,
    determine_exit,
    week_key,
    new_week_state,
    calculate_metrics,
)


# ============================================================
# PATHS
# ============================================================

INPUT = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(
        "data/historical/"
        "xauusd_h1_2024_2026_normalized.csv"
    )
)

OUT = (
    Path(sys.argv[2])
    if len(sys.argv) > 2
    else Path(
        "backtest_results/weekly_growth_v3"
    )
)


# ============================================================
# V3 PARAMETER GRID
# ============================================================

GRID = {
    "risk_reward": [
        2.0,
        2.5,
        3.0,
        3.5,
        4.0,
    ],

    "min_signal_score": [
        55,
        60,
        65,
        70,
    ],

    "max_trades_per_week": [
        6,
        8,
    ],

    "atr_stop_multiplier": [
        1.0,
        1.2,
        1.4,
    ],

    "profit_protection": [
        "none",
        "be_1r",
        "lock_0_5r",
        "trail_1r",
    ],
}


# ============================================================
# BASE STRATEGY SETTINGS
# ============================================================

BASE = {
    "weekly_target": 0.25,
    "weekly_loss_limit": -0.09,
    "risk_per_trade": 0.03,
    "spread": 0.30,
    "slippage": 0.05,
    "min_atr_ratio": 0.70,
    "max_atr_ratio": 1.80,
}


# ============================================================
# PROFIT PROTECTION
# ============================================================

def apply_profit_protection(
    position: Position,
    candle: pd.Series,
    mode: str,
) -> None:

    if mode == "none":
        return

    close = float(candle["close"])

    entry = float(position.entry_price)

    risk = float(position.risk_distance)

    if risk <= 0:
        return


    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if position.direction == "BUY":

        r_now = (
            close - entry
        ) / risk


        # Break-even after +1R
        if mode == "be_1r":

            if r_now >= 1.0:

                position.stop_price = max(
                    position.stop_price,
                    entry,
                )


        # Lock +0.5R after +1.5R
        elif mode == "lock_0_5r":

            if r_now >= 1.5:

                locked_price = (
                    entry
                    + (0.5 * risk)
                )

                position.stop_price = max(
                    position.stop_price,
                    locked_price,
                )


        # Trail by 1R after +2R
        elif mode == "trail_1r":

            if r_now >= 2.0:

                trailing_price = (
                    close - risk
                )

                position.stop_price = max(
                    position.stop_price,
                    trailing_price,
                )


    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    else:

        r_now = (
            entry - close
        ) / risk


        # Break-even after +1R
        if mode == "be_1r":

            if r_now >= 1.0:

                position.stop_price = min(
                    position.stop_price,
                    entry,
                )


        # Lock +0.5R after +1.5R
        elif mode == "lock_0_5r":

            if r_now >= 1.5:

                locked_price = (
                    entry
                    - (0.5 * risk)
                )

                position.stop_price = min(
                    position.stop_price,
                    locked_price,
                )


        # Trail by 1R after +2R
        elif mode == "trail_1r":

            if r_now >= 2.0:

                trailing_price = (
                    close + risk
                )

                position.stop_price = min(
                    position.stop_price,
                    trailing_price,
                )


# ============================================================
# V3 BACKTEST ENGINE
# ============================================================

def run_backtest_v3(
    df: pd.DataFrame,
    config: StrategyConfig,
    protection_mode: str,
) -> Tuple[
    List[Trade],
    List[Dict],
    float,
]:

    balance = float(
        config.starting_balance
    )

    trades: List[Trade] = []

    weekly_records: Dict[
        str,
        Dict
    ] = {}

    position = None

    current_week = None

    pending_signal = None


    # ========================================================
    # MAIN LOOP
    # ========================================================

    for i in range(1, len(df)):

        candle = df.iloc[i]

        timestamp = pd.Timestamp(
            candle["timestamp"]
        )

        this_week = week_key(
            timestamp
        )


        # ----------------------------------------------------
        # NEW WEEK
        # ----------------------------------------------------

        if this_week != current_week:

            current_week = this_week

            if this_week not in weekly_records:

                weekly_records[this_week] = (
                    new_week_state(
                        balance
                    )
                )

            pending_signal = None


        week = weekly_records[
            this_week
        ]


        # ====================================================
        # MANAGE EXISTING POSITION
        # ====================================================

        if position is not None:

            exit_result = determine_exit(
                position,
                candle,
                config,
            )


            # ------------------------------------------------
            # EXIT
            # ------------------------------------------------

            if exit_result is not None:

                (
                    raw_exit_price,
                    exit_reason,
                ) = exit_result


                exit_price = get_exit_price(
                    position.direction,
                    raw_exit_price,
                    config,
                )


                pnl = calculate_pnl(
                    position.direction,
                    position.entry_price,
                    exit_price,
                    position.volume,
                )


                balance_before = balance

                balance += pnl


                if position.risk_amount > 0:

                    r_multiple = (
                        pnl
                        / position.risk_amount
                    )

                else:

                    r_multiple = 0.0


                # ------------------------------------------------
                # WEEK STATISTICS
                # ------------------------------------------------

                if pnl > 0:

                    week["wins"] += 1

                elif pnl < 0:

                    week["losses"] += 1

                else:

                    week["break_evens"] += 1


                week["profit"] += pnl


                # ------------------------------------------------
                # SAVE TRADE
                # ------------------------------------------------

                trades.append(
                    Trade(
                        direction=position.direction,

                        signal_time=(
                            position
                            .signal_time
                            .isoformat()
                        ),

                        entry_time=(
                            position
                            .entry_time
                            .isoformat()
                        ),

                        exit_time=(
                            timestamp
                            .isoformat()
                        ),

                        entry_price=(
                            position
                            .entry_price
                        ),

                        exit_price=exit_price,

                        stop_price=(
                            position
                            .stop_price
                        ),

                        target_price=(
                            position
                            .target_price
                        ),

                        volume=(
                            position
                            .volume
                        ),

                        risk_amount=(
                            position
                            .risk_amount
                        ),

                        pnl=pnl,

                        r_multiple=(
                            r_multiple
                        ),

                        signal_score=(
                            position
                            .signal_score
                        ),

                        exit_reason=(
                            exit_reason
                        ),

                        setup_reason=(
                            position
                            .reason
                        ),

                        balance_before=(
                            balance_before
                        ),

                        balance_after=(
                            balance
                        ),

                        week=this_week,
                    )
                )


                week["trades"] += 1


                position = None

                pending_signal = None

                continue


            # ------------------------------------------------
            # PROFIT PROTECTION
            # ------------------------------------------------

            apply_profit_protection(
                position,
                candle,
                protection_mode,
            )


        # ====================================================
        # OPEN PENDING SIGNAL
        # ====================================================

        if (
            position is None
            and pending_signal is not None
        ):

            (
                direction,
                score,
                reason,
                signal_time,
            ) = pending_signal


            # ------------------------------------------------
            # WEEKLY RETURN
            # ------------------------------------------------

            if week["start_balance"] > 0:

                weekly_return = (
                    balance
                    - week["start_balance"]
                ) / week["start_balance"]

            else:

                weekly_return = 0.0


            # ------------------------------------------------
            # WEEKLY TARGET
            # ------------------------------------------------

            if (
                weekly_return
                >= config.weekly_target
            ):

                week["target_hit"] = True

                pending_signal = None


            # ------------------------------------------------
            # WEEKLY LOSS LIMIT
            # ------------------------------------------------

            elif (
                weekly_return
                <= config.weekly_loss_limit
            ):

                week["loss_limit_hit"] = True

                pending_signal = None


            # ------------------------------------------------
            # WEEKLY TRADE CAP
            # ------------------------------------------------

            elif (
                week["trades"]
                >= config.max_trades_per_week
            ):

                pending_signal = None


            # ------------------------------------------------
            # CREATE POSITION
            # ------------------------------------------------

            else:

                market_open = float(
                    candle["open"]
                )


                entry_price = get_entry_price(
                    direction,
                    market_open,
                    config,
                )


                atr = float(
                    candle["atr14"]
                )


                swing_low = float(
                    candle[
                        "previous_8_low"
                    ]
                )


                swing_high = float(
                    candle[
                        "previous_8_high"
                    ]
                )


                # --------------------------------------------
                # BUY STOP
                # --------------------------------------------

                if direction == "BUY":

                    atr_stop = (
                        entry_price
                        - (
                            atr
                            * config
                            .atr_stop_multiplier
                        )
                    )


                    structural_stop = (
                        swing_low
                        - (
                            atr
                            * 0.10
                        )
                    )


                    stop_price = min(
                        atr_stop,
                        structural_stop,
                    )


                    risk_distance = (
                        entry_price
                        - stop_price
                    )


                # --------------------------------------------
                # SELL STOP
                # --------------------------------------------

                else:

                    atr_stop = (
                        entry_price
                        + (
                            atr
                            * config
                            .atr_stop_multiplier
                        )
                    )


                    structural_stop = (
                        swing_high
                        + (
                            atr
                            * 0.10
                        )
                    )


                    stop_price = max(
                        atr_stop,
                        structural_stop,
                    )


                    risk_distance = (
                        stop_price
                        - entry_price
                    )


                # --------------------------------------------
                # INVALID STOP
                # --------------------------------------------

                if risk_distance <= 0:

                    pending_signal = None


                else:

                    (
                        volume,
                        risk_amount,
                    ) = calculate_volume_for_risk(
                        balance,
                        config.risk_per_trade,
                        risk_distance,
                        config,
                    )


                    # ----------------------------------------
                    # INVALID VOLUME
                    # ----------------------------------------

                    if volume <= 0:

                        pending_signal = None


                    else:

                        target_distance = (
                            risk_distance
                            * config.risk_reward
                        )


                        # ------------------------------------
                        # BUY TARGET
                        # ------------------------------------

                        if direction == "BUY":

                            target_price = (
                                entry_price
                                + target_distance
                            )


                        # ------------------------------------
                        # SELL TARGET
                        # ------------------------------------

                        else:

                            target_price = (
                                entry_price
                                - target_distance
                            )


                        # ------------------------------------
                        # CREATE POSITION
                        # ------------------------------------

                        position = Position(

                            direction=direction,

                            signal_time=signal_time,

                            entry_time=timestamp,

                            entry_price=entry_price,

                            stop_price=stop_price,

                            target_price=target_price,

                            volume=volume,

                            risk_amount=risk_amount,

                            risk_distance=risk_distance,

                            signal_score=score,

                            reason=reason,
                        )


                        pending_signal = None


        # ====================================================
        # GENERATE NEXT SIGNAL
        # ====================================================

        if i < len(df) - 1:

            (
                signal_direction,
                score,
                reason,
            ) = score_signal(
                candle,
                config,
            )


            if signal_direction in {
                "BUY",
                "SELL",
            }:

                pending_signal = (
                    signal_direction,
                    score,
                    reason,
                    timestamp,
                )

            else:

                pending_signal = None


    # ========================================================
    # CLOSE POSITION AT END OF DATA
    # ========================================================

    if position is not None:

        final_candle = df.iloc[-1]

        timestamp = pd.Timestamp(
            final_candle["timestamp"]
        )

        this_week = week_key(
            timestamp
        )


        raw_exit_price = float(
            final_candle["close"]
        )


        exit_price = get_exit_price(
            position.direction,
            raw_exit_price,
            config,
        )


        pnl = calculate_pnl(
            position.direction,
            position.entry_price,
            exit_price,
            position.volume,
        )


        balance_before = balance

        balance += pnl


        if position.risk_amount > 0:

            r_multiple = (
                pnl
                / position.risk_amount
            )

        else:

            r_multiple = 0.0


        week = weekly_records[
            this_week
        ]


        if pnl > 0:

            week["wins"] += 1

        elif pnl < 0:

            week["losses"] += 1

        else:

            week["break_evens"] += 1


        week["profit"] += pnl

        week["trades"] += 1


        trades.append(
            Trade(

                direction=(
                    position.direction
                ),

                signal_time=(
                    position
                    .signal_time
                    .isoformat()
                ),

                entry_time=(
                    position
                    .entry_time
                    .isoformat()
                ),

                exit_time=(
                    timestamp
                    .isoformat()
                ),

                entry_price=(
                    position
                    .entry_price
                ),

                exit_price=exit_price,

                stop_price=(
                    position
                    .stop_price
                ),

                target_price=(
                    position
                    .target_price
                ),

                volume=(
                    position.volume
                ),

                risk_amount=(
                    position
                    .risk_amount
                ),

                pnl=pnl,

                r_multiple=(
                    r_multiple
                ),

                signal_score=(
                    position
                    .signal_score
                ),

                exit_reason=(
                    "END_OF_DATA"
                ),

                setup_reason=(
                    position
                    .reason
                ),

                balance_before=(
                    balance_before
                ),

                balance_after=(
                    balance
                ),

                week=this_week,
            )
        )


    # ========================================================
    # WEEKLY RESULTS
    # ========================================================

    weekly_rows = []


    for (
        week_name,
        state,
    ) in weekly_records.items():

        start_balance = float(
            state["start_balance"]
        )


        if start_balance > 0:

            weekly_return = (
                state["profit"]
                / start_balance
            )

        else:

            weekly_return = 0.0


        weekly_rows.append(
            {
                "week": week_name,

                "start_balance": (
                    start_balance
                ),

                "profit": (
                    state["profit"]
                ),

                "weekly_return": (
                    weekly_return
                ),

                "weekly_return_pct": (
                    weekly_return * 100
                ),

                "trades": (
                    state["trades"]
                ),

                "wins": (
                    state["wins"]
                ),

                "losses": (
                    state["losses"]
                ),

                "break_evens": (
                    state["break_evens"]
                ),

                "target_hit": (
                    state["target_hit"]
                ),

                # ------------------------------------------------
                # IMPORTANT COMPATIBILITY FIX
                #
                # The existing calculate_metrics() function
                # expects this exact key.
                # ------------------------------------------------

                "target_25pct_hit": (
                    state["target_hit"]
                ),

                "loss_limit_hit": (
                    state["loss_limit_hit"]
                ),
            }
        )


    return (
        trades,
        weekly_rows,
        balance,
    )


# ============================================================
# RUN ONE VARIANT
# ============================================================

def run_variant(
    config_values: Dict,
    frame: pd.DataFrame,
    protection_mode: str,
) -> Dict:

    cfg = StrategyConfig(
        **config_values,
        starting_balance=1000.0,
    )


    (
        trades,
        weeks,
        end_balance,
    ) = run_backtest_v3(
        frame,
        cfg,
        protection_mode,
    )


    metrics = calculate_metrics(
        trades,
        weeks,
        cfg.starting_balance,
        end_balance,
        cfg,
    )


    return {
        "metrics": metrics,
        "trades": trades,
        "weeks": weeks,
    }


# ============================================================
# CANDIDATE SELECTION SCORE
# ============================================================

def selection_score(
    metrics: Dict,
) -> float:

    profit_factor = (
        metrics["profit_factor"]
        or 0.0
    )


    return (
        metrics["total_return_pct"]

        - (
            0.75
            * abs(
                metrics[
                    "max_drawdown_pct"
                ]
            )
        )

        + (
            10.0
            * max(
                0.0,
                profit_factor - 1.0,
            )
        )
    )


# ============================================================
# TRADE DIAGNOSTICS
# ============================================================

def diagnostic_summary(
    trades: List[Trade],
) -> Dict:

    exit_reasons = Counter(
        trade.exit_reason
        for trade in trades
    )


    setup_reasons = Counter(
        trade.setup_reason
        for trade in trades
    )


    scores = [
        trade.signal_score
        for trade in trades
    ]


    r_values = [
        trade.r_multiple
        for trade in trades
    ]


    return {

        "exit_reasons": dict(
            exit_reasons
        ),

        "setup_reasons": dict(
            setup_reasons.most_common(
                20
            )
        ),

        "signal_score_distribution": {
            str(score): scores.count(score)
            for score in sorted(
                set(scores)
            )
        },

        "average_r": (
            sum(r_values)
            / len(r_values)
            if r_values
            else 0.0
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print(
        "RAYMOND V2.8 WEEKLY GROWTH V3"
    )
    print(
        "=============================="
    )
    print()
    print(
        "RESEARCH ONLY: YES"
    )
    print(
        "LIVE TRADING: NO"
    )
    print()


    # ========================================================
    # LOAD DATA
    # ========================================================

    print(
        "Loading historical data..."
    )


    df = calculate_indicators(
        load_data(INPUT),
        StrategyConfig(),
    )


    if len(df) < 300:

        raise SystemExit(
            "Not enough candles for V3 research. "
            f"Found {len(df)}, need at least 300."
        )


    # ========================================================
    # PERIODS
    # ========================================================

    train = df[
        (
            df["timestamp"]
            >= pd.Timestamp(
                "2024-01-01",
                tz="UTC",
            )
        )
        &
        (
            df["timestamp"]
            < pd.Timestamp(
                "2025-01-01",
                tz="UTC",
            )
        )
    ].copy()


    selection = df[
        (
            df["timestamp"]
            >= pd.Timestamp(
                "2025-01-01",
                tz="UTC",
            )
        )
        &
        (
            df["timestamp"]
            < pd.Timestamp(
                "2026-01-01",
                tz="UTC",
            )
        )
    ].copy()


    holdout = df[
        df["timestamp"]
        >= pd.Timestamp(
            "2026-01-01",
            tz="UTC",
        )
    ].copy()


    print(
        f"2024 candles: {len(train):,}"
    )

    print(
        f"2025 candles: {len(selection):,}"
    )

    print(
        f"2026+ candles: {len(holdout):,}"
    )

    print()


    if len(train) < 300:

        raise SystemExit(
            "2024 development period "
            "does not contain enough candles."
        )


    if len(selection) < 300:

        raise SystemExit(
            "2025 selection period "
            "does not contain enough candles."
        )


    if len(holdout) < 100:

        raise SystemExit(
            "2026+ holdout period "
            "does not contain enough candles."
        )


    # ========================================================
    # GRID SEARCH
    # ========================================================

    candidates = []

    keys = list(
        GRID.keys()
    )


    combinations = list(
        itertools.product(
            *(
                GRID[key]
                for key in keys
            )
        )
    )


    total_combinations = len(
        combinations
    )


    print(
        "Testing parameter combinations:"
    )

    print(
        total_combinations
    )

    print()


    for index, values in enumerate(
        combinations,
        start=1,
    ):

        params = dict(
            zip(
                keys,
                values,
            )
        )


        config = {
            **BASE,

            "risk_reward": (
                params[
                    "risk_reward"
                ]
            ),

            "min_signal_score": (
                params[
                    "min_signal_score"
                ]
            ),

            "max_trades_per_week": (
                params[
                    "max_trades_per_week"
                ]
            ),

            "atr_stop_multiplier": (
                params[
                    "atr_stop_multiplier"
                ]
            ),
        }


        # ----------------------------------------------------
        # 2024 DEVELOPMENT
        # ----------------------------------------------------

        train_result = run_variant(
            config,
            train,
            params[
                "profit_protection"
            ],
        )


        train_metrics = (
            train_result["metrics"]
        )


        # ----------------------------------------------------
        # BASIC DEVELOPMENT FILTER
        # ----------------------------------------------------

        if (
            train_metrics[
                "total_return_pct"
            ] <= 0
        ):

            continue


        if (
            (
                train_metrics[
                    "profit_factor"
                ]
                or 0.0
            )
            <= 1.0
        ):

            continue


        if (
            train_metrics[
                "total_trades"
            ] < 10
        ):

            continue


        # ----------------------------------------------------
        # 2025 SELECTION
        # ----------------------------------------------------

        selection_result = run_variant(
            config,
            selection,
            params[
                "profit_protection"
            ],
        )


        selection_metrics = (
            selection_result[
                "metrics"
            ]
        )


        # ----------------------------------------------------
        # SELECTION FILTER
        # ----------------------------------------------------

        if (
            selection_metrics[
                "total_return_pct"
            ] <= 0
        ):

            continue


        if (
            (
                selection_metrics[
                    "profit_factor"
                ]
                or 0.0
            )
            <= 1.0
        ):

            continue


        if (
            selection_metrics[
                "total_trades"
            ] < 8
        ):

            continue


        # ----------------------------------------------------
        # STORE CANDIDATE
        # ----------------------------------------------------

        candidates.append(
            {

                "params": params,

                "train_return_pct": (
                    train_metrics[
                        "total_return_pct"
                    ]
                ),

                "train_profit_factor": (
                    train_metrics[
                        "profit_factor"
                    ]
                ),

                "train_drawdown_pct": (
                    train_metrics[
                        "max_drawdown_pct"
                    ]
                ),

                "train_win_rate_pct": (
                    train_metrics[
                        "win_rate_pct"
                    ]
                ),

                "train_trades": (
                    train_metrics[
                        "total_trades"
                    ]
                ),

                "selection_return_pct": (
                    selection_metrics[
                        "total_return_pct"
                    ]
                ),

                "selection_profit_factor": (
                    selection_metrics[
                        "profit_factor"
                    ]
                ),

                "selection_drawdown_pct": (
                    selection_metrics[
                        "max_drawdown_pct"
                    ]
                ),

                "selection_win_rate_pct": (
                    selection_metrics[
                        "win_rate_pct"
                    ]
                ),

                "selection_trades": (
                    selection_metrics[
                        "total_trades"
                    ]
                ),

                "selection_score": (
                    selection_score(
                        selection_metrics
                    )
                ),
            }
        )


        # ----------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------

        if (
            index % 25 == 0
            or index == total_combinations
        ):

            print(
                f"Progress: "
                f"{index}/"
                f"{total_combinations}"
            )


    # ========================================================
    # NO VALID CANDIDATES
    # ========================================================

    if not candidates:

        raise SystemExit(
            "No V3 candidate passed "
            "the development and "
            "selection filters."
        )


    # ========================================================
    # SORT CANDIDATES
    # ========================================================

    candidates.sort(
        key=lambda item: (
            item[
                "selection_score"
            ]
        ),
        reverse=True,
    )


    best = candidates[0]


    # ========================================================
    # SELECTED CONFIGURATION
    # ========================================================

    selected_config = {
        **BASE,

        "risk_reward": (
            best["params"][
                "risk_reward"
            ]
        ),

        "min_signal_score": (
            best["params"][
                "min_signal_score"
            ]
        ),

        "max_trades_per_week": (
            best["params"][
                "max_trades_per_week"
            ]
        ),

        "atr_stop_multiplier": (
            best["params"][
                "atr_stop_multiplier"
            ]
        ),
    }


    selected_protection = (
        best["params"][
            "profit_protection"
        ]
    )


    # ========================================================
    # FINAL UNSEEN HOLDOUT
    # ========================================================

    print()
    print(
        "Running final unseen 2026+ holdout..."
    )


    holdout_result = run_variant(
        selected_config,
        holdout,
        selected_protection,
    )


    holdout_metrics = (
        holdout_result[
            "metrics"
        ]
    )


    # ========================================================
    # FULL PERIOD
    # ========================================================

    print(
        "Running selected configuration "
        "over full period..."
    )


    full_result = run_variant(
        selected_config,
        df,
        selected_protection,
    )


    full_metrics = (
        full_result[
            "metrics"
        ]
    )


    # ========================================================
    # DIAGNOSTICS
    # ========================================================

    diagnostics = diagnostic_summary(
        full_result["trades"]
    )


    # ========================================================
    # OUTPUT DIRECTORY
    # ========================================================

    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )


    # ========================================================
    # TOP 50
    # ========================================================

    pd.DataFrame(
        candidates
    ).head(50).to_csv(
        OUT
        / "top_50_candidates.csv",
        index=False,
    )


    # ========================================================
    # OPTIMIZATION JSON
    # ========================================================

    with open(
        OUT
        / "optimization.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {

                "status": (
                    "completed"
                ),

                "research_only": True,

                "live_trading": False,

                "method": (
                    "three_period_"
                    "robustness_test"
                ),

                "development_period": (
                    "2024-01-01 through "
                    "2024-12-31"
                ),

                "selection_period": (
                    "2025-01-01 through "
                    "2025-12-31"
                ),

                "final_unseen_holdout": (
                    "2026-01-01 onward"
                ),

                "candidates_tested": (
                    len(candidates)
                ),

                "selected": best,

                "holdout_metrics": (
                    holdout_metrics
                ),

                "full_period_metrics": (
                    full_metrics
                ),

                "diagnostics": (
                    diagnostics
                ),
            },

            f,

            indent=2,

            default=str,
        )


    # ========================================================
    # SUMMARY
    # ========================================================

    with open(
        OUT
        / "summary.txt",
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "RAYMOND V2.8 "
            "WEEKLY GROWTH V3\n"
        )

        f.write(
            "==============================\n\n"
        )

        f.write(
            "RESEARCH ONLY: YES\n"
        )

        f.write(
            "LIVE TRADING: NO\n\n"
        )


        f.write(
            "SELECTED PARAMETERS\n"
        )

        f.write(
            "-------------------\n"
        )

        f.write(
            f"{best['params']}\n\n"
        )


        f.write(
            "DEVELOPMENT 2024\n"
        )

        f.write(
            "----------------\n"
        )

        f.write(
            "Return: "
            f"{best['train_return_pct']:.2f}%\n"
        )

        f.write(
            "PF: "
            f"{best['train_profit_factor']}\n"
        )

        f.write(
            "Win rate: "
            f"{best['train_win_rate_pct']:.2f}%\n"
        )

        f.write(
            "Drawdown: "
            f"{best['train_drawdown_pct']:.2f}%\n"
        )

        f.write(
            "Trades: "
            f"{best['train_trades']}\n\n"
        )


        f.write(
            "SELECTION 2025\n"
        )

        f.write(
            "--------------\n"
        )

        f.write(
            "Return: "
            f"{best['selection_return_pct']:.2f}%\n"
        )

        f.write(
            "PF: "
            f"{best['selection_profit_factor']}\n"
        )

        f.write(
            "Win rate: "
            f"{best['selection_win_rate_pct']:.2f}%\n"
        )

        f.write(
            "Drawdown: "
            f"{best['selection_drawdown_pct']:.2f}%\n"
        )

        f.write(
            "Trades: "
            f"{best['selection_trades']}\n\n"
        )


        f.write(
            "FINAL UNSEEN HOLDOUT 2026+\n"
        )

        f.write(
            "---------------------------\n"
        )

        f.write(
            "Return: "
            f"{holdout_metrics['total_return_pct']:.2f}%\n"
        )

        f.write(
            "PF: "
            f"{holdout_metrics['profit_factor']}\n"
        )

        f.write(
            "Win rate: "
            f"{holdout_metrics['win_rate_pct']:.2f}%\n"
        )

        f.write(
            "Drawdown: "
            f"{holdout_metrics['max_drawdown_pct']:.2f}%\n"
        )

        f.write(
            "Trades: "
            f"{holdout_metrics['total_trades']}\n\n"
        )


        f.write(
            "FULL PERIOD\n"
        )

        f.write(
            "-----------\n"
        )

        f.write(
            "Return: "
            f"{full_metrics['total_return_pct']:.2f}%\n"
        )

        f.write(
            "PF: "
            f"{full_metrics['profit_factor']}\n"
        )

        f.write(
            "Win rate: "
            f"{full_metrics['win_rate_pct']:.2f}%\n"
        )

        f.write(
            "Drawdown: "
            f"{full_metrics['max_drawdown_pct']:.2f}%\n"
        )

        f.write(
            "Trades: "
            f"{full_metrics['total_trades']}\n\n"
        )


        f.write(
            "TRADE DIAGNOSTICS\n"
        )

        f.write(
            "-----------------\n"
        )

        f.write(
            json.dumps(
                diagnostics,
                indent=2,
            )
        )


    # ========================================================
    # FULL TRADE CSV
    # ========================================================

    pd.DataFrame(
        [

            {

                "direction": (
                    trade.direction
                ),

                "signal_time": (
                    trade.signal_time
                ),

                "entry_time": (
                    trade.entry_time
                ),

                "exit_time": (
                    trade.exit_time
                ),

                "entry_price": (
                    trade.entry_price
                ),

                "exit_price": (
                    trade.exit_price
                ),

                "stop_price": (
                    trade.stop_price
                ),

                "target_price": (
                    trade.target_price
                ),

                "volume": (
                    trade.volume
                ),

                "risk_amount": (
                    trade.risk_amount
                ),

                "pnl": (
                    trade.pnl
                ),

                "r_multiple": (
                    trade.r_multiple
                ),

                "signal_score": (
                    trade.signal_score
                ),

                "exit_reason": (
                    trade.exit_reason
                ),

                "setup_reason": (
                    trade.setup_reason
                ),

                "balance_before": (
                    trade.balance_before
                ),

                "balance_after": (
                    trade.balance_after
                ),

                "week": (
                    trade.week
                ),
            }

            for trade
            in full_result["trades"]

        ]

    ).to_csv(
        OUT
        / "selected_full_period_trades.csv",
        index=False,
    )


    # ========================================================
    # CONSOLE OUTPUT
    # ========================================================

    print()
    print(
        "RAYMOND V2.8 "
        "WEEKLY GROWTH V3"
    )

    print(
        "=============================="
    )

    print()

    print(
        "SELECTED:"
    )

    print(
        best["params"]
    )

    print()

    print(
        "2024 DEVELOPMENT:"
    )

    print(
        f"Return: "
        f"{best['train_return_pct']:.2f}%"
    )

    print(
        f"PF: "
        f"{best['train_profit_factor']}"
    )

    print(
        f"Win rate: "
        f"{best['train_win_rate_pct']:.2f}%"
    )

    print(
        f"Drawdown: "
        f"{best['train_drawdown_pct']:.2f}%"
    )

    print(
        f"Trades: "
        f"{best['train_trades']}"
    )

    print()

    print(
        "2025 SELECTION:"
    )

    print(
        f"Return: "
        f"{best['selection_return_pct']:.2f}%"
    )

    print(
        f"PF: "
        f"{best['selection_profit_factor']}"
    )

    print(
        f"Win rate: "
        f"{best['selection_win_rate_pct']:.2f}%"
    )

    print(
        f"Drawdown: "
        f"{best['selection_drawdown_pct']:.2f}%"
    )

    print(
        f"Trades: "
        f"{best['selection_trades']}"
    )

    print()

    print(
        "2026+ FINAL UNSEEN HOLDOUT:"
    )

    print(
        f"Return: "
        f"{holdout_metrics['total_return_pct']:.2f}%"
    )

    print(
        f"PF: "
        f"{holdout_metrics['profit_factor']}"
    )

    print(
        f"Win rate: "
        f"{holdout_metrics['win_rate_pct']:.2f}%"
    )

    print(
        f"Drawdown: "
        f"{holdout_metrics['max_drawdown_pct']:.2f}%"
    )

    print(
        f"Trades: "
        f"{holdout_metrics['total_trades']}"
    )

    print()

    print(
        "FULL PERIOD:"
    )

    print(
        f"Return: "
        f"{full_metrics['total_return_pct']:.2f}%"
    )

    print(
        f"PF: "
        f"{full_metrics['profit_factor']}"
    )

    print(
        f"Win rate: "
        f"{full_metrics['win_rate_pct']:.2f}%"
    )

    print(
        f"Drawdown: "
        f"{full_metrics['max_drawdown_pct']:.2f}%"
    )

    print(
        f"Trades: "
        f"{full_metrics['total_trades']}"
    )

    print()

    print(
        "Results written to:"
    )

    print(
        OUT
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
