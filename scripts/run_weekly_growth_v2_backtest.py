#!/usr/bin/env python3
from pathlib import Path
import sys
import json
import itertools
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_weekly_growth_backtest import (
    StrategyConfig,
    load_data,
    calculate_indicators,
    run_backtest,
    calculate_metrics,
)

INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "data/historical/xauusd_h1_2024_2026_normalized.csv"
)

OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
    "backtest_results/weekly_growth_v2"
)

GRID = {
    "risk_reward": [2.5, 3.0, 3.5, 4.0],
    "min_signal_score": [65, 70, 75, 80],
    "max_trades_per_week": [6, 8],
    "atr_stop_multiplier": [1.0, 1.2, 1.4],
}


def run(config_values, frame, starting_balance=1000.0):
    cfg = StrategyConfig(
        **{
            **config_values,
            "starting_balance": starting_balance,
        }
    )

    trades, weeks, end_balance = run_backtest(frame, cfg)

    return calculate_metrics(
        trades,
        weeks,
        starting_balance,
        end_balance,
        cfg,
    )


def candidate_score(metrics):
    profit_factor = metrics["profit_factor"] or 0.0

    return (
        metrics["total_return"]
        - 0.35 * abs(min(0.0, metrics["max_drawdown"]))
        + 0.03 * max(0.0, profit_factor - 1.0)
    )


def main():

    base_config = StrategyConfig()

    df = calculate_indicators(
        load_data(INPUT),
        base_config,
    )

    train = df[
        df["timestamp"] < pd.Timestamp(
            "2026-01-01",
            tz="UTC",
        )
    ].copy()

    validation = df[
        df["timestamp"] >= pd.Timestamp(
            "2026-01-01",
            tz="UTC",
        )
    ].copy()

    base = {
        "weekly_target": 0.25,
        "weekly_loss_limit": -0.09,
        "risk_per_trade": 0.03,
        "spread": 0.30,
        "slippage": 0.05,
        "min_atr_ratio": 0.70,
        "max_atr_ratio": 1.80,
    }

    candidates = []

    keys = list(GRID.keys())

    for values in itertools.product(
        *(GRID[key] for key in keys)
    ):

        params = dict(
            zip(keys, values)
        )

        config = {
            **base,
            **params,
        }

        train_metrics = run(
            config,
            train,
            1000.0,
        )

        if (
            train_metrics["total_return"] <= 0
            or
            (train_metrics["profit_factor"] or 0.0) <= 1.0
        ):
            continue

        validation_metrics = run(
            config,
            validation,
            1000.0,
        )

        candidates.append(
            {
                "params": params,

                "train_return_pct":
                    train_metrics["total_return_pct"],

                "train_profit_factor":
                    train_metrics["profit_factor"],

                "train_drawdown_pct":
                    train_metrics["max_drawdown_pct"],

                "validation_return_pct":
                    validation_metrics["total_return_pct"],

                "validation_profit_factor":
                    validation_metrics["profit_factor"],

                "validation_drawdown_pct":
                    validation_metrics["max_drawdown_pct"],

                "validation_win_rate_pct":
                    validation_metrics["win_rate_pct"],

                "validation_trades":
                    validation_metrics["total_trades"],
            }
        )

    if not candidates:
        raise SystemExit(
            "No profitable parameter combination "
            "passed the training filter."
        )

    for candidate in candidates:

        candidate["score"] = candidate_score(
            {
                "total_return":
                    candidate["validation_return_pct"],

                "max_drawdown":
                    candidate["validation_drawdown_pct"],

                "profit_factor":
                    candidate["validation_profit_factor"],
            }
        )

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    best = candidates[0]

    selected_config = {
        **base,
        **best["params"],
    }

    full_metrics = run(
        selected_config,
        df,
        1000.0,
    )

    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = {
        "status": "completed",
        "research_only": True,
        "live_trading": False,

        "method":
            "walk_forward_parameter_selection",

        "training_period":
            "2024-01-01 through 2025-12-31",

        "validation_period":
            "2026-01-01 onward",

        "candidates_tested":
            len(candidates),

        "selected":
            best,

        "full_period_metrics":
            full_metrics,
    }

    with open(
        OUT / "optimization.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            result,
            f,
            indent=2,
            default=str,
        )

    pd.DataFrame(
        candidates
    ).head(25).to_csv(
        OUT / "top_25_candidates.csv",
        index=False,
    )

    summary = f"""
RAYMOND V2.8 WEEKLY GROWTH V2
==============================

RESEARCH ONLY: YES
LIVE TRADING: NO

SELECTED PARAMETERS
-------------------
{best["params"]}

TRAINING PERIOD
---------------
2024-01-01 through 2025-12-31

Training return:
{best["train_return_pct"]:.2f}%

Training profit factor:
{best["train_profit_factor"]}

Training max drawdown:
{best["train_drawdown_pct"]:.2f}%

UNSEEN VALIDATION
-----------------
2026 onward

Validation return:
{best["validation_return_pct"]:.2f}%

Validation profit factor:
{best["validation_profit_factor"]}

Validation max drawdown:
{best["validation_drawdown_pct"]:.2f}%

Validation win rate:
{best["validation_win_rate_pct"]:.2f}%

Validation trades:
{best["validation_trades"]}

FULL PERIOD
-----------
Return:
{full_metrics["total_return_pct"]:.2f}%

Profit factor:
{full_metrics["profit_factor"]}

Win rate:
{full_metrics["win_rate_pct"]:.2f}%

Max drawdown:
{full_metrics["max_drawdown_pct"]:.2f}%

Trades:
{full_metrics["total_trades"]}
"""

    with open(
        OUT / "summary.txt",
        "w",
        encoding="utf-8",
    ) as f:

        f.write(summary)

    print(summary)


if __name__ == "__main__":
    main()
