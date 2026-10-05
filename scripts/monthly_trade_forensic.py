#!/usr/bin/env python3
"""
RAYMOND V2.8 monthly trade price-path forensic analyzer.

RESEARCH ONLY:
- Reads the existing monthly trade audit.
- Reads XAUUSD M5 OHLC data.
- Reconstructs MFE, MAE and reversal behavior.
- Does not place trades.
- Does not modify positions.
- Does not modify the live strategy.
- Does not promote candidates.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPORT_TYPE = "RAYMOND_MONTHLY_TRADE_FORENSIC"
VERSION = "1.0"
SYMBOL = "XAUUSD"


def first(obj: dict, *keys: str, default=None):
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return default


def num(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def parse_time(value: Any):
    if value is None:
        return None

    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        x = float(value)

        if abs(x) >= 1e17:
            unit = "ns"
        elif abs(x) >= 1e14:
            unit = "us"
        elif abs(x) >= 1e11:
            unit = "ms"
        else:
            unit = "s"

        return pd.to_datetime(
            x,
            unit=unit,
            utc=True,
            errors="coerce",
        )

    return pd.to_datetime(
        value,
        utc=True,
        errors="coerce",
    )


def normalize_timestamp(series: pd.Series) -> pd.Series:
    """
    Correctly detect Unix seconds/milliseconds/microseconds/nanoseconds.

    This prevents a 2026 Unix timestamp from accidentally becoming
    a January 1970 timestamp when pandas assumes nanoseconds.
    """

    numeric = pd.to_numeric(
        series,
        errors="coerce",
    )

    if numeric.notna().mean() >= 0.80:
        values = numeric.dropna().abs()

        if not values.empty:
            median = float(values.median())

            if median >= 1e17:
                unit = "ns"
            elif median >= 1e14:
                unit = "us"
            elif median >= 1e11:
                unit = "ms"
            elif median >= 1e9:
                unit = "s"
            else:
                unit = None

            if unit:
                return pd.to_datetime(
                    numeric,
                    unit=unit,
                    utc=True,
                    errors="coerce",
                )

    return pd.to_datetime(
        series,
        utc=True,
        errors="coerce",
    )


def load_m5(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    df.columns = [
        str(column)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        for column in df.columns
    ]

    timestamp_column = None

    for candidate in (
        "timestamp",
        "time",
        "datetime",
        "date",
        "timestamp_utc",
    ):
        if candidate in df.columns:
            timestamp_column = candidate
            break

    if timestamp_column is None:
        raise ValueError(
            "M5 data has no timestamp column."
        )

    aliases = {
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c"),
        "volume": ("volume", "vol", "v"),
    }

    for target, candidates in aliases.items():
        if target in df.columns:
            continue

        for candidate in candidates:
            if candidate in df.columns:
                df[target] = df[candidate]
                break

    required = [
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
            f"M5 data missing columns: {missing}"
        )

    df["timestamp"] = normalize_timestamp(
        df[timestamp_column]
    )

    for column in required:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    if "volume" not in df.columns:
        df["volume"] = 0.0

    df["volume"] = pd.to_numeric(
        df["volume"],
        errors="coerce",
    ).fillna(0.0)

    df = df[
        [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    ]

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
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )

    if df.empty:
        raise ValueError(
            "M5 dataset is empty."
        )

    start = df["timestamp"].min()
    end = df["timestamp"].max()

    if start.year < 2020 or end.year > 2100:
        raise ValueError(
            f"Invalid M5 timestamp range: "
            f"{start} -> {end}"
        )

    if (df["high"] < df["low"]).any():
        raise ValueError(
            "M5 data contains high < low."
        )

    return df


def risk_distance(trade: dict) -> float:
    persisted = first(
        trade,
        "initial_risk_distance",
        "risk_1r",
    )

    if finite(persisted) and abs(float(persisted)) > 0:
        return abs(float(persisted))

    entry = num(
        first(
            trade,
            "entry_price",
            default=0.0,
        )
    )

    stop = num(
        first(
            trade,
            "initial_stop_loss",
            "stop_loss",
            default=0.0,
        )
    )

    return abs(entry - stop)


def classify_loss(
    pnl: float,
    mfe_r: float,
    reached_tp: bool,
    recrossed: bool,
) -> str:

    if pnl >= 0:
        return "not_a_loss"

    if reached_tp:
        return "reached_tp_then_lost"

    if mfe_r >= 2.0:
        return "reached_2r_then_reversed_to_loss"

    if mfe_r >= 1.5:
        return "reached_1_5r_then_reversed_to_loss"

    if mfe_r >= 1.0:
        return "reached_1r_then_reversed_to_loss"

    if mfe_r >= 0.75:
        return "reached_0_75r_then_reversed_to_loss"

    if mfe_r >= 0.5:
        return "reached_0_5r_then_reversed_to_loss"

    if mfe_r >= 0.25:
        return "reached_0_25r_then_reversed_to_loss"

    if mfe_r > 0 and recrossed:
        return "briefly_favorable_then_reversed_to_loss"

    if mfe_r > 0:
        return "favorable_but_below_0_25r"

    return "never_favorable"


def analyze_trade(
    trade: dict,
    m5: pd.DataFrame,
) -> dict:

    entry = num(
        first(
            trade,
            "entry_price",
            default=0.0,
        )
    )

    direction = str(
        first(
            trade,
            "direction",
            default="",
        )
    ).upper()

    pnl = num(
        first(
            trade,
            "pnl",
            "total_trade_pnl",
            default=0.0,
        )
    )

    opened = parse_time(
        first(
            trade,
            "opened_at",
            "entry_time",
            "open_time",
        )
    )

    closed = parse_time(
        first(
            trade,
            "closed_at",
            "exit_time",
            "close_time",
        )
    )

    if direction not in {"BUY", "SELL"}:
        raise ValueError(
            f"Unsupported direction: {direction}"
        )

    if (
        opened is None
        or closed is None
        or pd.isna(opened)
        or pd.isna(closed)
        or closed < opened
    ):
        raise ValueError(
            "Invalid trade timestamps."
        )

    risk = risk_distance(trade)

    candles = m5[
        (m5["timestamp"] >= opened)
        & (m5["timestamp"] <= closed)
    ].copy()

    if candles.empty:
        return {
            "trade_id": first(
                trade,
                "trade_id",
                "position_id",
                default="",
            ),
            "direction": direction,
            "pnl": pnl,
            "entry_price": entry,
            "risk_distance": risk,
            "market_candles": 0,
            "data_status":
                "NO_M5_CANDLES_IN_TRADE_WINDOW",
            "mfe_r": None,
            "mae_r": None,
            "reached_favorable_price": False,
            "recrossed_entry_after_favorable_move": False,
            "reached_tp": False,
            "loss_classification": "unavailable",
        }

    if direction == "BUY":
        favorable = candles["high"] - entry
        adverse = entry - candles["low"]

        final_move = (
            num(candles.iloc[-1]["close"])
            - entry
        )
    else:
        favorable = entry - candles["low"]
        adverse = candles["high"] - entry

        final_move = (
            entry
            - num(candles.iloc[-1]["close"])
        )

    mfe_index = favorable.idxmax()
    mae_index = adverse.idxmax()

    mfe_price = max(
        0.0,
        num(favorable.loc[mfe_index]),
    )

    mae_price = max(
        0.0,
        num(adverse.loc[mae_index]),
    )

    mfe_r = (
        mfe_price / risk
        if risk > 0
        else float("nan")
    )

    mae_r = (
        mae_price / risk
        if risk > 0
        else float("nan")
    )

    final_r = (
        final_move / risk
        if risk > 0
        else float("nan")
    )

    mfe_time = candles.loc[
        mfe_index,
        "timestamp",
    ]

    mae_time = candles.loc[
        mae_index,
        "timestamp",
    ]

    favorable_rows = candles[
        favorable > 0
    ]

    reached_favorable = (
        not favorable_rows.empty
    )

    recrossed = False
    recross_time = None

    if reached_favorable:
        first_favorable_time = (
            favorable_rows["timestamp"].min()
        )

        later = candles[
            candles["timestamp"]
            > first_favorable_time
        ]

        if direction == "BUY":
            recross = later[
                later["low"] <= entry
            ]
        else:
            recross = later[
                later["high"] >= entry
            ]

        if not recross.empty:
            recrossed = True
            recross_time = recross.iloc[0][
                "timestamp"
            ]

    take_profit = first(
        trade,
        "take_profit",
        "take_profit_1",
        "tp",
    )

    reached_tp = False

    if finite(take_profit):
        tp = float(take_profit)

        if direction == "BUY":
            reached_tp = bool(
                (candles["high"] >= tp).any()
            )
        else:
            reached_tp = bool(
                (candles["low"] <= tp).any()
            )

    return {
        "trade_id": first(
            trade,
            "trade_id",
            "position_id",
            default="",
        ),
        "symbol": first(
            trade,
            "symbol",
            default=SYMBOL,
        ),
        "direction": direction,
        "pnl": pnl,
        "quantity": num(
            first(
                trade,
                "quantity",
                "original_quantity",
                default=0.0,
            )
        ),
        "entry_price": entry,
        "exit_price": first(
            trade,
            "exit_price",
        ),
        "initial_stop_loss": first(
            trade,
            "initial_stop_loss",
            "stop_loss",
        ),
        "take_profit": take_profit,
        "risk_distance": risk,
        "opened_at": opened.isoformat(),
        "closed_at": closed.isoformat(),
        "market_candles": int(len(candles)),
        "data_status": "OK",

        "mfe_price": mfe_price,
        "mae_price": mae_price,

        "mfe_r": (
            None
            if not finite(mfe_r)
            else mfe_r
        ),

        "mae_r": (
            None
            if not finite(mae_r)
            else mae_r
        ),

        "final_price_move": final_move,

        "final_price_move_r": (
            None
            if not finite(final_r)
            else final_r
        ),

        "giveback_r": (
            None
            if not finite(mfe_r)
            or not finite(final_r)
            else mfe_r - final_r
        ),

        "mfe_time": mfe_time.isoformat(),
        "mae_time": mae_time.isoformat(),

        "minutes_entry_to_mfe": (
            mfe_time - opened
        ).total_seconds() / 60.0,

        "minutes_mfe_to_exit": (
            closed - mfe_time
        ).total_seconds() / 60.0,

        "reached_favorable_price":
            reached_favorable,

        "recrossed_entry_after_favorable_move":
            recrossed,

        "recross_time": (
            recross_time.isoformat()
            if recross_time is not None
            else None
        ),

        "reached_tp": reached_tp,

        "mfe_ge_0r":
            mfe_r >= 0
            if finite(mfe_r)
            else False,

        "mfe_ge_0_25r":
            mfe_r >= 0.25
            if finite(mfe_r)
            else False,

        "mfe_ge_0_5r":
            mfe_r >= 0.5
            if finite(mfe_r)
            else False,

        "mfe_ge_0_75r":
            mfe_r >= 0.75
            if finite(mfe_r)
            else False,

        "mfe_ge_1r":
            mfe_r >= 1.0
            if finite(mfe_r)
            else False,

        "mfe_ge_1_5r":
            mfe_r >= 1.5
            if finite(mfe_r)
            else False,

        "mfe_ge_2r":
            mfe_r >= 2.0
            if finite(mfe_r)
            else False,

        "regime": first(
            trade,
            "regime",
        ),

        "setup": first(
            trade,
            "setup",
        ),

        "technical_score": first(
            trade,
            "technical_score",
        ),

        "confidence": first(
            trade,
            "confidence",
        ),

        "break_even_applied": bool(
            first(
                trade,
                "break_even_applied",
                default=False,
            )
        ),

        "partial_close_applied": bool(
            first(
                trade,
                "partial_close_applied",
                default=False,
            )
        ),

        "trailing_active": bool(
            first(
                trade,
                "trailing_active",
                default=False,
            )
        ),

        "management_status": first(
            trade,
            "management_status",
        ),

        "last_management_action": first(
            trade,
            "last_management_action",
        ),

        "trade_thesis": first(
            trade,
            "trade_thesis",
        ),

        "favorable_first": (
            reached_favorable
            and pnl < 0
        ),

        "loss_classification":
            classify_loss(
                pnl,
                mfe_r
                if finite(mfe_r)
                else 0.0,
                reached_tp,
                recrossed,
            ),
    }


def mean_value(values):
    values = [
        float(v)
        for v in values
        if finite(v)
    ]

    return (
        statistics.mean(values)
        if values
        else None
    )


def median_value(values):
    values = [
        float(v)
        for v in values
        if finite(v)
    ]

    return (
        statistics.median(values)
        if values
        else None
    )


def summarize(trades):
    losses = [
        t
        for t in trades
        if num(t.get("pnl")) < 0
    ]

    wins = [
        t
        for t in trades
        if num(t.get("pnl")) > 0
    ]

    def count(key):
        return sum(
            1
            for t in losses
            if t.get(key)
        )

    summary = {
        "trade_count": len(trades),
        "loss_count": len(losses),
        "win_count": len(wins),

        "losses_favorable_first":
            sum(
                bool(t.get("favorable_first"))
                for t in losses
            ),

        "losses_recrossed_entry":
            count(
                "recrossed_entry_after_favorable_move"
            ),

        "losses_reached_tp_then_lost":
            count("reached_tp"),

        "losses_mfe_ge_0r":
            count("mfe_ge_0r"),

        "losses_mfe_ge_0_25r":
            count("mfe_ge_0_25r"),

        "losses_mfe_ge_0_5r":
            count("mfe_ge_0_5r"),

        "losses_mfe_ge_0_75r":
            count("mfe_ge_0_75r"),

        "losses_mfe_ge_1r":
            count("mfe_ge_1r"),

        "losses_mfe_ge_1_5r":
            count("mfe_ge_1_5r"),

        "losses_mfe_ge_2r":
            count("mfe_ge_2r"),

        "average_loss_mfe_r":
            mean_value(
                t.get("mfe_r")
                for t in losses
            ),

        "median_loss_mfe_r":
            median_value(
                t.get("mfe_r")
                for t in losses
            ),

        "average_loss_mae_r":
            mean_value(
                t.get("mae_r")
                for t in losses
            ),

        "median_loss_mae_r":
            median_value(
                t.get("mae_r")
                for t in losses
            ),

        "classification_counts":
            dict(
                Counter(
                    t.get(
                        "loss_classification"
                    )
                    for t in losses
                )
            ),

        "direction": {},
    }

    for direction in (
        "BUY",
        "SELL",
    ):
        subset = [
            t
            for t in trades
            if t.get("direction")
            == direction
        ]

        subset_losses = [
            t
            for t in subset
            if num(t.get("pnl")) < 0
        ]

        summary["direction"][direction] = {
            "trades": len(subset),
            "losses": len(subset_losses),

            "total_pnl":
                sum(
                    num(t.get("pnl"))
                    for t in subset
                ),

            "favorable_first_losses":
                sum(
                    bool(
                        t.get(
                            "favorable_first"
                        )
                    )
                    for t in subset_losses
                ),

            "mfe_ge_0_5r_losses":
                sum(
                    bool(
                        t.get(
                            "mfe_ge_0_5r"
                        )
                    )
                    for t in subset_losses
                ),

            "mfe_ge_1r_losses":
                sum(
                    bool(
                        t.get(
                            "mfe_ge_1r"
                        )
                    )
                    for t in subset_losses
                ),
        }

    return summary


def render_markdown(report):
    summary = report["summary"]

    lines = [
        "# RAYMOND V2.8 Monthly Trade Forensic Report",
        "",
        f"- Month: {report['month']}",
        f"- Symbol: {report['symbol']}",
        "- Research only: true",
        "",
        "## Price-path summary",
        "",
        f"- Trades: {summary['trade_count']}",
        f"- Losses: {summary['loss_count']}",
        f"- Favorable-first losses: "
        f"{summary['losses_favorable_first']}",
        f"- Entry recrosses: "
        f"{summary['losses_recrossed_entry']}",
        f"- TP-then-loss: "
        f"{summary['losses_reached_tp_then_lost']}",
        f"- Average losing MFE: "
        f"{summary['average_loss_mfe_r']}R",
        "",
        "## MFE thresholds",
        "",
        "| Threshold | Losing trades |",
        "|---:|---:|",
        f"| >0R | {summary['losses_mfe_ge_0r']} |",
        f"| >=0.25R | {summary['losses_mfe_ge_0_25r']} |",
        f"| >=0.50R | {summary['losses_mfe_ge_0_5r']} |",
        f"| >=0.75R | {summary['losses_mfe_ge_0_75r']} |",
        f"| >=1.00R | {summary['losses_mfe_ge_1r']} |",
        f"| >=1.50R | {summary['losses_mfe_ge_1_5r']} |",
        f"| >=2.00R | {summary['losses_mfe_ge_2r']} |",
        "",
        "## Loss classifications",
        "",
    ]

    for name, count in sorted(
        summary["classification_counts"].items()
    ):
        lines.append(
            f"- {name}: {count}"
        )

    lines += [
        "",
        "## Losing trades",
        "",
        "| Trade | Dir | P/L | MFE R | MAE R | Recross | TP | Classification |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]

    for trade in report["trades"]:
        if num(trade.get("pnl")) >= 0:
            continue

        mfe = (
            "n/a"
            if trade.get("mfe_r") is None
            else f"{num(trade.get('mfe_r')):.4f}"
        )

        mae = (
            "n/a"
            if trade.get("mae_r") is None
            else f"{num(trade.get('mae_r')):.4f}"
        )

        lines.append(
            f"| {trade.get('trade_id', '')} "
            f"| {trade.get('direction', '')} "
            f"| {num(trade.get('pnl')):.2f} "
            f"| {mfe} "
            f"| {mae} "
            f"| {'YES' if trade.get('recrossed_entry_after_favorable_move') else 'NO'} "
            f"| {'YES' if trade.get('reached_tp') else 'NO'} "
            f"| {trade.get('loss_classification', '')} |"
        )

    lines += [
        "",
        "## Safety",
        "",
        "Research-only analysis. No strategy, position, "
        "order, or production configuration was modified.",
    ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--audit",
        required=True,
    )

    parser.add_argument(
        "--m5",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    with open(
        args.audit,
        "r",
        encoding="utf-8",
    ) as file:
        audit = json.load(file)

    if (
        audit.get("report_type")
        != "RAYMOND_MONTHLY_TRADE_AUDIT"
    ):
        raise SystemExit(
            "Wrong monthly audit report type."
        )

    if audit.get("research_only") is not True:
        raise SystemExit(
            "Audit is not research-only."
        )

    if (
        audit.get("live_trading_changed")
        is not False
    ):
        raise SystemExit(
            "Audit reports live trading changed."
        )

    if (
        audit.get(
            "accounting",
            {},
        ).get(
            "accounting_reconciled"
        )
        is not True
    ):
        raise SystemExit(
            "Audit accounting is not reconciled."
        )

    m5 = load_m5(
        Path(args.m5)
    )

    raw_trades = audit.get(
        "trades",
        [],
    )

    if not isinstance(
        raw_trades,
        list,
    ):
        raise SystemExit(
            "Audit trades field is not a list."
        )

    analyzed = [
        analyze_trade(
            trade,
            m5,
        )
        for trade in raw_trades
    ]

    report = {
        "report_type":
            REPORT_TYPE,

        "version":
            VERSION,

        "research_only":
            True,

        "live_trading_changed":
            False,

        "strategy_modified":
            False,

        "positions_modified":
            False,

        "orders_created":
            False,

        "candidates_promoted":
            False,

        "symbol":
            audit.get(
                "symbol",
                SYMBOL,
            ),

        "month":
            audit.get("month"),

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "market_data": {
            "source":
                "Dukascopy XAUUSD M5",

            "file":
                str(args.m5),

            "rows":
                int(len(m5)),

            "start":
                m5[
                    "timestamp"
                ].min().isoformat(),

            "end":
                m5[
                    "timestamp"
                ].max().isoformat(),
        },

        "summary":
            summarize(
                analyzed
            ),

        "trades":
            analyzed,

        "safety": {
            "research_only":
                True,

            "live_trading_changed":
                False,

            "strategy_modified":
                False,

            "positions_modified":
                False,

            "orders_created":
                False,

            "candidates_promoted":
                False,

            "intrabar_order_invented":
                False,
        },
    }

    output = Path(
        args.output
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        output
        / "monthly_trade_forensic.json"
    ).write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    (
        output
        / "monthly_trade_forensic.md"
    ).write_text(
        render_markdown(report),
        encoding="utf-8",
    )

    summary = report["summary"]

    print(
        "=================================================="
    )
    print(
        "RAYMOND V2.8 MONTHLY TRADE FORENSIC"
    )
    print(
        "=================================================="
    )
    print(
        f"Month: {report['month']}"
    )
    print(
        f"Trades: {summary['trade_count']}"
    )
    print(
        f"Losses: {summary['loss_count']}"
    )
    print(
        "Favorable-first losses: "
        f"{summary['losses_favorable_first']}"
    )
    print(
        "MFE >= 0.50R losses: "
        f"{summary['losses_mfe_ge_0_5r']}"
    )
    print(
        "MFE >= 1.00R losses: "
        f"{summary['losses_mfe_ge_1r']}"
    )
    print(
        "Reached TP then lost: "
        f"{summary['losses_reached_tp_then_lost']}"
    )
    print(
        "M5 range: "
        f"{m5['timestamp'].min()} -> "
        f"{m5['timestamp'].max()}"
    )
    print(
        "RESEARCH ONLY: no strategy, "
        "position, or order was modified."
    )


if __name__ == "__main__":
    main()
