#!/usr/bin/env python3
"""
RAYMOND v2.8 — WEEKLY GROWTH STRATEGY V1
=========================================

Research-only XAUUSD backtest engine.

Purpose
-------
Test whether a high-confluence XAUUSD H1 strategy can achieve a weekly
account-growth objective of >= 25% starting from a $1,000 account.

IMPORTANT
---------
- This is a BACKTEST / RESEARCH engine only.
- It does NOT place broker orders.
- It does NOT connect to MT5 or Exness.
- It does NOT enable live trading.
- A 25% weekly result is an objective for research, NOT a guarantee.
- Risk is deliberately capped and every trade must pass the strategy rules.

XAUUSD contract model
---------------------
CONTRACT_SIZE = 100 oz per 1.00 lot

Therefore:

PnL = (exit_price - entry_price) * lots * 100

For example:

2051.00 -> 2056.00
Move = $5.00
Lot = 0.02

PnL = 5 * 0.02 * 100 = $10

For SELL trades the price difference is reversed.

Data
----
The input CSV should contain at least:

timestamp
open
high
low
close

Optional:
volume

Timestamp should be parseable by pandas.

Example:

timestamp,open,high,low,close
2026-01-02 00:00:00,4320,4330,4310,4325
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ============================================================================
# XAUUSD CONTRACT
# ============================================================================

CONTRACT_SIZE = 100.0
TICK_SIZE = 0.01
TICK_VALUE_PER_LOT = 1.0


# ============================================================================
# DEFAULT STRATEGY CONFIGURATION
# ============================================================================

DEFAULT_STARTING_BALANCE = 1000.0

DEFAULT_RISK_PER_TRADE = 0.03
DEFAULT_WEEKLY_TARGET = 0.25
DEFAULT_WEEKLY_LOSS_LIMIT = -0.09

DEFAULT_MAX_TRADES_PER_WEEK = 6

DEFAULT_RISK_REWARD = 2.5

DEFAULT_ATR_PERIOD = 14
DEFAULT_EMA_FAST = 20
DEFAULT_EMA_SLOW = 50

DEFAULT_SWING_LOOKBACK = 8
DEFAULT_LIQUIDITY_LOOKBACK = 20

DEFAULT_ATR_STOP_MULTIPLIER = 1.20

DEFAULT_MIN_SIGNAL_SCORE = 75

DEFAULT_SPREAD = 0.30
DEFAULT_SLIPPAGE = 0.05

DEFAULT_MIN_ATR_RATIO = 0.70
DEFAULT_MAX_ATR_RATIO = 1.80

DEFAULT_MIN_VOLUME = 0.01
DEFAULT_MAX_VOLUME = 100.0
DEFAULT_VOLUME_STEP = 0.01


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class StrategyConfig:
    starting_balance: float = DEFAULT_STARTING_BALANCE

    risk_per_trade: float = DEFAULT_RISK_PER_TRADE

    weekly_target: float = DEFAULT_WEEKLY_TARGET
    weekly_loss_limit: float = DEFAULT_WEEKLY_LOSS_LIMIT

    max_trades_per_week: int = DEFAULT_MAX_TRADES_PER_WEEK

    risk_reward: float = DEFAULT_RISK_REWARD

    atr_period: int = DEFAULT_ATR_PERIOD
    ema_fast: int = DEFAULT_EMA_FAST
    ema_slow: int = DEFAULT_EMA_SLOW

    swing_lookback: int = DEFAULT_SWING_LOOKBACK
    liquidity_lookback: int = DEFAULT_LIQUIDITY_LOOKBACK

    atr_stop_multiplier: float = DEFAULT_ATR_STOP_MULTIPLIER

    min_signal_score: int = DEFAULT_MIN_SIGNAL_SCORE

    spread: float = DEFAULT_SPREAD
    slippage: float = DEFAULT_SLIPPAGE

    min_atr_ratio: float = DEFAULT_MIN_ATR_RATIO
    max_atr_ratio: float = DEFAULT_MAX_ATR_RATIO

    min_volume: float = DEFAULT_MIN_VOLUME
    max_volume: float = DEFAULT_MAX_VOLUME
    volume_step: float = DEFAULT_VOLUME_STEP


@dataclass
class Position:
    direction: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp

    entry_price: float
    stop_price: float
    target_price: float

    volume: float

    risk_amount: float
    risk_distance: float

    signal_score: int

    reason: str


@dataclass
class Trade:
    direction: str

    signal_time: str
    entry_time: str
    exit_time: str

    entry_price: float
    exit_price: float

    stop_price: float
    target_price: float

    volume: float

    risk_amount: float
    pnl: float

    r_multiple: float

    signal_score: int

    exit_reason: str
    setup_reason: str

    balance_before: float
    balance_after: float

    week: str


# ============================================================================
# ARGUMENTS
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Raymond v2.8 Weekly Growth Strategy V1 backtest"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to normalized H1 OHLC CSV",
    )

    parser.add_argument(
        "--output-dir",
        default="backtest_results/weekly_growth_v1",
        help="Directory for result files",
    )

    parser.add_argument(
        "--starting-balance",
        type=float,
        default=DEFAULT_STARTING_BALANCE,
    )

    parser.add_argument(
        "--risk-per-trade",
        type=float,
        default=DEFAULT_RISK_PER_TRADE,
    )

    parser.add_argument(
        "--weekly-target",
        type=float,
        default=DEFAULT_WEEKLY_TARGET,
    )

    parser.add_argument(
        "--weekly-loss-limit",
        type=float,
        default=DEFAULT_WEEKLY_LOSS_LIMIT,
    )

    parser.add_argument(
        "--max-trades-per-week",
        type=int,
        default=DEFAULT_MAX_TRADES_PER_WEEK,
    )

    parser.add_argument(
        "--risk-reward",
        type=float,
        default=DEFAULT_RISK_REWARD,
    )

    parser.add_argument(
        "--min-signal-score",
        type=int,
        default=DEFAULT_MIN_SIGNAL_SCORE,
    )

    parser.add_argument(
        "--spread",
        type=float,
        default=DEFAULT_SPREAD,
    )

    parser.add_argument(
        "--slippage",
        type=float,
        default=DEFAULT_SLIPPAGE,
    )

    return parser.parse_args()


# ============================================================================
# DATA LOADING
# ============================================================================

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize common OHLC column names.
    """

    mapping = {}

    for column in df.columns:
        normalized = str(column).strip().lower()

        if normalized in {"date", "datetime", "time", "timestamp"}:
            mapping[column] = "timestamp"

        elif normalized in {"open", "o"}:
            mapping[column] = "open"

        elif normalized in {"high", "h"}:
            mapping[column] = "high"

        elif normalized in {"low", "l"}:
            mapping[column] = "low"

        elif normalized in {"close", "c"}:
            mapping[column] = "close"

        elif normalized in {"volume", "vol", "tick_volume"}:
            mapping[column] = "volume"

    df = df.rename(columns=mapping)

    required = ["timestamp", "open", "high", "low", "close"]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}"
        )

    return df


