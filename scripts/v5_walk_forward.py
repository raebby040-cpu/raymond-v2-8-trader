"""
RAYMOND V2.8 - V5 WALK-FORWARD RESEARCH RUNNER
================================================

STEP 4 OF V5 RESEARCH ARCHITECTURE

Purpose
-------
Run rolling walk-forward research using the CANONICAL V5 EXECUTION
ENGINE for every candidate evaluation.

Research structure
------------------

    TRAIN
      |
      v
    SELECT TOP CANDIDATES
      |
      v
    VALIDATION
      |
      v
    LOCK BEST CONFIG
      |
      v
    UNSEEN TEST
      |
      v
    DEGRADATION ANALYSIS

Important
---------
The execution engine is the single source of truth for:

    - signal execution
    - entry price
    - stop loss
    - take profit
    - risk sizing
    - XAUUSD contract calculation
    - spread
    - slippage
    - break-even
    - trailing stop
    - TP extension
    - weekly limits
    - trade P&L
    - equity
    - drawdown

This file does NOT contain a second trading simulator.

Research only
-------------
No MT5.
No Exness.
No broker orders.
No live trading.

XAUUSD model
------------
1.00 lot = 100 oz

P&L:

    (exit_price - entry_price)
        * 100
        * lots
        * direction

Example:

    2051 -> 2056
    0.02 lot

    $5 * 100 * 0.02 = $10
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ============================================================================
# PROJECT IMPORTS
# ============================================================================

SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from v5_execution_engine import (
    calculate_indicators,
    run_backtest,
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

DEFAULT_WEEKLY_LOSS_LIMIT = -0.09
DEFAULT_SPREAD = 0.30
DEFAULT_SLIPPAGE = 0.05


# ============================================================================
# STRATEGY FAMILIES
# ============================================================================

STRATEGY_FAMILIES = [
    "TREND_CONTINUATION",
    "PULLBACK_RETEST",
    "BREAKOUT",
    "LIQUIDITY_REVERSAL",
    "RANGE_MEAN_REVERSION",
    "MOMENTUM_EXPANSION",
]


# ============================================================================
# REGIMES
# ============================================================================

REGIMES = [
    "BULL_TREND",
    "BEAR_TREND",
    "RANGE",
    "VOLATILITY_COMPRESSION",
    "VOLATILITY_EXPANSION",
    "TRANSITION",
]


# ============================================================================
# WALK-FORWARD WINDOW
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
# WALK-FORWARD WINDOWS
# ============================================================================

def build_windows() -> List[WalkForwardWindow]:
    """
    Rolling windows.

    WF1
        Train:      2024
        Validation: Oct 2024 -> Mar 2025
        Test:       Apr 2025 -> Sep 2025

    WF2
        Train:      2024 -> Mar 2025
        Validation: Apr 2025 -> Sep 2025
        Test:       Oct 2025 -> Mar 2026

    WF3
        Train:      2024 -> Sep 2025
        Validation: Oct 2025 -> Mar 2026
        Test:       Apr 2026 -> Sep 2026

    WF4
        Train:      2024 -> Dec 2025
        Validation: Jan 2026 -> Mar 2026
        Test:       Apr 2026 -> Sep 2026

    IMPORTANT:
    WF3 and WF4 share the same final test period.
    WF4 is therefore treated as an expanding-window robustness check,
    not as an independent additional holdout.
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


# ============================================================================
# PARAMETER GRID
# ============================================================================

def parameter_grid() -> List[Dict]:
    """
    Full V5 research grid.

    6 strategy families
    x 6 regimes
    x 4 signal thresholds
    x 5 RR values
    x 4 ATR stop values
    x 4 risk values
    x 3 weekly trade limits
    x 2 BE values
    x 3 trailing start values
    x 3 trailing distance values

    Total:

        622,080 configurations
    """

    grid: List[Dict] = []

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
                                                        DEFAULT_WEEKLY_LOSS_LIMIT,

                                                    "starting_balance":
                                                        STARTING_BALANCE,

                                                    "spread":
                                                        DEFAULT_SPREAD,

                                                    "slippage":
                                                        DEFAULT_SLIPPAGE,
                                                }
                                            )

    return grid


# ============================================================================
# DATA LOADING
# ============================================================================

