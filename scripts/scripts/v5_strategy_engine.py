#!/usr/bin/env python3
"""
RAYMOND v2.8 — V5 STRATEGY ENGINE
==================================

Research-only strategy-family and market-regime engine.

V5 design goals
---------------
1. Detect the current market regime.
2. Evaluate multiple genuinely different strategy families.
3. Keep strategy generation separate from:
   - position sizing
   - execution
   - P&L
   - optimization
4. Prevent future-data leakage.
5. Produce transparent reasons for every candidate signal.

Strategy families
-----------------
- TREND_CONTINUATION
- PULLBACK_RETEST
- BREAKOUT
- LIQUIDITY_REVERSAL
- RANGE_MEAN_REVERSION
- MOMENTUM_EXPANSION

Regimes
-------
- BULL_TREND
- BEAR_TREND
- RANGE
- VOLATILITY_COMPRESSION
- VOLATILITY_EXPANSION
- TRANSITION

This module does NOT place trades.
It does NOT connect to MT5/Exness.
It does NOT modify V4.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd


# ============================================================
# CONSTANTS
# ============================================================

MIN_BARS = 300

ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50

RSI_PERIOD = 14

SWING_LOOKBACK = 8
LIQUIDITY_LOOKBACK = 20

ATR_BASELINE_LOOKBACK = 50

BREAKOUT_LOOKBACK = 20

RANGE_LOOKBACK = 20

REGIME_SCORE_THRESHOLD = 2.0


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class StrategySignal:
    timestamp: str
    strategy: str
    direction: str
    score: float
    reason: str


# ============================================================
# DATA LOADING
# ============================================================

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}

    for column in df.columns:
        name = str(column).strip().lower()

        if name in {"date", "datetime", "time", "timestamp"}:
            mapping[column] = "timestamp"

        elif name in {"open", "o"}:
            mapping[column] = "open"

        elif name in {"high", "h"}:
            mapping[column] = "high"

        elif name in {"low", "l"}:
            mapping[column] = "low"

        elif name in {"close", "c"}:
            mapping[column] = "close"

        elif name in {"volume", "vol", "tick_volume"}:
            mapping[column] = "volume"

    return df.rename(columns=mapping)


def load_data(path: Path) -> pd.DataFrame:

    if not path.exists():
        raise FileNotFoundError(
            f"Input file not found: {path}"
        )

    df = pd.read_csv(path)

    df = normalize_columns(df)

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
        errors="coerce",
        utc=True,
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

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(
            df["volume"],
            errors="coerce",
        )
    else:
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

    if len(df) < MIN_BARS:
        raise ValueError(
            f"Only {len(df)} candles found. "
            f"At least {MIN_BARS} are required."
        )

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(
    df: pd.DataFrame,
) -> pd.DataFrame:

    x = df.copy()

    close = x["close"]

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    x["ema20"] = (
        close
        .ewm(
            span=EMA_FAST,
            adjust=False,
        )
        .mean()
    )

    x["ema50"] = (
        close
        .ewm(
            span=EMA_SLOW,
            adjust=False,
        )
        .mean()
    )

    # --------------------------------------------------------
    # TRUE RANGE / ATR
    # --------------------------------------------------------

    previous_close = close.shift(1)

    tr1 = x["high"] - x["low"]

    tr2 = (
        x["high"] - previous_close
    ).abs()

    tr3 = (
        x["low"] - previous_close
    ).abs()

    x["tr"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    x["atr14"] = (
        x["tr"]
        .rolling(ATR_PERIOD)
        .mean()
    )

    # --------------------------------------------------------
    # ATR REGIME
    # --------------------------------------------------------

    x["atr_median"] = (
        x["atr14"]
        .rolling(ATR_BASELINE_LOOKBACK)
        .median()
    )

    x["atr_ratio"] = (
        x["atr14"]
        / x["atr_median"]
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    delta = close.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = (
        gain
        .ewm(
            alpha=1 / RSI_PERIOD,
            adjust=False,
            min_periods=RSI_PERIOD,
        )
        .mean()
    )

    avg_loss = (
        loss
        .ewm(
            alpha=1 / RSI_PERIOD,
            adjust=False,
            min_periods=RSI_PERIOD,
        )
        .mean()
    )

    rs = (
        avg_gain
        / avg_loss.replace(0, np.nan)
    )

    x["rsi14"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    ema12 = (
        close
        .ewm(
            span=12,
            adjust=False,
        )
        .mean()
    )

    ema26 = (
        close
        .ewm(
            span=26,
            adjust=False,
        )
        .mean()
    )

    x["macd"] = (
        ema12 - ema26
    )

    x["macd_signal"] = (
        x["macd"]
        .ewm(
            span=9,
            adjust=False,
        )
        .mean()
    )

    x["macd_hist"] = (
        x["macd"]
        - x["macd_signal"]
    )

    # --------------------------------------------------------
    # STRUCTURE
    # --------------------------------------------------------

    x["previous_20_high"] = (
        x["high"]
        .shift(1)
        .rolling(
            LIQUIDITY_LOOKBACK
        )
        .max()
    )

    x["previous_20_low"] = (
        x["low"]
        .shift(1)
        .rolling(
            LIQUIDITY_LOOKBACK
        )
        .min()
    )

    x["previous_8_high"] = (
        x["high"]
        .shift(1)
        .rolling(
            SWING_LOOKBACK
        )
        .max()
    )

    x["previous_8_low"] = (
        x["low"]
        .shift(1)
        .rolling(
            SWING_LOOKBACK
        )
        .min()
    )

    # --------------------------------------------------------
    # BREAKOUT LEVELS
    # --------------------------------------------------------

    x["breakout_high"] = (
        x["high"]
        .shift(1)
        .rolling(
            BREAKOUT_LOOKBACK
        )
        .max()
    )

    x["breakout_low"] = (
        x["low"]
        .shift(1)
        .rolling(
            BREAKOUT_LOOKBACK
        )
        .min()
    )

    # --------------------------------------------------------
    # RANGE
    # --------------------------------------------------------

    x["range_high"] = (
        x["high"]
        .shift(1)
        .rolling(
            RANGE_LOOKBACK
        )
        .max()
    )

    x["range_low"] = (
        x["low"]
        .shift(1)
        .rolling(
            RANGE_LOOKBACK
        )
        .min()
    )

    x["range_width"] = (
        x["range_high"]
        - x["range_low"]
    )

    x["range_width_atr"] = (
        x["range_width"]
        / x["atr14"]
    )

    # --------------------------------------------------------
    # CANDLE STRUCTURE
    # --------------------------------------------------------

    x["candle_range"] = (
        x["high"]
        - x["low"]
    )

    x["body"] = (
        x["close"]
        - x["open"]
    ).abs()

    x["body_ratio"] = np.divide(
        x["body"],
        x["candle_range"],
        out=np.zeros(len(x)),
        where=x["candle_range"] > 0,
    )

    x["close_location"] = np.divide(
        x["close"] - x["low"],
        x["candle_range"],
        out=np.full(len(x), 0.5),
        where=x["candle_range"] > 0,
    )

    return x


# ============================================================
# REGIME DETECTION
# ============================================================

def detect_regime(row: pd.Series) -> str:

    required = [
        "close",
        "ema20",
        "ema50",
        "atr_ratio",
        "macd_hist",
        "range_width_atr",
    ]

    if any(
        pd.isna(row.get(field))
        for field in required
    ):
        return "TRANSITION"

    close = float(row["close"])
    ema20 = float(row["ema20"])
    ema50 = float(row["ema50"])

    atr_ratio = float(
        row["atr_ratio"]
    )

    macd_hist = float(
        row["macd_hist"]
    )

    range_width_atr = float(
        row["range_width_atr"]
    )

    bullish_points = 0
    bearish_points = 0

    # Trend structure
    if ema20 > ema50:
        bullish_points += 1

    if ema20 < ema50:
        bearish_points += 1

    if close > ema20:
        bullish_points += 1

    if close < ema20:
        bearish_points += 1

    # Momentum
    if macd_hist > 0:
        bullish_points += 1

    if macd_hist < 0:
        bearish_points += 1

    # Strong trend
    if (
        bullish_points >= 3
        and atr_ratio >= 0.85
    ):
        return "BULL_TREND"

    if (
        bearish_points >= 3
        and atr_ratio >= 0.85
    ):
        return "BEAR_TREND"

    # Volatility compression
    if atr_ratio < 0.70:
        return "VOLATILITY_COMPRESSION"

    # Volatility expansion
    if atr_ratio > 1.50:
        return "VOLATILITY_EXPANSION"

    # Range
    if range_width_atr < 6.0:
        return "RANGE"

    return "TRANSITION"


# ============================================================
# STRATEGY 1 — TREND CONTINUATION
# ============================================================

def trend_continuation(
    row: pd.Series,
    regime: str,
) -> List[StrategySignal]:

    signals = []

    if regime == "BULL_TREND":

        if (
            row["close"] > row["ema20"]
            and row["ema20"] > row["ema50"]
            and 52 <= row["rsi14"] <= 72
            and row["macd_hist"] > 0
        ):

            score = 70.0

            if row["close_location"] >= 0.65:
                score += 10

            signals.append(
                StrategySignal(
                    timestamp=row["timestamp"].isoformat(),
                    strategy="TREND_CONTINUATION",
                    direction="BUY",
                    score=min(score, 100),
                    reason=(
                        "bull_trend|"
                        "ema_alignment|"
                        "positive_momentum"
                    ),
                )
            )

    elif regime == "BEAR_TREND":

        if (
            row["close"] < row["ema20"]
            and row["ema20"] < row["ema50"]
            and 28 <= row["rsi14"] <= 48
            and row["macd_hist"] < 0
        ):

            score = 70.0

            if row["close_location"] <= 0.35:
                score += 10

            signals.append(
                StrategySignal(
                    timestamp=row["timestamp"].isoformat(),
                    strategy="TREND_CONTINUATION",
                    direction="SELL",
                    score=min(score, 100),
                    reason=(
                        "bear_trend|"
                        "ema_alignment|"
                        "negative_momentum"
                    ),
                )
            )

    return signals


# ============================================================
# STRATEGY 2 — PULLBACK / RETEST
# ============================================================

def pullback_retest(
    row: pd.Series,
    regime: str,
) -> List[StrategySignal]:

    signals = []

    if regime == "BULL_TREND":

        if (
            row["low"] <= row["ema20"]
            and row["close"] > row["ema20"]
            and row["close"] > row["ema50"]
            and row["rsi14"] >= 50
        ):

            score = 75.0

            if row["close_location"] >= 0.65:
                score += 10

            signals.append(
                StrategySignal(
                    timestamp=row["timestamp"].isoformat(),
                    strategy="PULLBACK_RETEST",
                    direction="BUY",
                    score=min(score, 100),
                    reason=(
                        "bull_trend|"
                        "ema20_reclaim|"
                        "pullback_rejection"
                    ),
                )
            )

    elif regime == "BEAR_TREND":

        if (
            row["high"] >= row["ema20"]
            and row["close"] < row["ema20"]
            and row["close"] < row["ema50"]
            and row["rsi14"] <= 50
        ):

            score = 75.0

            if row["close_location"] <= 0.35:
                score += 10

            signals.append(
                StrategySignal(
                    timestamp=row["timestamp"].isoformat(),
                    strategy="PULLBACK_RETEST",
                    direction="SELL",
                    score=min(score, 100),
                    reason=(
                        "bear_trend|"
                        "ema20_rejection|"
                        "pullback_rejection"
                    ),
                )
            )

    return signals


# ============================================================
# STRATEGY 3 — BREAKOUT
# ============================================================

def breakout(
    row: pd.Series,
    regime: str,
) -> List[StrategySignal]:

    signals = []

    if pd.isna(row["breakout_high"]):
        return signals

    if pd.isna(row["breakout_low"]):
        return signals

    # Long breakout
    if (
        row["close"]
        > row["breakout_high"]
        and row["body_ratio"] >= 0.50
        and row["close_location"] >= 0.70
        and row["atr_ratio"] >= 1.0
    ):

        score = 75.0

        if regime in {
            "BULL_TREND",
            "VOLATILITY_EXPANSION",
        }:
            score += 10

        signals.append(
            StrategySignal(
                timestamp=row["timestamp"].isoformat(),
                strategy="BREAKOUT",
                direction="BUY",
                score=min(score, 100),
                reason=(
                    "range_high_break|"
                    "strong_body|"
                    "volatility_expansion"
                ),
            )
        )

    # Short breakout
    if (
        row["close"]
        < row["breakout_low"]
        and row["body_ratio"] >= 0.50
        and row["close_location"] <= 0.30
        and row["atr_ratio"] >= 1.0
    ):

        score = 75.0

        if regime in {
            "BEAR_TREND",
            "VOLATILITY_EXPANSION",
        }:
            score += 10

        signals.append(
            StrategySignal(
                timestamp=row["timestamp"].isoformat(),
                strategy="BREAKOUT",
                direction="SELL",
                score=min(score, 100),
                reason=(
                    "range_low_break|"
                    "strong_body|"
                    "volatility_expansion"
                ),
            )
        )

    return signals


# ============================================================
# STRATEGY 4 — LIQUIDITY REVERSAL
# ============================================================

def liquidity_reversal(
    row: pd.Series,
    regime: str,
) -> List[StrategySignal]:

    signals = []

    # Sell-side liquidity sweep -> BUY
    if (
        row["low"]
        < row["previous_20_low"]
        and row["close"]
        > row["previous_20_low"]
        and row["close_location"] >= 0.65
    ):

        score = 70.0

        if row["rsi14"] <= 45:
            score += 10

        signals.append(
            StrategySignal(
                timestamp=row["timestamp"].isoformat(),
                strategy="LIQUIDITY_REVERSAL",
                direction="BUY",
                score=min(score, 100),
                reason=(
                    "sell_side_sweep|"
                    "reclaim|"
                    "bullish_rejection"
                ),
            )
        )

    # Buy-side liquidity sweep -> SELL
    if (
        row["high"]
        > row["previous_20_high"]
        and row["close"]
        < row["previous_20_high"]
        and row["close_location"] <= 0.35
    ):

        score = 70.0

        if row["rsi14"] >= 55:
            score += 10

        signals.append(
            StrategySignal(
                timestamp=row["timestamp"].isoformat(),
                strategy="LIQUIDITY_REVERSAL",
                direction="SELL",
                score=min(score, 100),
                reason=(
                    "buy_side_sweep|"
                    "rejection|"
                    "bearish_rejection"
                ),
            )
        )

    return signals


# ============================================================
# STRATEGY 5 — RANGE MEAN REVERSION
# ============================================================

def range_mean_reversion(
    row: pd.Series,
    regime: str,
) -> List[StrategySignal]:

    signals = []

    if regime != "RANGE":
        return signals

    if (
        row["close"] <= row["range_low"] + row["atr14"] * 0.75
        and row["rsi14"] <= 35
        and row["close_location"] >= 0.45
    ):

        signals.append(
            StrategySignal(
                timestamp=row["timestamp"].isoformat(),
                strategy="RANGE_MEAN_REVERSION",
                direction="BUY",
                score=75.0,
                reason=(
                    "range_low|"
                    "oversold|"
                    "rejection"
                ),
            )
        )

    if (
        row["close"] >= row["range_high"] - row["atr14"] * 0.75
        and row["rsi14"] >= 65
        and row["close_location"] <= 0.55
    ):

        signals.append(
            StrategySignal(
                timestamp=row["timestamp"].isoformat(),
                strategy="RANGE_MEAN_REVERSION",
                direction="SELL",
                score=75.0,
                reason=(
                    "range_high|"
                    "overbought|"
                    "rejection"
                ),
            )
        )

    return signals


# ============================================================
# STRATEGY 6 — MOMENTUM / VOLATILITY EXPANSION
# ============================================================

def momentum_expansion(
    row: pd.Series,
    regime: str,
) -> List[StrategySignal]:

    signals = []

    if regime != "VOLATILITY_EXPANSION":
        return signals

    # Bullish expansion
    if (
        row["close"] > row["open"]
        and row["body_ratio"] >= 0.60
        and row["close_location"] >= 0.75
        and row["rsi14"] >= 58
        and row["macd_hist"] > 0
    ):

        signals.append(
            StrategySignal(
                timestamp=row["timestamp"].isoformat(),
                strategy="MOMENTUM_EXPANSION",
                direction="BUY",
                score=80.0,
                reason=(
                    "volatility_expansion|"
                    "strong_bullish_body|"
                    "momentum_confirmation"
                ),
            )
        )

    # Bearish expansion
    if (
        row["close"] < row["open"]
        and row["body_ratio"] >= 0.60
        and row["close_location"] <= 0.25
        and row["rsi14"] <= 42
        and row["macd_hist"] < 0
    ):

        signals.append(
            StrategySignal(
                timestamp=row["timestamp"].isoformat(),
                strategy="MOMENTUM_EXPANSION",
                direction="SELL",
                score=80.0,
                reason=(
                    "volatility_expansion|"
                    "strong_bearish_body|"
                    "momentum_confirmation"
                ),
            )
        )

    return signals


# ============================================================
# STRATEGY DISPATCH
# ============================================================

STRATEGY_FUNCTIONS = {
    "TREND_CONTINUATION": trend_continuation,
    "PULLBACK_RETEST": pullback_retest,
    "BREAKOUT": breakout,
    "LIQUIDITY_REVERSAL": liquidity_reversal,
    "RANGE_MEAN_REVERSION": range_mean_reversion,
    "MOMENTUM_EXPANSION": momentum_expansion,
}


def evaluate_row(
    row: pd.Series,
) -> List[StrategySignal]:

    regime = detect_regime(row)

    signals = []

    for function in STRATEGY_FUNCTIONS.values():

        generated = function(
            row,
            regime,
        )

        signals.extend(generated)

    return signals


# ============================================================
# DATASET EVALUATION
# ============================================================

def evaluate_dataset(
    df: pd.DataFrame,
) -> pd.DataFrame:

    records = []

    for _, row in df.iterrows():

        regime = detect_regime(row)

        signals = evaluate_row(row)

        if signals:

            for signal in signals:

                records.append(
                    {
                        "timestamp": signal.timestamp,
                        "regime": regime,
                        "strategy": signal.strategy,
                        "direction": signal.direction,
                        "score": signal.score,
                        "reason": signal.reason,
                    }
                )

        else:

            records.append(
                {
                    "timestamp": row["timestamp"].isoformat(),
                    "regime": regime,
                    "strategy": "NONE",
                    "direction": "WAIT",
                    "score": 0.0,
                    "reason": "no_strategy_triggered",
                }
            )

    return pd.DataFrame(records)


# ============================================================
# DIAGNOSTICS
# ============================================================

def diagnostics(
    df: pd.DataFrame,
    signals: pd.DataFrame,
) -> Dict:

    regime_counts = (
        df["regime"]
        .value_counts()
        .to_dict()
    )

    strategy_counts = (
        signals[
            signals["strategy"] != "NONE"
        ]["strategy"]
        .value_counts()
        .to_dict()
    )

    direction_counts = (
        signals[
            signals["direction"] != "WAIT"
        ]["direction"]
        .value_counts()
        .to_dict()
    )

    regime_strategy = (
        signals[
            signals["strategy"] != "NONE"
        ]
        .groupby(
            ["regime", "strategy"]
        )
        .size()
        .to_dict()
    )

    return {
        "candles": len(df),
        "regimes": {
            str(k): int(v)
            for k, v in regime_counts.items()
        },
        "strategy_signals": {
            str(k): int(v)
            for k, v in strategy_counts.items()
        },
        "directions": {
            str(k): int(v)
            for k, v in direction_counts.items()
        },
        "regime_strategy_matrix": {
            f"{k[0]}::{k[1]}": int(v)
            for k, v in regime_strategy.items()
        },
    }


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Raymond V2.8 V5 strategy-family "
            "and regime engine"
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Normalized XAUUSD H1 CSV",
    )

    parser.add_argument(
        "--output-dir",
        default="backtest_results/weekly_growth_v5",
    )

    args = parser.parse_args()

    input_path = Path(
        args.input
    )

    output_dir = Path(
        args.output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "========================================"
    )

    print(
        "RAYMOND v2.8 V5 STRATEGY ENGINE"
    )

    print(
        "========================================"
    )

    print(
        "RESEARCH ONLY: YES"
    )

    print(
        "LIVE TRADING: NO"
    )

    print()

    print(
        f"Loading: {input_path}"
    )

    df = load_data(
        input_path
    )

    print(
        f"Loaded {len(df):,} candles."
    )

    print()

    print(
        "Calculating indicators..."
    )

    df = calculate_indicators(
        df
    )

    print(
        "Detecting market regimes..."
    )

    df["regime"] = [
        detect_regime(row)
        for _, row in df.iterrows()
    ]

    print(
        "Evaluating strategy families..."
    )

    signal_df = evaluate_dataset(
        df
    )

    # --------------------------------------------------------
    # SAVE REGIME DATA
    # --------------------------------------------------------

    regime_columns = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "ema20",
        "ema50",
        "atr14",
        "atr_ratio",
        "rsi14",
        "macd_hist",
        "range_width_atr",
        "regime",
    ]

    df[
        regime_columns
    ].to_csv(
        output_dir
        / "v5_regimes.csv",
        index=False,
    )

    # --------------------------------------------------------
    # SAVE SIGNALS
    # --------------------------------------------------------

    signal_df.to_csv(
        output_dir
        / "v5_strategy_signals.csv",
        index=False,
    )

    # --------------------------------------------------------
    # DIAGNOSTICS
    # --------------------------------------------------------

    report = diagnostics(
        df,
        signal_df,
    )

    with (
        output_dir
        / "v5_engine_diagnostics.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = []

    summary.append(
        "RAYMOND v2.8 V5 STRATEGY ENGINE"
    )

    summary.append(
        "================================"
    )

    summary.append(
        ""
    )

    summary.append(
        "Research only: YES"
    )

    summary.append(
        "Live trading: NO"
    )

    summary.append(
        ""
    )

    summary.append(
        f"Candles: {len(df):,}"
    )

    summary.append(
        ""
    )

    summary.append(
        "MARKET REGIMES"
    )

    summary.append(
        "--------------"
    )

    for regime, count in sorted(
        report["regimes"].items()
    ):

        summary.append(
            f"{regime}: {count:,}"
        )

    summary.append(
        ""
    )

    summary.append(
        "STRATEGY SIGNALS"
    )

    summary.append(
        "----------------"
    )

    for strategy, count in sorted(
        report[
            "strategy_signals"
        ].items()
    ):

        summary.append(
            f"{strategy}: {count:,}"
        )

    summary.append(
        ""
    )

    summary.append(
        "DIRECTION"
    )

    summary.append(
        "---------"
    )

    for direction, count in sorted(
        report[
            "directions"
        ].items()
    ):

        summary.append(
            f"{direction}: {count:,}"
        )

    summary.append(
        ""
    )

    summary.append(
        "IMPORTANT:"
    )

    summary.append(
        "This file only generates strategy candidates."
    )

    summary.append(
        "It does not calculate trading profit."
    )

    summary.append(
        "It does not perform optimization."
    )

    summary.append(
        "It does not place broker orders."
    )

    summary_text = "\n".join(
        summary
    )

    (
        output_dir
        / "summary.txt"
    ).write_text(
        summary_text,
        encoding="utf-8",
    )

    print()

    print(
        summary_text
    )

    print()

    print(
        "Results saved to:"
    )

    print(
        output_dir
    )


if __name__ == "__main__":
    main()
