"""
RAYMOND V2.8 - V5 EXECUTION & BACKTEST ENGINE
===============================================

STEP 3 OF V5 RESEARCH ARCHITECTURE

Research-only XAUUSD execution/backtest engine.

IMPORTANT:
- No MT5 connection.
- No Exness connection.
- No broker orders.
- No live trading.
- No broker position modification.

CORE OBJECTIVES
---------------
1. Correct XAUUSD contract/P&L calculation.
2. Risk-based position sizing.
3. Spread and slippage.
4. Initial stop loss and take profit.
5. Persistent break-even.
6. Persistent trailing stop.
7. Persistent TP extension.
8. Weekly trade/risk controls.
9. Complete trade journal.
10. Equity curve and drawdown.
11. Yearly/monthly/weekly reporting.
12. Development/selection/holdout separation.

XAUUSD CONTRACT MODEL
---------------------
1.00 lot = 100 oz.

P&L:

    BUY  = (exit - entry) * 100 * lots
    SELL = (entry - exit) * 100 * lots

Example:

    2051 -> 2056
    0.02 lot

    5 * 100 * 0.02 = $10

LOOKAHEAD CONTROL
-----------------
Historical OHLC data cannot tell us the exact intrabar sequence.

Therefore the engine uses this order for an already-open position:

    1. Check the EXISTING stop/target.
    2. If touched, exit using the existing level.
    3. If not touched, update break-even/trailing/TP.
    4. Updated management levels become effective on the NEXT candle.

This prevents a candle from both creating a new trailing/BE level
and then using that newly-created level to exit itself.
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
# DEFAULTS
# ============================================================================

DEFAULT_DATA = (
    "data/historical/xauusd_h1_2024_2026_normalized.csv"
)

DEFAULT_OUTPUT = (
    "backtest_results/weekly_growth_v5"
)

STARTING_BALANCE = 1000.0

# XAUUSD:
# 1.00 lot = 100 ounces
CONTRACT_SIZE = 100.0

MIN_LOT = 0.01
MAX_LOT = 100.0
LOT_STEP = 0.01

SPREAD = 0.30
SLIPPAGE = 0.05

DEFAULT_RISK_PER_TRADE = 0.02

DEFAULT_RR = 2.5
DEFAULT_ATR_STOP = 1.2

DEFAULT_MAX_TRADES_PER_WEEK = 5

DEFAULT_BREAK_EVEN_R = 1.0
DEFAULT_BREAK_EVEN_LOCK_R = 0.0

DEFAULT_TRAILING_START_R = 2.0
DEFAULT_TRAILING_DISTANCE_R = 1.0

DEFAULT_MAX_WEEKLY_LOSS = -0.09

ENTRY_COOLDOWN_BARS = 1


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Position:
    direction: str
    strategy_family: str
    regime: str

    entry_time: str
    entry_price: float

    stop_price: float
    target_price: float

    initial_stop_distance: float

    lots: float
    risk_amount: float

    initial_target_r: float

    break_even_triggered: bool = False
    trailing_active: bool = False
    tp_extended: bool = False

    bars_held: int = 0


@dataclass
class Trade:
    entry_time: str
    exit_time: str

    strategy_family: str
    regime: str
    direction: str

    entry_price: float
    exit_price: float

    initial_stop: float
    initial_target: float

    final_stop: float
    final_target: float

    lots: float

    initial_risk_amount: float

    price_move: float
    gross_pnl: float

    spread_cost: float
    slippage_cost: float

    net_pnl: float

    r_multiple: float

    exit_reason: str

    break_even_triggered: bool
    trailing_used: bool
    tp_extended: bool

    bars_held: int


# ============================================================================
# XAUUSD CONTRACT MODEL
# ============================================================================

def calculate_xauusd_pnl(
    entry_price: float,
    exit_price: float,
    lots: float,
    direction: str,
    contract_size: float = CONTRACT_SIZE,
) -> float:
    """
    Correct XAUUSD P&L.

    BUY:
        (exit - entry) * contract_size * lots

    SELL:
        (entry - exit) * contract_size * lots
    """

    if direction == "BUY":
        difference = exit_price - entry_price

    elif direction == "SELL":
        difference = entry_price - exit_price

    else:
        raise ValueError(
            f"Invalid direction: {direction}"
        )

    return (
        difference
        * contract_size
        * lots
    )


def round_lots(
    lots: float,
    min_lot: float = MIN_LOT,
    max_lot: float = MAX_LOT,
    lot_step: float = LOT_STEP,
) -> float:
    """
    Round down to broker lot step.
    """

    if lots <= 0:
        return 0.0

    lots = min(
        max(lots, min_lot),
        max_lot,
    )

    steps = math.floor(
        lots / lot_step + 1e-12
    )

    rounded = steps * lot_step

    rounded = min(
        max(rounded, min_lot),
        max_lot,
    )

    return round(
        rounded,
        8,
    )


def calculate_lot_size(
    balance: float,
    risk_fraction: float,
    stop_distance: float,
    contract_size: float = CONTRACT_SIZE,
) -> Tuple[float, float]:
    """
    Risk-based XAUUSD sizing.

    Risk per one lot:

        stop_distance * 100

    Lots:

        requested risk / risk per one lot
    """

    if (
        balance <= 0
        or risk_fraction <= 0
        or stop_distance <= 0
    ):
        return 0.0, 0.0

    requested_risk = (
        balance * risk_fraction
    )

    risk_per_one_lot = (
        stop_distance * contract_size
    )

    if risk_per_one_lot <= 0:
        return 0.0, 0.0

    raw_lots = (
        requested_risk /
        risk_per_one_lot
    )

    lots = round_lots(
        raw_lots
    )

    actual_risk = (
        stop_distance
        * contract_size
        * lots
    )

    return lots, actual_risk


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
            "Missing required columns: "
            f"{missing}"
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
# INDICATORS
# ============================================================================

def calculate_indicators(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    close = df["close"]

    df["ema20"] = (
        close
        .ewm(
            span=20,
            adjust=False,
        )
        .mean()
    )

    df["ema50"] = (
        close
        .ewm(
            span=50,
            adjust=False,
        )
        .mean()
    )

    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            df["high"] - df["low"],

            (
                df["high"] -
                previous_close
            ).abs(),

            (
                df["low"] -
                previous_close
            ).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["atr14"] = (
        true_range
        .rolling(14)
        .mean()
    )

    df["atr50"] = (
        true_range
        .rolling(50)
        .mean()
    )

    df["atr_ratio"] = (
        df["atr14"] /
        df["atr50"].replace(
            0,
            np.nan,
        )
    )

    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain
        .rolling(14)
        .mean()
    )

    avg_loss = (
        loss
        .rolling(14)
        .mean()
    )

    rs = (
        avg_gain /
        avg_loss.replace(
            0,
            np.nan,
        )
    )

    df["rsi14"] = (
        100 -
        (
            100 /
            (1 + rs)
        )
    )

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

    df["macd"] = (
        ema12 - ema26
    )

    df["macd_signal"] = (
        df["macd"]
        .ewm(
            span=9,
            adjust=False,
        )
        .mean()
    )

    df["range_high"] = (
        df["high"]
        .rolling(20)
        .max()
        .shift(1)
    )

    df["range_low"] = (
        df["low"]
        .rolling(20)
        .min()
        .shift(1)
    )

    return df


# ============================================================================
# REGIME
# ============================================================================

def detect_regime(
    row: pd.Series,
) -> str:

    required = [
        row.get("ema20"),
        row.get("ema50"),
        row.get("atr_ratio"),
        row.get("close"),
    ]

    if any(
        pd.isna(value)
        for value in required
    ):
        return "TRANSITION"

    ema20 = row["ema20"]
    ema50 = row["ema50"]
    close = row["close"]
    atr_ratio = row["atr_ratio"]

    distance = (
        abs(ema20 - ema50) /
        max(abs(close), 1e-9)
    )

    if atr_ratio < 0.70:
        return "VOLATILITY_COMPRESSION"

    if atr_ratio > 1.50:
        return "VOLATILITY_EXPANSION"

    if (
        ema20 > ema50
        and close > ema50
        and distance > 0.001
    ):
        return "BULL_TREND"

    if (
        ema20 < ema50
        and close < ema50
        and distance > 0.001
    ):
        return "BEAR_TREND"

    if distance < 0.001:
        return "RANGE"

    return "TRANSITION"


# ============================================================================
# SIGNAL ENGINE
# ============================================================================

def generate_signal(
    row: pd.Series,
    strategy_family: str,
    regime: str,
    minimum_score: float,
) -> Tuple[str, float]:

    actual_regime = detect_regime(
        row
    )

    if actual_regime != regime:
        return "WAIT", 0.0

    values = [
        row.get("close"),
        row.get("ema20"),
        row.get("ema50"),
        row.get("rsi14"),
        row.get("macd"),
        row.get("macd_signal"),
    ]

    if any(
        pd.isna(value)
        for value in values
    ):
        return "WAIT", 0.0

    close = row["close"]
    ema20 = row["ema20"]
    ema50 = row["ema50"]
    rsi = row["rsi14"]
    macd = row["macd"]
    macd_signal = row["macd_signal"]

    buy_score = 0.0
    sell_score = 0.0

    # ------------------------------------------------------------------
    # TREND CONTINUATION
    # ------------------------------------------------------------------

    if strategy_family == "TREND_CONTINUATION":

        if regime == "BULL_TREND":

            buy_score = 30

            if close > ema20:
                buy_score += 20

            if macd > macd_signal:
                buy_score += 20

            if 52 <= rsi <= 72:
                buy_score += 20

        elif regime == "BEAR_TREND":

            sell_score = 30

            if close < ema20:
                sell_score += 20

            if macd < macd_signal:
                sell_score += 20

            if 28 <= rsi <= 48:
                sell_score += 20

    # ------------------------------------------------------------------
    # PULLBACK RETEST
    # ------------------------------------------------------------------

    elif strategy_family == "PULLBACK_RETEST":

        if regime == "BULL_TREND":

            if close > ema50:
                buy_score += 25

            if close >= ema20:
                buy_score += 25

            if macd >= macd_signal:
                buy_score += 20

            if 45 <= rsi <= 65:
                buy_score += 20

        elif regime == "BEAR_TREND":

            if close < ema50:
                sell_score += 25

            if close <= ema20:
                sell_score += 25

            if macd <= macd_signal:
                sell_score += 20

            if 35 <= rsi <= 55:
                sell_score += 20

    # ------------------------------------------------------------------
    # BREAKOUT
    # ------------------------------------------------------------------

    elif strategy_family == "BREAKOUT":

        range_high = row.get(
            "range_high"
        )

        range_low = row.get(
            "range_low"
        )

        if (
            pd.notna(range_high)
            and close > range_high
        ):

            buy_score = 50

            if macd > macd_signal:
                buy_score += 20

            if rsi > 55:
                buy_score += 20

        elif (
            pd.notna(range_low)
            and close < range_low
        ):

            sell_score = 50

            if macd < macd_signal:
                sell_score += 20

            if rsi < 45:
                sell_score += 20

    # ------------------------------------------------------------------
    # LIQUIDITY REVERSAL
    # ------------------------------------------------------------------

    elif strategy_family == "LIQUIDITY_REVERSAL":

        range_high = row.get(
            "range_high"
        )

        range_low = row.get(
            "range_low"
        )

        if (
            pd.notna(range_low)
            and row["low"] < range_low
            and close > range_low
        ):

            buy_score = 55

            if rsi < 45:
                buy_score += 20

            if macd > macd_signal:
                buy_score += 15

        elif (
            pd.notna(range_high)
            and row["high"] > range_high
            and close < range_high
        ):

            sell_score = 55

            if rsi > 55:
                sell_score += 20

            if macd < macd_signal:
                sell_score += 15

    # ------------------------------------------------------------------
    # RANGE MEAN REVERSION
    # ------------------------------------------------------------------

    elif strategy_family == "RANGE_MEAN_REVERSION":

        if regime == "RANGE":

            range_high = row.get(
                "range_high"
            )

            range_low = row.get(
                "range_low"
            )

            if (
                pd.notna(range_low)
                and close <= range_low * 1.001
                and rsi < 40
            ):

                buy_score = 70

                if macd > macd_signal:
                    buy_score += 20

            elif (
                pd.notna(range_high)
                and close >= range_high * 0.999
                and rsi > 60
            ):

                sell_score = 70

                if macd < macd_signal:
                    sell_score += 20

    # ------------------------------------------------------------------
    # MOMENTUM EXPANSION
    # ------------------------------------------------------------------

    elif strategy_family == "MOMENTUM_EXPANSION":

        if regime == "VOLATILITY_EXPANSION":

            if (
                close > ema20
                and ema20 > ema50
                and macd > macd_signal
                and rsi > 55
            ):

                buy_score = 90

            elif (
                close < ema20
                and ema20 < ema50
                and macd < macd_signal
                and rsi < 45
            ):

                sell_score = 90

    if buy_score >= minimum_score:
        return (
            "BUY",
            min(buy_score, 100),
        )

    if sell_score >= minimum_score:
        return (
            "SELL",
            min(sell_score, 100),
        )

    return "WAIT", 0.0


# ============================================================================
# EXECUTION PRICING
# ============================================================================

def get_entry_price(
    market_price: float,
    direction: str,
    spread: float,
    slippage: float,
) -> float:

    half_spread = spread / 2.0

    if direction == "BUY":

        return (
            market_price
            + half_spread
            + slippage
        )

    return (
        market_price
        - half_spread
        - slippage
    )


def get_exit_price(
    market_price: float,
    direction: str,
    spread: float,
    slippage: float,
) -> float:

    half_spread = spread / 2.0

    if direction == "BUY":

        return (
            market_price
            - half_spread
            - slippage
        )

    return (
        market_price
        + half_spread
        + slippage
    )


# ============================================================================
# POSITION MANAGEMENT
# ============================================================================

def update_position(
    position: Position,
    row: pd.Series,
    break_even_r: float,
    break_even_lock_r: float,
    trailing_start_r: float,
    trailing_distance_r: float,
    allow_tp_extension: bool = True,
) -> None:
    """
    Apply management rules AFTER the existing SL/TP has been checked.

    This means levels created from this candle cannot be used to exit
    the same candle.
    """

    high = float(row["high"])
    low = float(row["low"])

    risk_distance = (
        position.initial_stop_distance
    )

    # BUY
    if position.direction == "BUY":

        # Break-even
        if (
            not position.break_even_triggered
            and high >= (
                position.entry_price
                + risk_distance
                * break_even_r
            )
        ):

            position.stop_price = max(
                position.stop_price,
                position.entry_price
                + risk_distance
                * break_even_lock_r,
            )

            position.break_even_triggered = True

        # TP extension
        if (
            allow_tp_extension
            and not position.tp_extended
            and high >= (
                position.entry_price
                + risk_distance * 2.0
            )
        ):

            position.target_price = (
                position.entry_price
                + risk_distance
                * max(
                    position.initial_target_r,
                    3.0,
                )
            )

            position.tp_extended = True

        # Trailing
        if high >= (
            position.entry_price
            + risk_distance
            * trailing_start_r
        ):

            new_stop = (
                high
                - risk_distance
                * trailing_distance_r
            )

            if new_stop > position.stop_price:

                position.stop_price = new_stop
                position.trailing_active = True

    # SELL
    else:

        # Break-even
        if (
            not position.break_even_triggered
            and low <= (
                position.entry_price
                - risk_distance
                * break_even_r
            )
        ):

            position.stop_price = min(
                position.stop_price,
                position.entry_price
                - risk_distance
                * break_even_lock_r,
            )

            position.break_even_triggered = True

        # TP extension
        if (
            allow_tp_extension
            and not position.tp_extended
            and low <= (
                position.entry_price
                - risk_distance * 2.0
            )
        ):

            position.target_price = (
                position.entry_price
                - risk_distance
                * max(
                    position.initial_target_r,
                    3.0,
                )
            )

            position.tp_extended = True

        # Trailing
        if low <= (
            position.entry_price
            - risk_distance
            * trailing_start_r
        ):

            new_stop = (
                low
                + risk_distance
                * trailing_distance_r
            )

            if new_stop < position.stop_price:

                position.stop_price = new_stop
                position.trailing_active = True


# ============================================================================
# EXIT CHECK
# ============================================================================

def check_exit(
    position: Position,
    row: pd.Series,
) -> Optional[Tuple[float, str]]:
    """
    Check only the EXISTING SL and TP.

    No newly-created BE/trailing level is applied here.
    """

    high = float(row["high"])
    low = float(row["low"])

    if position.direction == "BUY":

        stop_hit = (
            low <= position.stop_price
        )

        target_hit = (
            high >= position.target_price
        )

        # Conservative assumption when both are touched.
        if stop_hit:
            return (
                position.stop_price,
                "STOP",
            )

        if target_hit:
            return (
                position.target_price,
                "TARGET",
            )

    else:

        stop_hit = (
            high >= position.stop_price
        )

        target_hit = (
            low <= position.target_price
        )

        if stop_hit:
            return (
                position.stop_price,
                "STOP",
            )

        if target_hit:
            return (
                position.target_price,
                "TARGET",
            )

    return None


# ============================================================================
# TRADE CLOSE
# ============================================================================

def close_position(
    position: Position,
    timestamp: pd.Timestamp,
    market_exit: float,
    balance: float,
    spread: float,
    slippage: float,
) -> Tuple[Trade, float]:

    exit_price = get_exit_price(
        market_exit,
        position.direction,
        spread,
        slippage,
    )

    gross_pnl = calculate_xauusd_pnl(
        position.entry_price,
        exit_price,
        position.lots,
        position.direction,
    )

    # Diagnostic cost fields.
    #
    # Spread/slippage are already represented in the entry/exit prices,
    # therefore they MUST NOT be subtracted again.

    spread_cost = (
        spread
        * CONTRACT_SIZE
        * position.lots
    )

    slippage_cost = (
        slippage
        * 2.0
        * CONTRACT_SIZE
        * position.lots
    )

    net_pnl = gross_pnl

    risk_amount = position.risk_amount

    if risk_amount > 0:

        r_multiple = (
            net_pnl / risk_amount
        )

    else:

        r_multiple = 0.0

    if position.direction == "BUY":

        price_move = (
            exit_price -
            position.entry_price
        )

    else:

        price_move = (
            position.entry_price -
            exit_price
        )

    initial_stop = (
        position.entry_price
        - position.initial_stop_distance
        if position.direction == "BUY"
        else
        position.entry_price
        + position.initial_stop_distance
    )

    initial_target = (
        position.entry_price
        + position.initial_stop_distance
        * position.initial_target_r
        if position.direction == "BUY"
        else
        position.entry_price
        - position.initial_stop_distance
        * position.initial_target_r
    )

    if abs(
        exit_price -
        position.target_price
    ) < 1e-8:

        exit_reason = "TARGET"

    elif position.trailing_active:

        exit_reason = "STOP_OR_TRAIL"

    else:

        exit_reason = "STOP"

    trade = Trade(
        entry_time=position.entry_time,
        exit_time=timestamp.isoformat(),

        strategy_family=(
            position.strategy_family
        ),

        regime=position.regime,

        direction=position.direction,

        entry_price=position.entry_price,
        exit_price=exit_price,

        initial_stop=initial_stop,
        initial_target=initial_target,

        final_stop=position.stop_price,
        final_target=position.target_price,

        lots=position.lots,

        initial_risk_amount=(
            position.risk_amount
        ),

        price_move=price_move,

        gross_pnl=gross_pnl,

        spread_cost=spread_cost,

        slippage_cost=slippage_cost,

        net_pnl=net_pnl,

        r_multiple=r_multiple,

        exit_reason=exit_reason,

        break_even_triggered=(
            position.break_even_triggered
        ),

        trailing_used=(
            position.trailing_active
        ),

        tp_extended=(
            position.tp_extended
        ),

        bars_held=position.bars_held,
    )

    balance += net_pnl

    return trade, balance


# ============================================================================
# BACKTEST
# ============================================================================

def run_backtest(
    df: pd.DataFrame,
    strategy_family: str,
    regime: str,
    minimum_score: float,
    risk_reward: float,
    atr_stop_multiplier: float,
    risk_per_trade: float,
    max_trades_per_week: int,
    break_even_r: float,
    break_even_lock_r: float,
    trailing_start_r: float,
    trailing_distance_r: float,
    weekly_loss_limit: float,
    starting_balance: float,
    spread: float,
    slippage: float,
) -> Tuple[
    List[Trade],
    pd.DataFrame,
    Dict,
]:

    balance = float(
        starting_balance
    )

    peak_equity = float(
        starting_balance
    )

    position: Optional[Position] = None

    trades: List[Trade] = []

    equity_records = []

    weekly_trade_counts: Dict[str, int] = {}

    weekly_start_balance = (
        float(starting_balance)
    )

    current_week = None

    last_entry_index = -999999

    for index in range(
        60,
        len(df),
    ):

        row = df.iloc[index]

        timestamp = row["timestamp"]

        week_key = timestamp.strftime(
            "%Y-%W"
        )

        # --------------------------------------------------------------
        # NEW WEEK
        # --------------------------------------------------------------

        if current_week != week_key:

            current_week = week_key

            weekly_start_balance = balance

            weekly_trade_counts[
                week_key
            ] = 0

        # --------------------------------------------------------------
        # MANAGE OPEN POSITION
        # --------------------------------------------------------------
        #
        # IMPORTANT:
        #
        # 1. Check existing SL/TP first.
        # 2. If hit -> exit.
        # 3. If not hit -> apply BE/trailing/TP extension.
        #
        # This removes same-candle management lookahead.
        # --------------------------------------------------------------

        if position is not None:

            # Count the current candle as a held candle.
            position.bars_held += 1

            # FIRST: check the levels that existed before this candle.
            exit_result = check_exit(
                position,
                row,
            )

            if exit_result is not None:

                market_exit, reason = (
                    exit_result
                )

                trade, balance = (
                    close_position(
                        position=position,
                        timestamp=timestamp,
                        market_exit=market_exit,
                        balance=balance,
                        spread=spread,
                        slippage=slippage,
                    )
                )

                # Preserve the actual exit reason.
                if reason == "TARGET":

                    trade.exit_reason = "TARGET"

                else:

                    trade.exit_reason = (
                        "STOP_OR_TRAIL"
                        if position.trailing_active
                        else "STOP"
                    )

                trades.append(trade)

                position = None

            else:

                # SECOND: only after the existing levels survive,
                # update management for the NEXT candle.
                update_position(
                    position=position,
                    row=row,
                    break_even_r=break_even_r,
                    break_even_lock_r=break_even_lock_r,
                    trailing_start_r=trailing_start_r,
                    trailing_distance_r=trailing_distance_r,
                )

        # --------------------------------------------------------------
        # EQUITY RECORD
        # --------------------------------------------------------------

        if position is None:

            equity = balance

        else:

            mark_price = float(
                row["close"]
            )

            unrealized = (
                calculate_xauusd_pnl(
                    position.entry_price,
                    mark_price,
                    position.lots,
                    position.direction,
                )
            )

            equity = (
                balance +
                unrealized
            )

        peak_equity = max(
            peak_equity,
            equity,
        )

        drawdown_pct = (
            (
                peak_equity -
                equity
            )
            /
            peak_equity
            * 100
            if peak_equity > 0
            else 0.0
        )

        equity_records.append(
            {
                "timestamp": timestamp,
                "balance": balance,
                "equity": equity,
                "peak_equity": peak_equity,
                "drawdown_pct": drawdown_pct,
            }
        )

        # --------------------------------------------------------------
        # WEEKLY REALIZED LOSS LIMIT
        # --------------------------------------------------------------
        #
        # The weekly limit is based on REALIZED balance.
        #
        # Existing positions are still managed.
        # The limit blocks NEW entries only.
        # --------------------------------------------------------------

        if weekly_start_balance > 0:

            weekly_return = (
                balance -
                weekly_start_balance
            ) / weekly_start_balance

        else:

            weekly_return = 0.0

        weekly_loss_limit_hit = (
            weekly_return <=
            weekly_loss_limit
        )

        if weekly_loss_limit_hit:
            continue

        # --------------------------------------------------------------
        # DO NOT OPEN WHILE IN POSITION
        # --------------------------------------------------------------

        if position is not None:
            continue

        # --------------------------------------------------------------
        # COOLDOWN
        # --------------------------------------------------------------

        if (
            index -
            last_entry_index
            <= ENTRY_COOLDOWN_BARS
        ):
            continue

        # --------------------------------------------------------------
        # WEEKLY TRADE LIMIT
        # --------------------------------------------------------------

        trade_count = (
            weekly_trade_counts.get(
                week_key,
                0,
            )
        )

        if (
            trade_count >=
            max_trades_per_week
        ):
            continue

        # --------------------------------------------------------------
        # SIGNAL
        # --------------------------------------------------------------

        signal, score = (
            generate_signal(
                row=row,
                strategy_family=strategy_family,
                regime=regime,
                minimum_score=minimum_score,
            )
        )

        if signal not in {
            "BUY",
            "SELL",
        }:
            continue

        if score < minimum_score:
            continue

        atr = row["atr14"]

        if (
            pd.isna(atr)
            or atr <= 0
        ):
            continue

        # --------------------------------------------------------------
        # ENTRY
        # --------------------------------------------------------------

        market_price = float(
            row["close"]
        )

        entry_price = get_entry_price(
            market_price,
            signal,
            spread,
            slippage,
        )

        stop_distance = (
            float(atr)
            * atr_stop_multiplier
        )

        if stop_distance <= 0:
            continue

        if signal == "BUY":

            stop_price = (
                entry_price -
                stop_distance
            )

            target_price = (
                entry_price +
                stop_distance *
                risk_reward
            )

        else:

            stop_price = (
                entry_price +
                stop_distance
            )

            target_price = (
                entry_price -
                stop_distance *
                risk_reward
            )

        lots, actual_risk = (
            calculate_lot_size(
                balance=balance,
                risk_fraction=risk_per_trade,
                stop_distance=stop_distance,
            )
        )

        if lots < MIN_LOT:
            continue

        position = Position(
            direction=signal,

            strategy_family=(
                strategy_family
            ),

            regime=regime,

            entry_time=(
                timestamp.isoformat()
            ),

            entry_price=entry_price,

            stop_price=stop_price,

            target_price=target_price,

            initial_stop_distance=(
                stop_distance
            ),

            lots=lots,

            risk_amount=actual_risk,

            initial_target_r=(
                risk_reward
            ),
        )

        weekly_trade_counts[
            week_key
        ] = trade_count + 1

        last_entry_index = index

    # ------------------------------------------------------------------
    # FORCE CLOSE AT END OF DATA
    # ------------------------------------------------------------------

    if position is not None:

        last_row = df.iloc[-1]

        # The final market close is used as the forced exit.
        trade, balance = close_position(
            position=position,
            timestamp=last_row["timestamp"],
            market_exit=float(
                last_row["close"]
            ),
            balance=balance,
            spread=spread,
            slippage=slippage,
        )

        trade.exit_reason = "END_OF_DATA"

        trades.append(trade)

        position = None

    equity_df = pd.DataFrame(
        equity_records
    )

    metrics = calculate_metrics(
        trades=trades,
        equity_df=equity_df,
        starting_balance=starting_balance,
        ending_balance=balance,
    )

    return (
        trades,
        equity_df,
        metrics,
    )


# ============================================================================
# METRICS
# ============================================================================

def calculate_metrics(
    trades: List[Trade],
    equity_df: pd.DataFrame,
    starting_balance: float,
    ending_balance: float,
) -> Dict:

    if not trades:

        return {
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
            "ending_balance": ending_balance,
        }

    pnl = np.array(
        [
            trade.net_pnl
            for trade in trades
        ],
        dtype=float,
    )

    r_values = np.array(
        [
            trade.r_multiple
            for trade in trades
        ],
        dtype=float,
    )

    wins = int(
        (pnl > 1e-9).sum()
    )

    losses = int(
        (pnl < -1e-9).sum()
    )

    breakevens = int(
        (
            np.abs(pnl)
            <= 1e-9
        ).sum()
    )

    gross_profit = float(
        pnl[pnl > 0].sum()
    )

    gross_loss = float(
        pnl[pnl < 0].sum()
    )

    net_profit = float(
        pnl.sum()
    )

    trade_count = len(
        trades
    )

    win_rate = (
        wins /
        trade_count
        * 100
    )

    if gross_loss < 0:

        profit_factor = (
            gross_profit /
            abs(gross_loss)
        )

    else:

        profit_factor = (
            999.0
            if gross_profit > 0
            else 0.0
        )

    average_win = (
        float(
            pnl[pnl > 0].mean()
        )
        if wins
        else 0.0
    )

    average_loss = (
        float(
            pnl[pnl < 0].mean()
        )
        if losses
        else 0.0
    )

    expectancy = float(
        pnl.mean()
    )

    average_r = float(
        r_values.mean()
    )

    if (
        not equity_df.empty
        and "equity" in equity_df
    ):

        equity = (
            equity_df["equity"]
            .astype(float)
        )

        peak = equity.cummax()

        drawdown = (
            peak - equity
        )

        drawdown_pct = (
            drawdown /
            peak.replace(
                0,
                np.nan,
            )
            * 100
        )

        max_drawdown = float(
            drawdown.max()
        )

        max_drawdown_pct = float(
            drawdown_pct.max()
        )

    else:

        max_drawdown = 0.0
        max_drawdown_pct = 0.0

    return {
        "trades": trade_count,

        "wins": wins,

        "losses": losses,

        "breakevens": breakevens,

        "win_rate_pct": win_rate,

        "gross_profit": gross_profit,

        "gross_loss": gross_loss,

        "net_profit": net_profit,

        "return_pct": (
            (
                ending_balance -
                starting_balance
            )
            /
            starting_balance
            * 100
        ),

        "profit_factor": profit_factor,

        "expectancy": expectancy,

        "average_r": average_r,

        "average_win": average_win,

        "average_loss": average_loss,

        "max_drawdown": max_drawdown,

        "max_drawdown_pct": max_drawdown_pct,

        "ending_balance": ending_balance,
    }


# ============================================================================
# PERIOD REPORTS
# ============================================================================

def period_report(
    trades: List[Trade],
) -> pd.DataFrame:

    if not trades:
        return pd.DataFrame()

    rows = []

    for trade in trades:

        rows.append(
            {
                "timestamp": pd.to_datetime(
                    trade.exit_time,
                    utc=True,
                ),
                "pnl": trade.net_pnl,
                "r": trade.r_multiple,
                "strategy": (
                    trade.strategy_family
                ),
                "regime": trade.regime,
            }
        )

    df = pd.DataFrame(rows)

    df["year"] = (
        df["timestamp"]
        .dt.year
    )

    df["month"] = (
        df["timestamp"]
        .dt.to_period("M")
        .astype(str)
    )

    df["week"] = (
        df["timestamp"]
        .dt.strftime("%Y-%W")
    )

    return df


def summarize_periods(
    trades: List[Trade],
) -> Dict:

    report = period_report(
        trades
    )

    if report.empty:

        return {
            "years": {},
            "months": {},
            "weeks": {},
        }

    def aggregate(
        grouped,
    ):

        output = {}

        for name, group in grouped:

            pnl = float(
                group["pnl"].sum()
            )

            count = len(group)

            wins = int(
                (
                    group["pnl"] > 0
                ).sum()
            )

            output[str(name)] = {
                "trades": count,

                "wins": wins,

                "losses": int(
                    (
                        group["pnl"] < 0
                    ).sum()
                ),

                "net_pnl": pnl,

                "win_rate_pct": (
                    wins /
                    count
                    * 100
                    if count
                    else 0.0
                ),

                "average_r": float(
                    group["r"].mean()
                ),
            }

        return output

    return {
        "years": aggregate(
            report.groupby("year")
        ),

        "months": aggregate(
            report.groupby("month")
        ),

        "weeks": aggregate(
            report.groupby("week")
        ),
    }


# ============================================================================
# STRATEGY REPORT
# ============================================================================

def strategy_breakdown(
    trades: List[Trade],
) -> pd.DataFrame:

    if not trades:
        return pd.DataFrame()

    rows = []

    for trade in trades:

        rows.append(
            {
                "strategy": (
                    trade.strategy_family
                ),

                "regime": trade.regime,

                "pnl": trade.net_pnl,

                "r": trade.r_multiple,

                "win": (
                    trade.net_pnl > 0
                ),
            }
        )

    df = pd.DataFrame(rows)

    result = (
        df.groupby(
            [
                "strategy",
                "regime",
            ]
        )
        .agg(
            trades=("pnl", "size"),
            net_pnl=("pnl", "sum"),
            average_r=("r", "mean"),
            wins=("win", "sum"),
        )
        .reset_index()
    )

    result["win_rate_pct"] = (
        result["wins"] /
        result["trades"]
        * 100
    )

    return result


# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config(
    path: Optional[str],
) -> Dict:

    config = {
        "strategy_family":
            "TREND_CONTINUATION",

        "regime":
            "BULL_TREND",

        "minimum_score":
            60.0,

        "risk_reward":
            DEFAULT_RR,

        "atr_stop_multiplier":
            DEFAULT_ATR_STOP,

        "risk_per_trade":
            DEFAULT_RISK_PER_TRADE,

        "max_trades_per_week":
            DEFAULT_MAX_TRADES_PER_WEEK,

        "break_even_r":
            DEFAULT_BREAK_EVEN_R,

        "break_even_lock_r":
            DEFAULT_BREAK_EVEN_LOCK_R,

        "trailing_start_r":
            DEFAULT_TRAILING_START_R,

        "trailing_distance_r":
            DEFAULT_TRAILING_DISTANCE_R,

        "weekly_loss_limit":
            DEFAULT_MAX_WEEKLY_LOSS,

        "starting_balance":
            STARTING_BALANCE,

        "spread":
            SPREAD,

        "slippage":
            SLIPPAGE,
    }

    if path is None:
        return config

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        supplied = json.load(
            file
        )

    config.update(
        supplied
    )

    return config


# ============================================================================
# SAVE RESULTS
# ============================================================================

def save_results(
    output_dir: Path,
    trades: List[Trade],
    equity_df: pd.DataFrame,
    metrics: Dict,
    config: Dict,
) -> None:

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    trades_df = pd.DataFrame(
        [
            asdict(trade)
            for trade in trades
        ]
    )

    trades_df.to_csv(
        output_dir /
        "v5_trades.csv",
        index=False,
    )

    equity_df.to_csv(
        output_dir /
        "v5_equity_curve.csv",
        index=False,
    )

    periods = summarize_periods(
        trades
    )

    with open(
        output_dir /
        "v5_period_breakdown.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            periods,
            file,
            indent=2,
            default=str,
        )

    strategy_df = strategy_breakdown(
        trades
    )

    strategy_df.to_csv(
        output_dir /
        "v5_strategy_breakdown.csv",
        index=False,
    )

    with open(
        output_dir /
        "v5_metrics.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metrics,
            file,
            indent=2,
            default=str,
        )

    with open(
        output_dir /
        "v5_execution_config.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            config,
            file,
            indent=2,
            default=str,
        )

    lines = [
        "RAYMOND V2.8 V5 EXECUTION ENGINE",
        "=" * 80,
        "RESEARCH ONLY - NO LIVE BROKER EXECUTION",
        "",
        "XAUUSD CONTRACT MODEL",
        "----------------------",
        f"Contract size: {CONTRACT_SIZE:.2f} oz/lot",
        "Example: $5 movement at 0.02 lot = $10",
        "",
        "CONFIGURATION",
        "-------------",
    ]

    for key, value in config.items():

        lines.append(
            f"{key}: {value}"
        )

    lines.extend(
        [
            "",
            "RESULTS",
            "-------",
            (
                f"Starting balance: "
                f"{config['starting_balance']:.2f}"
            ),
            (
                f"Ending balance: "
                f"{metrics['ending_balance']:.2f}"
            ),
            (
                f"Net profit: "
                f"{metrics['net_profit']:.2f}"
            ),
            (
                f"Return: "
                f"{metrics['return_pct']:.2f}%"
            ),
            (
                f"Trades: "
                f"{metrics['trades']}"
            ),
            (
                f"Wins: "
                f"{metrics['wins']}"
            ),
            (
                f"Losses: "
                f"{metrics['losses']}"
            ),
            (
                f"Breakevens: "
                f"{metrics['breakevens']}"
            ),
            (
                f"Win rate: "
                f"{metrics['win_rate_pct']:.2f}%"
            ),
            (
                f"Gross profit: "
                f"{metrics['gross_profit']:.2f}"
            ),
            (
                f"Gross loss: "
                f"{metrics['gross_loss']:.2f}"
            ),
            (
                f"Profit factor: "
                f"{metrics['profit_factor']:.4f}"
            ),
            (
                f"Expectancy/trade: "
                f"{metrics['expectancy']:.4f}"
            ),
            (
                f"Average R: "
                f"{metrics['average_r']:.4f}"
            ),
            (
                f"Average win: "
                f"{metrics['average_win']:.4f}"
            ),
            (
                f"Average loss: "
                f"{metrics['average_loss']:.4f}"
            ),
            (
                f"Max drawdown: "
                f"{metrics['max_drawdown']:.2f}"
            ),
            (
                f"Max drawdown %: "
                f"{metrics['max_drawdown_pct']:.2f}%"
            ),
            "",
            "IMPORTANT ACCOUNTING CHECK",
            "---------------------------",
            (
                "Ending balance must equal "
                "starting balance + sum(all net trade P&L)"
            ),
            (
                f"{config['starting_balance']:.2f} + "
                f"{metrics['net_profit']:.2f} = "
                f"{metrics['ending_balance']:.2f}"
            ),
            "",
            "Trade-level P&L:",
            "price movement × 100 oz × lot size",
            "",
            "LOOKAHEAD CONTROL:",
            "Existing SL/TP checked before BE/trailing/TP updates.",
            "Management changes become effective on the next candle.",
        ]
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


# ============================================================================
# PERIOD RUNNER
# ============================================================================

def run_period(
    df: pd.DataFrame,
    config: Dict,
    period_name: str,
) -> Dict:

    if period_name == "development":

        data = df[
            df["timestamp"].dt.year == 2024
        ].copy()

    elif period_name == "selection":

        data = df[
            df["timestamp"].dt.year == 2025
        ].copy()

    elif period_name == "holdout":

        data = df[
            df["timestamp"].dt.year >= 2026
        ].copy()

    elif period_name == "full":

        data = df.copy()

    else:

        raise ValueError(
            f"Unknown period: {period_name}"
        )

    if len(data) < 100:

        raise ValueError(
            f"Not enough data for {period_name}"
        )

    trades, equity, metrics = run_backtest(
        df=data,

        strategy_family=(
            config["strategy_family"]
        ),

        regime=config["regime"],

        minimum_score=(
            config["minimum_score"]
        ),

        risk_reward=(
            config["risk_reward"]
        ),

        atr_stop_multiplier=(
            config["atr_stop_multiplier"]
        ),

        risk_per_trade=(
            config["risk_per_trade"]
        ),

        max_trades_per_week=(
            config["max_trades_per_week"]
        ),

        break_even_r=(
            config["break_even_r"]
        ),

        break_even_lock_r=(
            config["break_even_lock_r"]
        ),

        trailing_start_r=(
            config["trailing_start_r"]
        ),

        trailing_distance_r=(
            config["trailing_distance_r"]
        ),

        weekly_loss_limit=(
            config["weekly_loss_limit"]
        ),

        starting_balance=(
            config["starting_balance"]
        ),

        spread=config["spread"],

        slippage=config["slippage"],
    )

    return {
        "period": period_name,
        "trades": trades,
        "equity": equity,
        "metrics": metrics,
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Raymond V2.8 V5 execution engine"
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
        "--config",
        default=None,
    )

    parser.add_argument(
        "--period",
        choices=[
            "development",
            "selection",
            "holdout",
            "full",
            "all",
        ],
        default="all",
    )

    args = parser.parse_args()

    print("=" * 80)
    print(
        "RAYMOND V2.8 - V5 EXECUTION ENGINE"
    )
    print("=" * 80)

    df = load_data(
        args.data
    )

    df = calculate_indicators(
        df
    )

    print(
        f"Loaded rows: {len(df):,}"
    )

    config = load_config(
        args.config
    )

    output_root = Path(
        args.output
    )

    periods = [
        "development",
        "selection",
        "holdout",
        "full",
    ]

    if args.period != "all":

        periods = [
            args.period
        ]

    combined_summary = {}

    for period_name in periods:

        print()
        print(
            f"RUNNING: {period_name.upper()}"
        )

        result = run_period(
            df,
            config,
            period_name,
        )

        period_output = (
            output_root /
            period_name
        )

        save_results(
            output_dir=period_output,
            trades=result["trades"],
            equity_df=result["equity"],
            metrics=result["metrics"],
            config=config,
        )

        combined_summary[
            period_name
        ] = result["metrics"]

        metrics = result["metrics"]

        print(
            f"Trades: "
            f"{metrics['trades']}"
        )

        print(
            f"Win rate: "
            f"{metrics['win_rate_pct']:.2f}%"
        )

        print(
            f"Net profit: "
            f"{metrics['net_profit']:.2f}"
        )

        print(
            f"Return: "
            f"{metrics['return_pct']:.2f}%"
        )

        print(
            f"Profit factor: "
            f"{metrics['profit_factor']:.4f}"
        )

        print(
            f"Max DD: "
            f"{metrics['max_drawdown_pct']:.2f}%"
        )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_root /
        "v5_all_period_metrics.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            combined_summary,
            file,
            indent=2,
            default=str,
        )

    print()
    print("=" * 80)
    print(
        "V5 EXECUTION ENGINE COMPLETE"
    )
    print("=" * 80)

    print(
        f"Results: {output_root}"
    )


if __name__ == "__main__":
    main()