def load_data(path: str) -> pd.DataFrame:

    print()
    print("=" * 80)
    print("LOADING MARKET DATA")
    print("=" * 80)

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
            f"Missing required columns: {missing}"
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
        subset=["timestamp"]
    )

    df = df.reset_index(
        drop=True
    )

    if df.empty:
        raise ValueError(
            "Market data is empty after validation."
        )

    print(
        f"Rows loaded: {len(df):,}"
    )

    print(
        f"First timestamp: "
        f"{df['timestamp'].iloc[0]}"
    )

    print(
        f"Last timestamp: "
        f"{df['timestamp'].iloc[-1]}"
    )

    return df


# ============================================================================
# PERIOD FILTER
# ============================================================================

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

    result = df.loc[
        (
            df["timestamp"] >= start_ts
        )
        &
        (
            df["timestamp"] <= end_ts
        )
    ].copy()

    return result.reset_index(
        drop=True
    )


# ============================================================================
# METRIC HELPERS
# ============================================================================

def safe_float(
    value,
    default: float = 0.0,
) -> float:

    try:
        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):
        return default


def trade_consistency(
    trades,
) -> float:

    if not trades:
        return 0.0

    rows = []

    for trade in trades:

        try:
            timestamp = pd.to_datetime(
                trade.exit_time,
                utc=True,
            )

            pnl = safe_float(
                trade.net_pnl
            )

            rows.append(
                {
                    "timestamp": timestamp,
                    "pnl": pnl,
                }
            )

        except Exception:
            continue

    if not rows:
        return 0.0

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

    if monthly.empty:
        return 0.0

    return float(
        (
            monthly > 0
        ).mean()
        * 100.0
    )


# ============================================================================
# ROBUST SELECTION SCORE
# ============================================================================

