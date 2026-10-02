
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
from typing import Dict, List, Optional, Tuple

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

H1 = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/historical/xauusd_h1_2024_2026_normalized.csv")
M15 = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/historical/xauusd_m15_2024_2026_normalized.csv")
M5 = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("data/historical/xauusd_m5_2024_2026_normalized.csv")
OUT = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("backtest_results/weekly_growth_v4")

GRID = {
    "risk_reward": [2.5, 3.0, 3.5, 4.0],
    "min_signal_score": [60, 65, 70],
    "max_trades_per_week": [6, 8],
    "atr_stop_multiplier": [1.0, 1.2, 1.4],
    "profit_protection": ["none", "be_1r", "lock_0_5r", "trail_1r"],
    "lower_confirmation": ["both", "m15", "m5"],
    "thesis_exit": [False, True],
}

BASE = {
    "weekly_target": 0.25,
    "weekly_loss_limit": -0.09,
    "risk_per_trade": 0.03,
    "spread": 0.30,
    "slippage": 0.05,
    "min_atr_ratio": 0.70,
    "max_atr_ratio": 1.80,
}

_DATASETS = {}


def load_ohlc(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Required data file not found: {path}")
    df = pd.read_csv(path)
    rename = {}
    for column in df.columns:
        name = str(column).strip().lower()
        if name in {"date", "datetime", "time", "timestamp"}:
            rename[column] = "timestamp"
        elif name in {"open", "o"}:
            rename[column] = "open"
        elif name in {"high", "h"}:
            rename[column] = "high"
        elif name in {"low", "l"}:
            rename[column] = "low"
        elif name in {"close", "c"}:
            rename[column] = "close"
        elif name in {"volume", "vol", "tick_volume"}:
            rename[column] = "volume"
    df = df.rename(columns=rename)
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"{path}: missing columns {sorted(missing)}")
    raw = df["timestamp"]
    if pd.api.types.is_numeric_dtype(raw):
        df["timestamp"] = pd.to_datetime(pd.to_numeric(raw, errors="coerce"), unit="ms", utc=True, errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(raw, utc=True, errors="coerce")
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    if len(df) < 300:
        raise SystemExit(f"{path}: only {len(df)} rows. At least 300 are required.")
    return df


def lower_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.set_index("timestamp").copy()
    x["ema20"] = x["close"].ewm(span=20, adjust=False).mean()
    x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()
    delta = x["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    x["rsi14"] = 100 - (100 / (1 + rs))
    x["bull_candle"] = x["close"] > x["open"]
    x["bear_candle"] = x["close"] < x["open"]
    x = x.reset_index()
    return x[["timestamp", "close", "ema20", "ema50", "rsi14", "bull_candle", "bear_candle"]]


def build_confirmation(h1: pd.DataFrame, m15: pd.DataFrame, m5: pd.DataFrame) -> pd.DataFrame:
    m15base = lower_features(m15)
    m15f = m15base.rename(columns={c: f"m15_{c}" for c in m15base.columns if c != "timestamp"})
    m5base = lower_features(m5)
    m5f = m5base.rename(columns={c: f"m5_{c}" for c in m5base.columns if c != "timestamp"})
    out = h1[["timestamp"]].copy()
    out["lookup_time"] = out["timestamp"] + pd.Timedelta(minutes=59, seconds=59)
    out = pd.merge_asof(out.sort_values("lookup_time"), m15f.sort_values("timestamp"),
                        left_on="lookup_time", right_on="timestamp", direction="backward")
    out = out.drop(columns=["timestamp_y"]).rename(columns={"timestamp_x": "timestamp"})
    out = pd.merge_asof(out.sort_values("lookup_time"), m5f.sort_values("timestamp"),
                        left_on="lookup_time", right_on="timestamp", direction="backward")
    out = out.drop(columns=["timestamp_y"]).rename(columns={"timestamp_x": "timestamp"})
    return out.drop(columns=["lookup_time"])


def _reason(parts: List[str]) -> str:
    return "|".join(parts)


def prepare_data(frame: pd.DataFrame, confirmation_frame: pd.DataFrame) -> Dict:
    x = frame.reset_index(drop=True)
    n = len(x)

    close = x["close"].to_numpy(dtype=float)
    high = x["high"].to_numpy(dtype=float)
    low = x["low"].to_numpy(dtype=float)
    open_ = x["open"].to_numpy(dtype=float)
    ema20 = x["ema20"].to_numpy(dtype=float)
    ema50 = x["ema50"].to_numpy(dtype=float)
    atr = x["atr14"].to_numpy(dtype=float)
    rsi = x["rsi14"].to_numpy(dtype=float)
    macd = x["macd_hist"].to_numpy(dtype=float)
    atr_ratio = x["atr_ratio"].to_numpy(dtype=float)
    prev20h = x["previous_20_high"].to_numpy(dtype=float)
    prev20l = x["previous_20_low"].to_numpy(dtype=float)
    prev8h = x["previous_8_high"].to_numpy(dtype=float)
    prev8l = x["previous_8_low"].to_numpy(dtype=float)
    trend = x["trend"].astype(str).to_numpy()

    valid = (
        np.isfinite(close) & np.isfinite(high) & np.isfinite(low) &
        np.isfinite(ema20) & np.isfinite(ema50) & np.isfinite(atr) &
        np.isfinite(rsi) & np.isfinite(macd) & np.isfinite(atr_ratio) &
        np.isfinite(prev20h) & np.isfinite(prev20l) &
        np.isfinite(prev8h) & np.isfinite(prev8l)
    )
    volatility = valid & (atr_ratio >= BASE["min_atr_ratio"]) & (atr_ratio <= BASE["max_atr_ratio"])

    buy_score = np.zeros(n, dtype=np.int16)
    sell_score = np.zeros(n, dtype=np.int16)
    buy_reason = [""] * n
    sell_reason = [""] * n
    buy_parts = [[] for _ in range(n)]
    sell_parts = [[] for _ in range(n)]

    c_range = high - low
    loc = np.divide(close - low, c_range, out=np.zeros(n), where=c_range > 0)

    cond = volatility & (trend == "BULL")
    buy_score[cond] += 20
    for i in np.flatnonzero(cond):
        buy_parts[i].append("h4_bull_regime")

    cond = volatility & (close > ema50)
    buy_score[cond] += 15
    for i in np.flatnonzero(cond):
        buy_parts[i].append("h1_above_ema50")

    cond = volatility & (low <= ema20) & (close > ema20)
    buy_score[cond] += 15
    for i in np.flatnonzero(cond):
        buy_parts[i].append("ema20_pullback_reclaim")

    cond = volatility & (low < prev20l) & (close > prev20l)
    buy_score[cond] += 15
    for i in np.flatnonzero(cond):
        buy_parts[i].append("sell_side_liquidity_sweep")

    cond = volatility & (rsi >= 52) & (rsi <= 72) & (macd > 0)
    buy_score[cond] += 15
    for i in np.flatnonzero(cond):
        buy_parts[i].append("bullish_momentum")

    cond = volatility & (c_range > 0) & (loc >= 0.65)
    buy_score[cond] += 10
    for i in np.flatnonzero(cond):
        buy_parts[i].append("strong_bullish_close")

    cond = volatility & (trend == "BEAR")
    sell_score[cond] += 20
    for i in np.flatnonzero(cond):
        sell_parts[i].append("h4_bear_regime")

    cond = volatility & (close < ema50)
    sell_score[cond] += 15
    for i in np.flatnonzero(cond):
        sell_parts[i].append("h1_below_ema50")

    cond = volatility & (high >= ema20) & (close < ema20)
    sell_score[cond] += 15
    for i in np.flatnonzero(cond):
        sell_parts[i].append("ema20_pullback_rejection")

    cond = volatility & (high > prev20h) & (close < prev20h)
    sell_score[cond] += 15
    for i in np.flatnonzero(cond):
        sell_parts[i].append("buy_side_liquidity_sweep")

    cond = volatility & (rsi >= 28) & (rsi <= 48) & (macd < 0)
    sell_score[cond] += 15
    for i in np.flatnonzero(cond):
        sell_parts[i].append("bearish_momentum")

    cond = volatility & (c_range > 0) & (loc <= 0.35)
    sell_score[cond] += 10
    for i in np.flatnonzero(cond):
        sell_parts[i].append("strong_bearish_close")

    for i in range(n):
        if not valid[i] or not volatility[i]:
            buy_reason[i] = "volatility_filter_failed" if valid[i] is False or not volatility[i] else ""
            sell_reason[i] = buy_reason[i]
        else:
            buy_reason[i] = _reason(buy_parts[i])
            sell_reason[i] = _reason(sell_parts[i])

    cf = confirmation_frame
    def arr(name, default=np.nan):
        if name in cf.columns:
            return cf[name].to_numpy()
        return np.full(n, default)

    m15_close = arr("m15_close", np.nan).astype(float)
    m15_ema20 = arr("m15_ema20", np.nan).astype(float)
    m15_ema50 = arr("m15_ema50", np.nan).astype(float)
    m15_rsi = arr("m15_rsi14", np.nan).astype(float)
    m15_bull = arr("m15_bull_candle", False).astype(bool)
    m15_bear = arr("m15_bear_candle", False).astype(bool)

    m5_close = arr("m5_close", np.nan).astype(float)
    m5_ema20 = arr("m5_ema20", np.nan).astype(float)
    m5_ema50 = arr("m5_ema50", np.nan).astype(float)
    m5_rsi = arr("m5_rsi14", np.nan).astype(float)
    m5_bull = arr("m5_bull_candle", False).astype(bool)
    m5_bear = arr("m5_bear_candle", False).astype(bool)

    def ok(c, e20, e50, r, bull, buy):
        finite = np.isfinite(c) & np.isfinite(e20) & np.isfinite(e50) & np.isfinite(r)
        if buy:
            return finite & (c > e20) & (e20 > e50) & (r >= 52) & (r <= 75) & bull
        return finite & (c < e20) & (e20 < e50) & (r >= 25) & (r <= 48) & bull

    m15_buy = ok(m15_close, m15_ema20, m15_ema50, m15_rsi, m15_bull, True)
    m15_sell = ok(m15_close, m15_ema20, m15_ema50, m15_rsi, m15_bear, False)
    m5_buy = ok(m5_close, m5_ema20, m5_ema50, m5_rsi, m5_bull, True)
    m5_sell = ok(m5_close, m5_ema20, m5_ema50, m5_rsi, m5_bear, False)

    ts = x["timestamp"].tolist()
    ts_iso = [pd.Timestamp(t).isoformat() for t in ts]
    iso = x["timestamp"].dt.isocalendar()
    weeks = (iso["year"].astype(str) + "-W" + iso["week"].astype(int).astype(str).str.zfill(2)).to_numpy()

    return {
        "n": n, "timestamp": ts, "iso": ts_iso, "week": weeks,
        "open": open_, "high": high, "low": low, "close": close,
        "ema50": ema50, "atr": atr, "prev8h": prev8h, "prev8l": prev8l,
        "trend": trend, "buy_score": buy_score, "sell_score": sell_score,
        "buy_reason": buy_reason, "sell_reason": sell_reason,
        "m15_buy": m15_buy, "m15_sell": m15_sell,
        "m5_buy": m5_buy, "m5_sell": m5_sell,
    }


def _confirm(d, i, direction, mode):
    if direction == "BUY":
        m15 = d["m15_buy"][i]
        m5 = d["m5_buy"][i]
    else:
        m15 = d["m15_sell"][i]
        m5 = d["m5_sell"][i]
    if mode == "both":
        return bool(m15 and m5)
    if mode == "m15":
        return bool(m15)
    return bool(m5)


def simulate(d: Dict, config: Dict, protection: str, confirm_mode: str, thesis_exit: bool, want_trades: bool = False):
    cfg = StrategyConfig(**config, starting_balance=1000.0)
    n = d["n"]
    balance = 1000.0
    trades = []
    weekly_records = {}
    position = None
    current_week = None
    pending = None

    def ensure_week(w):
        if w not in weekly_records:
            weekly_records[w] = {
                "start_balance": balance, "profit": 0.0, "trades": 0,
                "wins": 0, "losses": 0, "break_evens": 0,
                "target_hit": False, "loss_limit_hit": False,
            }
        return weekly_records[w]

    for i in range(1, n):
        w = d["week"][i]
        if w != current_week:
            current_week = w
            ensure_week(w)
            pending = None
        week = weekly_records[w]

        if position is not None:
            direction = position["direction"]
            stop = position["stop"]
            target = position["target"]
            hi = d["high"][i]
            lo = d["low"][i]
            exit_result = None

            if direction == "BUY":
                stop_hit = lo <= stop
                target_hit = hi >= target
            else:
                stop_hit = hi >= stop
                target_hit = lo <= target

            if stop_hit and target_hit:
                exit_result = (stop, "STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST")
            elif stop_hit:
                exit_result = (stop, "STOP_LOSS")
            elif target_hit:
                exit_result = (target, "TAKE_PROFIT")
            elif thesis_exit:
                if direction == "BUY" and d["close"][i] < d["ema50"][i] and d["trend"][i] == "BEAR":
                    exit_result = (d["close"][i], "THESIS_EXIT")
                elif direction == "SELL" and d["close"][i] > d["ema50"][i] and d["trend"][i] == "BULL":
                    exit_result = (d["close"][i], "THESIS_EXIT")

            if exit_result is not None:
                raw, reason = exit_result
                exit_price = get_exit_price(direction, raw, cfg)
                pnl = calculate_pnl(direction, position["entry"], exit_price, position["volume"])
                before = balance
                balance += pnl
                r = pnl / position["risk_amount"] if position["risk_amount"] > 0 else 0.0
                if pnl > 0: week["wins"] += 1
                elif pnl < 0: week["losses"] += 1
                else: week["break_evens"] += 1
                week["profit"] += pnl
                week["trades"] += 1
                if want_trades:
                    trades.append(Trade(
                        direction=direction,
                        signal_time=position["signal_time"],
                        entry_time=position["entry_time"],
                        exit_time=d["iso"][i],
                        entry_price=position["entry"],
                        exit_price=exit_price,
                        stop_price=position["stop"],
                        target_price=position["target"],
                        volume=position["volume"],
                        risk_amount=position["risk_amount"],
                        pnl=pnl,
                        r_multiple=r,
                        signal_score=position["score"],
                        exit_reason=reason,
                        setup_reason=position["reason"],
                        balance_before=before,
                        balance_after=balance,
                        week=w,
                    ))
                position = None
                pending = None
                continue

            if protection != "none":
                entry = position["entry"]
                risk = position["risk_distance"]
                close = d["close"][i]
                if risk > 0:
                    if direction == "BUY":
                        r_now = (close - entry) / risk
                        if protection == "be_1r" and r_now >= 1.0:
                            position["stop"] = max(position["stop"], entry)
                        elif protection == "lock_0_5r" and r_now >= 1.5:
                            position["stop"] = max(position["stop"], entry + 0.5 * risk)
                        elif protection == "trail_1r" and r_now >= 2.0:
                            position["stop"] = max(position["stop"], close - risk)
                    else:
                        r_now = (entry - close) / risk
                        if protection == "be_1r" and r_now >= 1.0:
                            position["stop"] = min(position["stop"], entry)
                        elif protection == "lock_0_5r" and r_now >= 1.5:
                            position["stop"] = min(position["stop"], entry - 0.5 * risk)
                        elif protection == "trail_1r" and r_now >= 2.0:
                            position["stop"] = min(position["stop"], close + risk)

        if position is None and pending is not None:
            direction, score, reason, signal_iso = pending
            start = week["start_balance"]
            weekly_return = (balance - start) / start if start > 0 else 0.0
            if weekly_return >= cfg.weekly_target:
                week["target_hit"] = True
                pending = None
            elif weekly_return <= cfg.weekly_loss_limit:
                week["loss_limit_hit"] = True
                pending = None
            elif week["trades"] >= cfg.max_trades_per_week:
                pending = None
            else:
                market_open = d["open"][i]
                entry = get_entry_price(direction, market_open, cfg)
                atr = d["atr"][i]
                if direction == "BUY":
                    atr_stop = entry - atr * cfg.atr_stop_multiplier
                    structural_stop = d["prev8l"][i] - atr * 0.10
                    stop = min(atr_stop, structural_stop)
                    risk_distance = entry - stop
                else:
                    atr_stop = entry + atr * cfg.atr_stop_multiplier
                    structural_stop = d["prev8h"][i] + atr * 0.10
                    stop = max(atr_stop, structural_stop)
                    risk_distance = stop - entry
                if risk_distance <= 0:
                    pending = None
                else:
                    volume, risk_amount = calculate_volume_for_risk(balance, cfg.risk_per_trade, risk_distance, cfg)
                    if volume <= 0:
                        pending = None
                    else:
                        target = entry + risk_distance * cfg.risk_reward if direction == "BUY" else entry - risk_distance * cfg.risk_reward
                        position = {
                            "direction": direction, "signal_time": signal_iso, "entry_time": d["timestamp"][i],
                            "entry": entry, "stop": stop, "target": target, "volume": volume,
                            "risk_amount": risk_amount, "risk_distance": risk_distance,
                            "score": int(score), "reason": reason,
                        }
                        pending = None

        if i < n - 1:
            threshold = cfg.min_signal_score
            bs = int(d["buy_score"][i])
            ss = int(d["sell_score"][i])
            if bs >= threshold:
                direction = "BUY"
                score = bs
                reason = d["buy_reason"][i]
            elif ss >= threshold:
                direction = "SELL"
                score = ss
                reason = d["sell_reason"][i]
            else:
                direction = None
            if direction is not None and _confirm(d, i, direction, confirm_mode):
                reason = reason + "|lower_tf_" + confirm_mode + "_confirmed"
                pending = (direction, score, reason, d["iso"][i])
            else:
                pending = None

    if position is not None:
        i = n - 1
        direction = position["direction"]
        raw = d["close"][i]
        exit_price = get_exit_price(direction, raw, cfg)
        pnl = calculate_pnl(direction, position["entry"], exit_price, position["volume"])
        before = balance
        balance += pnl
        w = d["week"][i]
        week = weekly_records[w]
        if pnl > 0: week["wins"] += 1
        elif pnl < 0: week["losses"] += 1
        else: week["break_evens"] += 1
        week["profit"] += pnl
        week["trades"] += 1
        if want_trades:
            trades.append(Trade(
                direction=direction, signal_time=position["signal_time"], entry_time=position["entry_time"],
                exit_time=d["iso"][i], entry_price=position["entry"], exit_price=exit_price,
                stop_price=position["stop"], target_price=position["target"], volume=position["volume"],
                risk_amount=position["risk_amount"], pnl=pnl, r_multiple=pnl / position["risk_amount"] if position["risk_amount"] > 0 else 0.0,
                signal_score=position["score"], exit_reason="END_OF_DATA", setup_reason=position["reason"],
                balance_before=before, balance_after=balance, week=w,
            ))

    weekly_rows = []
    for wk, state in weekly_records.items():
        start = float(state["start_balance"])
        ret = state["profit"] / start if start > 0 else 0.0
        weekly_rows.append({
            "week": wk, "start_balance": start, "profit": state["profit"],
            "weekly_return": ret, "weekly_return_pct": ret * 100,
            "trades": state["trades"], "wins": state["wins"], "losses": state["losses"],
            "break_evens": state["break_evens"], "target_hit": state["target_hit"],
            "target_25pct_hit": state["target_hit"], "loss_limit_hit": state["loss_limit_hit"],
        })
    return trades, weekly_rows, balance


def _worker(payload):
    params = payload
    config = {**BASE,
              "risk_reward": params["risk_reward"],
              "min_signal_score": params["min_signal_score"],
              "max_trades_per_week": params["max_trades_per_week"],
              "atr_stop_multiplier": params["atr_stop_multiplier"]}
    d = _DATASETS
    train = simulate(d["train"], config, params["profit_protection"], params["lower_confirmation"], params["thesis_exit"])
    tm = calculate_metrics(train[0], train[1], 1000.0, train[2], StrategyConfig(**config, starting_balance=1000.0))
    if tm["total_return_pct"] <= 0 or (tm["profit_factor"] or 0.0) <= 1.0 or tm["total_trades"] < 8:
        return None
    sel = simulate(d["selection"], config, params["profit_protection"], params["lower_confirmation"], params["thesis_exit"])
    sm = calculate_metrics(sel[0], sel[1], 1000.0, sel[2], StrategyConfig(**config, starting_balance=1000.0))
    if sm["total_return_pct"] <= 0 or (sm["profit_factor"] or 0.0) <= 1.0 or sm["total_trades"] < 6:
        return None
    pf = sm["profit_factor"] or 0.0
    score = sm["total_return_pct"] - 0.75 * abs(sm["max_drawdown_pct"]) + 10.0 * max(0.0, pf - 1.0)
    return {
        "params": params,
        "train_return_pct": tm["total_return_pct"], "train_pf": tm["profit_factor"], "train_dd": tm["max_drawdown_pct"],
        "train_wr": tm["win_rate_pct"], "train_trades": tm["total_trades"],
        "selection_return_pct": sm["total_return_pct"], "selection_pf": sm["profit_factor"],
        "selection_dd": sm["max_drawdown_pct"], "selection_wr": sm["win_rate_pct"], "selection_trades": sm["total_trades"],
        "selection_score": score,
    }


def main():
    print("RAYMOND V2.8 WEEKLY GROWTH V4 - FAST")
    print("======================================")
    print("RESEARCH ONLY: YES")
    print("LIVE TRADING: NO")
    print()
    h1_raw = load_ohlc(H1)
    m15_raw = load_ohlc(M15)
    m5_raw = load_ohlc(M5)
    print(f"H1 rows: {len(h1_raw):,}")
    print(f"M15 rows: {len(m15_raw):,}")
    print(f"M5 rows: {len(m5_raw):,}")
    h1 = calculate_indicators(h1_raw, StrategyConfig())
    confirmation_frame = build_confirmation(h1, m15_raw, m5_raw)
    frame = h1.copy()
    for c in confirmation_frame.columns:
        if c != "timestamp":
            frame[c] = confirmation_frame[c].to_numpy()
    train = frame[(frame["timestamp"] >= pd.Timestamp("2024-01-01", tz="UTC")) & (frame["timestamp"] < pd.Timestamp("2025-01-01", tz="UTC"))].copy()
    selection = frame[(frame["timestamp"] >= pd.Timestamp("2025-01-01", tz="UTC")) & (frame["timestamp"] < pd.Timestamp("2026-01-01", tz="UTC"))].copy()
    holdout = frame[frame["timestamp"] >= pd.Timestamp("2026-01-01", tz="UTC")].copy()
    if len(train) < 300 or len(selection) < 300 or len(holdout) < 100:
        raise SystemExit("Not enough data in one or more required splits.")
    print(f"2024 development H1 candles: {len(train):,}")
    print(f"2025 selection H1 candles: {len(selection):,}")
    print(f"2026+ holdout H1 candles: {len(holdout):,}")
    print()
    keys = list(GRID.keys())
    combinations = [dict(zip(keys, vals)) for vals in itertools.product(*(GRID[k] for k in keys))]
    print(f"V4 combinations: {len(combinations)}")
    print("Fast engine: precomputed signals + parallel candidate evaluation")
    print()
    global _DATASETS
    _DATASETS = {
        "train": prepare_data(train, confirmation_frame.loc[train.index] if False else confirmation_frame.iloc[train.index].reset_index(drop=True)),
        "selection": prepare_data(selection, confirmation_frame.iloc[selection.index].reset_index(drop=True)),
        "holdout": prepare_data(holdout, confirmation_frame.iloc[holdout.index].reset_index(drop=True)),
        "full": prepare_data(frame, confirmation_frame),
    }
    candidates = []
    workers = min(2, os.cpu_count() or 1)
    if workers > 1 and "fork" in mp.get_all_start_methods():
        ctx = mp.get_context("fork")
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
            futures = [ex.submit(_worker, p) for p in combinations]
            for idx, fut in enumerate(as_completed(futures), 1):
                result = fut.result()
                if result is not None:
                    candidates.append(result)
                if idx % 25 == 0 or idx == len(combinations):
                    print(f"Progress {idx}/{len(combinations)} | valid candidates {len(candidates)}", flush=True)
    else:
        for idx, p in enumerate(combinations, 1):
            result = _worker(p)
            if result is not None:
                candidates.append(result)
            if idx % 25 == 0 or idx == len(combinations):
                print(f"Progress {idx}/{len(combinations)} | valid candidates {len(candidates)}", flush=True)
    if not candidates:
        raise SystemExit("No V4 candidate passed the development and selection filters.")
    candidates.sort(key=lambda x: x["selection_score"], reverse=True)
    best = candidates[0]
    params = best["params"]
    selected_config = {**BASE,
                       "risk_reward": params["risk_reward"],
                       "min_signal_score": params["min_signal_score"],
                       "max_trades_per_week": params["max_trades_per_week"],
                       "atr_stop_multiplier": params["atr_stop_multiplier"]}
    print()
    print("Running 2026+ unseen holdout...")
    holdout_result = simulate(_DATASETS["holdout"], selected_config, params["profit_protection"], params["lower_confirmation"], params["thesis_exit"], want_trades=True)
    holdout_metrics = calculate_metrics(holdout_result[0], holdout_result[1], 1000.0, holdout_result[2], StrategyConfig(**selected_config, starting_balance=1000.0))
    print("Running selected configuration over full period...")
    full_result = simulate(_DATASETS["full"], selected_config, params["profit_protection"], params["lower_confirmation"], params["thesis_exit"], want_trades=True)
    full_metrics = calculate_metrics(full_result[0], full_result[1], 1000.0, full_result[2], StrategyConfig(**selected_config, starting_balance=1000.0))
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(candidates).head(50).to_csv(OUT / "top_50_candidates.csv", index=False)
    trade_rows = [vars(t) for t in full_result[0]]
    pd.DataFrame(trade_rows).to_csv(OUT / "selected_full_period_trades.csv", index=False)
    summary = f"""RAYMOND V2.8 WEEKLY GROWTH V4
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
    (OUT / "summary.txt").write_text(summary, encoding="utf-8")
    (OUT / "optimization.json").write_text(json.dumps({
        "research_only": True, "live_trading": False, "selected": best,
        "holdout_metrics": holdout_metrics, "full_period_metrics": full_metrics,
        "data": {"h1": str(H1), "m15": str(M15), "m5": str(M5)},
        "engine": {"precomputed_signals": True, "parallel_workers": workers, "grid_size": len(combinations)},
    }, indent=2, default=str), encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
