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

    numeric_columns = [
        "risk_per_trade",
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

    for column in numeric_columns:

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

    test_dd = safe_float(
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

    score += (
        math.copysign(
            math.log1p(
                abs(test_return)
            ),
            test_return,
        )
        * 20.0
    )

    score += (
        np.clip(
            test_pf - 1.0,
            -1.0,
            3.0,
        )
        * 20.0
    )

    score += (
        np.clip(
            test_expectancy,
            -2.0,
            2.0,
        )
        * 10.0
    )

    if trades >= 30:
        score += 10.0
    elif trades >= 15:
        score += 5.0

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

    average_dd = float(
        df[
            "test_max_dd_pct"
        ].mean()
    )

    worst_dd = float(
        df[
            "test_max_dd_pct"
        ].max()
    )

    average_degradation = float(
        df[
            "return_change_pct"
        ].mean()
    )

    # --------------------------------------------------------------
    # Strong robustness
    # --------------------------------------------------------------

    if (
        windows >= 3
        and profitable_return_rate >= 75.0
        and pf_rate >= 75.0
        and median_return > 0
        and worst_return > -10.0
        and worst_pf > 0.90
    ):

        classification = (
            "ROBUST"
        )

        reason = (
            "The strategy remains "
            "profitable across most unseen "
            "windows with generally stable "
            "profit factor and controlled "
            "drawdown."
        )

    # --------------------------------------------------------------
    # Promising
    # --------------------------------------------------------------

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
            "There is evidence of an edge, "
            "but the unseen-window sample "
            "is not strong enough to call "
            "the strategy robust."
        )

    # --------------------------------------------------------------
    # Unstable
    # --------------------------------------------------------------

    elif (
        average_pf > 1.0
        and median_return > 0
        and worst_return < -10.0
    ):

        classification = (
            "UNSTABLE"
        )

        reason = (
            "The strategy can make money, "
            "but performance varies too much "
            "between unseen periods."
        )

    else:

        classification = (
            "NOT_ROBUST"
        )

        reason = (
            "The current V5 configuration "
            "does not demonstrate a sufficiently "
            "stable unseen-market edge."
        )

    return {
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

        "average_return_degradation_pct":
            average_degradation,
    }


# ============================================================================
# STRATEGY FAMILY ANALYSIS
# ============================================================================

def analyze_strategy_families(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if (
        "strategy" not in df.columns
        or df.empty
    ):

        return pd.DataFrame()

    grouped = (
        df.groupby(
            "strategy",
            dropna=False,
        )
        .agg(
            windows=(
                "window",
                "count",
            ),

            average_return_pct=(
                "test_return_pct",
                "mean",
            ),

            median_return_pct=(
                "test_return_pct",
                "median",
            ),

            compounded_return_pct=(
                "test_return_pct",
                compound_returns,
            ),

            average_pf=(
                "test_profit_factor",
                "mean",
            ),

            worst_pf=(
                "test_profit_factor",
                "min",
            ),

            average_dd_pct=(
                "test_max_dd_pct",
                "mean",
            ),

            worst_dd_pct=(
                "test_max_dd_pct",
                "max",
            ),

            average_win_rate_pct=(
                "test_win_rate_pct",
                "mean",
            ),

            average_expectancy=(
                "test_expectancy",
                "mean",
            ),
        )
        .reset_index()
    )

    grouped[
        "positive_windows"
    ] = (
        df.groupby(
            "strategy"
        )[
            "test_return_pct"
        ]
        .apply(
            lambda values:
            int(
                (
                    values > 0
                ).sum()
            )
        )
        .values
    )

    grouped[
        "positive_window_pct"
    ] = (
        grouped[
            "positive_windows"
        ]
        /
        grouped[
            "windows"
        ]
        *
        100.0
    )

    grouped = (
        grouped.sort_values(
            [
                "positive_window_pct",
                "average_pf",
                "average_return_pct",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
        .reset_index(drop=True)
    )

    return grouped


# ============================================================================
# REGIME ANALYSIS
# ============================================================================

def analyze_regimes(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if (
        "regime" not in df.columns
        or df.empty
    ):

        return pd.DataFrame()

    grouped = (
        df.groupby(
            "regime",
            dropna=False,
        )
        .agg(
            windows=(
                "window",
                "count",
            ),

            average_return_pct=(
                "test_return_pct",
                "mean",
            ),

            median_return_pct=(
                "test_return_pct",
                "median",
            ),

            average_pf=(
                "test_profit_factor",
                "mean",
            ),

            worst_pf=(
                "test_profit_factor",
                "min",
            ),

            average_dd_pct=(
                "test_max_dd_pct",
                "mean",
            ),

            worst_dd_pct=(
                "test_max_dd_pct",
                "max",
            ),

            average_win_rate_pct=(
                "test_win_rate_pct",
                "mean",
            ),

            average_expectancy=(
                "test_expectancy",
                "mean",
            ),
        )
        .reset_index()
    )

    grouped[
        "positive_windows"
    ] = (
        df.groupby(
            "regime"
        )[
            "test_return_pct"
        ]
        .apply(
            lambda values:
            int(
                (
                    values > 0
                ).sum()
            )
        )
        .values
    )

    grouped[
        "positive_window_pct"
    ] = (
        grouped[
            "positive_windows"
        ]
        /
        grouped[
            "windows"
        ]
        *
        100.0
    )

    return (
        grouped.sort_values(
            [
                "positive_window_pct",
                "average_pf",
                "average_return_pct",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
        .reset_index(drop=True)
    )


# ============================================================================
# DEGRADATION ANALYSIS
# ============================================================================

def analyze_degradation(
    df: pd.DataFrame,
) -> Dict:

    degradation = (
        pd.to_numeric(
            df[
                "return_change_pct"
            ],
            errors="coerce",
        )
        .dropna()
    )

    if degradation.empty:

        return {
            "average_pct":
                0.0,

            "median_pct":
                0.0,

            "worst_pct":
                0.0,

            "best_pct":
                0.0,

            "windows_with_degradation":
                0,
        }

    return {
        "average_pct":
            float(
                degradation.mean()
            ),

        "median_pct":
            float(
                degradation.median()
            ),

        "worst_pct":
            float(
                degradation.min()
            ),

        "best_pct":
            float(
                degradation.max()
            ),

        "windows_with_degradation":
            int(
                (
                    degradation < 0
                ).sum()
            ),
    }


# ============================================================================
# RISK ANALYSIS
# ============================================================================

def analyze_risk(
    df: pd.DataFrame,
) -> Dict:

    if df.empty:

        return {}

    returns = (
        pd.to_numeric(
            df[
                "test_return_pct"
            ],
            errors="coerce",
        )
        .dropna()
    )

    drawdowns = (
        pd.to_numeric(
            df[
                "test_max_dd_pct"
            ],
            errors="coerce",
        )
        .dropna()
    )

    if returns.empty:

        return {}

    return {
        "average_return_pct":
            float(
                returns.mean()
            ),

        "return_std_pct":
            float(
                returns.std()
            )
            if len(returns) > 1
            else 0.0,

        "return_coefficient_of_variation":
            float(
                returns.std()
                /
                abs(returns.mean())
            )
            if abs(returns.mean()) > 1e-9
            else 0.0,

        "average_drawdown_pct":
            float(
                drawdowns.mean()
            )
            if not drawdowns.empty
            else 0.0,

        "worst_drawdown_pct":
            float(
                drawdowns.max()
            )
            if not drawdowns.empty
            else 0.0,

        "return_to_average_dd":
            float(
                returns.mean()
                /
                drawdowns.mean()
            )
            if (
                not drawdowns.empty
                and drawdowns.mean() > 0
            )
            else 0.0,
    }


# ============================================================================
# FINAL EQUITY SIMULATION
# ============================================================================

def simulate_sequential_equity(
    returns: pd.Series,
    starting_balance: float = 1000.0,
) -> Dict:

    balance = (
        starting_balance
    )

    peak = balance
    max_drawdown = 0.0

    equity_values = []

    for return_pct in returns:

        return_pct = safe_float(
            return_pct
        )

        balance *= (
            1.0 +
            return_pct / 100.0
        )

        peak = max(
            peak,
            balance,
        )

        drawdown = (
            (
                peak -
                balance
            )
            /
            peak
            *
            100.0
        )

        max_drawdown = max(
            max_drawdown,
            drawdown,
        )

        equity_values.append(
            balance
        )

    return {
        "starting_balance":
            starting_balance,

        "ending_balance":
            balance,

        "total_return_pct":
            (
                balance /
                starting_balance
                -
                1.0
            )
            * 100.0,

        "sequential_max_drawdown_pct":
            max_drawdown,

        "equity_curve":
            equity_values,
    }


# ============================================================================
# VERDICT
# ============================================================================

def build_verdict(
    classification: Dict,
    family_df: pd.DataFrame,
    regime_df: pd.DataFrame,
) -> Dict:

    classification_name = (
        classification.get(
            "classification",
            "UNKNOWN",
        )
    )

    if (
        classification_name
        == "ROBUST"
    ):

        verdict = (
            "V5 has passed the initial "
            "walk-forward robustness gate."
        )

        next_step = (
            "Proceed to deeper stress testing "
            "and Monte Carlo validation before "
            "any live-trading consideration."
        )

    elif (
        classification_name
        == "PROMISING_BUT_NEEDS_MORE_TESTING"
    ):

        verdict = (
            "V5 shows a potentially useful edge "
            "but has not yet demonstrated enough "
            "unseen-market stability."
        )

        next_step = (
            "Continue research with additional "
            "walk-forward windows, stress tests "
            "and parameter perturbation."
        )

    elif (
        classification_name
        == "UNSTABLE"
    ):

        verdict = (
            "V5 can work in some conditions but "
            "is not stable enough across regimes."
        )

        next_step = (
            "Improve regime/strategy selection "
            "before increasing risk or targeting "
            "aggressive compounding."
        )

    else:

        verdict = (
            "The current V5 research configuration "
            "does not demonstrate a reliable "
            "unseen-market edge."
        )

        next_step = (
            "Return to strategy-family and "
            "regime research rather than simply "
            "increasing risk."
        )

    best_family = None

    if (
        family_df is not None
        and not family_df.empty
    ):

        best_family = (
            family_df.iloc[0]
            .to_dict()
        )

    best_regime = None

    if (
        regime_df is not None
        and not regime_df.empty
    ):

        best_regime = (
            regime_df.iloc[0]
            .to_dict()
        )

    return {
        "classification":
            classification_name,

        "verdict":
            verdict,

        "recommended_next_step":
            next_step,

        "strongest_strategy_family":
            best_family,

        "strongest_regime":
            best_regime,
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Raymond V2.8 V5 robustness analyzer"
        )
    )

    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
    )

    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
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

    print("=" * 80)
    print(
        "RAYMOND V2.8 V5 ROBUSTNESS ANALYZER"
    )
    print("=" * 80)

    # --------------------------------------------------------------
    # LOAD
    # --------------------------------------------------------------

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

    # --------------------------------------------------------------
    # WINDOW SCORE
    # --------------------------------------------------------------

    df[
        "robustness_score"
    ] = df.apply(
        score_window,
        axis=1,
    )

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

    # --------------------------------------------------------------
    # CLASSIFICATION
    # --------------------------------------------------------------

    classification = (
        classify_robustness(
            df
        )
    )

    # --------------------------------------------------------------
    # STRATEGY FAMILIES
    # --------------------------------------------------------------

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

    # --------------------------------------------------------------
    # REGIMES
    # --------------------------------------------------------------

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

    # --------------------------------------------------------------
    # DEGRADATION
    # --------------------------------------------------------------

    degradation = (
        analyze_degradation(
            df
        )
    )

    # --------------------------------------------------------------
    # RISK
    # --------------------------------------------------------------

    risk = (
        analyze_risk(
            df
        )
    )

    # --------------------------------------------------------------
    # SEQUENTIAL EQUITY
    # --------------------------------------------------------------

    sequential = (
        simulate_sequential_equity(
            df[
                "test_return_pct"
            ]
        )
    )

    # --------------------------------------------------------------
    # VERDICT
    # --------------------------------------------------------------

    verdict = build_verdict(
        classification,
        family_df,
        regime_df,
    )

    # --------------------------------------------------------------
    # MASTER REPORT
    # --------------------------------------------------------------

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

    # --------------------------------------------------------------
    # HUMAN SUMMARY
    # --------------------------------------------------------------

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

    lines.append(
        f"Average DD: "
        f"{classification['average_test_drawdown_pct']:.2f}%"
    )

    lines.append(
        f"Worst DD: "
        f"{classification['worst_test_drawdown_pct']:.2f}%"
    )

    lines.append("")

    lines.append(
        "VALIDATION → UNSEEN DEGRADATION"
    )

    lines.append(
        "--------------------------------"
    )

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

    lines.append("")

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
            f"{best.get('strategy')}: "
            f"{best.get('average_return_pct', 0):.2f}% "
            f"average test return, "
            f"PF {best.get('average_pf', 0):.3f}"
        )

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
    # CONSOLE
    # --------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "ROBUSTNESS ANALYSIS COMPLETE"
    )
    print("=" * 80)

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
