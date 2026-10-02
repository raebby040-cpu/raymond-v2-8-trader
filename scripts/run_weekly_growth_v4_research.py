#!/usr/bin/env python3
from __future__ import annotations

import itertools
import json
import multiprocessing as mp
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from run_weekly_growth_backtest import (
    StrategyConfig,
    Position,
    Trade,
    calculate_indicators,
    calculate_metrics,
    calculate_volume_for_risk,
    get_entry_price,
    get_exit_price,
    calculate_pnl,
)


# ============================================================
# FILE PATHS
# ============================================================

H1 = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path("data/historical/xauusd_h1_2024_2026_normalized.csv")
)

M15 = (
    Path(sys.argv[2])
    if len(sys.argv) > 2
    else Path("data/historical/xauusd_m15_2024_2026_normalized.csv")
)

M5 = (
    Path(sys.argv[3])
    if len(sys.argv) > 3
    else Path("data/historical/xauusd_m5_2024_2026_normalized.csv")
)

OUT = (
    Path(sys.argv[4])
    if len(sys.argv) > 4
    else Path("backtest_results/weekly_growth_v4")
)


# ============================================================
# RESEARCH GRID
# ============================================================

GRID = {
    "risk_reward": [2.5, 3.0, 3.5, 4.0],
    "min_signal_score": [60, 65, 70],
    "max_trades_per_week": [6, 8],
    "atr_stop_multiplier": [1.0, 1.2, 1.4],
    "profit_protection": [
        "none",
        "be_1r",
        "lock_0_5r",
        "trail_1r",
    ],
    "lower_confirmation": [
        "m15",
        "m5",
        "both",
    ],
    "thesis_exit": [
        False,
        True,
    ],
}


# ============================================================
# BASE CONFIGURATION
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
# GLOBAL DATA FOR WORKERS
# ============================================================

_DATASETS = {}


