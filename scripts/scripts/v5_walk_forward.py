"""
RAYMOND V2.8 - V5 WALK-FORWARD RESEARCH RUNNER
================================================

STEP 4 OF V5 RESEARCH ARCHITECTURE

Purpose
-------
Run rolling walk-forward validation around the V5 strategy engine,
optimizer and execution engine.

Research structure
------------------
For each walk-forward window:

    TRAIN / DEVELOPMENT
            |
            v
       SELECT CONFIG
            |
            v
       LOCK CONFIG
            |
            v
     UNSEEN TEST WINDOW

The test window is NEVER used to optimize the configuration.

This is designed to answer:

    "Does the strategy continue working when market conditions change?"

It is NOT designed to maximize one historical backtest.

Research only
-------------
No MT5.
No Exness.
No broker orders.
No live trading.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ============================================================================
# PROJECT IMPORTS
# ============================================================================

SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPT_DIR),
    )


from v5_execution_engine import (
    calculate_indicators,
    detect_regime,
    evaluate_candidate,
    run_backtest,
    Candidate,
    STRATEGY_FAMILIES,
    REGIMES,
)


# ============================================================================
# DEFAULTS
# ============================================================================

DEFAULT_DATA = (
    "data/historical/xauusd_h1_2024_2026_normalized.csv"
)

DEFAULT_OUTPUT = (
    "backtest_results/weekly_growth_v5/walk_forward"
)

STARTING_BALANCE = 1000.0


# ============================================================================
# WALK-FORWARD WINDOWS
# ============================================================================

@dataclass
class WalkForwardWindow:
    name: str

    train_start: str
    train_end: str

    validation_start: str
    validation_end: str

    test_start: str
    test_end: str


# ============================================================================
# CANDIDATE PARAMETERS
# ============================================================================

def parameter_grid() -> List[Dict]:

    grid = []

    for strategy_family in STRATEGY_FAMILIES:

        for regime in REGIMES:

            for minimum_score in [
                55.0,
                60.0,
                65.0,
                70.0,
            ]:

                for risk_reward in [
                    1.5,
                    2.0,
                    2.5,
                    3.0,
                    3.5,
                ]:

                    for atr_stop_multiplier in [
                        0.8,
                        1.0,
                        1.2,
                        1.4,
                    ]:

                        for risk_per_trade in [
                            0.01,
                            0.015,
                            0.02,
                            0.025,
                        ]:

                            for max_trades_per_week in [
                                3,
                                5,
                                8,
                            ]:

                                for break_even_r in [
                                    0.8,
                                    1.0,
                                ]:

                                    for trailing_start_r in [
                                        1.5,
                                        2.0,
                                        2.5,
                                    ]:

                                        for trailing_distance_r in [
                                            0.75,
                                            1.0,
                                            1.25,
                                        ]:

                                            grid.append(
                                                {
                                                    "strategy_family":
                                                        strategy_family,

                                                    "regime":
                                                        regime,

                                                    "minimum_score":
                                                        minimum_score,

                                                    "risk_reward":
                                                        risk_reward,

                                                    "atr_stop_multiplier":
                                                        atr_stop_multiplier,

                                                    "risk_per_trade":
                                                        risk_per_trade,

                                                    "max_trades_per_week":
                                                        max_trades_per_week,

                                                    "break_even_r":
                                                        break_even_r,

                                                    "break_even_lock_r":
                                                        0.0,

                                                    "trailing_start_r":
                                                        trailing_start_r,

                                                    "trailing_distance_r":
                                                        trailing_distance_r,

                                                    "weekly_loss_limit":
                                                        -0.09,

                                                    "starting_balance":
                                                        STARTING_BALANCE,

                                                    "spread":
                                                        0.30,

                                                    "slippage":
                                                        0.05,
                                                }
                                            )

    return grid


# ============================================================================
# DATA
# ============================================================================

def load_data(
    path: str,
) -> pd.DataFrame:

    df = pd.read_csv(path)

    required = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            f"Missing columns: {missing}"
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=required
    )

    df = df.sort_values(
        "timestamp"
    )

    df = df.drop_duplicates(
        "timestamp"
    )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================================
# DATE WINDOWS
# ============================================================================

def build_windows() -> List[WalkForwardWindow]:

    """
    Windows deliberately keep the test period later than the
    optimization period.

    W1:
        Train:      2024
        Validate:   early 2025
        Test:       later 2025

    W2:
        Train:      2024 + early 2025
        Validate:   later 2025
        Test:       2026

    W3:
        Train:      2024 + 2025
        Validate:   early 2026
        Test:       later 2026

    If the dataset ends before a window, that window is skipped.
    """

    return [

        WalkForwardWindow(
            name="WF1",

            train_start="2024-01-01",
            train_end="2024-09-30 23:59:59",

            validation_start="2024-10-01",
            validation_end="2025-03-31 23:59:59",

            test_start="2025-04-01",
            test_end="2025-09-30 23:59:59",
        ),

        WalkForwardWindow(
            name="WF2",

            train_start="2024-01-01",
            train_end="2025-03-31 23:59:59",

            validation_start="2025-04-01",
            validation_end="2025-09-30 23:59:59",

            test_start="2025-10-01",
            test_end="2026-03-31 23:59:59",
        ),

        WalkForwardWindow(
            name="WF3",

            train_start="2024-01-01",
            train_end="2025-09-30 23:59:59",

            validation_start="2025-10-01",
            validation_end="2026-03-31 23:59:59",

            test_start="2026-04-01",
            test_end="2026-09-30 23:59:59",
        ),

        WalkForwardWindow(
            name="WF4",

            train_start="2024-01-01",
            train_end="2025-12-31 23:59:59",

            validation_start="2026-01-01",
            validation_end="2026-03-31 23:59:59",

            test_start="2026-04-01",
            test_end="2026-09-30 23:59:59",
        ),
    ]


def filter_period(
    df: pd.DataFrame,
    start: str,
    end: str,
) -> pd.DataFrame:

    start_ts = pd.Timestamp(
        start,
        tz="UTC",
    )

    end_ts = pd.Timestamp(
        end,
        tz="UTC",
    )

    mask = (
        (df["timestamp"] >= start_ts)
        &
        (df["timestamp"] <= end_ts)
    )

    return df.loc[
        mask
    ].copy()


# ============================================================================
# OPTIMIZATION OBJECTIVE
# ============================================================================

def robust_score(
    metrics: Dict,
) -> float:

    """
    Selection score used only on TRAIN / VALIDATION data.

    The objective rewards:

        return
        profit factor
        expectancy
        consistency
        sufficient trade count

    and penalizes:

        large drawdown
        very small samples

    This is deliberately NOT a win-rate optimizer.
    """

    trades = (
        metrics.get(
            "trades",
            0,
        )
    )

    if trades < 20:
        return -10000.0

    return_pct = float(
        metrics.get(
            "return_pct",
            0.0,
        )
    )

    profit_factor = float(
        metrics.get(
            "profit_factor",
            0.0,
        )
    )

    expectancy = float(
        metrics.get(
            "expectancy",
            0.0,
        )
    )

    drawdown = float(
        metrics.get(
            "max_drawdown_pct",
            0.0,
        )
    )

    # Monthly/period consistency proxy
    consistency = float(
        metrics.get(
            "consistency_pct",
            0.0,
        )
    )

    growth_component = (
        math.copysign(
            math.log1p(
                abs(return_pct)
            ),
            return_pct,
        )
        * 12.0
    )

    pf_component = (
        np.clip(
            profit_factor - 1.0,
            -1.0,
            4.0,
        )
        * 25.0
    )

    expectancy_component = (
        np.clip(
            expectancy,
            -2.0,
            2.0,
        )
        * 20.0
    )

    consistency_component = (
        consistency * 0.30
    )

    drawdown_penalty = (
        max(
            drawdown - 10.0,
            0.0,
        )
        * 2.5
    )

    sample_component = min(
        math.log1p(trades) * 2.0,
        15.0,
    )

    return float(
        growth_component
        + pf_component
        + expectancy_component
        + consistency_component
        + sample_component
        - drawdown_penalty
    )


# ============================================================================
# METRIC NORMALIZATION
# ============================================================================

def add_consistency_metric(
    metrics: Dict,
    trades,
) -> Dict:

    if not trades:

        metrics["consistency_pct"] = 0.0

        return metrics

    rows = []

    for trade in trades:

        rows.append(
            {
                "timestamp": pd.to_datetime(
                    trade.exit_time,
                    utc=True,
                ),

                "pnl":
                    trade.net_pnl,
            }
        )

    trade_df = pd.DataFrame(
        rows
    )

    trade_df["month"] = (
        trade_df["timestamp"]
        .dt.to_period("M")
        .astype(str)
    )

    monthly = (
        trade_df
        .groupby("month")["pnl"]
        .sum()
    )

    if len(monthly) == 0:

        metrics[
            "consistency_pct"
        ] = 0.0

    else:

        metrics[
            "consistency_pct"
        ] = float(
            (
                monthly > 0
            ).mean()
            * 100
        )

    return metrics


# ============================================================================
# EVALUATION
# ============================================================================

def evaluate_config(
    df: pd.DataFrame,
    config: Dict,
) -> Tuple[
    Dict,
    List,
]:

    trades, equity, metrics = (
        run_backtest(
            df=df,

            strategy_family=(
                config[
                    "strategy_family"
                ]
            ),

            regime=(
                config[
                    "regime"
                ]
            ),

            minimum_score=(
                config[
                    "minimum_score"
                ]
            ),

            risk_reward=(
                config[
                    "risk_reward"
                ]
            ),

            atr_stop_multiplier=(
                config[
                    "atr_stop_multiplier"
                ]
            ),

            risk_per_trade=(
                config[
                    "risk_per_trade"
                ]
            ),

            max_trades_per_week=(
                config[
                    "max_trades_per_week"
                ]
            ),

            break_even_r=(
                config[
                    "break_even_r"
                ]
            ),

            break_even_lock_r=(
                config[
                    "break_even_lock_r"
                ]
            ),

            trailing_start_r=(
                config[
                    "trailing_start_r"
                ]
            ),

            trailing_distance_r=(
                config[
                    "trailing_distance_r"
                ]
            ),

            weekly_loss_limit=(
                config[
                    "weekly_loss_limit"
                ]
            ),

            starting_balance=(
                config[
                    "starting_balance"
                ]
            ),

            spread=(
                config[
                    "spread"
                ]
            ),

            slippage=(
                config[
                    "slippage"
                ]
            ),
        )
    )

    metrics = (
        add_consistency_metric(
            metrics,
            trades,
        )
    )

    return metrics, trades


# ============================================================================
# TRAIN / VALIDATION SELECTION
# ============================================================================

def select_candidate(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    grid: List[Dict],
    top_n: int = 25,
) -> Tuple[
    Optional[Dict],
    pd.DataFrame,
]:

    records = []

    print(
        f"Evaluating {len(grid):,} "
        "candidate configurations..."
    )

    for index, config in enumerate(
        grid,
        start=1,
    ):

        train_metrics, _ = (
            evaluate_config(
                train_df,
                config,
            )
        )

        train_score = (
            robust_score(
                train_metrics
            )
        )

        # Ignore obviously weak training candidates.
        if train_score <= -9999:
            continue

        records.append(
            {
                "config": config,
                "train_score":
                    train_score,
                "train_return":
                    train_metrics[
                        "return_pct"
                    ],
                "train_pf":
                    train_metrics[
                        "profit_factor"
                    ],
                "train_dd":
                    train_metrics[
                        "max_drawdown_pct"
                    ],
                "train_trades":
                    train_metrics[
                        "trades"
                    ],
                "train_expectancy":
                    train_metrics[
                        "expectancy"
                    ],
            }
        )

        if index % 100 == 0:

            print(
                f"  {index:,}/"
                f"{len(grid):,}"
            )

    if not records:

        return None, pd.DataFrame()

    records.sort(
        key=lambda item:
        item["train_score"],
        reverse=True,
    )

    finalists = records[
        :top_n
    ]

    validation_records = []

    for item in finalists:

        config = item[
            "config"
        ]

        validation_metrics, _ = (
            evaluate_config(
                validation_df,
                config,
            )
        )

        validation_score = (
            robust_score(
                validation_metrics
            )
        )

        row = {
            "config":
                config,

            "train_score":
                item[
                    "train_score"
                ],

            "train_return":
                item[
                    "train_return"
                ],

            "train_pf":
                item[
                    "train_pf"
                ],

            "train_dd":
                item[
                    "train_dd"
                ],

            "train_trades":
                item[
                    "train_trades"
                ],

            "train_expectancy":
                item[
                    "train_expectancy"
                ],

            "validation_score":
                validation_score,

            "validation_return":
                validation_metrics[
                    "return_pct"
                ],

            "validation_pf":
                validation_metrics[
                    "profit_factor"
                ],

            "validation_dd":
                validation_metrics[
                    "max_drawdown_pct"
                ],

            "validation_trades":
                validation_metrics[
                    "trades"
                ],

            "validation_expectancy":
                validation_metrics[
                    "expectancy"
                ],

            "validation_consistency":
                validation_metrics.get(
                    "consistency_pct",
                    0.0,
                ),
        }

        validation_records.append(
            row
        )

    result_df = pd.DataFrame(
        validation_records
    )

    if result_df.empty:

        return None, result_df

    # Primary selection:
    # validation score.
    #
    # Secondary:
    # validation drawdown.
    #
    # Tertiary:
    # validation return.

    result_df = (
        result_df
        .sort_values(
            [
                "validation_score",
                "validation_return",
                "validation_pf",
                "validation_dd",
            ],
            ascending=[
                False,
                False,
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )

    best_config = result_df.iloc[
        0
    ]["config"]

    return (
        best_config,
        result_df,
    )


# ============================================================================
# UNSEEN TEST
# ============================================================================

def evaluate_unseen(
    test_df: pd.DataFrame,
    config: Dict,
) -> Dict:

    metrics, trades = (
        evaluate_config(
            test_df,
            config,
        )
    )

    return {
        "metrics":
            metrics,

        "trades":
            trades,
    }


# ============================================================================
# ROBUSTNESS TEST
# ============================================================================

def calculate_degradation(
    validation_metrics: Dict,
    test_metrics: Dict,
) -> Dict:

    validation_return = float(
        validation_metrics.get(
            "return_pct",
            0.0,
        )
    )

    test_return = float(
        test_metrics.get(
            "return_pct",
            0.0,
        )
    )

    validation_pf = float(
        validation_metrics.get(
            "profit_factor",
            0.0,
        )
    )

    test_pf = float(
        test_metrics.get(
            "profit_factor",
            0.0,
        )
    )

    if abs(validation_return) > 1e-9:

        return_degradation = (
            (
                test_return -
                validation_return
            )
            /
            abs(validation_return)
            * 100
        )

    else:

        return_degradation = 0.0

    if (
        abs(validation_pf)
        > 1e-9
    ):

        pf_degradation = (
            (
                test_pf -
                validation_pf
            )
            /
            abs(validation_pf)
            * 100
        )

    else:

        pf_degradation = 0.0

    return {
        "return_change_pct":
            return_degradation,

        "profit_factor_change_pct":
            pf_degradation,

        "validation_return":
            validation_return,

        "test_return":
            test_return,

        "validation_pf":
            validation_pf,

        "test_pf":
            test_pf,
    }


# ============================================================================
# WINDOW RUNNER
# ============================================================================

def run_window(
    df: pd.DataFrame,
    window: WalkForwardWindow,
    grid: List[Dict],
    output_dir: Path,
) -> Optional[Dict]:

    print()
    print("=" * 80)
    print(
        f"{window.name}"
    )
    print("=" * 80)

    train_df = filter_period(
        df,
        window.train_start,
        window.train_end,
    )

    validation_df = filter_period(
        df,
        window.validation_start,
        window.validation_end,
    )

    test_df = filter_period(
        df,
        window.test_start,
        window.test_end,
    )

    print(
        f"Train rows: "
        f"{len(train_df):,}"
    )

    print(
        f"Validation rows: "
        f"{len(validation_df):,}"
    )

    print(
        f"Test rows: "
        f"{len(test_df):,}"
    )

    if (
        len(train_df) < 500
        or len(validation_df) < 100
        or len(test_df) < 100
    ):

        print(
            "Skipping window: "
            "insufficient data."
        )

        return None

    best_config, ranking = (
        select_candidate(
            train_df=train_df,
            validation_df=validation_df,
            grid=grid,
            top_n=25,
        )
    )

    if best_config is None:

        print(
            "No valid candidate "
            "selected."
        )

        return None

    # --------------------------------------------------------------
    # LOCKED CONFIGURATION
    # --------------------------------------------------------------

    test_result = (
        evaluate_unseen(
            test_df,
            best_config,
        )
    )

    test_metrics = (
        test_result[
            "metrics"
        ]
    )

    validation_metrics, _ = (
        evaluate_config(
            validation_df,
            best_config,
        )
    )

    degradation = (
        calculate_degradation(
            validation_metrics,
            test_metrics,
        )
    )

    # --------------------------------------------------------------
    # SAVE WINDOW
    # --------------------------------------------------------------

    window_dir = (
        output_dir /
        window.name
    )

    window_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    ranking_output = (
        ranking.copy()
    )

    ranking_output[
        "config_json"
    ] = ranking_output[
        "config"
    ].apply(
        json.dumps
    )

    ranking_output = (
        ranking_output.drop(
            columns=[
                "config"
            ]
        )
    )

    ranking_output.to_csv(
        window_dir /
        "candidate_ranking.csv",
        index=False,
    )

    with open(
        window_dir /
        "selected_config.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            best_config,
            file,
            indent=2,
        )

    with open(
        window_dir /
        "validation_metrics.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            validation_metrics,
            file,
            indent=2,
            default=str,
        )

    with open(
        window_dir /
        "unseen_test_metrics.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            test_metrics,
            file,
            indent=2,
            default=str,
        )

    with open(
        window_dir /
        "degradation.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            degradation,
            file,
            indent=2,
            default=str,
        )

    trades_df = pd.DataFrame(
        [
            asdict(trade)
            for trade in test_result[
                "trades"
            ]
        ]
    )

    trades_df.to_csv(
        window_dir /
        "unseen_test_trades.csv",
        index=False,
    )

    # --------------------------------------------------------------
    # CONSOLE
    # --------------------------------------------------------------

    print()
    print(
        "SELECTED CONFIG"
    )

    print(
        f"Strategy: "
        f"{best_config['strategy_family']}"
    )

    print(
        f"Regime: "
        f"{best_config['regime']}"
    )

    print(
        f"Signal score: "
        f"{best_config['minimum_score']}"
    )

    print(
        f"R:R: "
        f"{best_config['risk_reward']}"
    )

    print(
        f"Risk/trade: "
        f"{best_config['risk_per_trade']:.2%}"
    )

    print()
    print(
        "UNSEEN TEST"
    )

    print(
        f"Trades: "
        f"{test_metrics['trades']}"
    )

    print(
        f"Win rate: "
        f"{test_metrics['win_rate_pct']:.2f}%"
    )

    print(
        f"Return: "
        f"{test_metrics['return_pct']:.2f}%"
    )

    print(
        f"Profit factor: "
        f"{test_metrics['profit_factor']:.3f}"
    )

    print(
        f"Max DD: "
        f"{test_metrics['max_drawdown_pct']:.2f}%"
    )

    print(
        f"Return change vs validation: "
        f"{degradation['return_change_pct']:.2f}%"
    )

    return {
        "window":
            window.name,

        "train_start":
            window.train_start,

        "train_end":
            window.train_end,

        "validation_start":
            window.validation_start,

        "validation_end":
            window.validation_end,

        "test_start":
            window.test_start,

        "test_end":
            window.test_end,

        "config":
            best_config,

        "validation":
            validation_metrics,

        "test":
            test_metrics,

        "degradation":
            degradation,
    }


# ============================================================================
# FINAL ROBUSTNESS REPORT
# ============================================================================

def build_final_report(
    results: List[Dict],
) -> Dict:

    if not results:

        return {
            "status":
                "no_valid_windows",

            "windows": 0,
        }

    test_returns = [
        result[
            "test"
        ][
            "return_pct"
        ]
        for result in results
    ]

    test_pf = [
        result[
            "test"
        ][
            "profit_factor"
        ]
        for result in results
    ]

    test_dd = [
        result[
            "test"
        ][
            "max_drawdown_pct"
        ]
        for result in results
    ]

    test_win_rate = [
        result[
            "test"
        ][
            "win_rate_pct"
        ]
        for result in results
    ]

    positive_windows = sum(
        value > 0
        for value in test_returns
    )

    profitable_pf_windows = sum(
        value > 1.0
        for value in test_pf
    )

    return {
        "status":
            "completed",

        "windows":
            len(results),

        "positive_test_windows":
            positive_windows,

        "positive_test_window_pct":
            (
                positive_windows /
                len(results) *
                100
            ),

        "pf_above_one_windows":
            profitable_pf_windows,

        "average_test_return_pct":
            float(
                np.mean(
                    test_returns
                )
            ),

        "median_test_return_pct":
            float(
                np.median(
                    test_returns
                )
            ),

        "worst_test_return_pct":
            float(
                np.min(
                    test_returns
                )
            ),

        "best_test_return_pct":
            float(
                np.max(
                    test_returns
                )
            ),

        "average_test_profit_factor":
            float(
                np.mean(
                    test_pf
                )
            ),

        "worst_test_profit_factor":
            float(
                np.min(
                    test_pf
                )
            ),

        "average_test_drawdown_pct":
            float(
                np.mean(
                    test_dd
                )
            ),

        "worst_test_drawdown_pct":
            float(
                np.max(
                    test_dd
                )
            ),

        "average_test_win_rate_pct":
            float(
                np.mean(
                    test_win_rate
                )
            ),

        "test_returns":
            test_returns,

        "test_profit_factors":
            test_pf,

        "test_drawdowns":
            test_dd,

        "test_win_rates":
            test_win_rate,
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Raymond V2.8 V5 walk-forward "
            "research runner"
        )
    )

    parser.add_argument(
        "--data",
        default=DEFAULT_DATA,
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=None,
        help=(
            "Limit the research grid for "
            "quick testing."
        ),
    )

    args = parser.parse_args()

    print("=" * 80)
    print(
        "RAYMOND V2.8 V5 WALK-FORWARD RESEARCH"
    )
    print("=" * 80)

    # --------------------------------------------------------------
    # LOAD
    # --------------------------------------------------------------

    df = load_data(
        args.data
    )

    df = calculate_indicators(
        df
    )

    print(
        f"Loaded rows: "
        f"{len(df):,}"
    )

    print(
        f"Data range: "
        f"{df['timestamp'].min()} "
        f"-> "
        f"{df['timestamp'].max()}"
    )

    # --------------------------------------------------------------
    # GRID
    # --------------------------------------------------------------

    grid = parameter_grid()

    if args.max_candidates:

        grid = grid[
            :args.max_candidates
        ]

    print(
        f"Research candidates: "
        f"{len(grid):,}"
    )

    # --------------------------------------------------------------
    # WINDOWS
    # --------------------------------------------------------------

    windows = build_windows()

    output_dir = Path(
        args.output
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    results = []

    for window in windows:

        result = run_window(
            df=df,
            window=window,
            grid=grid,
            output_dir=output_dir,
        )

        if result is not None:

            results.append(
                result
            )

    # --------------------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------------------

    final_report = (
        build_final_report(
            results
        )
    )

    with open(
        output_dir /
        "v5_walk_forward_report.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            final_report,
            file,
            indent=2,
            default=str,
        )

    # --------------------------------------------------------------
    # WINDOW TABLE
    # --------------------------------------------------------------

    if results:

        rows = []

        for result in results:

            test = result[
                "test"
            ]

            validation = result[
                "validation"
            ]

            config = result[
                "config"
            ]

            rows.append(
                {
                    "window":
                        result["window"],

                    "strategy":
                        config[
                            "strategy_family"
                        ],

                    "regime":
                        config[
                            "regime"
                        ],

                    "risk_per_trade":
                        config[
                            "risk_per_trade"
                        ],

                    "rr":
                        config[
                            "risk_reward"
                        ],

                    "validation_return_pct":
                        validation[
                            "return_pct"
                        ],

                    "test_return_pct":
                        test[
                            "return_pct"
                        ],

                    "test_trades":
                        test[
                            "trades"
                        ],

                    "test_win_rate_pct":
                        test[
                            "win_rate_pct"
                        ],

                    "test_profit_factor":
                        test[
                            "profit_factor"
                        ],

                    "test_max_dd_pct":
                        test[
                            "max_drawdown_pct"
                        ],

                    "test_expectancy":
                        test[
                            "expectancy"
                        ],

                    "return_change_pct":
                        result[
                            "degradation"
                        ][
                            "return_change_pct"
                        ],
                }
            )

        window_df = pd.DataFrame(
            rows
        )

        window_df.to_csv(
            output_dir /
            "v5_walk_forward_windows.csv",
            index=False,
        )

    # --------------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------------

    lines = []

    lines.append(
        "RAYMOND V2.8 V5 WALK-FORWARD REPORT"
    )

    lines.append(
        "=" * 80
    )

    lines.append(
        "RESEARCH ONLY"
    )

    lines.append("")

    lines.append(
        f"Completed windows: "
        f"{final_report.get('windows', 0)}"
    )

    lines.append(
        f"Positive unseen windows: "
        f"{final_report.get('positive_test_windows', 0)}"
    )

    lines.append(
        f"Positive unseen window rate: "
        f"{final_report.get('positive_test_window_pct', 0.0):.2f}%"
    )

    lines.append("")

    lines.append(
        "UNSEEN TEST PERFORMANCE"
    )

    lines.append(
        "------------------------"
    )

    lines.append(
        f"Average return: "
        f"{final_report.get('average_test_return_pct', 0.0):.2f}%"
    )

    lines.append(
        f"Median return: "
        f"{final_report.get('median_test_return_pct', 0.0):.2f}%"
    )

    lines.append(
        f"Best return: "
        f"{final_report.get('best_test_return_pct', 0.0):.2f}%"
    )

    lines.append(
        f"Worst return: "
        f"{final_report.get('worst_test_return_pct', 0.0):.2f}%"
    )

    lines.append(
        f"Average PF: "
        f"{final_report.get('average_test_profit_factor', 0.0):.3f}"
    )

    lines.append(
        f"Worst PF: "
        f"{final_report.get('worst_test_profit_factor', 0.0):.3f}"
    )

    lines.append(
        f"Average DD: "
        f"{final_report.get('average_test_drawdown_pct', 0.0):.2f}%"
    )

    lines.append(
        f"Worst DD: "
        f"{final_report.get('worst_test_drawdown_pct', 0.0):.2f}%"
    )

    lines.append(
        f"Average win rate: "
        f"{final_report.get('average_test_win_rate_pct', 0.0):.2f}%"
    )

    lines.append("")

    lines.append(
        "INTERPRETATION"
    )

    lines.append(
        "--------------"
    )

    lines.append(
        "A strategy is not considered robust merely "
        "because one backtest has a high return."
    )

    lines.append(
        "The important measurements are repeated "
        "unseen-window performance, PF, drawdown, "
        "expectancy and degradation."
    )

    lines.append("")

    lines.append(
        "The unseen test periods were not used "
        "to select their own configurations."
    )

    with open(
        output_dir /
        "summary.txt",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            "\n".join(lines)
        )

    # --------------------------------------------------------------
    # FINAL CONSOLE
    # --------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "V5 WALK-FORWARD COMPLETE"
    )
    print("=" * 80)

    print(
        f"Completed windows: "
        f"{final_report.get('windows', 0)}"
    )

    print(
        f"Positive unseen windows: "
        f"{final_report.get('positive_test_windows', 0)}"
    )

    print(
        f"Average unseen return: "
        f"{final_report.get('average_test_return_pct', 0.0):.2f}%"
    )

    print(
        f"Worst unseen return: "
        f"{final_report.get('worst_test_return_pct', 0.0):.2f}%"
    )

    print(
        f"Average unseen PF: "
        f"{final_report.get('average_test_profit_factor', 0.0):.3f}"
    )

    print(
        f"Worst unseen DD: "
        f"{final_report.get('worst_test_drawdown_pct', 0.0):.2f}%"
    )

    print()
    print(
        f"Results saved to: "
        f"{output_dir}"
    )


if __name__ == "__main__":
    main()