def load_data(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    df = pd.read_csv(path)

    df = normalize_columns(df)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
        utc=True,
    )

    numeric_columns = ["open", "high", "low", "close"]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(
            df["volume"],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
        ]
    )

    df = df.sort_values("timestamp")

    df = df.drop_duplicates(
        subset=["timestamp"],
        keep="last",
    )

    df = df.reset_index(drop=True)

    if len(df) < 300:
        raise ValueError(
            f"Not enough candles for backtest. "
            f"Found {len(df)}, need at least 300."
        )

    return df


# ============================================================================
# INDICATORS
# ============================================================================

def calculate_indicators(
    df: pd.DataFrame,
    config: StrategyConfig,
) -> pd.DataFrame:
    df = df.copy()

    close = df["close"]

    # EMA
    df["ema20"] = close.ewm(
        span=config.ema_fast,
        adjust=False,
    ).mean()

    df["ema50"] = close.ewm(
        span=config.ema_slow,
        adjust=False,
    ).mean()

    # True Range
    previous_close = close.shift(1)

    tr1 = df["high"] - df["low"]

    tr2 = (df["high"] - previous_close).abs()

    tr3 = (df["low"] - previous_close).abs()

    df["tr"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    # ATR
    df["atr14"] = df["tr"].rolling(
        config.atr_period
    ).mean()

    # RSI
    delta = close.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    average_gain = gain.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    average_loss = loss.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    rs = average_gain / average_loss.replace(
        0,
        np.nan,
    )

    df["rsi14"] = 100 - (
        100 / (1 + rs)
    )

    # MACD
    ema12 = close.ewm(
        span=12,
        adjust=False,
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False,
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False,
    ).mean()

    df["macd_hist"] = (
        df["macd"] - df["macd_signal"]
    )

    # ATR regime ratio
    df["atr_median"] = df["atr14"].rolling(
        50
    ).median()

    df["atr_ratio"] = (
        df["atr14"] /
        df["atr_median"]
    )

    # Prior structure
    df["previous_20_high"] = df["high"].shift(1).rolling(
        config.liquidity_lookback
    ).max()

    df["previous_20_low"] = df["low"].shift(1).rolling(
        config.liquidity_lookback
    ).min()

    df["previous_8_high"] = df["high"].shift(1).rolling(
        config.swing_lookback
    ).max()

    df["previous_8_low"] = df["low"].shift(1).rolling(
        config.swing_lookback
    ).min()

    # H4 indicators
    h4 = (
        df.set_index("timestamp")
        .resample(
            "4h",
            label="right",
            closed="right",
        )
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
            }
        )
        .dropna()
    )

    h4["ema20"] = h4["close"].ewm(
        span=config.ema_fast,
        adjust=False,
    ).mean()

    h4["ema50"] = h4["close"].ewm(
        span=config.ema_slow,
        adjust=False,
    ).mean()

    h4["trend"] = np.where(
        (
            (h4["ema20"] > h4["ema50"])
            &
            (h4["close"] > h4["ema20"])
        ),
        "BULL",
        np.where(
            (
                (h4["ema20"] < h4["ema50"])
                &
                (h4["close"] < h4["ema20"])
            ),
            "BEAR",
            "NEUTRAL",
        ),
    )

    h4 = h4[
        ["ema20", "ema50", "close", "trend"]
    ].reset_index()

    df = pd.merge_asof(
        df.sort_values("timestamp"),
        h4.sort_values("timestamp"),
        on="timestamp",
        direction="backward",
        suffixes=("", "_h4"),
    )

    return df.reset_index(drop=True)


# ============================================================================
# SIGNAL SCORING
# ============================================================================