# ============================================================
# DATA LOADING
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

    df = df.rename(columns=rename)

    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    }

    missing = required - set(df.columns)

    if missing:
        raise SystemExit(
            f"{path}: missing columns {sorted(missing)}"
        )

    raw_timestamp = df["timestamp"]

    if pd.api.types.is_numeric_dtype(raw_timestamp):

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

    x = df.set_index("timestamp").copy()

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
        delta.clip(lower=0)
        .ewm(
            alpha=1 / 14,
            adjust=False,
        )
        .mean()
    )

    loss = (
        -delta.clip(upper=0)
    ).ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    rs = gain / loss.replace(
        0,
        np.nan,
    )

    x["rsi14"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    x["bull_candle"] = (
        x["close"] > x["open"]
    )

    x["bear_candle"] = (
        x["close"] < x["open"]
    )

    x = x.reset_index()

    return x[
        [
            "timestamp",
            "close",
            "ema20",
            "ema50",
            "rsi14",
            "bull_candle",
            "bear_candle",
        ]
    ]


# ============================================================
# H1 -> M15 / M5 CONFIRMATION
# ============================================================

def build_confirmation(
    h1: pd.DataFrame,
    m15: pd.DataFrame,
    m5: pd.DataFrame,
) -> pd.DataFrame:

    m15base = lower_features(m15)

    m15f = m15base.rename(
        columns={
            column: f"m15_{column}"
            for column in m15base.columns
            if column != "timestamp"
        }
    )

    m5base = lower_features(m5)

    m5f = m5base.rename(
        columns={
            column: f"m5_{column}"
            for column in m5base.columns
            if column != "timestamp"
        }
    )

    out = h1[
        ["timestamp"]
    ].copy()

    # H1 candle is considered complete at
    # timestamp + 59m59s.
    #
    # This prevents using future M15/M5 candles.
    out["lookup_time"] = (
        out["timestamp"]
        + pd.Timedelta(
            minutes=59,
            seconds=59,
        )
    )

    out = pd.merge_asof(
        out.sort_values("lookup_time"),
        m15f.sort_values("timestamp"),
        left_on="lookup_time",
        right_on="timestamp",
        direction="backward",
    )

    out = (
        out.drop(
            columns=["timestamp_y"]
        )
        .rename(
            columns={
                "timestamp_x": "timestamp"
            }
        )
    )

    out = pd.merge_asof(
        out.sort_values("lookup_time"),
        m5f.sort_values("timestamp"),
        left_on="lookup_time",
        right_on="timestamp",
        direction="backward",
    )

    out = (
        out.drop(
            columns=["timestamp_y"]
        )
        .rename(
            columns={
                "timestamp_x": "timestamp"
            }
        )
    )

    return out.drop(
        columns=["lookup_time"]
    )


# ============================================================
# REASON BUILDER
# ============================================================

def _reason(
    parts: List[str],
) -> str:

    return "|".join(parts)


# ============================================================
# PRECOMPUTE DATA
# ============================================================

def prepare_data(
    frame: pd.DataFrame,
    confirmation_frame: pd.DataFrame,
) -> Dict:

    x = frame.reset_index(
        drop=True
    )

    confirmation_frame = (
        confirmation_frame
        .reset_index(drop=True)
    )

    n = len(x)

    close = x["close"].to_numpy(
        dtype=float
    )

    high = x["high"].to_numpy(
        dtype=float
    )

    low = x["low"].to_numpy(
        dtype=float
    )

    open_ = x["open"].to_numpy(
        dtype=float
    )

    ema20 = x["ema20"].to_numpy(
        dtype=float
    )

    ema50 = x["ema50"].to_numpy(
        dtype=float
    )

    atr = x["atr14"].to_numpy(
        dtype=float
    )

    rsi = x["rsi14"].to_numpy(
        dtype=float
    )

    macd = x["macd_hist"].to_numpy(
        dtype=float
    )

    atr_ratio = x["atr_ratio"].to_numpy(
        dtype=float
    )

    prev20h = x[
        "previous_20_high"
    ].to_numpy(dtype=float)

    prev20l = x[
        "previous_20_low"
    ].to_numpy(dtype=float)

    prev8h = x[
        "previous_8_high"
    ].to_numpy(dtype=float)

    prev8l = x[
        "previous_8_low"
    ].to_numpy(dtype=float)

    trend = (
        x["trend"]
        .astype(str)
        .to_numpy()
    )

    valid = (
        np.isfinite(close)
        & np.isfinite(high)
        & np.isfinite(low)
        & np.isfinite(ema20)
        & np.isfinite(ema50)
        & np.isfinite(atr)
        & np.isfinite(rsi)
        & np.isfinite(macd)
        & np.isfinite(atr_ratio)
        & np.isfinite(prev20h)
        & np.isfinite(prev20l)
        & np.isfinite(prev8h)
        & np.isfinite(prev8l)
    )

    volatility = (
        valid
        & (
            atr_ratio
            >= BASE["min_atr_ratio"]
        )
        & (
            atr_ratio
            <= BASE["max_atr_ratio"]
        )
    )

    buy_score = np.zeros(
        n,
        dtype=np.int16,
    )

    sell_score = np.zeros(
        n,
        dtype=np.int16,
    )

    buy_reason = [""] * n
    sell_reason = [""] * n

    buy_parts = [
        []
        for _ in range(n)
    ]

    sell_parts = [
        []
        for _ in range(n)
    ]

    candle_range = (
        high - low
    )

    location = np.divide(
        close - low,
        candle_range,
        out=np.zeros(n),
        where=candle_range > 0,
    )

    # ========================================================
    # BUY SCORE
    # ========================================================

    cond = (
        volatility
        & (trend == "BULL")
    )

    buy_score[cond] += 20

    for i in np.flatnonzero(cond):
        buy_parts[i].append(
            "h4_bull_regime"
        )

    cond = (
        volatility
        & (close > ema50)
    )

    buy_score[cond] += 15

    for i in np.flatnonzero(cond):
        buy_parts[i].append(
            "h1_above_ema50"
        )

    cond = (
        volatility
        & (low <= ema20)
        & (close > ema20)
    )

    buy_score[cond] += 15

    for i in np.flatnonzero(cond):
        buy_parts[i].append(
            "ema20_pullback_reclaim"
        )

    cond = (
        volatility
        & (low < prev20l)
        & (close > prev20l)
    )

    buy_score[cond] += 15

    for i in np.flatnonzero(cond):
        buy_parts[i].append(
            "sell_side_liquidity_sweep"
        )

    cond = (
        volatility
        & (rsi >= 52)
        & (rsi <= 72)
        & (macd > 0)
    )

    buy_score[cond] += 15

    for i in np.flatnonzero(cond):
        buy_parts[i].append(
            "bullish_momentum"
        )

    cond = (
        volatility
        & (candle_range > 0)
        & (location >= 0.65)
    )

    buy_score[cond] += 10

    for i in np.flatnonzero(cond):
        buy_parts[i].append(
            "strong_bullish_close"
        )

    # ========================================================
    # SELL SCORE
    # ========================================================

    cond = (
        volatility
        & (trend == "BEAR")
    )

    sell_score[cond] += 20

    for i in np.flatnonzero(cond):
        sell_parts[i].append(
            "h4_bear_regime"
        )

    cond = (
        volatility
        & (close < ema50)
    )

    sell_score[cond] += 15

    for i in np.flatnonzero(cond):
        sell_parts[i].append(
            "h1_below_ema50"
        )

    cond = (
        volatility
        & (high >= ema20)
        & (close < ema20)
    )

    sell_score[cond] += 15

    for i in np.flatnonzero(cond):
        sell_parts[i].append(
            "ema20_pullback_rejection"
        )

    cond = (
        volatility
        & (high > prev20h)
        & (close < prev20h)
    )

    sell_score[cond] += 15

    for i in np.flatnonzero(cond):
        sell_parts[i].append(
            "buy_side_liquidity_sweep"
        )

    cond = (
        volatility
        & (rsi >= 28)
        & (rsi <= 48)
        & (macd < 0)
    )

    sell_score[cond] += 15

    for i in np.flatnonzero(cond):
        sell_parts[i].append(
            "bearish_momentum"
        )

    cond = (
        volatility
        & (candle_range > 0)
        & (location <= 0.35)
    )

    sell_score[cond] += 10

    for i in np.flatnonzero(cond):
        sell_parts[i].append(
            "strong_bearish_close"
        )

    # ========================================================
    # REASONS
    # ========================================================

    for i in range(n):

        if not valid[i]:

            buy_reason[i] = (
                "indicator_data_invalid"
            )

            sell_reason[i] = (
                "indicator_data_invalid"
            )

        elif not volatility[i]:

            buy_reason[i] = (
                "volatility_filter_failed"
            )

            sell_reason[i] = (
                "volatility_filter_failed"
            )

        else:

            buy_reason[i] = _reason(
                buy_parts[i]
            )

            sell_reason[i] = _reason(
                sell_parts[i]
            )

    # ========================================================
    # LOWER TIMEFRAME ARRAYS
    # ========================================================

    def arr(
        name,
        default=np.nan,
    ):

        if name in confirmation_frame.columns:
            return (
                confirmation_frame[name]
                .to_numpy()
            )

        return np.full(
            n,
            default,
        )

    m15_close = arr(
        "m15_close"
    ).astype(float)

    m15_ema20 = arr(
        "m15_ema20"
    ).astype(float)

    m15_ema50 = arr(
        "m15_ema50"
    ).astype(float)

    m15_rsi = arr(
        "m15_rsi14"
    ).astype(float)

    m15_bull = arr(
        "m15_bull_candle",
        False,
    ).astype(bool)

    m15_bear = arr(
        "m15_bear_candle",
        False,
    ).astype(bool)

    m5_close = arr(
        "m5_close"
    ).astype(float)

    m5_ema20 = arr(
        "m5_ema20"
    ).astype(float)

    m5_ema50 = arr(
        "m5_ema50"
    ).astype(float)

    m5_rsi = arr(
        "m5_rsi14"
    ).astype(float)

    m5_bull = arr(
        "m5_bull_candle",
        False,
    ).astype(bool)

    m5_bear = arr(
        "m5_bear_candle",
        False,
    ).astype(bool)

    def ok(
        c,
        e20,
        e50,
        r,
        candle_direction,
        buy,
    ):

        finite = (
            np.isfinite(c)
            & np.isfinite(e20)
            & np.isfinite(e50)
            & np.isfinite(r)
        )

        if buy:

            return (
                finite
                & (c > e20)
                & (e20 > e50)
                & (r >= 52)
                & (r <= 75)
                & candle_direction
            )

        return (
            finite
            & (c < e20)
            & (e20 < e50)
            & (r >= 25)
            & (r <= 48)
            & candle_direction
        )

    m15_buy = ok(
        m15_close,
        m15_ema20,
        m15_ema50,
        m15_rsi,
        m15_bull,
        True,
    )

    m15_sell = ok(
        m15_close,
        m15_ema20,
        m15_ema50,
        m15_rsi,
        m15_bear,
        False,
    )

    m5_buy = ok(
        m5_close,
        m5_ema20,
        m5_ema50,
        m5_rsi,
        m5_bull,
        True,
    )

    m5_sell = ok(
        m5_close,
        m5_ema20,
        m5_ema50,
        m5_rsi,
        m5_bear,
        False,
    )

    timestamps = x[
        "timestamp"
    ].tolist()

    iso = [
        pd.Timestamp(t).isoformat()
        for t in timestamps
    ]

    calendar = (
        x["timestamp"]
        .dt.isocalendar()
    )

    weeks = (
        calendar["year"]
        .astype(str)
        + "-W"
        + calendar["week"]
        .astype(int)
        .astype(str)
        .str.zfill(2)
    ).to_numpy()

    return {
        "n": n,
        "timestamp": timestamps,
        "iso": iso,
        "week": weeks,

        "open": open_,
        "high": high,
        "low": low,
        "close": close,

        "ema50": ema50,
        "atr": atr,

        "prev8h": prev8h,
        "prev8l": prev8l,

        "trend": trend,

        "buy_score": buy_score,
        "sell_score": sell_score,

        "buy_reason": buy_reason,
        "sell_reason": sell_reason,

        "m15_buy": m15_buy,
        "m15_sell": m15_sell,

        "m5_buy": m5_buy,
        "m5_sell": m5_sell,
    }


# ============================================================
# LOWER TIMEFRAME CONFIRMATION
# ============================================================

def _confirm(
    d,
    i,
    direction,
    mode,
):

    if direction == "BUY":

        m15 = bool(
            d["m15_buy"][i]
        )

        m5 = bool(
            d["m5_buy"][i]
        )

    else:

        m15 = bool(
            d["m15_sell"][i]
        )

        m5 = bool(
            d["m5_sell"][i]
        )

    if mode == "m15":
        return m15

    if mode == "m5":
        return m5

    if mode == "both":
        return m15 and m5

    return False


# ============================================================
# DIAGNOSTIC COUNTS
# ============================================================

def signal_diagnostics(
    d: Dict,
    threshold: int,
):

    result = {
        "h1_buy_score_threshold": 0,
        "h1_sell_score_threshold": 0,

        "h1_buy_confirmable": 0,
        "h1_sell_confirmable": 0,

        "m15_buy": 0,
        "m15_sell": 0,

        "m5_buy": 0,
        "m5_sell": 0,

        "both_buy": 0,
        "both_sell": 0,

        "buy_sell_conflict": 0,

        "m15_total": 0,
        "m5_total": 0,
        "both_total": 0,
    }

    for i in range(
        1,
        d["n"] - 1,
    ):

        bs = int(
            d["buy_score"][i]
        )

        ss = int(
            d["sell_score"][i]
        )

        buy_ok = (
            bs >= threshold
        )

        sell_ok = (
            ss >= threshold
        )

        if buy_ok:
            result[
                "h1_buy_score_threshold"
            ] += 1

        if sell_ok:
            result[
                "h1_sell_score_threshold"
            ] += 1

        if buy_ok and sell_ok:

            result[
                "buy_sell_conflict"
            ] += 1

            # Higher score wins.
            direction = (
                "BUY"
                if bs > ss
                else "SELL"
            )

        elif buy_ok:

            direction = "BUY"

        elif sell_ok:

            direction = "SELL"

        else:

            continue

        if direction == "BUY":

            m15 = bool(
                d["m15_buy"][i]
            )

            m5 = bool(
                d["m5_buy"][i]
            )

            if m15:
                result[
                    "m15_buy"
                ] += 1

            if m5:
                result[
                    "m5_buy"
                ] += 1

            if m15 and m5:
                result[
                    "both_buy"
                ] += 1

        else:

            m15 = bool(
                d["m15_sell"][i]
            )

            m5 = bool(
                d["m5_sell"][i]
            )

            if m15:
                result[
                    "m15_sell"
                ] += 1

            if m5:
                result[
                    "m5_sell"
                ] += 1

            if m15 and m5:
                result[
                    "both_sell"
                ] += 1

    result[
        "m15_total"
    ] = (
        result["m15_buy"]
        + result["m15_sell"]
    )

    result[
        "m5_total"
    ] = (
        result["m5_buy"]
        + result["m5_sell"]
    )

    result[
        "both_total"
    ] = (
        result["both_buy"]
        + result["both_sell"]
    )

    return result


# ============================================================
# SIMULATION
# ============================================================

def simulate(
    d: Dict,
    config: Dict,
    protection: str,
    confirm_mode: str,
    thesis_exit: bool,
    want_trades: bool = False,
):

    cfg = StrategyConfig(
        **config,
        starting_balance=1000.0,
    )

    n = d["n"]

    balance = 1000.0

    trades = []

    weekly_records = {}

    position = None

    current_week = None

    pending = None

    stats = Counter()

    def ensure_week(w):

        if w not in weekly_records:

            weekly_records[w] = {
                "start_balance": balance,
                "profit": 0.0,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "break_evens": 0,
                "target_hit": False,
                "loss_limit_hit": False,
            }

        return weekly_records[w]

    for i in range(
        1,
        n,
    ):

        w = d["week"][i]

        if w != current_week:

            current_week = w

            ensure_week(w)

            pending = None

        week = weekly_records[w]

        # ====================================================
        # MANAGE OPEN POSITION
        # ====================================================

        if position is not None:

            direction = position[
                "direction"
            ]

            stop = position[
                "stop"
            ]

            target = position[
                "target"
            ]

            hi = d["high"][i]
            lo = d["low"][i]

            exit_result = None

            if direction == "BUY":

                stop_hit = lo <= stop

                target_hit = (
                    hi >= target
                )

            else:

                stop_hit = hi >= stop

                target_hit = (
                    lo <= target
                )

            if (
                stop_hit
                and target_hit
            ):

                exit_result = (
                    stop,
                    "STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST",
                )

            elif stop_hit:

                exit_result = (
                    stop,
                    "STOP_LOSS",
                )

            elif target_hit:

                exit_result = (
                    target,
                    "TAKE_PROFIT",
                )

            elif thesis_exit:

                if (
                    direction == "BUY"
                    and d["close"][i]
                    < d["ema50"][i]
                    and d["trend"][i]
                    == "BEAR"
                ):

                    exit_result = (
                        d["close"][i],
                        "THESIS_EXIT",
                    )

                elif (
                    direction == "SELL"
                    and d["close"][i]
                    > d["ema50"][i]
                    and d["trend"][i]
                    == "BULL"
                ):

                    exit_result = (
                        d["close"][i],
                        "THESIS_EXIT",
                    )

            if exit_result is not None:

                raw, reason = (
                    exit_result
                )

                exit_price = get_exit_price(
                    direction,
                    raw,
                    cfg,
                )

                pnl = calculate_pnl(
                    direction,
                    position["entry"],
                    exit_price,
                    position["volume"],
                )

                before = balance

                balance += pnl

                risk_amount = position[
                    "risk_amount"
                ]

                r_multiple = (
                    pnl / risk_amount
                    if risk_amount > 0
                    else 0.0
                )

                if pnl > 0:

                    week["wins"] += 1

                elif pnl < 0:

                    week["losses"] += 1

                else:

                    week[
                        "break_evens"
                    ] += 1

                week["profit"] += pnl

                week["trades"] += 1

                stats[
                    f"exit_{reason}"
                ] += 1

                if want_trades:

                    trades.append(
                        Trade(
                            direction=direction,
                            signal_time=position[
                                "signal_time"
                            ],
                            entry_time=position[
                                "entry_time"
                            ],
                            exit_time=d[
                                "iso"
                            ][i],
                            entry_price=position[
                                "entry"
                            ],
                            exit_price=exit_price,
                            stop_price=position[
                                "stop"
                            ],
                            target_price=position[
                                "target"
                            ],
                            volume=position[
                                "volume"
                            ],
                            risk_amount=risk_amount,
                            pnl=pnl,
                            r_multiple=r_multiple,
                            signal_score=position[
                                "score"
                            ],
                            exit_reason=reason,
                            setup_reason=position[
                                "reason"
                            ],
                            balance_before=before,
                            balance_after=balance,
                            week=w,
                        )
                    )

                position = None

                pending = None

                continue

            # =================================================
            # PROFIT PROTECTION
            # =================================================

            if protection != "none":

                entry = position[
                    "entry"
                ]

                risk = position[
                    "risk_distance"
                ]

                close = d[
                    "close"
                ][i]

                if risk > 0:

                    if direction == "BUY":

                        r_now = (
                            close - entry
                        ) / risk

                        if (
                            protection
                            == "be_1r"
                            and r_now >= 1.0
                        ):

                            position[
                                "stop"
                            ] = max(
                                position[
                                    "stop"
                                ],
                                entry,
                            )

                        elif (
                            protection
                            == "lock_0_5r"
                            and r_now >= 1.5
                        ):

                            position[
                                "stop"
                            ] = max(
                                position[
                                    "stop"
                                ],
                                entry
                                + 0.5 * risk,
                            )

                        elif (
                            protection
                            == "trail_1r"
                            and r_now >= 2.0
                        ):

                            position[
                                "stop"
                            ] = max(
                                position[
                                    "stop"
                                ],
                                close - risk,
                            )

                    else:

                        r_now = (
                            entry - close
                        ) / risk

                        if (
                            protection
                            == "be_1r"
                            and r_now >= 1.0
                        ):

                            position[
                                "stop"
                            ] = min(
                                position[
                                    "stop"
                                ],
                                entry,
                            )

                        elif (
                            protection
                            == "lock_0_5r"
                            and r_now >= 1.5
                        ):

                            position[
                                "stop"
                            ] = min(
                                position[
                                    "stop"
                                ],
                                entry
                                - 0.5 * risk,
                            )

                        elif (
                            protection
                            == "trail_1r"
                            and r_now >= 2.0
                        ):

                            position[
                                "stop"
                            ] = min(
                                position[
                                    "stop"
                                ],
                                close + risk,
                            )

        # ====================================================
        # ENTER PENDING SIGNAL
        # ====================================================

        if (
            position is None
            and pending is not None
        ):

            direction = pending[
                "direction"
            ]

            score = pending[
                "score"
            ]

            reason = pending[
                "reason"
            ]

            signal_iso = pending[
                "signal_iso"
            ]

            start = week[
                "start_balance"
            ]

            weekly_return = (
                (
                    balance - start
                )
                / start
                if start > 0
                else 0.0
            )

            if (
                weekly_return
                >= cfg.weekly_target
            ):

                week[
                    "target_hit"
                ] = True

                stats[
                    "weekly_target_block"
                ] += 1

                pending = None

            elif (
                weekly_return
                <= cfg.weekly_loss_limit
            ):

                week[
                    "loss_limit_hit"
                ] = True

                stats[
                    "weekly_loss_block"
                ] += 1

                pending = None

            elif (
                week["trades"]
                >= cfg.max_trades_per_week
            ):

                stats[
                    "weekly_trade_cap_block"
                ] += 1

                pending = None

            else:

                market_open = d[
                    "open"
                ][i]

                entry = get_entry_price(
                    direction,
                    market_open,
                    cfg,
                )

                atr = d[
                    "atr"
                ][i]

                if direction == "BUY":

                    atr_stop = (
                        entry
                        - atr
                        * cfg.atr_stop_multiplier
                    )

                    structural_stop = (
                        d["prev8l"][i]
                        - atr * 0.10
                    )

                    stop = min(
                        atr_stop,
                        structural_stop,
                    )

                    risk_distance = (
                        entry - stop
                    )

                else:

                    atr_stop = (
                        entry
                        + atr
                        * cfg.atr_stop_multiplier
                    )

                    structural_stop = (
                        d["prev8h"][i]
                        + atr * 0.10
                    )

                    stop = max(
                        atr_stop,
                        structural_stop,
                    )

                    risk_distance = (
                        stop - entry
                    )

                if risk_distance <= 0:

                    stats[
                        "invalid_risk_distance"
                    ] += 1

                    pending = None

                else:

                    volume, risk_amount = (
                        calculate_volume_for_risk(
                            balance,
                            cfg.risk_per_trade,
                            risk_distance,
                            cfg,
                        )
                    )

                    if volume <= 0:

                        stats[
                            "zero_volume"
                        ] += 1

                        pending = None

                    else:

                        if direction == "BUY":

                            target = (
                                entry
                                + risk_distance
                                * cfg.risk_reward
                            )

                        else:

                            target = (
                                entry
                                - risk_distance
                                * cfg.risk_reward
                            )

                        position = {
                            "direction": direction,
                            "signal_time": signal_iso,
                            "entry_time": d[
                                "timestamp"
                            ][i],
                            "entry": entry,
                            "stop": stop,
                            "target": target,
                            "volume": volume,
                            "risk_amount": risk_amount,
                            "risk_distance": risk_distance,
                            "score": int(score),
                            "reason": reason,
                        }

                        stats[
                            "entries"
                        ] += 1

                        pending = None

        # ====================================================
        # CREATE NEXT SIGNAL
        # ====================================================

        if i < n - 1:

            threshold = (
                cfg.min_signal_score
            )

            bs = int(
                d["buy_score"][i]
            )

            ss = int(
                d["sell_score"][i]
            )

            # IMPORTANT:
            # If both qualify, choose the stronger
            # directional score rather than BUY by default.

            if (
                bs >= threshold
                and ss >= threshold
            ):

                if bs > ss:

                    direction = "BUY"
                    score = bs
                    reason = d[
                        "buy_reason"
                    ][i]

                elif ss > bs:

                    direction = "SELL"
                    score = ss
                    reason = d[
                        "sell_reason"
                    ][i]

                else:

                    # Exact tie = no trade.
                    direction = None

                    stats[
                        "equal_score_conflict"
                    ] += 1

            elif bs >= threshold:

                direction = "BUY"

                score = bs

                reason = d[
                    "buy_reason"
                ][i]

            elif ss >= threshold:

                direction = "SELL"

                score = ss

                reason = d[
                    "sell_reason"
                ][i]

            else:

                direction = None

            if direction is not None:

                confirmed = _confirm(
                    d,
                    i,
                    direction,
                    confirm_mode,
                )

                if confirmed:

                    reason = (
                        reason
                        + "|lower_tf_"
                        + confirm_mode
                        + "_confirmed"
                    )

                    pending = (
                        direction,
                        score,
                        reason,
                        d["iso"][i],
                    )

                    stats[
                        f"confirmed_{confirm_mode}"
                    ] += 1

                else:

                    stats[
                        f"confirmation_failed_{confirm_mode}"
                    ] += 1

                    pending = None

            else:

                pending = None

    # ========================================================
    # FORCE CLOSE FINAL POSITION
    # ========================================================

    if position is not None:

        i = n - 1

        direction = position[
            "direction"
        ]

        raw = d[
            "close"
        ][i]

        exit_price = get_exit_price(
            direction,
            raw,
            cfg,
        )

        pnl = calculate_pnl(
            direction,
            position["entry"],
            exit_price,
            position["volume"],
        )

        before = balance

        balance += pnl

        w = d[
            "week"
        ][i]

        week = weekly_records[w]

        if pnl > 0:

            week["wins"] += 1

        elif pnl < 0:

            week["losses"] += 1

        else:

            week[
                "break_evens"
            ] += 1

        week[
            "profit"
        ] += pnl

        week[
            "trades"
        ] += 1

        stats[
            "end_of_data_exit"
        ] += 1

        if want_trades:

            trades.append(
                Trade(
                    direction=direction,
                    signal_time=position[
                        "signal_time"
                    ],
                    entry_time=position[
                        "entry_time"
                    ],
                    exit_time=d[
                        "iso"
                    ][i],
                    entry_price=position[
                        "entry"
                    ],
                    exit_price=exit_price,
                    stop_price=position[
                        "stop"
                    ],
                    target_price=position[
                        "target"
                    ],
                    volume=position[
                        "volume"
                    ],
                    risk_amount=position[
                        "risk_amount"
                    ],
                    pnl=pnl,
                    r_multiple=(
                        pnl
                        / position[
                            "risk_amount"
                        ]
                        if position[
                            "risk_amount"
                        ] > 0
                        else 0.0
                    ),
                    signal_score=position[
                        "score"
                    ],
                    exit_reason="END_OF_DATA",
                    setup_reason=position[
                        "reason"
                    ],
                    balance_before=before,
                    balance_after=balance,
                    week=w,
                )
            )

    # ========================================================
    # WEEKLY RECORDS
    # ========================================================

    weekly_rows = []

    for wk, state in (
        weekly_records.items()
    ):

        start = float(
            state["start_balance"]
        )

        ret = (
            state["profit"] / start
            if start > 0
            else 0.0
        )

        weekly_rows.append(
            {
                "week": wk,
                "start_balance": start,
                "profit": state[
                    "profit"
                ],
                "weekly_return": ret,
                "weekly_return_pct": (
                    ret * 100
                ),
                "trades": state[
                    "trades"
                ],
                "wins": state[
                    "wins"
                ],
                "losses": state[
                    "losses"
                ],
                "break_evens": state[
                    "break_evens"
                ],
                "target_hit": state[
                    "target_hit"
                ],
                "target_25pct_hit": state[
                    "target_hit"
                ],
                "loss_limit_hit": state[
                    "loss_limit_hit"
                ],
            }
        )

    return (
        trades,
        weekly_rows,
        balance,
        dict(stats),
    )


# ============================================================
# WORKER
# ============================================================

def _worker(
    payload,
):

    params = payload

    config = {
        **BASE,
        "risk_reward": params[
            "risk_reward"
        ],
        "min_signal_score": params[
            "min_signal_score"
        ],
        "max_trades_per_week": params[
            "max_trades_per_week"
        ],
        "atr_stop_multiplier": params[
            "atr_stop_multiplier"
        ],
    }

    d = _DATASETS

    # --------------------------------------------------------
    # DEVELOPMENT
    # --------------------------------------------------------

    train = simulate(
        d["train"],
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

    tm = calculate_metrics(
        train[0],
        train[1],
        1000.0,
        train[2],
        StrategyConfig(
            **config,
            starting_balance=1000.0,
        ),
    )

    train_return_ok = (
        tm["total_return_pct"] > 0
    )

    train_pf_ok = (
        (tm["profit_factor"] or 0.0)
        > 1.0
    )

    train_trade_ok = (
        tm["total_trades"] >= 8
    )

    if not (
        train_return_ok
        and train_pf_ok
        and train_trade_ok
    ):

        return {
            "params": params,
            "status": "rejected_development",
            "train_return_pct": tm[
                "total_return_pct"
            ],
            "train_pf": tm[
                "profit_factor"
            ],
            "train_dd": tm[
                "max_drawdown_pct"
            ],
            "train_wr": tm[
                "win_rate_pct"
            ],
            "train_trades": tm[
                "total_trades"
            ],
            "selection_return_pct": None,
            "selection_pf": None,
            "selection_dd": None,
            "selection_wr": None,
            "selection_trades": None,
            "selection_score": None,
        }

    # --------------------------------------------------------
    # SELECTION
    # --------------------------------------------------------

    sel = simulate(
        d["selection"],
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

    sm = calculate_metrics(
        sel[0],
        sel[1],
        1000.0,
        sel[2],
        StrategyConfig(
            **config,
            starting_balance=1000.0,
        ),
    )

    selection_return_ok = (
        sm["total_return_pct"] > 0
    )

    selection_pf_ok = (
        (sm["profit_factor"] or 0.0)
        > 1.0
    )

    selection_trade_ok = (
        sm["total_trades"] >= 6
    )

    if not (
        selection_return_ok
        and selection_pf_ok
        and selection_trade_ok
    ):

        return {
            "params": params,
            "status": "rejected_selection",
            "train_return_pct": tm[
                "total_return_pct"
            ],
            "train_pf": tm[
                "profit_factor"
            ],
            "train_dd": tm[
                "max_drawdown_pct"
            ],
            "train_wr": tm[
                "win_rate_pct"
            ],
            "train_trades": tm[
                "total_trades"
            ],
            "selection_return_pct": sm[
                "total_return_pct"
            ],
            "selection_pf": sm[
                "profit_factor"
            ],
            "selection_dd": sm[
                "max_drawdown_pct"
            ],
            "selection_wr": sm[
                "win_rate_pct"
            ],
            "selection_trades": sm[
                "total_trades"
            ],
            "selection_score": None,
        }

    pf = (
        sm["profit_factor"]
        or 0.0
    )

    score = (
        sm["total_return_pct"]
        - 0.75
        * abs(
            sm["max_drawdown_pct"]
        )
        + 10.0
        * max(
            0.0,
            pf - 1.0,
        )
    )

    return {
        "params": params,
        "status": "valid",
        "train_return_pct": tm[
            "total_return_pct"
        ],
        "train_pf": tm[
            "profit_factor"
        ],
        "train_dd": tm[
            "max_drawdown_pct"
        ],
        "train_wr": tm[
            "win_rate_pct"
        ],
        "train_trades": tm[
            "total_trades"
        ],
        "selection_return_pct": sm[
            "total_return_pct"
        ],
        "selection_pf": sm[
            "profit_factor"
        ],
        "selection_dd": sm[
            "max_drawdown_pct"
        ],
        "selection_wr": sm[
            "win_rate_pct"
        ],
        "selection_trades": sm[
            "total_trades"
        ],
        "selection_score": score,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "RAYMOND V2.8 WEEKLY GROWTH V4.1"
    )

    print(
        "================================="
    )

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

    h1_raw = load_ohlc(H1)

    m15_raw = load_ohlc(M15)

    m5_raw = load_ohlc(M5)

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

    # ========================================================
    # INDICATORS
    # ========================================================

    h1 = calculate_indicators(
        h1_raw,
        StrategyConfig(),
    )

    confirmation_frame = (
        build_confirmation(
            h1,
            m15_raw,
            m5_raw,
        )
    )

    frame = h1.copy()

    for column in (
        confirmation_frame.columns
    ):

        if column == "timestamp":
            continue

        frame[column] = (
            confirmation_frame[
                column
            ].to_numpy()
        )

    # ========================================================
    # DATA SPLITS
    # ========================================================

    train_mask = (
        frame["timestamp"]
        >= pd.Timestamp(
            "2024-01-01",
            tz="UTC",
        )
    ) & (
        frame["timestamp"]
        < pd.Timestamp(
            "2025-01-01",
            tz="UTC",
        )
    )

    selection_mask = (
        frame["timestamp"]
        >= pd.Timestamp(
            "2025-01-01",
            tz="UTC",
        )
    ) & (
        frame["timestamp"]
        < pd.Timestamp(
            "2026-01-01",
            tz="UTC",
        )
    )

    holdout_mask = (
        frame["timestamp"]
        >= pd.Timestamp(
            "2026-01-01",
            tz="UTC",
        )
    )

    train = frame[
        train_mask
    ].copy()

    selection = frame[
        selection_mask
    ].copy()

    holdout = frame[
        holdout_mask
    ].copy()

    if (
        len(train) < 300
        or len(selection) < 300
        or len(holdout) < 100
    ):

        raise SystemExit(
            "Not enough data in one or more required splits."
        )

    print(
        f"2024 development H1 candles: {len(train):,}"
    )

    print(
        f"2025 selection H1 candles: {len(selection):,}"
    )

    print(
        f"2026+ holdout H1 candles: {len(holdout):,}"
    )

    print()

    # ========================================================
    # PREPARE DATASETS
    # ========================================================

    global _DATASETS

    _DATASETS = {
        "train": prepare_data(
            train,
            confirmation_frame.iloc[
                train.index
            ].reset_index(
                drop=True
            ),
        ),

        "selection": prepare_data(
            selection,
            confirmation_frame.iloc[
                selection.index
            ].reset_index(
                drop=True
            ),
        ),

        "holdout": prepare_data(
            holdout,
            confirmation_frame.iloc[
                holdout.index
            ].reset_index(
                drop=True
            ),
        ),

        "full": prepare_data(
            frame,
            confirmation_frame,
        ),
    }

    # ========================================================
    # DIAGNOSTICS
    # ========================================================

    print(
        "SIGNAL DIAGNOSTICS"
    )

    print(
        "------------------"
    )

    for threshold in [
        60,
        65,
        70,
    ]:

        diagnostic = signal_diagnostics(
            _DATASETS["train"],
            threshold,
        )

        print()
        print(
            f"2024 threshold {threshold}"
        )

        print(
            f"  H1 BUY qualifying: "
            f"{diagnostic['h1_buy_score_threshold']:,}"
        )

        print(
            f"  H1 SELL qualifying: "
            f"{diagnostic['h1_sell_score_threshold']:,}"
        )

        print(
            f"  M15 confirmations: "
            f"{diagnostic['m15_total']:,}"
        )

        print(
            f"  M5 confirmations: "
            f"{diagnostic['m5_total']:,}"
        )

        print(
            f"  BOTH confirmations: "
            f"{diagnostic['both_total']:,}"
        )

        print(
            f"  BUY/SELL conflicts: "
            f"{diagnostic['buy_sell_conflict']:,}"
        )

    print()

    # ========================================================
    # GRID
    # ========================================================

    keys = list(
        GRID.keys()
    )

    combinations = [
        dict(
            zip(
                keys,
                values,
            )
        )
        for values in itertools.product(
            *(
                GRID[key]
                for key in keys
            )
        )
    ]

    print(
        f"V4.1 combinations: {len(combinations)}"
    )

    print(
        "Fast engine: precomputed signals + parallel evaluation"
    )

    print()

    # ========================================================
    # EVALUATE GRID
    # ========================================================

    candidates = []

    rejection_counts = Counter()

    workers = min(
        2,
        os.cpu_count() or 1,
    )

    print(
        f"Parallel workers: {workers}"
    )

    print()

    if (
        workers > 1
        and "fork"
        in mp.get_all_start_methods()
    ):

        ctx = mp.get_context(
            "fork"
        )

        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=ctx,
        ) as executor:

            futures = [
                executor.submit(
                    _worker,
                    params,
                )
                for params in combinations
            ]

            for index, future in enumerate(
                as_completed(futures),
                1,
            ):

                result = future.result()

                if result is not None:

                    status = result[
                        "status"
                    ]

                    rejection_counts[
                        status
                    ] += 1

                    if status == "valid":

                        candidates.append(
                            result
                        )

                if (
                    index % 25 == 0
                    or index
                    == len(combinations)
                ):

                    print(
                        f"Progress "
                        f"{index}/{len(combinations)} "
                        f"| valid candidates "
                        f"{len(candidates)}",
                        flush=True,
                    )

    else:

        for index, params in enumerate(
            combinations,
            1,
        ):

            result = _worker(
                params
            )

            if result is not None:

                status = result[
                    "status"
                ]

                rejection_counts[
                    status
                ] += 1

                if status == "valid":

                    candidates.append(
                        result
                    )

            if (
                index % 25 == 0
                or index
                == len(combinations)
            ):

                print(
                    f"Progress "
                    f"{index}/{len(combinations)} "
                    f"| valid candidates "
                    f"{len(candidates)}",
                    flush=True,
                )

    # ========================================================
    # SAVE DIAGNOSTIC SUMMARY
    # ========================================================

    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    diagnostic_payload = {
        "grid_size": len(
            combinations
        ),
        "valid_candidates": len(
            candidates
        ),
        "rejection_counts": dict(
            rejection_counts
        ),
        "threshold_diagnostics_2024": {
            str(threshold):
                signal_diagnostics(
                    _DATASETS[
                        "train"
                    ],
                    threshold,
                )
            for threshold in [
                60,
                65,
                70,
            ]
        },
    }

    (
        OUT
        / "v4_1_diagnostics.json"
    ).write_text(
        json.dumps(
            diagnostic_payload,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # NO VALID CANDIDATE
    # ========================================================

    if not candidates:

        diagnostic_text = (
            "\n"
            "NO V4.1 CANDIDATE PASSED "
            "ALL FILTERS.\n"
            "\n"
            "REJECTION SUMMARY\n"
            "------------------\n"
            f"Development rejected: "
            f"{rejection_counts.get('rejected_development', 0)}\n"
            f"Selection rejected: "
            f"{rejection_counts.get('rejected_selection', 0)}\n"
            f"Valid: "
            f"{rejection_counts.get('valid', 0)}\n"
        )

        print(
            diagnostic_text
        )

        (
            OUT
            / "summary.txt"
        ).write_text(
            diagnostic_text,
            encoding="utf-8",
        )

        print(
            "Detailed diagnostics saved to:"
        )

        print(
            OUT
            / "v4_1_diagnostics.json"
        )

        # Do NOT fail GitHub Actions merely because
        # the strategy has no valid candidate.
        #
        # This allows the diagnostic artifact to be
        # uploaded and inspected.

        return

    # ========================================================
    # SELECT BEST CANDIDATE
    # ========================================================

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
        "risk_reward": params[
            "risk_reward"
        ],
        "min_signal_score": params[
            "min_signal_score"
        ],
        "max_trades_per_week": params[
            "max_trades_per_week"
        ],
        "atr_stop_multiplier": params[
            "atr_stop_multiplier"
        ],
    }

    # ========================================================
    # HOLDOUT
    # ========================================================

    print()

    print(
        "Running 2026+ unseen holdout..."
    )

    holdout_result = simulate(
        _DATASETS["holdout"],
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
        want_trades=True,
    )

    holdout_metrics = calculate_metrics(
        holdout_result[0],
        holdout_result[1],
        1000.0,
        holdout_result[2],
        StrategyConfig(
            **selected_config,
            starting_balance=1000.0,
        ),
    )

    # ========================================================
    # FULL PERIOD
    # ========================================================

    print(
        "Running selected configuration over full period..."
    )

    full_result = simulate(
        _DATASETS["full"],
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
        want_trades=True,
    )

    full_metrics = calculate_metrics(
        full_result[0],
        full_result[1],
        1000.0,
        full_result[2],
        StrategyConfig(
            **selected_config,
            starting_balance=1000.0,
        ),
    )

    # ========================================================
    # SAVE CANDIDATES
    # ========================================================

    pd.DataFrame(
        candidates
    ).head(
        50
    ).to_csv(
        OUT
        / "top_50_candidates.csv",
        index=False,
    )

    trade_rows = [
        vars(trade)
        for trade
        in full_result[0]
    ]

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
RAYMOND V2.8 WEEKLY GROWTH V4.1
================================

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

GRID DIAGNOSTICS
----------------
Total combinations: {len(combinations)}
Valid candidates: {len(candidates)}
Development rejected: {rejection_counts.get('rejected_development', 0)}
Selection rejected: {rejection_counts.get('rejected_selection', 0)}
"""

    (
        OUT
        / "summary.txt"
    ).write_text(
        summary,
        encoding="utf-8",
    )

    # ========================================================
    # OPTIMIZATION JSON
    # ========================================================

    (
        OUT
        / "optimization.json"
    ).write_text(
        json.dumps(
            {
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

                "engine": {
                    "precomputed_signals": True,
                    "parallel_workers": workers,
                    "grid_size": len(
                        combinations
                    ),
                },

                "diagnostics":
                    diagnostic_payload,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(
        summary
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
