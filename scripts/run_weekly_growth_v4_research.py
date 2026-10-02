#!/usr/bin/env python3

"""RAYMOND V2.8 Weekly Growth V4 research.

Research only.
Uses real H1 + M15 + M5 data.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


import run_weekly_growth_v3_research as v3

from run_weekly_growth_backtest import (
    StrategyConfig,
    calculate_indicators,
    calculate_metrics,
)


# ============================================================
# PATHS
# ============================================================

H1 = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(
        "data/historical/"
        "xauusd_h1_2024_2026_normalized.csv"
    )
)

M15 = (
    Path(sys.argv[2])
    if len(sys.argv) > 2
    else Path(
        "data/historical/"
        "xauusd_m15_2024_2026_normalized.csv"
    )
)

M5 = (
    Path(sys.argv[3])
    if len(sys.argv) > 3
    else Path(
        "data/historical/"
        "xauusd_m5_2024_2026_normalized.csv"
    )
)

OUT = (
    Path(sys.argv[4])
    if len(sys.argv) > 4
    else Path(
        "backtest_results/weekly_growth_v4"
    )
)


# ============================================================
# V4 GRID
# ============================================================

GRID = {

    "risk_reward": [
        2.5,
        3.0,
        3.5,
        4.0,
    ],

    "min_signal_score": [
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

    "lower_confirmation": [
        "both",
        "m15",
        "m5",
    ],

    "thesis_exit": [
        False,
        True,
    ],
}


# ============================================================
# BASE SETTINGS
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
# LOAD OHLC
# ============================================================

def load_ohlc(path: Path) -> pd.DataFrame:

    if not path.exists():

        raise SystemExit(
            f"Required data file not found: {path}"
        )


    df = pd.read_csv(path)


    rename = {}


    for column in df.columns:

        name = str(column).strip().lower()


        if name in {
            "date",
            "datetime",
            "time",
            "timestamp",
        }:

            rename[column] = "timestamp"


        elif name in {
            "open",
            "o",
        }:

            rename[column] = "open"


        elif name in {
            "high",
            "h",
        }:

            rename[column] = "high"


        elif name in {
            "low",
            "l",
        }:

            rename[column] = "low"


        elif name in {
            "close",
            "c",
        }:

            rename[column] = "close"


        elif name in {
            "volume",
            "vol",
            "tick_volume",
        }:

            rename[column] = "volume"


    df = df.rename(
        columns=rename
    )


    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    }


    missing = (
        required
        - set(df.columns)
    )


    if missing:

        raise SystemExit(
            f"{path}: missing columns "
            f"{sorted(missing)}"
        )


    raw_timestamp = df["timestamp"]


    # Dukascopy numeric timestamps are
    # milliseconds since Unix epoch.

    if pd.api.types.is_numeric_dtype(
        raw_timestamp
    ):

        df["timestamp"] = pd.to_datetime(
            pd.to_numeric(
                raw_timestamp,
                errors="coerce",
            ),
            unit="ms",
            utc=True,
            errors="coerce",
        )

    else:

        df["timestamp"] = pd.to_datetime(
            raw_timestamp,
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


    if "volume" not in df.columns:

        df["volume"] = 0.0


    df = df.dropna(
        subset=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
        ]
    )


    df = (
        df.sort_values("timestamp")
        .drop_duplicates(
            "timestamp",
            keep="last",
        )
        .reset_index(drop=True)
    )


    if len(df) < 300:

        raise SystemExit(
            f"{path}: only {len(df)} rows. "
            "At least 300 are required."
        )


    return df


# ============================================================
# LOWER-TIMEFRAME FEATURES
# ============================================================

def lower_features(
    df: pd.DataFrame,
) -> pd.DataFrame:

    x = (
        df.copy()
        .set_index("timestamp")
    )


    x["ema20"] = (
        x["close"]
        .ewm(
            span=20,
            adjust=False,
        )
        .mean()
    )


    x["ema50"] = (
        x["close"]
        .ewm(
            span=50,
            adjust=False,
        )
        .mean()
    )


    delta = x["close"].diff()


    gain = (
        delta
        .clip(lower=0)
        .ewm(
            alpha=1 / 14,
            adjust=False,
        )
        .mean()
    )


    loss = (
        -delta
        .clip(upper=0)
        .ewm(
            alpha=1 / 14,
            adjust=False,
        )
        .mean()
    )


    rs = (
        gain
        / loss.replace(
            0,
            np.nan,
        )
    )


    x["rsi14"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )


    x["bull_candle"] = (
        x["close"]
        > x["open"]
    )


    x["bear_candle"] = (
        x["close"]
        < x["open"]
    )


    x = x.reset_index()


    return x[
        [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "ema20",
            "ema50",
            "rsi14",
            "bull_candle",
            "bear_candle",
        ]
    ]


# ============================================================
# BUILD LOWER-TIMEFRAME CONFIRMATION
# ============================================================

def build_confirmation(
    h1: pd.DataFrame,
    m15: pd.DataFrame,
    m5: pd.DataFrame,
) -> pd.DataFrame:

    m15_features = lower_features(
        m15
    )


    m5_features = lower_features(
        m5
    )


    m15_features = (
        m15_features.rename(
            columns={
                column: f"m15_{column}"
                for column
                in m15_features.columns
                if column != "timestamp"
            }
        )
    )


    m5_features = (
        m5_features.rename(
            columns={
                column: f"m5_{column}"
                for column
                in m5_features.columns
                if column != "timestamp"
            }
        )
    )


    output = h1[
        ["timestamp"]
    ].copy()


    # H1 candle timestamp is the candle open.
    # Signal is generated only after the H1 candle closes.
    #
    # Therefore we inspect lower-TF information
    # through the end of that H1 candle.

    output["lookup_time"] = (
        output["timestamp"]
        + pd.Timedelta(
            minutes=59,
            seconds=59,
        )
    )


    output = output.sort_values(
        "lookup_time"
    )


    output = pd.merge_asof(
        output,

        m15_features.sort_values(
            "timestamp"
        ),

        left_on="lookup_time",

        right_on="timestamp",

        direction="backward",
    )


    output = (
        output.drop(
            columns=["timestamp_y"]
        )
        .rename(
            columns={
                "timestamp_x":
                "timestamp"
            }
        )
    )


    output = pd.merge_asof(
        output.sort_values(
            "lookup_time"
        ),

        m5_features.sort_values(
            "timestamp"
        ),

        left_on="lookup_time",

        right_on="timestamp",

        direction="backward",
    )


    output = (
        output.drop(
            columns=["timestamp_y"]
        )
        .rename(
            columns={
                "timestamp_x":
                "timestamp"
            }
        )
    )


    return output.drop(
        columns=["lookup_time"]
    )


# ============================================================
# LOWER-TIMEFRAME CONFIRMATION
# ============================================================

def confirmation(
    row: pd.Series,
    direction: str,
    mode: str,
) -> bool:

    def timeframe_ok(
        prefix: str,
        buy: bool,
    ) -> bool:

        close = row.get(
            f"{prefix}_close"
        )

        ema20 = row.get(
            f"{prefix}_ema20"
        )

        ema50 = row.get(
            f"{prefix}_ema50"
        )

        rsi = row.get(
            f"{prefix}_rsi14"
        )


        candle_key = (
            f"{prefix}_bull_candle"
            if buy
            else
            f"{prefix}_bear_candle"
        )


        candle = row.get(
            candle_key
        )


        values = [
            close,
            ema20,
            ema50,
            rsi,
            candle,
        ]


        if any(
            pd.isna(value)
            for value in values
        ):

            return False


        if buy:

            return bool(
                close > ema20
                and ema20 > ema50
                and 52 <= rsi <= 75
                and candle
            )


        return bool(
            close < ema20
            and ema20 < ema50
            and 25 <= rsi <= 48
            and candle
        )


    buy = (
        direction == "BUY"
    )


    m15_ok = timeframe_ok(
        "m15",
        buy,
    )


    m5_ok = timeframe_ok(
        "m5",
        buy,
    )


    if mode == "both":

        return (
            m15_ok
            and m5_ok
        )


    if mode == "m15":

        return m15_ok


    if mode == "m5":

        return m5_ok


    return True


# ============================================================
# RUN ONE V4 VARIANT
# ============================================================

def run_variant(
    frame: pd.DataFrame,
    config: Dict,
    protection: str,
    confirm_mode: str,
    thesis_exit: bool,
):

    original_score = (
        v3.score_signal
    )


    original_exit = (
        v3.determine_exit
    )


    def filtered_score(
        row,
        cfg,
    ):

        direction, score, reason = (
            original_score(
                row,
                cfg,
            )
        )


        if direction in {
            "BUY",
            "SELL",
        }:

            confirmed = confirmation(
                row,
                direction,
                confirm_mode,
            )


            if not confirmed:

                return (
                    "WAIT",
                    score,
                    "lower_tf_confirmation_failed",
                )


            reason = (
                reason
                + "|lower_tf_"
                + confirm_mode
                + "_confirmed"
            )


        return (
            direction,
            score,
            reason,
        )


    def exit_with_thesis(
        position,
        candle,
        cfg,
    ):

        result = (
            original_exit(
                position,
                candle,
                cfg,
            )
        )


        if result is not None:

            return result


        if not thesis_exit:

            return None


        close = float(
            candle["close"]
        )


        ema50 = float(
            candle["ema50"]
        )


        trend = str(
            candle.get(
                "trend",
                "NEUTRAL",
            )
        )


        if (
            position.direction
            == "BUY"
            and close < ema50
            and trend == "BEAR"
        ):

            return (
                close,
                "THESIS_EXIT",
            )


        if (
            position.direction
            == "SELL"
            and close > ema50
            and trend == "BULL"
        ):

            return (
                close,
                "THESIS_EXIT",
            )


        return None


    v3.score_signal = (
        filtered_score
    )


    v3.determine_exit = (
        exit_with_thesis
    )


    try:

        cfg = StrategyConfig(
            **config,
            starting_balance=1000.0,
        )


        (
            trades,
            weeks,
            end_balance,
        ) = v3.run_backtest_v3(
            frame,
            cfg,
            protection,
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


    finally:

        v3.score_signal = (
            original_score
        )

        v3.determine_exit = (
            original_exit
        )


# ============================================================
# SELECTION SCORE
# ============================================================

def selection_score(
    metrics: Dict,
) -> float:

    profit_factor = (
        metrics.get(
            "profit_factor"
        )
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
# MAIN
# ============================================================

def main():

    print(
        "RAYMOND V2.8 WEEKLY GROWTH V4"
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


    # --------------------------------------------------------
    # LOAD H1
    # --------------------------------------------------------

    h1_raw = load_ohlc(
        H1
    )


    # --------------------------------------------------------
    # LOAD M15
    # --------------------------------------------------------

    m15_raw = load_ohlc(
        M15
    )


    # --------------------------------------------------------
    # LOAD M5
    # --------------------------------------------------------

    m5_raw = load_ohlc(
        M5
    )


    print(
        f"H1 rows: {len(h1_raw):,}"
    )

    print(
        f"M15 rows: {len(m15_raw):,}"
    )

    print(
        f"M5 rows: {len(m5_raw):,}"
    )

    print()


    # --------------------------------------------------------
    # H1 INDICATORS
    # --------------------------------------------------------

    h1 = calculate_indicators(
        h1_raw,
        StrategyConfig(),
    )


    # --------------------------------------------------------
    # LOWER-TIMEFRAME FEATURES
    # --------------------------------------------------------

    confirmation_frame = (
        build_confirmation(
            h1,
            m15_raw,
            m5_raw,
        )
    )


    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    frame = h1.merge(
        confirmation_frame,
        on="timestamp",
        how="left",
        suffixes=(
            "",
            "_confirmation",
        ),
    )


    for column in confirmation_frame.columns:

        if column == "timestamp":

            continue


        frame[column] = (
            confirmation_frame[column]
        )


    # --------------------------------------------------------
    # SPLITS
    # --------------------------------------------------------

    train = frame[
        (
            frame["timestamp"]
            >= pd.Timestamp(
                "2024-01-01",
                tz="UTC",
            )
        )
        &
        (
            frame["timestamp"]
            < pd.Timestamp(
                "2025-01-01",
                tz="UTC",
            )
        )
    ].copy()


    selection = frame[
        (
            frame["timestamp"]
            >= pd.Timestamp(
                "2025-01-01",
                tz="UTC",
            )
        )
        &
        (
            frame["timestamp"]
            < pd.Timestamp(
                "2026-01-01",
                tz="UTC",
            )
        )
    ].copy()


    holdout = frame[
        frame["timestamp"]
        >= pd.Timestamp(
            "2026-01-01",
            tz="UTC",
        )
    ].copy()


    print(
        f"2024 development H1 candles: "
        f"{len(train):,}"
    )

    print(
        f"2025 selection H1 candles: "
        f"{len(selection):,}"
    )

    print(
        f"2026+ holdout H1 candles: "
        f"{len(holdout):,}"
    )

    print()


    if len(train) < 300:

        raise SystemExit(
            "Not enough 2024 H1 candles."
        )


    if len(selection) < 300:

        raise SystemExit(
            "Not enough 2025 H1 candles."
        )


    if len(holdout) < 100:

        raise SystemExit(
            "Not enough 2026+ H1 candles."
        )


    # ========================================================
    # GRID
    # ========================================================

    keys = list(
        GRID.keys()
    )


    combinations = list(
        itertools.product(
            *[
                GRID[key]
                for key in keys
            ]
        )
    )


    print(
        f"V4 combinations: "
        f"{len(combinations)}"
    )

    print()


    candidates = []


    # ========================================================
    # TEST GRID
    # ========================================================

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
        # 2024
        # ----------------------------------------------------

        train_result = run_variant(
            train,
            config,
            params[
                "profit_protection"
            ],
            params[
                "lower_confirmation"
            ],
            params[
                "thesis_exit"
            ],
        )


        train_metrics = (
            train_result[
                "metrics"
            ]
        )


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
            ] < 8
        ):

            continue


        # ----------------------------------------------------
        # 2025
        # ----------------------------------------------------

        selection_result = run_variant(
            selection,
            config,
            params[
                "profit_protection"
            ],
            params[
                "lower_confirmation"
            ],
            params[
                "thesis_exit"
            ],
        )


        selection_metrics = (
            selection_result[
                "metrics"
            ]
        )


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
            ] < 6
        ):

            continue


        # ----------------------------------------------------
        # SAVE CANDIDATE
        # ----------------------------------------------------

        candidates.append(
            {

                "params": params,

                "train_return_pct": (
                    train_metrics[
                        "total_return_pct"
                    ]
                ),

                "train_pf": (
                    train_metrics[
                        "profit_factor"
                    ]
                ),

                "train_dd": (
                    train_metrics[
                        "max_drawdown_pct"
                    ]
                ),

                "train_wr": (
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

                "selection_pf": (
                    selection_metrics[
                        "profit_factor"
                    ]
                ),

                "selection_dd": (
                    selection_metrics[
                        "max_drawdown_pct"
                    ]
                ),

                "selection_wr": (
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


        if (
            index % 100 == 0
        ):

            print(
                f"Progress "
                f"{index}/"
                f"{len(combinations)}"
            )


    # ========================================================
    # VALID CANDIDATES
    # ========================================================

    if not candidates:

        raise SystemExit(
            "No V4 candidate passed "
            "the development and "
            "selection filters."
        )


    candidates.sort(
        key=lambda item:
        item[
            "selection_score"
        ],

        reverse=True,
    )


    best = candidates[0]


    params = best[
        "params"
    ]


    selected_config = {
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


    # ========================================================
    # FINAL UNSEEN HOLDOUT
    # ========================================================

    print()

    print(
        "Running 2026+ unseen holdout..."
    )


    holdout_result = run_variant(
        holdout,
        selected_config,
        params[
            "profit_protection"
        ],
        params[
            "lower_confirmation"
        ],
        params[
            "thesis_exit"
        ],
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
        frame,
        selected_config,
        params[
            "profit_protection"
        ],
        params[
            "lower_confirmation"
        ],
        params[
            "thesis_exit"
        ],
    )


    full_metrics = (
        full_result[
            "metrics"
        ]
    )


    # ========================================================
    # OUTPUT
    # ========================================================

    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )


    # --------------------------------------------------------
    # TOP 50
    # --------------------------------------------------------

    pd.DataFrame(
        candidates
    ).head(50).to_csv(
        OUT
        / "top_50_candidates.csv",
        index=False,
    )


    # --------------------------------------------------------
    # FULL TRADES
    # --------------------------------------------------------

    trade_rows = []


    for trade in full_result[
        "trades"
    ]:

        trade_rows.append(
            {

                "direction":
                    trade.direction,

                "signal_time":
                    trade.signal_time,

                "entry_time":
                    trade.entry_time,

                "exit_time":
                    trade.exit_time,

                "entry_price":
                    trade.entry_price,

                "exit_price":
                    trade.exit_price,

                "stop_price":
                    trade.stop_price,

                "target_price":
                    trade.target_price,

                "volume":
                    trade.volume,

                "risk_amount":
                    trade.risk_amount,

                "pnl":
                    trade.pnl,

                "r_multiple":
                    trade.r_multiple,

                "signal_score":
                    trade.signal_score,

                "exit_reason":
                    trade.exit_reason,

                "setup_reason":
                    trade.setup_reason,

                "balance_before":
                    trade.balance_before,

                "balance_after":
                    trade.balance_after,

                "week":
                    trade.week,
            }
        )


    pd.DataFrame(
        trade_rows
    ).to_csv(
        OUT
        / "selected_full_period_trades.csv",
        index=False,
    )


    # ========================================================
    # SUMMARY
    # ========================================================

    summary = f"""