def score_signal(
    row: pd.Series,
    config: StrategyConfig,
) -> Tuple[str, int, str]:
    """
    Score only a completed H1 candle.

    The next candle is used for entry.

    This prevents same-candle lookahead.
    """

    required = [
        "close",
        "high",
        "low",
        "ema20",
        "ema50",
        "atr14",
        "rsi14",
        "macd_hist",
        "atr_ratio",
        "previous_20_high",
        "previous_20_low",
        "previous_8_high",
        "previous_8_low",
        "trend",
    ]

    for field in required:
        value = row.get(field)

        if pd.isna(value):
            return "WAIT", 0, "insufficient_indicator_data"

    close = float(row["close"])
    high = float(row["high"])
    low = float(row["low"])

    ema20 = float(row["ema20"])
    ema50 = float(row["ema50"])

    atr = float(row["atr14"])

    rsi = float(row["rsi14"])

    macd_hist = float(row["macd_hist"])

    atr_ratio = float(row["atr_ratio"])

    previous_high = float(
        row["previous_20_high"]
    )

    previous_low = float(
        row["previous_20_low"]
    )

    previous_swing_high = float(
        row["previous_8_high"]
    )

    previous_swing_low = float(
        row["previous_8_low"]
    )

    trend = str(row["trend"])

    # ------------------------------------------------------------------
    # VOLATILITY FILTER
    # ------------------------------------------------------------------

    volatility_ok = (
        config.min_atr_ratio
        <= atr_ratio
        <= config.max_atr_ratio
    )

    if not volatility_ok:
        return (
            "WAIT",
            0,
            "volatility_filter_failed",
        )

    # ------------------------------------------------------------------
    # BUY SCORE
    # ------------------------------------------------------------------

    buy_score = 0

    buy_reasons: List[str] = []

    # H4 regime
    if trend == "BULL":
        buy_score += 20
        buy_reasons.append("h4_bull_regime")

    # H1 structure
    if close > ema50:
        buy_score += 15
        buy_reasons.append("h1_above_ema50")

    # Pullback / reclaim
    if low <= ema20 and close > ema20:
        buy_score += 15
        buy_reasons.append("ema20_pullback_reclaim")

    # Liquidity sweep
    if (
        low < previous_low
        and close > previous_low
    ):
        buy_score += 15
        buy_reasons.append("sell_side_liquidity_sweep")

    # Momentum
    if (
        52 <= rsi <= 72
        and macd_hist > 0
    ):
        buy_score += 15
        buy_reasons.append("bullish_momentum")

    # Candle strength
    candle_range = high - low

    if candle_range > 0:
        close_location = (
            close - low
        ) / candle_range

        if close_location >= 0.65:
            buy_score += 10
            buy_reasons.append(
                "strong_bullish_close"
            )

    # ------------------------------------------------------------------
    # SELL SCORE
    # ------------------------------------------------------------------

    sell_score = 0

    sell_reasons: List[str] = []

    # H4 regime
    if trend == "BEAR":
        sell_score += 20
        sell_reasons.append("h4_bear_regime")

    # H1 structure
    if close < ema50:
        sell_score += 15
        sell_reasons.append("h1_below_ema50")

    # Pullback / rejection
    if high >= ema20 and close < ema20:
        sell_score += 15
        sell_reasons.append(
            "ema20_pullback_rejection"
        )

    # Liquidity sweep
    if (
        high > previous_high
        and close < previous_high
    ):
        sell_score += 15
        sell_reasons.append(
            "buy_side_liquidity_sweep"
        )

    # Momentum
    if (
        28 <= rsi <= 48
        and macd_hist < 0
    ):
        sell_score += 15
        sell_reasons.append(
            "bearish_momentum"
        )

    # Candle strength
    if candle_range > 0:
        close_location = (
            close - low
        ) / candle_range

        if close_location <= 0.35:
            sell_score += 10
            sell_reasons.append(
                "strong_bearish_close"
            )

    # ------------------------------------------------------------------
    # STRUCTURAL SAFETY CHECKS
    # ------------------------------------------------------------------

    # A BUY requires bullish H4 regime.
    # A SELL requires bearish H4 regime.
    if buy_score >= config.min_signal_score:
        return (
            "BUY",
            buy_score,
            "|".join(buy_reasons),
        )

    if sell_score >= config.min_signal_score:
        return (
            "SELL",
            sell_score,
            "|".join(sell_reasons),
        )

    return (
        "WAIT",
        max(buy_score, sell_score),
        "signal_threshold_not_reached",
    )


# ============================================================================
# POSITION SIZING
# ============================================================================

def round_down_volume(
    volume: float,
    config: StrategyConfig,
) -> float:
    if volume <= 0:
        return 0.0

    step = config.volume_step

    rounded = (
        math.floor(
            volume / step
        )
        * step
    )

    rounded = max(
        rounded,
        config.min_volume,
    )

    rounded = min(
        rounded,
        config.max_volume,
    )

    return round(rounded, 2)


def calculate_volume_for_risk(
    balance: float,
    risk_fraction: float,
    stop_distance: float,
    config: StrategyConfig,
) -> Tuple[float, float]:
    """
    Correct XAUUSD position sizing.

    Dollar risk per 1.00 lot:

        stop_distance * CONTRACT_SIZE

    Example:

        stop distance = $5
        1 lot = 100 oz

        risk = $5 * 100 = $500

    If account risk is $30:

        lots = 30 / 500 = 0.06
    """

    if balance <= 0:
        return 0.0, 0.0

    if stop_distance <= 0:
        return 0.0, 0.0

    risk_amount = (
        balance * risk_fraction
    )

    risk_per_one_lot = (
        stop_distance
        * CONTRACT_SIZE
    )

    if risk_per_one_lot <= 0:
        return 0.0, 0.0

    raw_volume = (
        risk_amount
        / risk_per_one_lot
    )

    volume = round_down_volume(
        raw_volume,
        config,
    )

    if volume <= 0:
        return 0.0, 0.0

    actual_risk = (
        stop_distance
        * volume
        * CONTRACT_SIZE
    )

    return volume, actual_risk


# ============================================================================
# EXECUTION PRICES
# ============================================================================

def get_entry_price(
    direction: str,
    market_open: float,
    config: StrategyConfig,
) -> float:
    """
    Simplified spread + slippage model.

    BUY:
        pay above market

    SELL:
        receive below market
    """

    half_spread = (
        config.spread / 2.0
    )

    if direction == "BUY":
        return (
            market_open
            + half_spread
            + config.slippage
        )

    return (
        market_open
        - half_spread
        - config.slippage
    )