def robust_score(
    metrics: Dict,
) -> float:
    """
    Multi-objective selection score.

    It deliberately does NOT optimize win rate alone.

    Rewards:
        - positive return
        - profit factor
        - expectancy
        - consistency
        - reasonable sample size

    Penalizes:
        - excessive drawdown
        - insufficient trades
    """

    trades = int(
        safe_float(
            metrics.get(
                "trades",
                0,
            )
        )
    )

    if trades < 20:
        return -10000.0

    return_pct = safe_float(
        metrics.get(
            "return_pct",
            0.0,
        )
    )

    profit_factor = safe_float(
        metrics.get(
            "profit_factor",
            0.0,
        )
    )

    expectancy = safe_float(
        metrics.get(
            "expectancy",
            0.0,
        )
    )

    drawdown = safe_float(
        metrics.get(
            "max_drawdown_pct",
            0.0,
        )
    )

    consistency = safe_float(
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
# CANONICAL CANDIDATE EVALUATION
# ============================================================================

def evaluate_config(
    df: pd.DataFrame,
    config: Dict,
) -> Tuple[Dict, List]:
    """
    Evaluate ONE candidate through the canonical execution engine.

    This is the critical architecture repair.

    There is deliberately NO second simulator here.
    """

    if df.empty:
        return (
            {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "win_rate_pct": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "net_profit": 0.0,
                "return_pct": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
                "average_r": 0.0,
                "average_win": 0.0,
                "average_loss": 0.0,
                "max_drawdown": 0.0,
                "max_drawdown_pct": 0.0,
                "ending_balance":
                    config.get(
                        "starting_balance",
                        STARTING_BALANCE,
                    ),
                "consistency_pct": 0.0,
            },
            [],
        )

    trades, equity, metrics = run_backtest(
        df=df,

        strategy_family=config[
            "strategy_family"
        ],

        regime=config[
            "regime"
        ],

        minimum_score=config[
            "minimum_score"
        ],

        risk_reward=config[
            "risk_reward"
        ],

        atr_stop_multiplier=config[
            "atr_stop_multiplier"
        ],

        risk_per_trade=config[
            "risk_per_trade"
        ],

        max_trades_per_week=config[
            "max_trades_per_week"
        ],

        break_even_r=config[
            "break_even_r"
        ],

        break_even_lock_r=config[
            "break_even_lock_r"
        ],

        trailing_start_r=config[
            "trailing_start_r"
        ],

        trailing_distance_r=config[
            "trailing_distance_r"
        ],

        weekly_loss_limit=config[
            "weekly_loss_limit"
        ],

        starting_balance=config[
            "starting_balance"
        ],

        spread=config[
            "spread"
        ],

        slippage=config[
            "slippage"
        ],
    )

    metrics = dict(metrics)

    metrics[
        "consistency_pct"
    ] = trade_consistency(
        trades
    )

    return (
        metrics,
        trades,
    )


# ============================================================================
# CANDIDATE RECORD
# ============================================================================

def candidate_record(
    config: Dict,
    metrics: Dict,
    score: float,
    prefix: str,
) -> Dict:

    return {
        "strategy_family":
            config["strategy_family"],

        "regime":
            config["regime"],

        "minimum_score":
            config["minimum_score"],

        "risk_reward":
            config["risk_reward"],

        "atr_stop_multiplier":
            config["atr_stop_multiplier"],

        "risk_per_trade":
            config["risk_per_trade"],

        "max_trades_per_week":
            config["max_trades_per_week"],

        "break_even_r":
            config["break_even_r"],

        "break_even_lock_r":
            config["break_even_lock_r"],

        "trailing_start_r":
            config["trailing_start_r"],

        "trailing_distance_r":
            config["trailing_distance_r"],

        f"{prefix}_score":
            score,

        f"{prefix}_trades":
            metrics.get(
                "trades",
                0,
            ),

        f"{prefix}_wins":
            metrics.get(
                "wins",
                0,
            ),

        f"{prefix}_losses":
            metrics.get(
                "losses",
                0,
            ),

        f"{prefix}_breakevens":
            metrics.get(
                "breakevens",
                0,
            ),

        f"{prefix}_win_rate_pct":
            metrics.get(
                "win_rate_pct",
                0.0,
            ),

        f"{prefix}_gross_profit":
            metrics.get(
                "gross_profit",
                0.0,
            ),

        f"{prefix}_gross_loss":
            metrics.get(
                "gross_loss",
                0.0,
            ),

        f"{prefix}_net_profit":
            metrics.get(
                "net_profit",
                0.0,
            ),

        f"{prefix}_return_pct":
            metrics.get(
                "return_pct",
                0.0,
            ),

        f"{prefix}_profit_factor":
            metrics.get(
                "profit_factor",
                0.0,
            ),

        f"{prefix}_expectancy":
            metrics.get(
                "expectancy",
                0.0,
            ),

        f"{prefix}_average_r":
            metrics.get(
                "average_r",
                0.0,
            ),

        f"{prefix}_max_drawdown":
            metrics.get(
                "max_drawdown",
                0.0,
            ),

        f"{prefix}_max_drawdown_pct":
            metrics.get(
                "max_drawdown_pct",
                0.0,
            ),

        f"{prefix}_ending_balance":
            metrics.get(
                "ending_balance",
                STARTING_BALANCE,
            ),

        f"{prefix}_consistency_pct":
            metrics.get(
                "consistency_pct",
                0.0,
            ),
    }


# ============================================================================
# TRAIN SELECTION
# ============================================================================

def evaluate_training_candidates(
    train_df: pd.DataFrame,
    grid: List[Dict],
    max_candidates: Optional[int] = None,
) -> List[Dict]:

    """
    Evaluate the training period.

    If max_candidates is supplied, only that many candidates are evaluated.

    This is intended for QUICK integration tests only.

    IMPORTANT:
    A quick run is NOT considered representative of the complete grid.
    """

    if max_candidates is not None:
        candidates_to_test = grid[
            :max_candidates
        ]
    else:
        candidates_to_test = grid

    print()
    print("=" * 80)
    print("TRAINING CANDIDATE EVALUATION")
    print("=" * 80)

    print(
        f"Candidates available: "
        f"{len(grid):,}"
    )

    print(
        f"Candidates evaluated: "
        f"{len(candidates_to_test):,}"
    )

    records: List[Dict] = []

    total = len(
        candidates_to_test
    )

    for index, config in enumerate(
        candidates_to_test,
        start=1,
    ):

        metrics, _ = evaluate_config(
            train_df,
            config,
        )

        score = robust_score(
            metrics
        )

        if score <= -9999.0:
            continue

        record = candidate_record(
            config=config,
            metrics=metrics,
            score=score,
            prefix="train",
        )

        record[
            "_config"
        ] = config

        records.append(
            record
        )

        if (
            index == 1
            or index % 25 == 0
            or index == total
        ):

            print(
                f"Train progress: "
                f"{index:,}/{total:,}"
            )

    records.sort(
        key=lambda row:
        row["train_score"],
        reverse=True,
    )

    return records


# ============================================================================
# VALIDATION
# ============================================================================

def validate_top_candidates(
    validation_df: pd.DataFrame,
    training_records: List[Dict],
    top_n: int = 25,
) -> List[Dict]:

    """
    Only the strongest training candidates are sent to validation.

    The validation period is NOT used to generate the original grid.
    """

    finalists = training_records[
        :top_n
    ]

    print()
    print("=" * 80)
    print("VALIDATING TOP TRAINING CANDIDATES")
    print("=" * 80)

    print(
        f"Candidates entering validation: "
        f"{len(finalists)}"
    )

    records: List[Dict] = []

    for index, train_record in enumerate(
        finalists,
        start=1,
    ):

        config = train_record[
            "_config"
        ]

        metrics, _ = evaluate_config(
            validation_df,
            config,
        )

        validation_score = robust_score(
            metrics
        )

        record = dict(
            train_record
        )

        record.pop(
            "_config",
            None,
        )

        validation_fields = (
            candidate_record(
                config=config,
                metrics=metrics,
                score=validation_score,
                prefix="validation",
            )
        )

        record.update(
            validation_fields
        )

        record[
            "_config"
        ] = config

        records.append(
            record
        )

        print(
            f"Validation "
            f"{index}/{len(finalists)}: "
            f"{config['strategy_family']} / "
            f"{config['regime']} / "
            f"score={validation_score:.3f}"
        )

    records.sort(
        key=lambda row: (
            row["validation_score"],
            row["validation_profit_factor"],
            row["validation_return_pct"],
            -row["validation_max_drawdown_pct"],
        ),
        reverse=True,
    )

    return records


# ============================================================================
# CONFIG CLEANING
# ============================================================================

def clean_config(
    config: Dict,
) -> Dict:

    return {
        key: (
            value.item()
            if isinstance(
                value,
                np.generic,
            )
            else value
        )
        for key, value in config.items()
    }


# ============================================================================
# WINDOW EXECUTION
# ============================================================================

def run_walk_forward_window(
    df: pd.DataFrame,
    window: WalkForwardWindow,
    max_candidates: Optional[int],
    top_n: int,
    output_root: Path,
) -> Dict:

    print()
    print("#" * 80)
    print(
        f"STARTING {window.name}"
    )
    print("#" * 80)

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
        f"{window.name} train rows: "
        f"{len(train_df):,}"
    )

    print(
        f"{window.name} validation rows: "
        f"{len(validation_df):,}"
    )

    print(
        f"{window.name} test rows: "
        f"{len(test_df):,}"
    )

    if len(train_df) < 100:
        raise ValueError(
            f"{window.name}: insufficient training data."
        )

    if len(validation_df) < 50:
        raise ValueError(
            f"{window.name}: insufficient validation data."
        )

    if len(test_df) < 50:
        raise ValueError(
            f"{window.name}: insufficient test data."
        )

    grid = parameter_grid()

    training_records = (
        evaluate_training_candidates(
            train_df=train_df,
            grid=grid,
            max_candidates=max_candidates,
        )
    )

    if not training_records:
        raise RuntimeError(
            f"{window.name}: no valid training candidates."
        )

    validation_records = (
        validate_top_candidates(
            validation_df=validation_df,
            training_records=training_records,
            top_n=top_n,
        )
    )

    if not validation_records:
        raise RuntimeError(
            f"{window.name}: no valid validation candidates."
        )

    # --------------------------------------------------------------
    # LOCK BEST CONFIGURATION
    # --------------------------------------------------------------

    selected_record = validation_records[0]

    selected_config = clean_config(
        selected_record["_config"]
    )

    print()
    print(
        "=" * 80
    )
    print(
        f"{window.name} LOCKED CONFIGURATION"
    )
    print(
        "=" * 80
    )

    for key, value in selected_config.items():
        print(
            f"{key}: {value}"
        )

    # --------------------------------------------------------------
    # UNSEEN TEST
    # --------------------------------------------------------------

    print()
    print(
        "=" * 80
    )
    print(
        f"{window.name} UNSEEN TEST"
    )
    print(
        "=" * 80
    )

    test_metrics, test_trades = evaluate_config(
        test_df,
        selected_config,
    )

    test_score = robust_score(
        test_metrics
    )

    print(
        f"Test trades: "
        f"{test_metrics.get('trades', 0)}"
    )

    print(
        f"Test return: "
        f"{test_metrics.get('return_pct', 0.0):.4f}%"
    )

    print(
        f"Test profit factor: "
        f"{test_metrics.get('profit_factor', 0.0):.4f}"
    )

    print(
        f"Test win rate: "
        f"{test_metrics.get('win_rate_pct', 0.0):.4f}%"
    )

    print(
        f"Test drawdown: "
        f"{test_metrics.get('max_drawdown_pct', 0.0):.4f}%"
    )

    # --------------------------------------------------------------
    # DEGRADATION
    # --------------------------------------------------------------

    validation_return = safe_float(
        selected_record.get(
            "validation_return_pct",
            0.0,
        )
    )

    validation_pf = safe_float(
        selected_record.get(
            "validation_profit_factor",
            0.0,
        )
    )

    test_return = safe_float(
        test_metrics.get(
            "return_pct",
            0.0,
        )
    )

    test_pf = safe_float(
        test_metrics.get(
            "profit_factor",
            0.0,
        )
    )

    if abs(validation_return) > 1e-12:

        return_degradation_pct = (
            (
                test_return -
                validation_return
            )
            /
            abs(validation_return)
            * 100.0
        )

    else:

        return_degradation_pct = 0.0

    if abs(validation_pf) > 1e-12:

        pf_degradation_pct = (
            (
                test_pf -
                validation_pf
            )
            /
            abs(validation_pf)
            * 100.0
        )

    else:

        pf_degradation_pct = 0.0

    degradation = {
        "validation_return_pct":
            validation_return,

        "test_return_pct":
            test_return,

        "return_change_percentage":
            return_degradation_pct,

        "validation_profit_factor":
            validation_pf,

        "test_profit_factor":
            test_pf,

        "profit_factor_change_percentage":
            pf_degradation_pct,

        "interpretation":
            (
                "POSITIVE"
                if test_return >= validation_return
                else "DEGRADED"
            ),
    }

    # --------------------------------------------------------------
    # SAVE WINDOW
    # --------------------------------------------------------------

    window_output = (
        output_root /
        window.name
    )

    window_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Candidate ranking
    ranking_rows = []

    for row in validation_records:

        cleaned = {
            key: value
            for key, value in row.items()
            if key != "_config"
        }

        ranking_rows.append(
            cleaned
        )

    ranking_df = pd.DataFrame(
        ranking_rows
    )

    ranking_df.to_csv(
        window_output /
        "candidate_ranking.csv",
        index=False,
    )

    # Selected configuration
    with open(
        window_output /
        "selected_config.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            selected_config,
            file,
            indent=2,
            default=str,
        )

    # Validation metrics
    validation_metrics = dict(
        selected_record
    )

    validation_metrics.pop(
        "_config",
        None,
    )

    with open(
        window_output /
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

    # Test metrics
    with open(
        window_output /
        "unseen_test_metrics.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            {
                "metrics":
                    test_metrics,
                "score":
                    test_score,
            },
            file,
            indent=2,
            default=str,
        )

    # Degradation
    with open(
        window_output /
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

    # Unseen test trades
    if test_trades:

        trade_rows = []

        for trade in test_trades:

            if hasattr(
                trade,
                "__dataclass_fields__",
            ):

                from dataclasses import asdict

                trade_rows.append(
                    asdict(trade)
                )

            else:

                trade_rows.append(
                    vars(trade)
                )

        trades_df = pd.DataFrame(
            trade_rows
        )

    else:

        trades_df = pd.DataFrame()

    trades_df.to_csv(
        window_output /
        "unseen_test_trades.csv",
        index=False,
    )

    # Summary
    summary_lines = [
        "RAYMOND V2.8 V5 WALK-FORWARD",
        "=" * 80,
        "",
        f"Window: {window.name}",
        "",
        "TRAIN",
        "-----",
        f"Start: {window.train_start}",
        f"End:   {window.train_end}",
        f"Rows:  {len(train_df):,}",
        "",
        "VALIDATION",
        "----------",
        f"Start: {window.validation_start}",
        f"End:   {window.validation_end}",
        f"Rows:  {len(validation_df):,}",
        "",
        "UNSEEN TEST",
        "-----------",
        f"Start: {window.test_start}",
        f"End:   {window.test_end}",
        f"Rows:  {len(test_df):,}",
        "",
        "LOCKED CONFIGURATION",
        "--------------------",
    ]

    for key, value in selected_config.items():

        summary_lines.append(
            f"{key}: {value}"
        )

    summary_lines.extend(
        [
            "",
            "VALIDATION RESULTS",
            "------------------",
            f"Return: "
            f"{validation_return:.4f}%",
            f"Profit factor: "
            f"{validation_pf:.4f}",
            "",
            "UNSEEN TEST RESULTS",
            "-------------------",
            f"Trades: "
            f"{test_metrics.get('trades', 0)}",
            f"Wins: "
            f"{test_metrics.get('wins', 0)}",
            f"Losses: "
            f"{test_metrics.get('losses', 0)}",
            f"Breakevens: "
            f"{test_metrics.get('breakevens', 0)}",
            f"Win rate: "
            f"{test_metrics.get('win_rate_pct', 0.0):.4f}%",
            f"Net profit: "
            f"{test_metrics.get('net_profit', 0.0):.4f}",
            f"Return: "
            f"{test_return:.4f}%",
            f"Profit factor: "
            f"{test_pf:.4f}",
            f"Expectancy: "
            f"{test_metrics.get('expectancy', 0.0):.6f}",
            f"Average R: "
            f"{test_metrics.get('average_r', 0.0):.6f}",
            f"Max DD: "
            f"{test_metrics.get('max_drawdown_pct', 0.0):.4f}%",
            "",
            "DEGRADATION",
            "-----------",
            f"Return change: "
            f"{return_degradation_pct:.4f}%",
            f"Profit factor change: "
            f"{pf_degradation_pct:.4f}%",
            f"Interpretation: "
            f"{degradation['interpretation']}",
            "",
            "IMPORTANT",
            "---------",
            "WF3 and WF4 share the same final test period.",
            "WF4 is an expanding-window robustness check,",
            "not an independent additional holdout.",
        ]
    )

    with open(
        window_output /
        "summary.txt",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            "\n".join(
                summary_lines
            )
        )

    # --------------------------------------------------------------
    # RETURN WINDOW SUMMARY
    # --------------------------------------------------------------

    return {
        "window": window.name,

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

        "train_rows":
            len(train_df),

        "validation_rows":
            len(validation_df),

        "test_rows":
            len(test_df),

        "train_candidates_evaluated":
            len(
                grid
                if max_candidates is None
                else grid[:max_candidates]
            ),

        "validation_candidates":
            len(validation_records),

        "strategy_family":
            selected_config[
                "strategy_family"
            ],

        "regime":
            selected_config[
                "regime"
            ],

        "minimum_score":
            selected_config[
                "minimum_score"
            ],

        "risk_reward":
            selected_config[
                "risk_reward"
            ],

        "atr_stop_multiplier":
            selected_config[
                "atr_stop_multiplier"
            ],

        "risk_per_trade":
            selected_config[
                "risk_per_trade"
            ],

        "max_trades_per_week":
            selected_config[
                "max_trades_per_week"
            ],

        "break_even_r":
            selected_config[
                "break_even_r"
            ],

        "trailing_start_r":
            selected_config[
                "trailing_start_r"
            ],

        "trailing_distance_r":
            selected_config[
                "trailing_distance_r"
            ],

        "train_score":
            safe_float(
                training_records[0].get(
                    "train_score",
                    0.0,
                )
            ),

        "validation_score":
            safe_float(
                selected_record.get(
                    "validation_score",
                    0.0,
                )
            ),

        "validation_trades":
            selected_record.get(
                "validation_trades",
                0,
            ),

        "validation_return_pct":
            validation_return,

        "validation_profit_factor":
            validation_pf,

        "validation_max_drawdown_pct":
            selected_record.get(
                "validation_max_drawdown_pct",
                0.0,
            ),

        "validation_win_rate_pct":
            selected_record.get(
                "validation_win_rate_pct",
                0.0,
            ),

        "test_trades":
            test_metrics.get(
                "trades",
                0,
            ),

        "test_wins":
            test_metrics.get(
                "wins",
                0,
            ),

        "test_losses":
            test_metrics.get(
                "losses",
                0,
            ),

        "test_breakevens":
            test_metrics.get(
                "breakevens",
                0,
            ),

        "test_win_rate_pct":
            test_metrics.get(
                "win_rate_pct",
                0.0,
            ),

        "test_net_profit":
            test_metrics.get(
                "net_profit",
                0.0,
            ),

        "test_return_pct":
            test_return,

        "test_profit_factor":
            test_pf,

        "test_expectancy":
            test_metrics.get(
                "expectancy",
                0.0,
            ),

        "test_average_r":
            test_metrics.get(
                "average_r",
                0.0,
            ),

        "test_max_drawdown_pct":
            test_metrics.get(
                "max_drawdown_pct",
                0.0,
            ),

        "test_ending_balance":
            test_metrics.get(
                "ending_balance",
                STARTING_BALANCE,
            ),

        "return_change_percentage":
            return_degradation_pct,

        "profit_factor_change_percentage":
            pf_degradation_pct,

        "test_score":
            test_score,

        "test_period_independent":
            (
                window.name
                not in {"WF4"}
            ),
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Raymond V2.8 V5 canonical "
            "walk-forward research runner"
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
            "Maximum training candidates per "
            "walk-forward window. Use for quick "
            "integration tests only."
        ),
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=25,
        help=(
            "Number of top training candidates "
            "sent to validation."
        ),
    )

    parser.add_argument(
        "--window",
        choices=[
            "WF1",
            "WF2",
            "WF3",
            "WF4",
            "ALL",
        ],
        default="ALL",
    )

    args = parser.parse_args()

    if (
        args.max_candidates is not None
        and args.max_candidates <= 0
    ):
        raise ValueError(
            "--max-candidates must be greater than zero."
        )

    if args.top_n <= 0:
        raise ValueError(
            "--top-n must be greater than zero."
        )

    print("=" * 80)
    print(
        "RAYMOND V2.8 - V5 WALK-FORWARD RESEARCH"
    )
    print("=" * 80)

    print(
        "CANONICAL EXECUTION ENGINE: ENABLED"
    )

    print(
        "Research only: NO LIVE BROKER EXECUTION"
    )

    print(
        "XAUUSD contract: 100 oz per 1.00 lot"
    )

    print(
        "Starting balance: "
        f"${STARTING_BALANCE:.2f}"
    )

    if args.max_candidates is not None:

        print()
        print(
            "WARNING:"
        )

        print(
            "This is a QUICK integration run."
        )

        print(
            f"Only the first "
            f"{args.max_candidates:,} "
            "grid candidates will be evaluated."
        )

        print(
            "It must NOT be treated as a full "
            "strategy-selection result."
        )

    # --------------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------------

    df = load_data(
        args.data
    )

    # --------------------------------------------------------------
    # CALCULATE INDICATORS ON COMPLETE DATASET
    # --------------------------------------------------------------
    #
    # This is important.
    #
    # Indicators are calculated BEFORE period slicing so that the
    # beginning of each research window does not lose its indicator
    # warm-up context unnecessarily.
    #
    # No future bars are used by the indicator calculations.
    # --------------------------------------------------------------

    print()
    print(
        "=" * 80
    )
    print(
        "CALCULATING CANONICAL INDICATORS"
    )
    print(
        "=" * 80
    )

    df = calculate_indicators(
        df
    )

    print(
        f"Indicator-ready rows: "
        f"{len(df):,}"
    )

    # --------------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------------

    output_root = Path(
        args.output
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------------
    # WINDOWS
    # --------------------------------------------------------------

    windows = build_windows()

    if args.window != "ALL":

        windows = [
            window
            for window in windows
            if window.name == args.window
        ]

    if not windows:

        raise RuntimeError(
            "No walk-forward windows selected."
        )

    # --------------------------------------------------------------
    # RUN WINDOWS
    # --------------------------------------------------------------

    window_results: List[Dict] = []

    failed_windows: List[Dict] = []

    for window in windows:

        try:

            result = run_walk_forward_window(
                df=df,
                window=window,
                max_candidates=args.max_candidates,
                top_n=args.top_n,
                output_root=output_root,
            )

            window_results.append(
                result
            )

        except Exception as exc:

            print()
            print(
                "!" * 80
            )

            print(
                f"{window.name} FAILED"
            )

            print(
                str(exc)
            )

            print(
                "!" * 80
            )

            failed_windows.append(
                {
                    "window":
                        window.name,

                    "error":
                        str(exc),
                }
            )

    # --------------------------------------------------------------
    # OVERALL REPORT
    # --------------------------------------------------------------

    windows_df = pd.DataFrame(
        window_results
    )

    if not windows_df.empty:

        windows_df.to_csv(
            output_root /
            "v5_walk_forward_windows.csv",
            index=False,
        )

    report = {
        "research_name":
            "RAYMOND V2.8 V5 WALK-FORWARD",

        "research_only":
            True,

        "live_trading_enabled":
            False,

        "canonical_execution_engine":
            True,

        "xauusd_contract_size":
            100.0,

        "starting_balance":
            STARTING_BALANCE,

        "total_grid_candidates":
            len(parameter_grid()),

        "max_candidates":
            args.max_candidates,

        "top_n_validation":
            args.top_n,

        "windows_requested":
            [
                window.name
                for window in windows
            ],

        "windows_completed":
            len(window_results),

        "windows_failed":
            len(failed_windows),

        "failed_windows":
            failed_windows,

        "wf3_wf4_test_overlap_warning":
            True,

        "window_results":
            window_results,
    }

    with open(
        output_root /
        "v5_walk_forward_report.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
            default=str,
        )

    # --------------------------------------------------------------
    # OVERALL SUMMARY
    # --------------------------------------------------------------

    lines = [
        "RAYMOND V2.8 - V5 WALK-FORWARD RESEARCH",
        "=" * 80,
        "",
        "ARCHITECTURE",
        "------------",
        "Canonical execution engine: YES",
        "Second independent simulator: NO",
        "Live broker execution: NO",
        "",
        "XAUUSD CONTRACT",
        "---------------",
        "1.00 lot = 100 oz",
        "$5 price movement at 0.02 lot = $10",
        "",
        "RESEARCH GRID",
        "-------------",
        f"Total candidates: "
        f"{len(parameter_grid()):,}",
        f"Quick candidate limit: "
        f"{args.max_candidates}",
        "",
        "WINDOW RESULTS",
        "--------------",
    ]

    if window_results:

        for result in window_results:

            lines.extend(
                [
                    "",
                    result["window"],
                    "-" * 40,
                    f"Strategy: "
                    f"{result['strategy_family']}",
                    f"Regime: "
                    f"{result['regime']}",
                    f"RR: "
                    f"{result['risk_reward']}",
                    f"Risk/trade: "
                    f"{result['risk_per_trade']}",
                    f"Test trades: "
                    f"{result['test_trades']}",
                    f"Test win rate: "
                    f"{result['test_win_rate_pct']:.4f}%",
                    f"Test net profit: "
                    f"{result['test_net_profit']:.4f}",
                    f"Test return: "
                    f"{result['test_return_pct']:.4f}%",
                    f"Test PF: "
                    f"{result['test_profit_factor']:.4f}",
                    f"Test expectancy: "
                    f"{result['test_expectancy']:.6f}",
                    f"Test max DD: "
                    f"{result['test_max_drawdown_pct']:.4f}%",
                    f"Validation -> Test return change: "
                    f"{result['return_change_percentage']:.4f}%",
                    f"Validation -> Test PF change: "
                    f"{result['profit_factor_change_percentage']:.4f}%",
                ]
            )

    else:

        lines.extend(
            [
                "",
                "NO WINDOWS COMPLETED.",
            ]
        )

    if failed_windows:

        lines.extend(
            [
                "",
                "FAILED WINDOWS",
                "---------------",
            ]
        )

        for failure in failed_windows:

            lines.append(
                f"{failure['window']}: "
                f"{failure['error']}"
            )

    lines.extend(
        [
            "",
            "IMPORTANT RESEARCH NOTE",
            "------------------------",
            "WF3 and WF4 use the same final test period:",
            "2026-04-01 through 2026-09-30.",
            "",
            "Therefore WF4 must not be counted as a",
            "fully independent additional holdout.",
            "",
            "NEXT RESEARCH REQUIREMENT",
            "--------------------------",
            "A full-data run should be completed before",
            "making strategy changes based on results.",
            "",
            "A quick run is only an integration test.",
        ]
    )

    with open(
        output_root /
        "summary.txt",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            "\n".join(
                lines
            )
        )

    # --------------------------------------------------------------
    # FINAL CONSOLE OUTPUT
    # --------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "V5 WALK-FORWARD COMPLETE"
    )
    print("=" * 80)

    print(
        f"Completed windows: "
        f"{len(window_results)}"
    )

    print(
        f"Failed windows: "
        f"{len(failed_windows)}"
    )

    print(
        f"Results directory: "
        f"{output_root}"
    )

    if failed_windows:

        print()
        print(
            "WARNING: One or more windows failed."
        )

    if args.max_candidates is not None:

        print()
        print(
            "This was a QUICK integration run."
        )

        print(
            "Do not use its performance as the final"
        )

        print(
            "V5 strategy result."
        )


if __name__ == "__main__":
    main()