RAYMOND V2.8 WEEKLY GROWTH V4
==============================

RESEARCH ONLY: YES
LIVE TRADING: NO

SELECTED PARAMETERS
-------------------
{params}

DEVELOPMENT 2024
----------------
Return: {best['train_return_pct']:.2f}%
PF: {best['train_pf']}
Win rate: {best['train_wr']:.2f}%
Drawdown: {best['train_dd']:.2f}%
Trades: {best['train_trades']}

SELECTION 2025
--------------
Return: {best['selection_return_pct']:.2f}%
PF: {best['selection_pf']}
Win rate: {best['selection_wr']:.2f}%
Drawdown: {best['selection_dd']:.2f}%
Trades: {best['selection_trades']}

FINAL UNSEEN HOLDOUT 2026+
---------------------------
Return: {holdout_metrics['total_return_pct']:.2f}%
PF: {holdout_metrics['profit_factor']}
Win rate: {holdout_metrics['win_rate_pct']:.2f}%
Drawdown: {holdout_metrics['max_drawdown_pct']:.2f}%
Trades: {holdout_metrics['total_trades']}

FULL PERIOD
-----------
Return: {full_metrics['total_return_pct']:.2f}%
PF: {full_metrics['profit_factor']}
Win rate: {full_metrics['win_rate_pct']:.2f}%
Drawdown: {full_metrics['max_drawdown_pct']:.2f}%
Trades: {full_metrics['total_trades']}
"""


    (
        OUT
        / "summary.txt"
    ).write_text(
        summary,
        encoding="utf-8",
    )


    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    optimization = {

        "research_only": True,

        "live_trading": False,

        "selected": best,

        "holdout_metrics":
            holdout_metrics,

        "full_period_metrics":
            full_metrics,

        "data": {

            "h1": str(H1),

            "m15": str(M15),

            "m5": str(M5),

        },
    }


    (
        OUT
        / "optimization.json"
    ).write_text(
        json.dumps(
            optimization,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


    print()
    print(summary)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