def get_exit_price(
    direction: str,
    raw_price: float,
    config: StrategyConfig,
) -> float:
    """
    Simplified exit spread/slippage model.
    """

    half_spread = (
        config.spread / 2.0
    )

    if direction == "BUY":
        return (
            raw_price
            - half_spread
            - config.slippage
        )

    return (
        raw_price
        + half_spread
        + config.slippage
    )


# ============================================================================
# P&L
# ============================================================================

def calculate_pnl(
    direction: str,
    entry_price: float,
    exit_price: float,
    volume: float,
) -> float:
    """
    Correct XAUUSD P&L.

    BUY:

        (exit - entry) * volume * 100

    SELL:

        (entry - exit) * volume * 100
    """

    if direction == "BUY":
        price_difference = (
            exit_price - entry_price
        )
    else:
        price_difference = (
            entry_price - exit_price
        )

    return (
        price_difference
        * volume
        * CONTRACT_SIZE
    )


# ============================================================================
# POSITION EXIT LOGIC
# ============================================================================

def determine_exit(
    position: Position,
    candle: pd.Series,
    config: StrategyConfig,
) -> Optional[Tuple[float, str]]:
    high = float(candle["high"])
    low = float(candle["low"])

    if position.direction == "BUY":

        stop_hit = (
            low <= position.stop_price
        )

        target_hit = (
            high >= position.target_price
        )

        if stop_hit and target_hit:
            # Conservative assumption:
            # stop is hit before target when both
            # occur in the same candle.
            return (
                position.stop_price,
                "STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST",
            )

        if stop_hit:
            return (
                position.stop_price,
                "STOP_LOSS",
            )

        if target_hit:
            return (
                position.target_price,
                "TAKE_PROFIT",
            )

    else:

        stop_hit = (
            high >= position.stop_price
        )

        target_hit = (
            low <= position.target_price
        )

        if stop_hit and target_hit:
            return (
                position.stop_price,
                "STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST",
            )

        if stop_hit:
            return (
                position.stop_price,
                "STOP_LOSS",
            )

        if target_hit:
            return (
                position.target_price,
                "TAKE_PROFIT",
            )

    return None


# ============================================================================
# WEEKLY STATE
# ============================================================================

def week_key(timestamp: pd.Timestamp) -> str:
    iso = timestamp.isocalendar()

    return (
        f"{iso.year}-W"
        f"{int(iso.week):02d}"
    )


def new_week_state(
    balance: float,
) -> Dict:
    return {
        "start_balance": balance,
        "profit": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "break_evens": 0,
        "target_hit": False,
        "loss_limit_hit": False,
    }


# ============================================================================
# STRATEGY BACKTEST
# ============================================================================

