"""
RAYMOND V2.8 — MONTHLY TRADE FORENSIC ANALYZER

RESEARCH ONLY.

Reconstructs the price path of completed PAPER trades using:
    1. monthly_trade_audit.json
    2. normalized XAUUSD M5 OHLC data

This module NEVER:
- sends orders
- modifies positions
- modifies the active strategy
- promotes research candidates

IMPORTANT:
M5 OHLC cannot reveal the exact order of high/low movement inside one
candle. If both favorable and adverse levels occur in one candle,
the candle is marked ambiguous instead of inventing the intrabar order.

Only complete M5 candles inside the trade lifetime are used for
price-path extremes. Exact entry and exit prices are retained.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


THRESHOLDS_R = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def parse_time(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None

    try:
        result = pd.to_datetime(value, utc=True)
        return result if not pd.isna(result) else None
    except Exception:
        return None


def direction(value: Any) -> str:
    return str(value or "").strip().upper()


def threshold_key(value: float) -> str:
    return f"mfe_ge_{str(value).replace('.', '_')}R"


def load_m5(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"M5 data missing columns: {sorted(missing)}"
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    for column in (
        "open",
        "high",
        "low",
        "close",
    ):
        df[column] = pd.to_numeric(
            df[column],
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

    df = (
        df.sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )

    if df.empty:
        raise ValueError(
            "M5 dataset contains no usable rows."
        )

    return df


def favorable_move(
    side: str,
    entry: float,
    price: float,
) -> float:
    if side == "BUY":
        return price - entry

    if side == "SELL":
        return entry - price

    raise ValueError(
        f"Unsupported direction: {side}"
    )


def adverse_move(
    side: str,
    entry: float,
    price: float,
) -> float:
    if side == "BUY":
        return entry - price

    if side == "SELL":
        return price - entry

    raise ValueError(
        f"Unsupported direction: {side}"
    )


def analyze_trade(
    trade: dict[str, Any],
    m5: pd.DataFrame,
) -> dict[str, Any]:

    trade_id = str(
        trade.get("trade_id") or ""
    )

    side = direction(
        trade.get("direction")
    )

    entry = safe_float(
        trade.get("entry_price")
    )

    exit_price = safe_float(
        trade.get("exit_price")
    )

    opened = parse_time(
        trade.get("opened_at")
    )

    closed = parse_time(
        trade.get("closed_at")
    )

    risk = safe_float(
        trade.get("initial_risk_distance")
    )

    if not risk:
        stop = safe_float(
            trade.get("initial_stop_loss")
        )

        if (
            entry is not None
            and stop is not None
        ):
            risk = abs(
                entry - stop
            )

    pnl = safe_float(
        trade.get("total_trade_pnl")
    )

    result = {
        "trade_id": trade_id,
        "direction": side,
        "entry_price": entry,
        "exit_price": exit_price,
        "opened_at": (
            opened.isoformat()
            if opened is not None
            else None
        ),
        "closed_at": (
            closed.isoformat()
            if closed is not None
            else None
        ),
        "corrected_pnl": pnl,
        "quantity": safe_float(
            trade.get("quantity")
        ),
        "initial_risk_distance": risk,
        "research_only": True,
        "source_mode": (
            "M5_OHLC_CONSERVATIVE"
        ),
        "data_quality": {
            "usable_candles": 0,
            "ambiguous_candles": 0,
            "warnings": [],
        },
    }

    if (
        entry is None
        or exit_price is None
        or opened is None
        or closed is None
    ):
        result["classification"] = (
            "insufficient_trade_fields"
        )

        result["data_quality"]["warnings"].append(
            "Missing entry, exit, open, or close timestamp."
        )

        return result

    if closed < opened:
        result["classification"] = (
            "invalid_time_range"
        )

        result["data_quality"]["warnings"].append(
            "closed_at precedes opened_at."
        )

        return result

    if side not in {
        "BUY",
        "SELL",
    }:
        result["classification"] = (
            "unsupported_direction"
        )

        result["data_quality"]["warnings"].append(
            f"Unsupported direction: {side}"
        )

        return result

    if risk is None or risk <= 0:
        result["classification"] = (
            "missing_risk_1r"
        )

        result["data_quality"]["warnings"].append(
            "No valid initial 1R distance."
        )

        return result

    # Only complete M5 candles fully inside the trade lifetime.
    candle_end = (
        m5["timestamp"]
        + pd.Timedelta(minutes=5)
    )

    path = m5.loc[
        (m5["timestamp"] >= opened)
        & (candle_end <= closed)
    ].copy()

    result["data_quality"]["usable_candles"] = int(
        len(path)
    )

    if path.empty:
        result["classification"] = (
            "no_complete_m5_candles"
        )

        result["data_quality"]["warnings"].append(
            "No complete M5 candles inside trade lifetime."
        )

        return result

    mfe_price = 0.0
    mae_price = 0.0
    mfe_timestamp = None
    mfe_index = None

    ambiguous = 0

    for index, candle in path.iterrows():

        if side == "BUY":
            favorable = max(
                0.0,
                float(candle["high"]) - entry,
            )

            adverse = max(
                0.0,
                entry - float(candle["low"]),
            )

        else:
            favorable = max(
                0.0,
                entry - float(candle["low"]),
            )

            adverse = max(
                0.0,
                float(candle["high"]) - entry,
            )

        if (
            favorable > 0
            and adverse > 0
        ):
            ambiguous += 1

        if favorable > mfe_price:
            mfe_price = favorable
            mfe_timestamp = candle["timestamp"]
            mfe_index = index

        mae_price = max(
            mae_price,
            adverse,
        )

    result["data_quality"][
        "ambiguous_candles"
    ] = ambiguous

    # Exact final exit movement.
    final_favorable = favorable_move(
        side,
        entry,
        exit_price,
    )

    final_adverse = adverse_move(
        side,
        entry,
        exit_price,
    )

    if final_adverse > 0:
        mae_price = max(
            mae_price,
            final_adverse,
        )

    mfe_r = mfe_price / risk
    mae_r = mae_price / risk

    final_price_r = (
        final_favorable / risk
    )

    is_loss = (
        pnl is not None
        and pnl < 0
    )

    favorable_then_loss = (
        is_loss
        and mfe_price > 0
    )

    classification = (
        "never_favorable"
    )

    if favorable_then_loss:

        if mfe_r >= 2.0:
            classification = (
                "reached_2R_then_reversed_to_loss"
            )

        elif mfe_r >= 1.5:
            classification = (
                "reached_1_5R_then_reversed_to_loss"
            )

        elif mfe_r >= 1.0:
            classification = (
                "reached_1R_then_reversed_to_loss"
            )

        elif mfe_r >= 0.75:
            classification = (
                "reached_0_75R_then_reversed_to_loss"
            )

        elif mfe_r >= 0.5:
            classification = (
                "reached_0_5R_then_reversed_to_loss"
            )

        elif mfe_r >= 0.25:
            classification = (
                "meaningfully_favorable_then_reversed_to_loss"
            )

        else:
            classification = (
                "briefly_favorable_then_reversed_to_loss"
            )

    elif mfe_price > 0:
        classification = (
            "favorable_but_not_final_loss"
        )

    # Did price cross entry again after the MFE candle?
    crossed_entry = False

    if mfe_index is not None:

        after_mfe = path.loc[
            path.index > mfe_index
        ]

        if side == "BUY":
            crossed_entry = bool(
                (
                    after_mfe["low"]
                    <= entry
                ).any()
            )

        else:
            crossed_entry = bool(
                (
                    after_mfe["high"]
                    >= entry
                ).any()
            )

    # TP1 zone.
    tp1 = safe_float(
        trade.get("take_profit")
    )

    reached_tp1 = False

    if tp1 is not None:

        if side == "BUY":
            reached_tp1 = bool(
                (
                    path["high"]
                    >= tp1
                ).any()
            )

        else:
            reached_tp1 = bool(
                (
                    path["low"]
                    <= tp1
                ).any()
            )

    thresholds = {}

    for threshold in THRESHOLDS_R:
        thresholds[
            threshold_key(threshold)
        ] = (
            mfe_r >= threshold
        )

    result.update(
        {
            "classification": classification,
            "loss": is_loss,
            "favorable_then_loss": (
                favorable_then_loss
            ),
            "mfe_price": mfe_price,
            "mae_price": mae_price,
            "mfe_r": mfe_r,
            "mae_r": mae_r,
            "final_price_move_r": final_price_r,
            "giveback_r": (
                mfe_r - final_price_r
            ),
            "mfe_timestamp": (
                mfe_timestamp.isoformat()
                if mfe_timestamp is not None
                else None
            ),
            "time_entry_to_mfe_minutes": (
                (
                    mfe_timestamp - opened
                ).total_seconds()
                / 60.0
                if mfe_timestamp is not None
                else None
            ),
            "mfe_to_exit_minutes": (
                (
                    closed - mfe_timestamp
                ).total_seconds()
                / 60.0
                if mfe_timestamp is not None
                else None
            ),
            "reached_entry_then_reversed": (
                crossed_entry
            ),
            "reached_tp1_zone": (
                reached_tp1
            ),
            "thresholds_reached": thresholds,
            "stored_audit_mfe_r": safe_float(
                trade.get("max_profit_r")
            ),
            "stored_audit_mae_r": safe_float(
                trade.get("max_drawdown_r")
            ),
        }
    )

    if ambiguous:
        result["data_quality"]["warnings"].append(
            "At least one M5 candle touched both favorable "
            "and adverse sides; intrabar order is unknown."
        )

    return result


def summarize(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:

    losses = [
        trade
        for trade in trades
        if trade.get("loss")
    ]

    def count(
        predicate,
    ) -> int:
        return sum(
            1
            for trade in losses
            if predicate(trade)
        )

    def percent(
        number: int,
        total: int,
    ) -> float:

        if total == 0:
            return 0.0

        return round(
            number
            / total
            * 100.0,
            2,
        )

    thresholds = {}

    for threshold in THRESHOLDS_R:

        key = threshold_key(
            threshold
        )

        number = count(
            lambda trade, k=key:
                bool(
                    trade.get(
                        "thresholds_reached",
                        {},
                    ).get(k)
                )
        )

        thresholds[key] = {
            "losses_reaching_threshold": number,
            "losses_total": len(losses),
            "percent": percent(
                number,
                len(losses),
            ),
        }

    mfe_values = [
        float(trade.get("mfe_r") or 0)
        for trade in losses
        if trade.get("mfe_r") is not None
    ]

    mae_values = [
        float(trade.get("mae_r") or 0)
        for trade in losses
        if trade.get("mae_r") is not None
    ]

    return {
        "trades_analyzed": len(trades),
        "losses_analyzed": len(losses),

        "losses_favorable_first": count(
            lambda trade:
                bool(
                    trade.get(
                        "favorable_then_loss"
                    )
                )
        ),

        "losses_briefly_favorable_lt_0_25R": count(
            lambda trade:
                0
                < float(
                    trade.get("mfe_r") or 0
                )
                < 0.25
        ),

        "losses_ge_0_25R": count(
            lambda trade:
                float(
                    trade.get("mfe_r") or 0
                ) >= 0.25
        ),

        "losses_ge_0_5R": count(
            lambda trade:
                float(
                    trade.get("mfe_r") or 0
                ) >= 0.5
        ),

        "losses_ge_0_75R": count(
            lambda trade:
                float(
                    trade.get("mfe_r") or 0
                ) >= 0.75
        ),

        "losses_ge_1R": count(
            lambda trade:
                float(
                    trade.get("mfe_r") or 0
                ) >= 1.0
        ),

        "losses_ge_1_5R": count(
            lambda trade:
                float(
                    trade.get("mfe_r") or 0
                ) >= 1.5
        ),

        "losses_ge_2R": count(
            lambda trade:
                float(
                    trade.get("mfe_r") or 0
                ) >= 2.0
        ),

        "losses_crossed_entry_after_mfe": count(
            lambda trade:
                bool(
                    trade.get(
                        "reached_entry_then_reversed"
                    )
                )
        ),

        "losses_reached_tp1_then_lost": count(
            lambda trade:
                bool(
                    trade.get(
                        "reached_tp1_zone"
                    )
                )
        ),

        "average_loss_mfe_r": (
            round(
                sum(mfe_values)
                / len(mfe_values),
                6,
            )
            if mfe_values
            else 0.0
        ),

        "median_loss_mfe_r": (
            round(
                float(
                    pd.Series(
                        mfe_values
                    ).median()
                ),
                6,
            )
            if mfe_values
            else 0.0
        ),

        "average_loss_mae_r": (
            round(
                sum(mae_values)
                / len(mae_values),
                6,
            )
            if mae_values
            else 0.0
        ),

        "thresholds": thresholds,

        "classification_counts": (
            pd.Series(
                [
                    trade.get(
                        "classification",
                        "unknown",
                    )
                    for trade in losses
                ]
            )
            .value_counts()
            .to_dict()
            if losses
            else {}
        ),

        "interpretation": (
            "MFE above zero alone is not treated as meaningful. "
            "The important reversal thresholds are 0.25R, 0.5R, "
            "0.75R, 1R, 1.5R and 2R."
        ),
    }


def render_markdown(
    report: dict[str, Any],
) -> str:

    summary = report["summary"]

    lines = [
        "# RAYMOND V2.8 Monthly Trade Forensic Audit",
        "",
        f"**Month:** {report['month']}",
        f"**Symbol:** {report['symbol']}",
        "**Mode:** RESEARCH ONLY",
        "",
        "## Safety",
        "",
        "- No live orders.",
        "- No position modifications.",
        "- No strategy modifications.",
        "- No automatic promotion.",
        "",
        "## Reversal Analysis",
        "",
        f"- Trades analyzed: **{summary['trades_analyzed']}**",
        f"- Losing trades: **{summary['losses_analyzed']}**",
        f"- Losses favorable first: **{summary['losses_favorable_first']}**",
        f"- Losses reaching 0.25R+: **{summary['losses_ge_0_25R']}**",
        f"- Losses reaching 0.5R+: **{summary['losses_ge_0_5R']}**",
        f"- Losses reaching 0.75R+: **{summary['losses_ge_0_75R']}**",
        f"- Losses reaching 1R+: **{summary['losses_ge_1R']}**",
        f"- Losses reaching 1.5R+: **{summary['losses_ge_1_5R']}**",
        f"- Losses reaching 2R+: **{summary['losses_ge_2R']}**",
        f"- Losses crossing entry after MFE: **{summary['losses_crossed_entry_after_mfe']}**",
        f"- Losses reaching TP1 then losing: **{summary['losses_reached_tp1_then_lost']}**",
        "",
        f"- Average loss MFE: **{summary['average_loss_mfe_r']}R**",
        f"- Median loss MFE: **{summary['median_loss_mfe_r']}R**",
        f"- Average loss MAE: **{summary['average_loss_mae_r']}R**",
        "",
        "## Thresholds",
        "",
        "| Threshold | Losses | Percent |",
        "|---|---:|---:|",
    ]

    for key, value in summary[
        "thresholds"
    ].items():

        lines.append(
            f"| {key} | "
            f"{value['losses_reaching_threshold']} | "
            f"{value['percent']:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Losing Trades",
            "",
            "| Trade | Side | P/L | MFE R | MAE R | Classification | Crossed Entry | TP1 |",
            "|---|---|---:|---:|---:|---|---|---|",
        ]
    )

    for trade in report["trades"]:

        if not trade.get("loss"):
            continue

        lines.append(
            f"| {trade['trade_id']} | "
            f"{trade['direction']} | "
            f"{float(trade.get('corrected_pnl') or 0):.2f} | "
            f"{float(trade.get('mfe_r') or 0):.4f} | "
            f"{float(trade.get('mae_r') or 0):.4f} | "
            f"{trade.get('classification')} | "
            f"{trade.get('reached_entry_then_reversed')} | "
            f"{trade.get('reached_tp1_zone')} |"
        )

    lines.extend(
        [
            "",
            "## Important Limitation",
            "",
            "M5 OHLC cannot determine the exact order of movements "
            "inside an individual five-minute candle. Ambiguous candles "
            "are explicitly flagged rather than guessed.",
            "",
            "Partial entry/exit candles are excluded from the price "
            "extreme calculation so the analysis does not accidentally "
            "use movement that occurred outside the trade.",
            "",
            "This report is diagnostic research only.",
        ]
    )

    return "\n".join(lines)


def main() -> int:

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

    audit_path = Path(
        args.audit
    )

    m5_path = Path(
        args.m5
    )

    output_dir = Path(
        args.output
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit = json.loads(
        audit_path.read_text(
            encoding="utf-8"
        )
    )

    # Hard safety gates.
    if audit.get(
        "research_only"
    ) is not True:
        raise SystemExit(
            "REFUSING: audit is not research_only=true"
        )

    if audit.get(
        "live_trading_changed"
    ) is not False:
        raise SystemExit(
            "REFUSING: audit reports live trading changed"
        )

    m5 = load_m5(
        m5_path
    )

    source_trades = audit.get(
        "trades",
        [],
    )

    analyzed = [
        analyze_trade(
            trade,
            m5,
        )
        for trade in source_trades
    ]

    report = {
        "report_type":
            "RAYMOND_MONTHLY_TRADE_FORENSIC",

        "version":
            "1.0",

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
                "XAUUSD",
            ),

        "month":
            audit.get("month"),

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "market_data": {
            "timeframe": "M5",
            "rows": len(m5),
            "first_timestamp":
                m5["timestamp"]
                .min()
                .isoformat(),
            "last_timestamp":
                m5["timestamp"]
                .max()
                .isoformat(),
            "path_mode":
                "complete_M5_candles_plus_exact_entry_exit",
        },

        "summary":
            summarize(
                analyzed
            ),

        "trades":
            analyzed,

        "safety": {
            "research_only": True,
            "read_only": True,
            "live_trading_changed": False,
            "positions_modified": False,
            "strategy_modified": False,
            "orders_created": False,
            "candidates_promoted": False,
        },
    }

    json_output = (
        output_dir
        / "monthly_trade_forensic.json"
    )

    md_output = (
        output_dir
        / "monthly_trade_forensic.md"
    )

    json_output.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    md_output.write_text(
        render_markdown(
            report
        ),
        encoding="utf-8",
    )

    summary = report["summary"]

    print(
        "========================================"
    )

    print(
        "RAYMOND MONTHLY TRADE FORENSIC"
    )

    print(
        "========================================"
    )

    print(
        "Month:",
        report["month"],
    )

    print(
        "Research only:",
        report["research_only"],
    )

    print(
        "Trades analyzed:",
        summary["trades_analyzed"],
    )

    print(
        "Losses:",
        summary["losses_analyzed"],
    )

    print(
        "Losses favorable first:",
        summary[
            "losses_favorable_first"
        ],
    )

    print(
        "Losses >= 0.25R:",
        summary[
            "losses_ge_0_25R"
        ],
    )

    print(
        "Losses >= 0.50R:",
        summary[
            "losses_ge_0_5R"
        ],
    )

    print(
        "Losses >= 0.75R:",
        summary[
            "losses_ge_0_75R"
        ],
    )

    print(
        "Losses >= 1R:",
        summary[
            "losses_ge_1R"
        ],
    )

    print(
        "Losses >= 1.5R:",
        summary[
            "losses_ge_1_5R"
        ],
    )

    print(
        "Losses >= 2R:",
        summary[
            "losses_ge_2R"
        ],
    )

    print(
        "Losses crossed entry after MFE:",
        summary[
            "losses_crossed_entry_after_mfe"
        ],
    )

    print(
        "Losses reached TP1 then lost:",
        summary[
            "losses_reached_tp1_then_lost"
        ],
    )

    print(
        "Average loss MFE R:",
        summary[
            "average_loss_mfe_r"
        ],
    )

    print(
        "========================================"
    )

    print(
        "NO STRATEGY OR LIVE TRADING CHANGES."
    )

    print(
        "========================================"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
