#!/usr/bin/env python3
"""
RAYMOND v2.8 - WEEKLY GROWTH V3 RESEARCH

Research only.

V3 is designed to answer:
1. Can we increase trade frequency without destroying expectancy?
2. Does a lower signal threshold help?
3. Does a lower target work better when profit protection is enabled?
4. Can break-even / profit-locking reduce drawdown?
5. Does the improvement survive a completely separate 2026 holdout?

Data split:
- 2024: development/training
- 2025: parameter-selection validation
- 2026: final unseen holdout

This file does NOT modify or place live trades.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_weekly_growth_backtest import (
    StrategyConfig,
    Position,
    Trade,
    load_data,
    calculate_indicators,
    score_signal,
    calculate_volume_for_risk,
    get_entry_price,
    get_exit_price,
    calculate_pnl,
    determine_exit,
    week_key,
    new_week_state,
    calculate_metrics,
)


INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "data/historical/xauusd_h1_2024_2026_normalized.csv"
)

OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
    "backtest_results/weekly_growth_v3"
)


GRID = {
    "risk_reward": [2.0, 2.5, 3.0, 3.5, 4.0],
    "min_signal_score": [55, 60, 65, 70],
    "max_trades_per_week": [6, 8],
    "atr_stop_multiplier": [1.0, 1.2, 1.4],
    "profit_protection": [
        "none",
        "be_1r",
        "lock_0_5r",
        "trail_1r",
    ],
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


def apply_profit_protection(
    position: Position,
    candle: pd.Series,
    mode: str,
) -> None:

    if mode == "none":
        return

    close = float(candle["close"])
    entry = position.entry_price
    risk = position.risk_distance

    if risk <= 0:
        return

    if position.direction == "BUY":
        r_now = (close - entry) / risk

        if mode == "be_1r":
            if r_now >= 1.0:
                position.stop_price = max(
                    position.stop_price,
                    entry,
                )

        elif mode == "lock_0_5r":
            if r_now >= 1.5:
                locked = entry + (0.5 * risk)
                position.stop_price = max(
                    position.stop_price,
                    locked,
                )

        elif mode == "trail_1r":
            if r_now >= 2.0:
                trailing = close - risk
                position.stop_price = max(
                    position.stop_price,
                    trailing,
                )

    else:
        r_now = (entry - close) / risk

        if mode == "be_1r":
            if r_now >= 1.0:
                position.stop_price = min(
                    position.stop_price,
                    entry,
                )

        elif mode == "lock_0_5r":
            if r_now >= 1.5:
                locked = entry - (0.5 * risk)
                position.stop_price = min(
                    position.stop_price,
                    locked,
                )

        elif mode == "trail_1r":
            if r_now >= 2.0:
                trailing = close + risk
                position.stop_price = min(
                    position.stop_price,
                    trailing,
                )


def run_backtest_v3(
    df: pd.DataFrame,
    config: StrategyConfig,
    protection_mode: str,
) -> Tuple[List[Trade], List[Dict], float]:

    balance = config.starting_balance

    trades: List[Trade] = []
    weekly_records: Dict[str, Dict] = {}

    position = None
    current_week = None
    pending_signal = None

    for i in range(1, len(df)):

        candle = df.iloc[i]

        timestamp = pd.Timestamp(
            candle["timestamp"]
        )

        this_week = week_key(timestamp)

        if this_week != current_week:

            current_week = this_week

            if this_week not in weekly_records:
                weekly_records[this_week] = (
                    new_week_state(balance)
                )

            pending_signal = None

        week = weekly_records[this_week]

        if position is not None:

            exit_result = determine_exit(
                position,
                candle,
                config,
            )

            if exit_result is not None:

                raw_exit_price, exit_reason = exit_result

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

                r_multiple = (
                    pnl / position.risk_amount
                    if position.risk_amount > 0
                    else 0.0
                )

                if pnl > 0:
                    week["wins"] += 1
                elif pnl < 0:
                    week["losses"] += 1
                else:
                    week["break_evens"] += 1

                week["profit"] += pnl

                trades.append(
                    Trade(
                        direction=position.direction,
                        signal_time=position.signal_time.isoformat(),
                        entry_time=position.entry_time.isoformat(),
                        exit_time=timestamp.isoformat(),
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        stop_price=position.stop_price,
                        target_price=position.target_price,
                        volume=position.volume,
                        risk_amount=position.risk_amount,
                        pnl=pnl,
                        r_multiple=r_multiple,
                        signal_score=position.signal_score,
                        exit_reason=exit_reason,
                        setup_reason=position.reason,
                        balance_before=balance_before,
                        balance_after=balance,
                        week=this_week,
                    )
                )

                week["trades"] += 1

                position = None
                pending_signal = None

                continue

            apply_profit_protection(
                position,
                candle,
                protection_mode,
            )

        if position is None and pending_signal is not None:

            direction, score, reason, signal_time = pending_signal

            weekly_return = (
                (
                    balance - week["start_balance"]
                )
                / week["start_balance"]
                if week["start_balance"] > 0
                else 0.0
            )

            if weekly_return >= config.weekly_target:

                week["target_hit"] = True
                pending_signal = None

            elif weekly_return <= config.weekly_loss_limit:

                week["loss_limit_hit"] = True
                pending_signal = None

            elif week["trades"] >= config.max_trades_per_week:

                pending_signal = None

            else:

                market_open = float(candle["open"])

                entry_price = get_entry_price(
                    direction,
                    market_open,
                    config,
                )

                atr = float(candle["atr14"])

                swing_low = float(candle["previous_8_low"])
                swing_high = float(candle["previous_8_high"])

                if direction == "BUY":

                    atr_stop = (
                        entry_price
                        - atr * config.atr_stop_multiplier
                    )

                    structural_stop = (
                        swing_low - atr * 0.10
                    )

                    stop_price = min(
                        atr_stop,
                        structural_stop,
                    )

                    risk_distance = (
                        entry_price - stop_price
                    )

                else:

                    atr_stop = (
                        entry_price
                        + atr * config.atr_stop_multiplier
                    )

                    structural_stop = (
                        swing_high + atr * 0.10
                    )

                    stop_price = max(
                        atr_stop,
                        structural_stop,
                    )

                    risk_distance = (
                        stop_price - entry_price
                    )

                if risk_distance <= 0:

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
                                entry_price + target_distance
                            )
                        else:
                            target_price = (
                                entry_price - target_distance
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

        if i < len(df) - 1:

            signal_direction, score, reason = score_signal(
                candle,
                config,
            )

            if signal_direction in {"BUY", "SELL"}:

                pending_signal = (
                    signal_direction,
                    score,
                    reason,
                    timestamp,
                )

            else:

                pending_signal = None

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

        r_multiple = (
            pnl / position.risk_amount
            if position.risk_amount > 0
            else 0.0
        )

        week = weekly_records[this_week]

        if pnl > 0:
            week["wins"] += 1
        elif pnl < 0:
            week["losses"] += 1
        else:
            week["break_evens"] += 1

        week["profit"] += pnl
        week["trades"] += 1

        trades.append(
            Trade(
                direction=position.direction,
                signal_time=position.signal_time.isoformat(),
                entry_time=position.entry_time.isoformat(),
                exit_time=timestamp.isoformat(),
                entry_price=position.entry_price,
                exit_price=exit_price,
                stop_price=position.stop_price,
                target_price=position.target_price,
                volume=position.volume,
                risk_amount=position.risk_amount,
                pnl=pnl,
                r_multiple=r_multiple,
                signal_score=position.signal_score,
                exit_reason="END_OF_DATA",
                setup_reason=position.reason,
                balance_before=balance_before,
                balance_after=balance,
                week=this_week,
            )
        )

    weekly_rows = []

    for week_name, state in weekly_records.items():

        start_balance = state["start_balance"]

        weekly_return = (
            state["profit"] / start_balance
            if start_balance > 0
            else 0.0
        )

        weekly_rows.append(
            {
                "week": week_name,
                "start_balance": start_balance,
                "profit": state["profit"],
                "weekly_return": weekly_return,
                "weekly_return_pct": weekly_return * 100,
                "trades": state["trades"],
                "wins": state["wins"],
                "losses": state["losses"],
                "break_evens": state["break_evens"],
                "target_hit": state["target_hit"],
                "loss_limit_hit": state["loss_limit_hit"],
            }
        )

    return trades, weekly_rows, balance


def run_variant(
    config_values: Dict,
    frame: pd.DataFrame,
    protection_mode: str,
) -> Dict:

    cfg = StrategyConfig(
        **config_values,
        starting_balance=1000.0,
    )

    trades, weeks, end_balance = run_backtest_v3(
        frame,
        cfg,
        protection_mode,
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


def selection_score(metrics: Dict) -> float:

    pf = metrics["profit_factor"] or 0.0

    return (
        metrics["total_return_pct"]
        - 0.75 * abs(metrics["max_drawdown_pct"])
        + 10.0 * max(0.0, pf - 1.0)
    )


def diagnostic_summary(trades: List[Trade]) -> Dict:

    exits = Counter(
        trade.exit_reason
        for trade in trades
    )

    setups = Counter(
        trade.setup_reason
        for trade in trades
    )

    scores = [
        trade.signal_score
        for trade in trades
    ]

    r_values = [
        trade.r_multiple
        for trade in trades
    ]

    return {
        "exit_reasons": dict(exits),
        "setup_reasons": dict(
            setups.most_common(20)
        ),
        "signal_score_distribution": {
            str(score): scores.count(score)
            for score in sorted(set(scores))
        },
        "average_r": (
            sum(r_values) / len(r_values)
            if r_values
            else 0.0
        ),
    }


def main() -> None:

    df = calculate_indicators(
        load_data(INPUT),
        StrategyConfig(),
    )

    train = df[
        (df["timestamp"] >= pd.Timestamp("2024-01-01", tz="UTC"))
        & (df["timestamp"] < pd.Timestamp("2025-01-01", tz="UTC"))
    ].copy()

    selection = df[
        (df["timestamp"] >= pd.Timestamp("2025-01-01", tz="UTC"))
        & (df["timestamp"] < pd.Timestamp("2026-01-01", tz="UTC"))
    ].copy()

    holdout = df[
        df["timestamp"] >= pd.Timestamp("2026-01-01", tz="UTC")
    ].copy()

    candidates = []

    keys = list(GRID.keys())

    import itertools

    for values in itertools.product(
        *(GRID[key] for key in keys)
    ):

        params = dict(
            zip(keys, values)
        )

        config = {
            **BASE,
            "risk_reward": params["risk_reward"],
            "min_signal_score": params["min_signal_score"],
            "max_trades_per_week": params["max_trades_per_week"],
            "atr_stop_multiplier": params["atr_stop_multiplier"],
        }

        train_result = run_variant(
            config,
            train,
            params["profit_protection"],
        )

        train_metrics = train_result["metrics"]

        if (
            train_metrics["total_return_pct"] <= 0
            or (train_metrics["profit_factor"] or 0.0) <= 1.0
            or train_metrics["total_trades"] < 10
        ):
            continue

        selection_result = run_variant(
            config,
            selection,
            params["profit_protection"],
        )

        selection_metrics = selection_result["metrics"]

        if (
            selection_metrics["total_return_pct"] <= 0
            or (selection_metrics["profit_factor"] or 0.0) <= 1.0
            or selection_metrics["total_trades"] < 8
        ):
            continue

        candidates.append(
            {
                "params": params,
                "train_return_pct": train_metrics["total_return_pct"],
                "train_profit_factor": train_metrics["profit_factor"],
                "train_drawdown_pct": train_metrics["max_drawdown_pct"],
                "train_win_rate_pct": train_metrics["win_rate_pct"],
                "train_trades": train_metrics["total_trades"],
                "selection_return_pct": selection_metrics["total_return_pct"],
                "selection_profit_factor": selection_metrics["profit_factor"],
                "selection_drawdown_pct": selection_metrics["max_drawdown_pct"],
                "selection_win_rate_pct": selection_metrics["win_rate_pct"],
                "selection_trades": selection_metrics["total_trades"],
                "selection_score": selection_score(selection_metrics),
            }
        )

    if not candidates:
        raise SystemExit(
            "No V3 candidate passed the development and selection filters."
        )

    candidates.sort(
        key=lambda item: item["selection_score"],
        reverse=True,
    )

    best = candidates[0]

    selected_config = {
        **BASE,
        "risk_reward": best["params"]["risk_reward"],
        "min_signal_score": best["params"]["min_signal_score"],
        "max_trades_per_week": best["params"]["max_trades_per_week"],
        "atr_stop_multiplier": best["params"]["atr_stop_multiplier"],
    }

    selected_protection = best["params"]["profit_protection"]

    holdout_result = run_variant(
        selected_config,
        holdout,
        selected_protection,
    )

    full_result = run_variant(
        selected_config,
        df,
        selected_protection,
    )

    holdout_metrics = holdout_result["metrics"]
    full_metrics = full_result["metrics"]

    diagnostics = diagnostic_summary(
        full_result["trades"]
    )

    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    pd.DataFrame(
        candidates
    ).head(50).to_csv(
        OUT / "top_50_candidates.csv",
        index=False,
    )

    with open(
        OUT / "optimization.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {
                "status": "completed",
                "research_only": True,
                "live_trading": False,
                "method": "three_period_robustness_test",
                "development_period": "2024-01-01 through 2024-12-31",
                "selection_period": "2025-01-01 through 2025-12-31",
                "final_unseen_holdout": "2026-01-01 onward",
                "candidates_tested": len(candidates),
                "selected": best,
                "holdout_metrics": holdout_metrics,
                "full_period_metrics": full_metrics,
                "diagnostics": diagnostics,
            },
            f,
            indent=2,
            default=str,
        )

    with open(
        OUT / "summary.txt",
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "RAYMOND V2.8 WEEKLY GROWTH V3\n"
            "==============================\n\n"
            "RESEARCH ONLY: YES\n"
            "LIVE TRADING: NO\n\n"
        )

        f.write(
            "SELECTED PARAMETERS\n"
            "-------------------\n"
        )

        f.write(
            f"{best['params']}\n\n"
        )

        f.write(
            "DEVELOPMENT 2024\n"
            "----------------\n"
            f"Return: {best['train_return_pct']:.2f}%\n"
            f"PF: {best['train_profit_factor']}\n"
            f"Win rate: {best['train_win_rate_pct']:.2f}%\n"
            f"Drawdown: {best['train_drawdown_pct']:.2f}%\n"
            f"Trades: {best['train_trades']}\n\n"
        )

        f.write(
            "SELECTION 2025\n"
            "--------------\n"
            f"Return: {best['selection_return_pct']:.2f}%\n"
            f"PF: {best['selection_profit_factor']}\n"
            f"Win rate: {best['selection_win_rate_pct']:.2f}%\n"
            f"Drawdown: {best['selection_drawdown_pct']:.2f}%\n"
            f"Trades: {best['selection_trades']}\n\n"
        )

        f.write(
            "FINAL UNSEEN HOLDOUT 2026+\n"
            "---------------------------\n"
            f"Return: {holdout_metrics['total_return_pct']:.2f}%\n"
            f"PF: {holdout_metrics['profit_factor']}\n"
            f"Win rate: {holdout_metrics['win_rate_pct']:.2f}%\n"
            f"Drawdown: {holdout_metrics['max_drawdown_pct']:.2f}%\n"
            f"Trades: {holdout_metrics['total_trades']}\n\n"
        )

        f.write(
            "FULL PERIOD\n"
            "-----------\n"
            f"Return: {full_metrics['total_return_pct']:.2f}%\n"
            f"PF: {full_metrics['profit_factor']}\n"
            f"Win rate: {full_metrics['win_rate_pct']:.2f}%\n"
            f"Drawdown: {full_metrics['max_drawdown_pct']:.2f}%\n"
            f"Trades: {full_metrics['total_trades']}\n\n"
        )

        f.write(
            "TRADE DIAGNOSTICS\n"
            "-----------------\n"
        )

        f.write(
            json.dumps(
                diagnostics,
                indent=2,
            )
        )

    pd.DataFrame(
        [
            {
                "direction": t.direction,
                "signal_time": t.signal_time,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "stop_price": t.stop_price,
                "target_price": t.target_price,
                "volume": t.volume,
                "risk_amount": t.risk_amount,
                "pnl": t.pnl,
                "r_multiple": t.r_multiple,
                "signal_score": t.signal_score,
                "exit_reason": t.exit_reason,
                "setup_reason": t.setup_reason,
                "balance_before": t.balance_before,
                "balance_after": t.balance_after,
                "week": t.week,
            }
            for t in full_result["trades"]
        ]
    ).to_csv(
        OUT / "selected_full_period_trades.csv",
        index=False,
    )

    print()
    print("RAYMOND V2.8 WEEKLY GROWTH V3")
    print("==============================")
    print()
    print("SELECTED:")
    print(best["params"])
    print()
    print("2024 DEVELOPMENT:")
    print(f"Return: {best['train_return_pct']:.2f}%")
    print(f"PF: {best['train_profit_factor']}")
    print(f"Win rate: {best['train_win_rate_pct']:.2f}%")
    print(f"Drawdown: {best['train_drawdown_pct']:.2f}%")
    print(f"Trades: {best['train_trades']}")
    print()
    print("2025 SELECTION:")
    print(f"Return: {best['selection_return_pct']:.2f}%")
    print(f"PF: {best['selection_profit_factor']}")
    print(f"Win rate: {best['selection_win_rate_pct']:.2f}%")
    print(f"Drawdown: {best['selection_drawdown_pct']:.2f}%")
    print(f"Trades: {best['selection_trades']}")
    print()
    print("2026+ FINAL UNSEEN HOLDOUT:")
    print(f"Return: {holdout_metrics['total_return_pct']:.2f}%")
    print(f"PF: {holdout_metrics['profit_factor']}")
    print(f"Win rate: {holdout_metrics['win_rate_pct']:.2f}%")
    print(f"Drawdown: {holdout_metrics['max_drawdown_pct']:.2f}%")
    print(f"Trades: {holdout_metrics['total_trades']}")
    print()
    print("FULL PERIOD:")
    print(f"Return: {full_metrics['total_return_pct']:.2f}%")
    print(f"PF: {full_metrics['profit_factor']}")
    print(f"Win rate: {full_metrics['win_rate_pct']:.2f}%")
    print(f"Drawdown: {full_metrics['max_drawdown_pct']:.2f}%")
    print(f"Trades: {full_metrics['total_trades']}")
    print()
    print("Results written to:")
    print(OUT)


if __name__ == "__main__":
    main()