def run_backtest(
    df: pd.DataFrame,
    config: StrategyConfig,
) -> Tuple[
    List[Trade],
    List[Dict],
    float,
]:
    """
    Run the complete weekly-growth strategy.

    Signal:
        completed H1 candle

    Entry:
        next H1 candle open

    Exit:
        stop or target

    Weekly entry restrictions:
        stop opening new positions after:
            >= weekly target
            <= weekly loss limit

    Existing positions are allowed to finish naturally.
    """

    balance = (
        config.starting_balance
    )

    trades: List[Trade] = []

    weekly_records: Dict[str, Dict] = {}

    position: Optional[Position] = None

    current_week: Optional[str] = None

    pending_signal: Optional[
        Tuple[
            str,
            int,
            str,
            pd.Timestamp,
        ]
    ] = None

    for i in range(1, len(df)):

        candle = df.iloc[i]

        timestamp = pd.Timestamp(
            candle["timestamp"]
        )

        this_week = week_key(timestamp)

        # --------------------------------------------------------------
        # CREATE WEEK
        # --------------------------------------------------------------

        if this_week != current_week:

            current_week = this_week

            if this_week not in weekly_records:
                weekly_records[this_week] = (
                    new_week_state(balance)
                )

            pending_signal = None

        week = weekly_records[
            this_week
        ]

        # --------------------------------------------------------------
        # FIRST: MANAGE EXISTING POSITION
        # --------------------------------------------------------------

        if position is not None:

            exit_result = determine_exit(
                position,
                candle,
                config,
            )

            if exit_result is not None:

                raw_exit_price, exit_reason = (
                    exit_result
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

                if (
                    position.risk_amount
                    > 0
                ):
                    r_multiple = (
                        pnl
                        / position.risk_amount
                    )
                else:
                    r_multiple = 0.0

                if pnl > 0:
                    week["wins"] += 1

                elif pnl < 0:
                    week["losses"] += 1

                else:
                    week["break_evens"] += 1

                # Profit is attributed to the week
                # in which the trade closes.
                week["profit"] += pnl

                trade = Trade(
                    direction=position.direction,

                    signal_time=(
                        position.signal_time
                        .isoformat()
                    ),

                    entry_time=(
                        position.entry_time
                        .isoformat()
                    ),

                    exit_time=(
                        timestamp.isoformat()
                    ),

                    entry_price=(
                        position.entry_price
                    ),

                    exit_price=exit_price,

                    stop_price=(
                        position.stop_price
                    ),

                    target_price=(
                        position.target_price
                    ),

                    volume=position.volume,

                    risk_amount=(
                        position.risk_amount
                    ),

                    pnl=pnl,

                    r_multiple=r_multiple,

                    signal_score=(
                        position.signal_score
                    ),

                    exit_reason=exit_reason,

                    setup_reason=(
                        position.reason
                    ),

                    balance_before=(
                        balance_before
                    ),

                    balance_after=(
                        balance
                    ),

                    week=this_week,
                )

                trades.append(trade)

                week["trades"] += 1

                position = None

                # Do not use the same candle to
                # generate a new entry.
                pending_signal = None

                continue

        # --------------------------------------------------------------
        # ENTRY SIGNAL FROM PREVIOUS COMPLETED CANDLE
        # --------------------------------------------------------------

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

            weekly_return = (
                (
                    balance
                    - week["start_balance"]
                )
                / week["start_balance"]
                if week["start_balance"] > 0
                else 0.0
            )

            # Stop opening new trades after
            # weekly target has been achieved.
            if (
                weekly_return
                >= config.weekly_target
            ):
                week["target_hit"] = True
                pending_signal = None

            # Stop opening new trades after
            # weekly loss limit.
            elif (
                weekly_return
                <= config.weekly_loss_limit
            ):
                week["loss_limit_hit"] = True
                pending_signal = None

            # Max weekly entries.
            elif (
                week["trades"]
                >= config.max_trades_per_week
            ):
                pending_signal = None

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
                    candle["previous_8_low"]
                )

                swing_high = float(
                    candle["previous_8_high"]
                )

                # --------------------------------------------------
                # STOP CALCULATION
                # --------------------------------------------------

                if direction == "BUY":

                    atr_stop = (
                        entry_price
                        - (
                            atr
                            * config.atr_stop_multiplier
                        )
                    )

                    structural_stop = (
                        swing_low
                        - (
                            atr * 0.10
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

                else:

                    atr_stop = (
                        entry_price
                        + (
                            atr
                            * config.atr_stop_multiplier
                        )
                    )

                    structural_stop = (
                        swing_high
                        + (
                            atr * 0.10
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

                # Safety check
                if (
                    not math.isfinite(
                        risk_distance
                    )
                    or risk_distance <= 0
                ):
                    pending_signal = None

                else:

                    volume, risk_amount = (
                        calculate_volume_for_risk(
                            balance,
                            config.risk_per_trade,
                            risk_distance,
                            config,
                        )
                    )

                    if volume <= 0:
                        pending_signal = None

                    else:

                        target_distance = (
                            risk_distance
                            * config.risk_reward
                        )

                        if direction == "BUY":

                            target_price = (
                                entry_price
                                + target_distance
                            )

                        else:

                            target_price = (
                                entry_price
                                - target_distance
                            )

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

        # --------------------------------------------------------------
        # GENERATE SIGNAL USING COMPLETED CANDLE
        # --------------------------------------------------------------

        # Current candle is now complete for purposes
        # of the next iteration.
        #
        # We generate a signal from candle i and
        # execute it on candle i+1.
        if i < len(df) - 1:

            signal_direction, score, reason = (
                score_signal(
                    candle,
                    config,
                )
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

    # ==================================================================
    # FORCE-CLOSE REMAINING POSITION AT FINAL CLOSE
    # ==================================================================

    if position is not None:

        final_candle = df.iloc[-1]

        timestamp = pd.Timestamp(
            final_candle["timestamp"]
        )

        this_week = week_key(timestamp)

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

        if this_week not in weekly_records:
            weekly_records[this_week] = (
                new_week_state(
                    balance_before
                )
            )

        week = weekly_records[
            this_week
        ]

        week["profit"] += pnl
        week["trades"] += 1

        if pnl > 0:
            week["wins"] += 1

        elif pnl < 0:
            week["losses"] += 1

        else:
            week["break_evens"] += 1

        trades.append(
            Trade(
                direction=position.direction,

                signal_time=(
                    position.signal_time.isoformat()
                ),

                entry_time=(
                    position.entry_time.isoformat()
                ),

                exit_time=(
                    timestamp.isoformat()
                ),

                entry_price=(
                    position.entry_price
                ),

                exit_price=exit_price,

                stop_price=(
                    position.stop_price
                ),

                target_price=(
                    position.target_price
                ),

                volume=position.volume,

                risk_amount=(
                    position.risk_amount
                ),

                pnl=pnl,

                r_multiple=r_multiple,

                signal_score=(
                    position.signal_score
                ),

                exit_reason="END_OF_DATA",

                setup_reason=(
                    position.reason
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

        position = None

    # ==================================================================
    # BUILD WEEKLY TABLE
    # ==================================================================

    weekly_rows: List[Dict] = []

    for key, state in weekly_records.items():

        start_balance = float(
            state["start_balance"]
        )

        profit = float(
            state["profit"]
        )

        end_balance = (
            start_balance + profit
        )

        if start_balance > 0:
            weekly_return = (
                profit
                / start_balance
            )
        else:
            weekly_return = 0.0

        target_hit = (
            weekly_return
            >= config.weekly_target
        )

        loss_limit_hit = (
            weekly_return
            <= config.weekly_loss_limit
        )

        weekly_rows.append(
            {
                "week": key,
                "start_balance": start_balance,
                "profit": profit,
                "end_balance": end_balance,
                "weekly_return": weekly_return,
                "weekly_return_pct": (
                    weekly_return * 100
                ),
                "trades": state["trades"],
                "wins": state["wins"],
                "losses": state["losses"],
                "break_evens": state[
                    "break_evens"
                ],
                "win_rate_pct": (
                    (
                        state["wins"]
                        / state["trades"]
                    )
                    * 100
                    if state["trades"] > 0
                    else 0.0
                ),
                "target_25pct_hit": (
                    target_hit
                ),
                "loss_limit_hit": (
                    loss_limit_hit
                ),
            }
        )

    weekly_rows.sort(
        key=lambda x: x["week"]
    )

    return (
        trades,
        weekly_rows,
        balance,
    )


# ============================================================================
# RESULT METRICS
# ============================================================================

def calculate_metrics(
    trades: List[Trade],
    weekly_rows: List[Dict],
    starting_balance: float,
    ending_balance: float,
    config: StrategyConfig,
) -> Dict:
    total_trades = len(trades)

    wins = sum(
        1
        for trade in trades
        if trade.pnl > 0
    )

    losses = sum(
        1
        for trade in trades
        if trade.pnl < 0
    )

    break_evens = (
        total_trades
        - wins
        - losses
    )

    total_profit = (
        ending_balance
        - starting_balance
    )

    total_return = (
        total_profit
        / starting_balance
        if starting_balance > 0
        else 0.0
    )

    gross_profit = sum(
        trade.pnl
        for trade in trades
        if trade.pnl > 0
    )

    gross_loss = sum(
        trade.pnl
        for trade in trades
        if trade.pnl < 0
    )

    profit_factor = (
        gross_profit
        / abs(gross_loss)
        if gross_loss < 0
        else math.inf
    )

    win_rate = (
        wins / total_trades
        if total_trades > 0
        else 0.0
    )

    weekly_target_hits = sum(
        1
        for row in weekly_rows
        if row["target_25pct_hit"]
    )

    total_weeks = len(
        weekly_rows
    )

    weekly_target_hit_rate = (
        weekly_target_hits
        / total_weeks
        if total_weeks > 0
        else 0.0
    )

    positive_weeks = sum(
        1
        for row in weekly_rows
        if row["profit"] > 0
    )

    negative_weeks = sum(
        1
        for row in weekly_rows
        if row["profit"] < 0
    )

    flat_weeks = (
        total_weeks
        - positive_weeks
        - negative_weeks
    )

    average_weekly_return = (
        float(
            np.mean(
                [
                    row["weekly_return"]
                    for row in weekly_rows
                ]
            )
        )
        if weekly_rows
        else 0.0
    )

    median_weekly_return = (
        float(
            np.median(
                [
                    row["weekly_return"]
                    for row in weekly_rows
                ]
            )
        )
        if weekly_rows
        else 0.0
    )

    best_week = max(
        weekly_rows,
        key=lambda x: x["weekly_return"],
        default=None,
    )

    worst_week = min(
        weekly_rows,
        key=lambda x: x["weekly_return"],
        default=None,
    )

    # --------------------------------------------------------------
    # MAX DRAWDOWN
    # --------------------------------------------------------------

    equity = starting_balance
    peak = starting_balance
    max_drawdown = 0.0

    for trade in trades:

        equity = trade.balance_after

        if equity > peak:
            peak = equity

        if peak > 0:
            drawdown = (
                equity - peak
            ) / peak

            if drawdown < max_drawdown:
                max_drawdown = drawdown

    # --------------------------------------------------------------
    # R MULTIPLES
    # --------------------------------------------------------------

    r_values = [
        trade.r_multiple
        for trade in trades
        if math.isfinite(
            trade.r_multiple
        )
    ]

    average_r = (
        float(np.mean(r_values))
        if r_values
        else 0.0
    )

    total_r = (
        float(np.sum(r_values))
        if r_values
        else 0.0
    )

    return {
        "starting_balance": starting_balance,
        "ending_balance": ending_balance,

        "total_profit": total_profit,

        "total_return": total_return,
        "total_return_pct": (
            total_return * 100
        ),

        "total_trades": total_trades,

        "wins": wins,
        "losses": losses,
        "break_evens": break_evens,

        "win_rate": win_rate,
        "win_rate_pct": (
            win_rate * 100
        ),

        "gross_profit": gross_profit,
        "gross_loss": gross_loss,

        "profit_factor": (
            None
            if math.isinf(
                profit_factor
            )
            else profit_factor
        ),

        "average_r": average_r,
        "total_r": total_r,

        "total_weeks": total_weeks,

        "positive_weeks": positive_weeks,
        "negative_weeks": negative_weeks,
        "flat_weeks": flat_weeks,

        "weekly_target": (
            config.weekly_target
        ),

        "weekly_target_pct": (
            config.weekly_target * 100
        ),

        "weekly_target_hits": (
            weekly_target_hits
        ),

        "weekly_target_hit_rate": (
            weekly_target_hit_rate
        ),

        "weekly_target_hit_rate_pct": (
            weekly_target_hit_rate * 100
        ),

        "average_weekly_return": (
            average_weekly_return
        ),

        "average_weekly_return_pct": (
            average_weekly_return * 100
        ),

        "median_weekly_return": (
            median_weekly_return
        ),

        "median_weekly_return_pct": (
            median_weekly_return * 100
        ),

        "best_week": (
            best_week["week"]
            if best_week
            else None
        ),

        "best_week_return_pct": (
            best_week[
                "weekly_return_pct"
            ]
            if best_week
            else None
        ),

        "worst_week": (
            worst_week["week"]
            if worst_week
            else None
        ),

        "worst_week_return_pct": (
            worst_week[
                "weekly_return_pct"
            ]
            if worst_week
            else None
        ),

        "max_drawdown": max_drawdown,

        "max_drawdown_pct": (
            max_drawdown * 100
        ),

        "contract_size": (
            CONTRACT_SIZE
        ),

        "tick_size": TICK_SIZE,

        "tick_value_per_lot": (
            TICK_VALUE_PER_LOT
        ),

        "risk_per_trade_pct": (
            config.risk_per_trade * 100
        ),

        "risk_reward": (
            config.risk_reward
        ),

        "max_trades_per_week": (
            config.max_trades_per_week
        ),
    }


# ============================================================================
# SAVE RESULTS
# ============================================================================

def save_results(
    output_dir: Path,
    trades: List[Trade],
    weekly_rows: List[Dict],
    metrics: Dict,
    config: StrategyConfig,
    input_path: Path,
    df: pd.DataFrame,
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------------
    # TRADES CSV
    # --------------------------------------------------------------

    trades_path = (
        output_dir
        / "trades.csv"
    )

    trade_rows = [
        asdict(trade)
        for trade in trades
    ]

    pd.DataFrame(
        trade_rows
    ).to_csv(
        trades_path,
        index=False,
    )

    # --------------------------------------------------------------
    # WEEKLY CSV
    # --------------------------------------------------------------

    weekly_path = (
        output_dir
        / "weekly.csv"
    )

    pd.DataFrame(
        weekly_rows
    ).to_csv(
        weekly_path,
        index=False,
    )

    # --------------------------------------------------------------
    # RESULT JSON
    # --------------------------------------------------------------

    result = {
        "status": "completed",

        "strategy": (
            "RAYMOND v2.8 "
            "WEEKLY GROWTH V1"
        ),

        "symbol": "XAUUSD",

        "timeframe": "H1",

        "research_only": True,

        "live_trading": False,

        "input_file": str(
            input_path
        ),

        "data_start": (
            df["timestamp"]
            .min()
            .isoformat()
        ),

        "data_end": (
            df["timestamp"]
            .max()
            .isoformat()
        ),

        "configuration": asdict(
            config
        ),

        "contract": {
            "contract_size": (
                CONTRACT_SIZE
            ),
            "tick_size": TICK_SIZE,
            "tick_value_per_lot": (
                TICK_VALUE_PER_LOT
            ),
            "pnl_formula": (
                "(exit-entry)"
                " * volume * 100"
                " for BUY; reverse "
                "for SELL"
            ),
        },

        "metrics": metrics,
    }

    result_path = (
        output_dir
        / "result.json"
    )

    with result_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            indent=2,
        )

    # --------------------------------------------------------------
    # HUMAN-READABLE SUMMARY
    # --------------------------------------------------------------

    summary_path = (
        output_dir
        / "summary.txt"
    )

    with summary_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            "RAYMOND v2.8 XAUUSD "
            "WEEKLY GROWTH V1\n"
        )

        file.write(
            "====================================\n\n"
        )

        file.write(
            "RESEARCH ONLY: YES\n"
        )

        file.write(
            "LIVE TRADING: NO\n\n"
        )

        file.write(
            f"Starting balance: "
            f"${metrics['starting_balance']:.2f}\n"
        )

        file.write(
            f"Ending balance: "
            f"${metrics['ending_balance']:.2f}\n"
        )

        file.write(
            f"Total profit: "
            f"${metrics['total_profit']:.2f}\n"
        )

        file.write(
            f"Total return: "
            f"{metrics['total_return_pct']:.2f}%\n"
        )

        file.write(
            f"Total trades: "
            f"{metrics['total_trades']}\n"
        )

        file.write(
            f"Wins: "
            f"{metrics['wins']}\n"
        )

        file.write(
            f"Losses: "
            f"{metrics['losses']}\n"
        )

        file.write(
            f"Break-even: "
            f"{metrics['break_evens']}\n"
        )

        file.write(
            f"Win rate: "
            f"{metrics['win_rate_pct']:.2f}%\n"
        )

        file.write(
            f"Profit factor: "
            f"{metrics['profit_factor']}\n"
        )

        file.write(
            f"Average R: "
            f"{metrics['average_r']:.3f}\n"
        )

        file.write(
            f"Total R: "
            f"{metrics['total_r']:.3f}\n"
        )

        file.write(
            f"Total weeks: "
            f"{metrics['total_weeks']}\n"
        )

        file.write(
            f"Positive weeks: "
            f"{metrics['positive_weeks']}\n"
        )

        file.write(
            f"Negative weeks: "
            f"{metrics['negative_weeks']}\n"
        )

        file.write(
            f"Flat weeks: "
            f"{metrics['flat_weeks']}\n"
        )

        file.write(
            f"Weekly target: "
            f"{metrics['weekly_target_pct']:.2f}%\n"
        )

        file.write(
            f"Weeks >= target: "
            f"{metrics['weekly_target_hits']}\n"
        )

        file.write(
            f"Target hit rate: "
            f"{metrics['weekly_target_hit_rate_pct']:.2f}%\n"
        )

        file.write(
            f"Average weekly return: "
            f"{metrics['average_weekly_return_pct']:.2f}%\n"
        )

        file.write(
            f"Median weekly return: "
            f"{metrics['median_weekly_return_pct']:.2f}%\n"
        )

        file.write(
            f"Best week: "
            f"{metrics['best_week']} "
            f"({metrics['best_week_return_pct']})\n"
        )

        file.write(
            f"Worst week: "
            f"{metrics['worst_week']} "
            f"({metrics['worst_week_return_pct']})\n"
        )

        file.write(
            f"Maximum drawdown: "
            f"{metrics['max_drawdown_pct']:.2f}%\n"
        )

        file.write(
            "\nXAUUSD P&L CONTRACT\n"
        )

        file.write(
            "------------------------------------\n"
        )

        file.write(
            f"Contract size: "
            f"{CONTRACT_SIZE} oz per lot\n"
        )

        file.write(
            f"Tick size: "
            f"{TICK_SIZE}\n"
        )

        file.write(
            f"Tick value per lot: "
            f"${TICK_VALUE_PER_LOT}\n"
        )

        file.write(
            "\nExample:\n"
        )

        file.write(
            "$2051 -> $2056 at 0.02 lot "
            "= $10 before costs.\n"
        )


# ============================================================================
# VALIDATION
# ============================================================================

def validate_config(
    config: StrategyConfig,
) -> None:
    if config.starting_balance <= 0:
        raise ValueError(
            "Starting balance must be > 0."
        )

    if not (
        0 < config.risk_per_trade <= 1
    ):
        raise ValueError(
            "Risk per trade must be between "
            "0 and 1."
        )

    if config.weekly_target <= 0:
        raise ValueError(
            "Weekly target must be > 0."
        )

    if config.weekly_loss_limit >= 0:
        raise ValueError(
            "Weekly loss limit must be "
            "negative."
        )

    if config.max_trades_per_week <= 0:
        raise ValueError(
            "Max trades per week must be > 0."
        )

    if config.risk_reward <= 0:
        raise ValueError(
            "Risk/reward must be > 0."
        )

    if config.min_signal_score < 0:
        raise ValueError(
            "Signal score cannot be negative."
        )

    if config.min_signal_score > 100:
        raise ValueError(
            "Signal score cannot exceed 100."
        )

    if config.spread < 0:
        raise ValueError(
            "Spread cannot be negative."
        )

    if config.slippage < 0:
        raise ValueError(
            "Slippage cannot be negative."
        )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    args = parse_args()

    config = StrategyConfig(
        starting_balance=(
            args.starting_balance
        ),

        risk_per_trade=(
            args.risk_per_trade
        ),

        weekly_target=(
            args.weekly_target
        ),

        weekly_loss_limit=(
            args.weekly_loss_limit
        ),

        max_trades_per_week=(
            args.max_trades_per_week
        ),

        risk_reward=(
            args.risk_reward
        ),

        min_signal_score=(
            args.min_signal_score
        ),

        spread=args.spread,

        slippage=args.slippage,
    )

    validate_config(config)

    input_path = Path(
        args.input
    )

    output_dir = Path(
        args.output_dir
    )

    print(
        "========================================"
    )

    print(
        "RAYMOND v2.8 "
        "WEEKLY GROWTH STRATEGY V1"
    )

    print(
        "========================================"
    )

    print(
        "Research-only backtest"
    )

    print(
        f"Input: {input_path}"
    )

    print(
        f"Starting balance: "
        f"${config.starting_balance:.2f}"
    )

    print(
        f"Weekly target: "
        f"{config.weekly_target * 100:.2f}%"
    )

    print(
        f"Risk per trade: "
        f"{config.risk_per_trade * 100:.2f}%"
    )

    print(
        f"Risk/reward: "
        f"{config.risk_reward:.2f}R"
    )

    print()

    # --------------------------------------------------------------
    # LOAD
    # --------------------------------------------------------------

    df = load_data(
        input_path
    )

    print(
        f"Loaded {len(df):,} candles."
    )

    print(
        f"Data start: "
        f"{df['timestamp'].min()}"
    )

    print(
        f"Data end: "
        f"{df['timestamp'].max()}"
    )

    # --------------------------------------------------------------
    # INDICATORS
    # --------------------------------------------------------------

    print(
        "Calculating indicators..."
    )

    df = calculate_indicators(
        df,
        config,
    )

    # --------------------------------------------------------------
    # BACKTEST
    # --------------------------------------------------------------

    print(
        "Running backtest..."
    )

    trades, weekly_rows, ending_balance = (
        run_backtest(
            df,
            config,
        )
    )

    # --------------------------------------------------------------
    # METRICS
    # --------------------------------------------------------------

    metrics = calculate_metrics(
        trades,
        weekly_rows,
        config.starting_balance,
        ending_balance,
        config,
    )

    # --------------------------------------------------------------
    # SAVE
    # --------------------------------------------------------------

    save_results(
        output_dir,
        trades,
        weekly_rows,
        metrics,
        config,
        input_path,
        df,
    )

    # --------------------------------------------------------------
    # CONSOLE SUMMARY
    # --------------------------------------------------------------

    print()
    print(
        "========================================"
    )
    print(
        "BACKTEST COMPLETE"
    )
    print(
        "========================================"
    )

    print(
        f"Starting balance: "
        f"${metrics['starting_balance']:.2f}"
    )

    print(
        f"Ending balance: "
        f"${metrics['ending_balance']:.2f}"
    )

    print(
        f"Total profit: "
        f"${metrics['total_profit']:.2f}"
    )

    print(
        f"Total return: "
        f"{metrics['total_return_pct']:.2f}%"
    )

    print(
        f"Trades: "
        f"{metrics['total_trades']}"
    )

    print(
        f"Win rate: "
        f"{metrics['win_rate_pct']:.2f}%"
    )

    print(
        f"Profit factor: "
        f"{metrics['profit_factor']}"
    )

    print(
        f"Average R: "
        f"{metrics['average_r']:.3f}"
    )

    print(
        f"Total R: "
        f"{metrics['total_r']:.3f}"
    )

    print(
        f"Weeks: "
        f"{metrics['total_weeks']}"
    )

    print(
        f"Positive weeks: "
        f"{metrics['positive_weeks']}"
    )

    print(
        f"Negative weeks: "
        f"{metrics['negative_weeks']}"
    )

    print(
        f"Weeks >= 25%: "
        f"{metrics['weekly_target_hits']}"
    )

    print(
        f"25% target hit rate: "
        f"{metrics['weekly_target_hit_rate_pct']:.2f}%"
    )

    print(
        f"Average weekly return: "
        f"{metrics['average_weekly_return_pct']:.2f}%"
    )

    print(
        f"Median weekly return: "
        f"{metrics['median_weekly_return_pct']:.2f}%"
    )

    print(
        f"Maximum drawdown: "
        f"{metrics['max_drawdown_pct']:.2f}%"
    )

    print()

    print(
        "Results saved to:"
    )

    print(
        f"{output_dir}"
    )

    print()

    print(
        "Files:"
    )

    print(
        "  result.json"
    )

    print(
        "  trades.csv"
    )

    print(
        "  weekly.csv"
    )

    print(
        "  summary.txt"
    )


if __name__ == "__main__":
    main()
