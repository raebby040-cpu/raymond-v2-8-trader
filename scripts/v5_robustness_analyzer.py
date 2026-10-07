"""
RAYMOND V2.8 - V5 ROBUSTNESS ANALYZER
=====================================

STEP 6 OF V5 RESEARCH ARCHITECTURE

Reads V5 walk-forward results and produces a robustness report.

This is research only.

It does NOT:
    - place broker orders
    - connect to MT5
    - connect to Exness
    - enable live trading
    - modify strategy parameters

Purpose
-------
Determine whether V5 is genuinely robust across unseen periods.

Main questions
--------------
1. Are unseen test windows profitable?
2. Is profit factor consistently above 1?
3. How much does performance degrade from validation to test?
4. Is performance concentrated in one window?
5. Which strategy families survive unseen testing?
6. Which market regimes produce the edge?
7. Is drawdown acceptable?
8. Is the strategy stable enough for another research stage?

Important
---------
A high total return alone is NOT considered sufficient evidence.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd


# ============================================================================
# DEFAULTS
# ============================================================================

DEFAULT_INPUT = (
    "backtest_results/weekly_growth_v5/walk_forward"
)

DEFAULT_OUTPUT = (
    "backtest_results/weekly_growth_v5/robustness"
)


# ============================================================================
# HELPERS
# ============================================================================

def safe_float(
    value,
    default: float = 0.0,
) -> float:

    try:
        if value is None:
            return default

        value = float(value)

        if not math.isfinite(value):
            return default

        return value

    except (
        TypeError,
        ValueError,
    ):

        return default


def safe_optional_float(
    value,
):
    try:
        if value is None:
            return None

        value = float(value)

        if not math.isfinite(value):
            return None

        return value

    except (
        TypeError,
        ValueError,
    ):

        return None


def load_json(
    path: Path,
) -> Dict:

    if not path.exists():
        return {}

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


# ============================================================================
# WALK-FORWARD SUMMARY
# ============================================================================

def load_window_results(
    input_dir: Path,
) -> pd.DataFrame:

    path = (
        input_dir /
        "v5_walk_forward_windows.csv"
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Missing walk-forward file: {path}"
        )

    df = pd.read_csv(
        path
    )

    # ------------------------------------------------------------------------
    # SCHEMA COMPATIBILITY
    # ------------------------------------------------------------------------
    #
    # V5 walk-forward files have existed in more than one schema revision.
    #
    # Current names:
    #   test_max_drawdown_pct
    #   return_change_percentage
    #
    # Older names:
    #   test_max_dd_pct
    #   return_change_pct
    #
    # Normalize them into the canonical names used by this analyzer.
    # ------------------------------------------------------------------------

    aliases = {

        "test_max_dd_pct": [
            "test_max_dd_pct",
            "test_max_drawdown_pct",
            "test_max_drawdown",
        ],

        "return_change_pct": [
            "return_change_pct",
            "return_change_percentage",
        ],
    }

    for canonical, candidates in aliases.items():

        if canonical not in df.columns:

            for candidate in candidates:

                if candidate in df.columns:

                    df[canonical] = df[candidate]

                    break

    # ------------------------------------------------------------------------
    # REQUIRED COLUMN CHECK
    # ------------------------------------------------------------------------

    required_columns = [
        "test_return_pct",
        "test_profit_factor",
        "test_trades",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "Walk-forward results are missing required "
            f"columns: {missing}"
        )

    # ------------------------------------------------------------------------
    # OPTIONAL COLUMNS
    # ------------------------------------------------------------------------
    #
    # Do NOT invent measured drawdown if an old artifact genuinely lacks it.
    # NaN makes that limitation explicit.
    # ------------------------------------------------------------------------

    if "test_max_dd_pct" not in df.columns:

        df["test_max_dd_pct"] = np.nan

    if "return_change_pct" not in df.columns:

        df["return_change_pct"] = np.nan

    optional_numeric_columns = [
        "risk_per_trade",
        "risk_reward",
        "rr",
        "validation_return_pct",
        "test_return_pct",
        "test_trades",
        "test_win_rate_pct",
        "test_profit_factor",
        "test_max_dd_pct",
        "test_expectancy",
        "return_change_pct",
    ]

    for column in optional_numeric_columns:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    return df


# ============================================================================
# COMPOUNDED RETURN
# ============================================================================

def compound_returns(
    returns: pd.Series,
) -> float:
    """
    Compound sequential percentage returns.

    Example:
        +10%, +10%
        = 1.10 * 1.10 - 1
        = 21%
    """

    result = 1.0

    for value in returns:

        value = safe_float(
            value
        )

        result *= (
            1.0 +
            value / 100.0
        )

    return (
        result -
        1.0
    ) * 100.0


# ============================================================================
# WINDOW SCORE
# ============================================================================

def score_window(
    row: pd.Series,
) -> float:

    test_return = safe_float(
        row.get(
            "test_return_pct"
        )
    )

    test_pf = safe_float(
        row.get(
            "test_profit_factor"
        )
    )

    test_dd = safe_optional_float(
        row.get(
            "test_max_dd_pct"
        )
    )

    test_expectancy = safe_float(
        row.get(
            "test_expectancy"
        )
    )

    trades = int(
        safe_float(
            row.get(
                "test_trades"
            )
        )
    )

    score = 0.0

    # ------------------------------------------------------------------------
    # RETURN
    # ------------------------------------------------------------------------

    score += (
        math.copysign(
            math.log1p(
                abs(test_return)
            ),
            test_return,
        )
        * 20.0
    )

    # ------------------------------------------------------------------------
    # PROFIT FACTOR
    # ------------------------------------------------------------------------

    score += (
        np.clip(
            test_pf - 1.0,
            -1.0,
            3.0,
        )
        * 20.0
    )

    # ------------------------------------------------------------------------
    # EXPECTANCY
    # ------------------------------------------------------------------------

    score += (
        np.clip(
            test_expectancy,
            -2.0,
            2.0,
        )
        * 10.0
    )

    # ------------------------------------------------------------------------
    # SAMPLE SIZE
    # ------------------------------------------------------------------------

    if trades >= 30:

        score += 10.0

    elif trades >= 15:

        score += 5.0

    # ------------------------------------------------------------------------
    # DRAWDOWN
    # ------------------------------------------------------------------------

    # Only apply the DD penalty when measured DD is actually available.
    if test_dd is not None:

        score -= max(
            test_dd - 10.0,
            0.0,
        ) * 2.0

    return float(
        score
    )


# ============================================================================
# ROBUSTNESS CLASSIFICATION
# ============================================================================

def classify_robustness(
    df: pd.DataFrame,
) -> Dict:

    if df.empty:

        return {
            "classification":
                "INSUFFICIENT_DATA",

            "reason":
                "No walk-forward windows available.",
        }

    windows = len(df)

    positive = int(
        (
            df[
                "test_return_pct"
            ] > 0
        ).sum()
    )

    pf_above_one = int(
        (
            df[
                "test_profit_factor"
            ] > 1.0
        ).sum()
    )

    profitable_return_rate = (
        positive /
        windows *
        100.0
    )

    pf_rate = (
        pf_above_one /
        windows *
        100.0
    )

    median_return = float(
        df[
            "test_return_pct"
        ].median()
    )

    worst_return = float(
        df[
            "test_return_pct"
        ].min()
    )

    average_pf = float(
        df[
            "test_profit_factor"
        ].mean()
    )

    worst_pf = float(
        df[
            "test_profit_factor"
        ].min()
    )

    # ------------------------------------------------------------------------
    # DRAWDOWN
    # ------------------------------------------------------------------------

    dd_series = pd.to_numeric(
        df[
            "test_max_dd_pct"
        ],
        errors="coerce",
    )

    valid_dd = (
        dd_series
        .dropna()
    )

    if valid_dd.empty:

        average_dd = None
        worst_dd = None

    else:

        average_dd = float(
            valid_dd.mean()
        )

        worst_dd = float(
            valid_dd.max()
        )

    # ------------------------------------------------------------------------
    # DEGRADATION
    # ------------------------------------------------------------------------

    degradation_series = pd.to_numeric(
        df[
            "return_change_pct"
        ],
        errors="coerce",
    )

    valid_degradation = (
        degradation_series
        .dropna()
    )

    if valid_degradation.empty:

        average_degradation = None

    else:

        average_degradation = float(
            valid_degradation.mean()
        )

    # ------------------------------------------------------------------------
    # STRONG ROBUSTNESS
    # ------------------------------------------------------------------------

    strong_conditions = (
        windows >= 3
        and profitable_return_rate >= 75.0
        and pf_rate >= 75.0
        and median_return > 0
        and worst_return > -10.0
        and worst_pf > 0.90
    )

    if strong_conditions:

        classification = (
            "ROBUST"
        )

        reason = (
            "The unseen windows satisfy the primary "
            "robustness gates: consistent positive returns, "
            "profit factor above 1, positive median return, "
            "controlled worst-window loss, and acceptable "
            "worst-window profit factor."
        )

    # ------------------------------------------------------------------------
    # PROMISING
    # ------------------------------------------------------------------------

    elif (
        windows >= 2
        and profitable_return_rate >= 50.0
        and average_pf > 1.0
        and median_return > 0
    ):

        classification = (
            "PROMISING_BUT_NEEDS_MORE_TESTING"
        )

        reason = (
            "The unseen results show evidence of an edge, "
            "but the consistency or sample size is not "
            "strong enough for a robust classification."
        )

    # ------------------------------------------------------------------------
    # UNSTABLE
    # ------------------------------------------------------------------------

    elif (
        average_pf > 1.0
        and median_return > 0
        and worst_return < -10.0
    ):

        classification = (
            "UNSTABLE"
        )

        reason = (
            "Average performance is positive, but at least "
            "one unseen window experiences a materially large "
            "loss. The edge is therefore unstable."
        )

    # ------------------------------------------------------------------------
    # NOT ROBUST
    # ------------------------------------------------------------------------

    else:

        classification = (
            "NOT_ROBUST"
        )

        reason = (
            "The unseen-window results do not currently "
            "provide sufficient evidence of a stable edge."
        )

    result = {

        "classification":
            classification,

        "reason":
            reason,

        "windows":
            windows,

        "positive_windows":
            positive,

        "positive_window_pct":
            profitable_return_rate,

        "pf_above_one_windows":
            pf_above_one,

        "pf_above_one_pct":
            pf_rate,

        "median_test_return_pct":
            median_return,

        "worst_test_return_pct":
            worst_return,

        "average_test_profit_factor":
            average_pf,

        "worst_test_profit_factor":
            worst_pf,

        "average_test_drawdown_pct":
            average_dd,

        "worst_test_drawdown_pct":
            worst_dd,

        "average_return_change_pct":
            average_degradation,
    }

    return result


# ============================================================================
# STRATEGY FAMILY ANALYSIS
# ============================================================================

def analyze_strategy_families(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if "strategy_family" not in df.columns:

        return pd.DataFrame()

    rows: List[Dict] = []

    for strategy, group in df.groupby(
        "strategy_family"
    ):

        returns = pd.to_numeric(
            group[
                "test_return_pct"
            ],
            errors="coerce",
        ).dropna()

        pf = pd.to_numeric(
            group[
                "test_profit_factor"
            ],
            errors="coerce",
        ).dropna()

        positive_windows = int(
            (
                returns > 0
            ).sum()
        )

        window_count = len(
            group
        )

        rows.append({

            "strategy_family":
                strategy,

            "windows":
                window_count,

            "positive_windows":
                positive_windows,

            "positive_window_pct":
                (
                    positive_windows /
                    window_count *
                    100.0
                )
                if window_count
                else 0.0,

            "average_return_pct":
                float(
                    returns.mean()
                )
                if not returns.empty
                else 0.0,

            "median_return_pct":
                float(
                    returns.median()
                )
                if not returns.empty
                else 0.0,

            "worst_return_pct":
                float(
                    returns.min()
                )
                if not returns.empty
                else 0.0,

            "average_pf":
                float(
                    pf.mean()
                )
                if not pf.empty
                else 0.0,

            "worst_pf":
                float(
                    pf.min()
                )
                if not pf.empty
                else 0.0,
        })

    result = pd.DataFrame(
        rows
    )

    if not result.empty:

        result = result.sort_values(
            [
                "average_return_pct",
                "average_pf",
            ],
            ascending=False,
        )

    return result


# ============================================================================
# REGIME ANALYSIS
# ============================================================================

def analyze_regimes(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if "regime" not in df.columns:

        return pd.DataFrame()

    rows: List[Dict] = []

    for regime, group in df.groupby(
        "regime"
    ):

        returns = pd.to_numeric(
            group[
                "test_return_pct"
            ],
            errors="coerce",
        ).dropna()

        pf = pd.to_numeric(
            group[
                "test_profit_factor"
            ],
            errors="coerce",
        ).dropna()

        positive_windows = int(
            (
                returns > 0
            ).sum()
        )

        window_count = len(
            group
        )

        rows.append({

            "regime":
                regime,

            "windows":
                window_count,

            "positive_windows":
                positive_windows,

            "positive_window_pct":
                (
                    positive_windows /
                    window_count *
                    100.0
                )
                if window_count
                else 0.0,

            "average_return_pct":
                float(
                    returns.mean()
                )
                if not returns.empty
                else 0.0,

            "median_return_pct":
                float(
                    returns.median()
                )
                if not returns.empty
                else 0.0,

            "worst_return_pct":
                float(
                    returns.min()
                )
                if not returns.empty
                else 0.0,

            "average_pf":
                float(
                    pf.mean()
                )
                if not pf.empty
                else 0.0,

            "worst_pf":
                float(
                    pf.min()
                )
                if not pf.empty
                else 0.0,
        })

    result = pd.DataFrame(
        rows
    )

    if not result.empty:

        result = result.sort_values(
            [
                "average_return_pct",
                "average_pf",
            ],
            ascending=False,
        )

    return result


# ============================================================================
# DEGRADATION ANALYSIS
# ============================================================================

def analyze_degradation(
    df: pd.DataFrame,
) -> Dict:

    series = pd.to_numeric(
        df[
            "return_change_pct"
        ],
        errors="coerce",
    ).dropna()

    if series.empty:

        return {

            "available":
                False,

            "average_pct":
                None,

            "median_pct":
                None,

            "worst_pct":
                None,

            "windows_with_degradation":
                0,

            "reason":
                "No validation-to-test degradation field "
                "was available in the walk-forward artifact.",
        }

    return {

        "available":
            True,

        "average_pct":
            float(
                series.mean()
            ),

        "median_pct":
            float(
                series.median()
            ),

        "worst_pct":
            float(
                series.min()
            ),

        "windows_with_degradation":
            int(
                (
                    series < 0
                ).sum()
            ),

        "reason":
            "Validation-to-test return changes were available "
            "and analyzed.",
    }


# ============================================================================
# RISK ANALYSIS
# ============================================================================

def analyze_risk(
    df: pd.DataFrame,
) -> Dict:

    dd = pd.to_numeric(
        df[
            "test_max_dd_pct"
        ],
        errors="coerce",
    ).dropna()

    returns = pd.to_numeric(
        df[
            "test_return_pct"
        ],
        errors="coerce",
    ).dropna()

    if dd.empty:

        return {

            "drawdown_available":
                False,

            "average_drawdown_pct":
                None,

            "worst_drawdown_pct":
                None,

            "drawdown_reason":
                "The walk-forward artifact did not contain "
                "a measured test drawdown field.",
        }

    return {

        "drawdown_available":
            True,

        "average_drawdown_pct":
            float(
                dd.mean()
            ),

        "worst_drawdown_pct":
            float(
                dd.max()
            ),

        "return_std_pct":
            float(
                returns.std()
            )
            if len(returns) > 1
            else 0.0,

        "drawdown_reason":
            "Measured test drawdown was available.",
    }


# ============================================================================
# SEQUENTIAL EQUITY
# ============================================================================

def simulate_sequential_equity(
    returns: pd.Series,
    starting_balance: float = 1000.0,
) -> Dict:

    balance = float(
        starting_balance
    )

    peak = balance
    max_drawdown_pct = 0.0

    equity_points = []

    for value in returns:

        value = safe_float(
            value
        )

        balance *= (
            1.0 +
            value / 100.0
        )

        peak = max(
            peak,
            balance,
        )

        # --------------------------------------------------------------------
        # FIX:
        # The conditional expression must include the condition BEFORE
        # the "else" branch and the whole expression must be enclosed.
        # --------------------------------------------------------------------

        drawdown_pct = (
            (
                peak -
                balance
            )
            /
            peak *
            100.0
            if peak > 0
            else 0.0
        )

        max_drawdown_pct = max(
            max_drawdown_pct,
            drawdown_pct,
        )

        equity_points.append(
            balance
        )

    total_return_pct = (
        (
            balance -
            starting_balance
        )
        /
        starting_balance *
        100.0
    )

    return {

        "starting_balance":
            starting_balance,

        "ending_balance":
            balance,

        "total_return_pct":
            total_return_pct,

        "sequential_max_drawdown_pct":
            max_drawdown_pct,

        "windows_processed":
            len(equity_points),

        "equity_points":
            equity_points,
    }


# ============================================================================
# FINAL VERDICT
# ============================================================================

def build_verdict(
    classification: Dict,
    family_df: pd.DataFrame,
    regime_df: pd.DataFrame,
) -> Dict:

    classification_name = (
        classification[
            "classification"
        ]
    )

    strongest_strategy_family = None

    if (
        family_df is not None
        and not family_df.empty
    ):

        strongest_strategy_family = (
            family_df.iloc[0].to_dict()
        )

    strongest_regime = None

    if (
        regime_df is not None
        and not regime_df.empty
    ):

        strongest_regime = (
            regime_df.iloc[0].to_dict()
        )

    if classification_name == "ROBUST":

        verdict = (
            "V5 ROBUSTNESS GATE PASSED"
        )

        next_step = (
            "Proceed to deeper validation: full-resolution "
            "research, additional walk-forward testing, "
            "stress testing, Monte Carlo analysis, and "
            "parameter sensitivity testing. Do not enable "
            "live trading solely from this result."
        )

    elif classification_name == "PROMISING_BUT_NEEDS_MORE_TESTING":

        verdict = (
            "V5 SHOWS PROMISING EVIDENCE BUT IS NOT YET ROBUST"
        )

        next_step = (
            "Run the full V5 research pipeline and expand "
            "unseen testing before changing strategy logic. "
            "Investigate which strategy families and regimes "
            "remain positive."
        )

    elif classification_name == "UNSTABLE":

        verdict = (
            "V5 HAS AN UNSTABLE EDGE"
        )

        next_step = (
            "Do not advance to live trading. Investigate "
            "regime dependency, drawdown concentration, "
            "strategy-family stability, and validation-to-test "
            "degradation before further optimization."
        )

    else:

        verdict = (
            "V5 DOES NOT YET HAVE A VALIDATED ROBUST EDGE"
        )

        next_step = (
            "Do not enable live trading. Complete the full "
            "research run and analyze strategy families, "
            "regimes, parameter sensitivity, and unseen "
            "walk-forward performance before modifying the "
            "strategy."
        )

    return {

        "verdict":
            verdict,

        "classification":
            classification_name,

        "recommended_next_step":
            next_step,

        "strongest_strategy_family":
            strongest_strategy_family,

        "strongest_regime":
            strongest_regime,
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Analyze V5 walk-forward robustness."
        )
    )

    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=(
            "Walk-forward result directory."
        ),
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=(
            "Robustness output directory."
        ),
    )

    args = parser.parse_args()

    input_dir = Path(
        args.input
    )

    output_dir = Path(
        args.output
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "RAYMOND V2.8 V5 ROBUSTNESS ANALYZER"
    )

    print(
        "===================================="
    )

    print(
        f"Input: {input_dir}"
    )

    print(
        f"Output: {output_dir}"
    )

    print()

    # ------------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------------

    df = load_window_results(
        input_dir
    )

    print(
        f"Walk-forward windows: "
        f"{len(df)}"
    )

    if df.empty:

        raise SystemExit(
            "No walk-forward results found."
        )

    # ------------------------------------------------------------------------
    # WINDOW SCORE
    # ------------------------------------------------------------------------

    df[
        "robustness_score"
    ] = df.apply(
        score_window,
        axis=1,
    )

    if "window" in df.columns:

        df = (
            df.sort_values(
                "window"
            )
            .reset_index(
                drop=True
            )
        )

    df.to_csv(
        output_dir /
        "scored_walk_forward_windows.csv",
        index=False,
    )

    # ------------------------------------------------------------------------
    # CLASSIFICATION
    # ------------------------------------------------------------------------

    classification = (
        classify_robustness(
            df
        )
    )

    # ------------------------------------------------------------------------
    # STRATEGY FAMILIES
    # ------------------------------------------------------------------------

    family_df = (
        analyze_strategy_families(
            df
        )
    )

    if not family_df.empty:

        family_df.to_csv(
            output_dir /
            "strategy_family_analysis.csv",
            index=False,
        )

    # ------------------------------------------------------------------------
    # REGIMES
    # ------------------------------------------------------------------------

    regime_df = (
        analyze_regimes(
            df
        )
    )

    if not regime_df.empty:

        regime_df.to_csv(
            output_dir /
            "regime_analysis.csv",
            index=False,
        )

    # ------------------------------------------------------------------------
    # DEGRADATION
    # ------------------------------------------------------------------------

    degradation = (
        analyze_degradation(
            df
        )
    )

    # ------------------------------------------------------------------------
    # RISK
    # ------------------------------------------------------------------------

    risk = (
        analyze_risk(
            df
        )
    )

    # ------------------------------------------------------------------------
    # SEQUENTIAL EQUITY
    # ------------------------------------------------------------------------

    sequential = (
        simulate_sequential_equity(
            df[
                "test_return_pct"
            ]
        )
    )

    # ------------------------------------------------------------------------
    # VERDICT
    # ------------------------------------------------------------------------

    verdict = build_verdict(
        classification,
        family_df,
        regime_df,
    )

    # ------------------------------------------------------------------------
    # MASTER REPORT
    # ------------------------------------------------------------------------

    report = {

        "status":
            "completed",

        "classification":
            classification,

        "degradation":
            degradation,

        "risk":
            risk,

        "sequential_equity":
            sequential,

        "verdict":
            verdict,

        "windows":
            df.to_dict(
                orient="records"
            ),
    }

    with open(
        output_dir /
        "v5_robustness_report.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
            default=str,
        )

    # ------------------------------------------------------------------------
    # HUMAN SUMMARY
    # ------------------------------------------------------------------------

    lines = []

    lines.append(
        "RAYMOND V2.8 V5 ROBUSTNESS REPORT"
    )

    lines.append(
        "=" * 80
    )

    lines.append("")

    lines.append(
        f"CLASSIFICATION: "
        f"{classification['classification']}"
    )

    lines.append("")

    lines.append(
        classification[
            "reason"
        ]
    )

    lines.append("")

    lines.append(
        "UNSEEN WINDOW STATISTICS"
    )

    lines.append(
        "-------------------------"
    )

    lines.append(
        f"Windows: "
        f"{classification['windows']}"
    )

    lines.append(
        f"Positive windows: "
        f"{classification['positive_windows']}"
    )

    lines.append(
        f"Positive window rate: "
        f"{classification['positive_window_pct']:.2f}%"
    )

    lines.append(
        f"PF > 1 windows: "
        f"{classification['pf_above_one_windows']}"
    )

    lines.append(
        f"PF > 1 rate: "
        f"{classification['pf_above_one_pct']:.2f}%"
    )

    lines.append(
        f"Median test return: "
        f"{classification['median_test_return_pct']:.2f}%"
    )

    lines.append(
        f"Worst test return: "
        f"{classification['worst_test_return_pct']:.2f}%"
    )

    lines.append(
        f"Average test PF: "
        f"{classification['average_test_profit_factor']:.3f}"
    )

    lines.append(
        f"Worst test PF: "
        f"{classification['worst_test_profit_factor']:.3f}"
    )

    if (
        classification[
            "average_test_drawdown_pct"
        ]
        is None
    ):

        lines.append(
            "Average DD: unavailable"
        )

    else:

        lines.append(
            f"Average DD: "
            f"{classification['average_test_drawdown_pct']:.2f}%"
        )

    if (
        classification[
            "worst_test_drawdown_pct"
        ]
        is None
    ):

        lines.append(
            "Worst DD: unavailable"
        )

    else:

        lines.append(
            f"Worst DD: "
            f"{classification['worst_test_drawdown_pct']:.2f}%"
        )

    lines.append("")

    # ------------------------------------------------------------------------
    # VALIDATION → UNSEEN DEGRADATION
    # ------------------------------------------------------------------------

    lines.append(
        "VALIDATION → UNSEEN DEGRADATION"
    )

    lines.append(
        "--------------------------------"
    )

    if degradation[
        "available"
    ]:

        lines.append(
            f"Average return change: "
            f"{degradation['average_pct']:.2f}%"
        )

        lines.append(
            f"Median return change: "
            f"{degradation['median_pct']:.2f}%"
        )

        lines.append(
            f"Worst return change: "
            f"{degradation['worst_pct']:.2f}%"
        )

        lines.append(
            f"Windows with degradation: "
            f"{degradation['windows_with_degradation']}"
        )

    else:

        lines.append(
            "Validation-to-test degradation: unavailable"
        )

    lines.append("")

    # ------------------------------------------------------------------------
    # SEQUENTIAL EQUITY
    # ------------------------------------------------------------------------

    lines.append(
        "SEQUENTIAL EQUITY"
    )

    lines.append(
        "-----------------"
    )

    lines.append(
        f"Starting balance: "
        f"${sequential['starting_balance']:.2f}"
    )

    lines.append(
        f"Ending balance: "
        f"${sequential['ending_balance']:.2f}"
    )

    lines.append(
        f"Sequential return: "
        f"{sequential['total_return_pct']:.2f}%"
    )

    lines.append(
        f"Sequential max DD: "
        f"{sequential['sequential_max_drawdown_pct']:.2f}%"
    )

    lines.append("")

    # ------------------------------------------------------------------------
    # VERDICT
    # ------------------------------------------------------------------------

    lines.append(
        "VERDICT"
    )

    lines.append(
        "-------"
    )

    lines.append(
        verdict[
            "verdict"
        ]
    )

    lines.append("")

    lines.append(
        "NEXT STEP"
    )

    lines.append(
        "---------"
    )

    lines.append(
        verdict[
            "recommended_next_step"
        ]
    )

    # ------------------------------------------------------------------------
    # STRONGEST STRATEGY
    # ------------------------------------------------------------------------

    if (
        verdict[
            "strongest_strategy_family"
        ]
        is not None
    ):

        best = verdict[
            "strongest_strategy_family"
        ]

        lines.append("")

        lines.append(
            "STRONGEST STRATEGY FAMILY"
        )

        lines.append(
            f"{best.get('strategy_family')}: "
            f"{best.get('average_return_pct', 0):.2f}% "
            f"average test return, "
            f"PF {best.get('average_pf', 0):.3f}"
        )

    # ------------------------------------------------------------------------
    # STRONGEST REGIME
    # ------------------------------------------------------------------------

    if (
        verdict[
            "strongest_regime"
        ]
        is not None
    ):

        best = verdict[
            "strongest_regime"
        ]

        lines.append("")

        lines.append(
            "STRONGEST REGIME"
        )

        lines.append(
            f"{best.get('regime')}: "
            f"{best.get('average_return_pct', 0):.2f}% "
            f"average test return, "
            f"PF {best.get('average_pf', 0):.3f}"
        )

    lines.append("")

    lines.append(
        "IMPORTANT:"
    )

    lines.append(
        "A large historical return is not enough "
        "to establish robustness."
    )

    lines.append(
        "Unseen-window consistency, drawdown, "
        "profit factor and degradation are "
        "the primary research gates."
    )

    # ------------------------------------------------------------------------
    # WRITE SUMMARY
    # ------------------------------------------------------------------------

    with open(
        output_dir /
        "summary.txt",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            "\n".join(
                lines
            )
        )

    # ------------------------------------------------------------------------
    # CONSOLE
    # ------------------------------------------------------------------------

    print()

    print(
        "=" * 80
    )

    print(
        "ROBUSTNESS ANALYSIS COMPLETE"
    )

    print(
        "=" * 80
    )

    print(
        f"Classification: "
        f"{classification['classification']}"
    )

    print(
        f"Positive unseen windows: "
        f"{classification['positive_window_pct']:.2f}%"
    )

    print(
        f"Average unseen PF: "
        f"{classification['average_test_profit_factor']:.3f}"
    )

    print(
        f"Worst unseen return: "
        f"{classification['worst_test_return_pct']:.2f}%"
    )

    print(
        f"Sequential return: "
        f"{sequential['total_return_pct']:.2f}%"
    )

    print(
        f"Sequential max DD: "
        f"{sequential['sequential_max_drawdown_pct']:.2f}%"
    )

    print()

    print(
        f"Results saved to: "
        f"{output_dir}"
    )


if __name__ == "__main__":

    main()
