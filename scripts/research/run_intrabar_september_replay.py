from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CONTRACT_SIZE = 100.0
REPORT_TYPE = "RAYMOND_INTRABAR_PAPER_LIFECYCLE_REPLAY"
VERSION = "1.0"


def num(value, default=0.0):
    try:
        value = float(value)
        return default if pd.isna(value) else value
    except (TypeError, ValueError):
        return default


def first(trade, *keys, default=None):
    for key in keys:
        if trade.get(key) not in (None, ""):
            return trade[key]
    return default


def parse_time(value):
    return pd.to_datetime(value, utc=True, errors="coerce")


def direction(trade):
    return str(
        first(
            trade,
            "direction",
            "trade_direction",
            default="",
        )
    ).upper()


def load_m5(path):
    df = pd.read_csv(path)

    df.columns = [
        str(c)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        for c in df.columns
    ]

    aliases = {
        "timestamp": [
            "timestamp",
            "time",
            "datetime",
            "date",
            "timestamp_utc",
        ],
        "open": ["open", "o"],
        "high": ["high", "h"],
        "low": ["low", "l"],
        "close": ["close", "c"],
    }

    rename = {}

    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in df.columns:
                rename[candidate] = target
                break

    df = df.rename(columns=rename)

    required = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:
        raise SystemExit(
            "M5 data missing: "
            + ", ".join(missing)
        )

    raw = df["timestamp"]

    numeric = pd.to_numeric(
        raw,
        errors="coerce",
    )

    if numeric.notna().mean() >= 0.8:
        median = float(
            numeric.dropna()
            .abs()
            .median()
        )

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
            df["timestamp"] = pd.to_datetime(
                numeric,
                unit=unit,
                utc=True,
                errors="coerce",
            )
        else:
            df["timestamp"] = pd.to_datetime(
                raw,
                utc=True,
                errors="coerce",
            )
    else:
        df["timestamp"] = pd.to_datetime(
            raw,
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

    return (
        df
        .dropna(subset=required)
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )


def valid_position(
    direction_value,
    entry,
    stop,
    tp,
):
    return (
        (
            direction_value == "BUY"
            and stop < entry < tp
        )
        or
        (
            direction_value == "SELL"
            and tp < entry < stop
        )
    )


def candle_event(
    direction_value,
    row,
    stop,
    tp,
):
    if direction_value == "BUY":
        hit_stop = row.low <= stop
        hit_tp = row.high >= tp

    elif direction_value == "SELL":
        hit_stop = row.high >= stop
        hit_tp = row.low <= tp

    else:
        return "INVALID"

    # Conservative same-candle rule.
    #
    # If both levels are touched inside
    # one M5 candle, we do NOT assume the
    # favorable sequence.
    if hit_stop:
        return "STOP_LOSS"

    if hit_tp:
        return "TAKE_PROFIT"

    return None


def replay_trade(
    trade,
    m5,
):
    trade_id = str(
        first(
            trade,
            "trade_id",
            "position_id",
            default="",
        )
    )

    direction_value = direction(trade)

    entry = num(
        first(
            trade,
            "entry_price",
            "entry",
        )
    )

    stop = num(
        first(
            trade,
            "initial_stop_loss",
            "stop_loss",
        )
    )

    tp = num(
        first(
            trade,
            "take_profit",
            "take_profit_1",
            "tp",
        )
    )

    quantity = num(
        first(
            trade,
            "original_quantity",
            "quantity",
        )
    )

    opened = parse_time(
        first(
            trade,
            "opened_at",
            "open_time",
        )
    )

    closed = parse_time(
        first(
            trade,
            "closed_at",
            "close_time",
        )
    )

    stored_pnl = num(
        trade.get("pnl")
    )

    result = {
        "trade_id": trade_id,
        "direction": direction_value,
        "stored_pnl": stored_pnl,
        "entry_price": entry,
        "initial_stop_loss": stop,
        "take_profit": tp,
        "quantity": quantity,
    }

    if not valid_position(
        direction_value,
        entry,
        stop,
        tp,
    ):
        result.update(
            {
                "status": "INVALID_POSITION",
                "first_event": None,
                "crossed_tp": False,
                "crossed_sl": False,
            }
        )

        return result

    if (
        pd.isna(opened)
        or pd.isna(closed)
    ):
        result.update(
            {
                "status": "MISSING_TIME",
                "first_event": None,
                "crossed_tp": False,
                "crossed_sl": False,
            }
        )

        return result

    candles = m5[
        (m5["timestamp"] >= opened)
        & (m5["timestamp"] <= closed)
    ]

    if candles.empty:
        result.update(
            {
                "status": "NO_M5_DATA",
                "first_event": None,
                "crossed_tp": False,
                "crossed_sl": False,
            }
        )

        return result

    first_event = None
    event_time = None

    crossed_tp = False
    crossed_sl = False

    for row in candles.itertuples(
        index=False
    ):
        if direction_value == "BUY":
            crossed_tp = (
                crossed_tp
                or row.high >= tp
            )

            crossed_sl = (
                crossed_sl
                or row.low <= stop
            )

        else:
            crossed_tp = (
                crossed_tp
                or row.low <= tp
            )

            crossed_sl = (
                crossed_sl
                or row.high >= stop
            )

        event = candle_event(
            direction_value,
            row,
            stop,
            tp,
        )

        if event:
            first_event = event
            event_time = row.timestamp
            break

    counterfactual_tp_pnl = None

    if first_event == "TAKE_PROFIT":

        if direction_value == "BUY":
            counterfactual_tp_pnl = (
                (tp - entry)
                * quantity
                * CONTRACT_SIZE
            )

        else:
            counterfactual_tp_pnl = (
                (entry - tp)
                * quantity
                * CONTRACT_SIZE
            )

    result.update(
        {
            "status": "OK",
            "m5_candles_in_trade_window": int(
                len(candles)
            ),
            "first_event": first_event,
            "event_time": (
                event_time.isoformat()
                if event_time is not None
                else None
            ),
            "crossed_tp": bool(
                crossed_tp
            ),
            "crossed_sl": bool(
                crossed_sl
            ),
            "counterfactual_full_tp_pnl":
                counterfactual_tp_pnl,
            "stored_last_management_action":
                trade.get(
                    "last_management_action"
                ),
            "break_even_applied": bool(
                trade.get(
                    "break_even_applied",
                    False,
                )
            ),
            "partial_close_applied": bool(
                trade.get(
                    "partial_close_applied",
                    False,
                )
            ),
            "trailing_active": bool(
                trade.get(
                    "trailing_active",
                    False,
                )
            ),
        }
    )

    return result


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
        "--forensic",
        required=False,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    audit = json.loads(
        Path(args.audit)
        .read_text(
            encoding="utf-8"
        )
    )

    if audit.get(
        "report_type"
    ) != "RAYMOND_MONTHLY_TRADE_AUDIT":
        raise SystemExit(
            "Wrong audit report type."
        )

    if audit.get(
        "research_only"
    ) is not True:
        raise SystemExit(
            "Audit is not research-only."
        )

    if audit.get(
        "live_trading_changed"
    ) is not False:
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

    trades = audit.get(
        "trades",
        [],
    )

    if (
        not isinstance(trades, list)
        or not trades
    ):
        raise SystemExit(
            "Audit contains no trade records."
        )

    m5 = load_m5(
        Path(args.m5)
    )

    results = [
        replay_trade(
            trade,
            m5,
        )
        for trade in trades
    ]

    forensic = None

    if (
        args.forensic
        and Path(args.forensic).exists()
    ):
        forensic = json.loads(
            Path(args.forensic)
            .read_text(
                encoding="utf-8"
            )
        )

    tp_losses = [
        result
        for result in results
        if (
            result.get(
                "crossed_tp"
            )
            and result.get(
                "stored_pnl",
                0,
            ) < 0
        )
    ]

    first_tp = [
        result
        for result in results
        if result.get(
            "first_event"
        ) == "TAKE_PROFIT"
    ]

    invalid = [
        result
        for result in results
        if result.get(
            "status"
        ) == "INVALID_POSITION"
    ]

    stored_total = sum(
        result["stored_pnl"]
        for result in results
    )

    hypothetical_tp_total = sum(
        num(
            result.get(
                "counterfactual_full_tp_pnl"
            )
        )
        for result in first_tp
    )

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
                "XAUUSD",
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
                m5["timestamp"]
                .min()
                .isoformat(),

            "end":
                m5["timestamp"]
                .max()
                .isoformat(),
        },

        "comparison": {
            "audited_trade_count":
                len(results),

            "replay_valid_trade_count":
                sum(
                    result.get(
                        "status"
                    ) == "OK"
                    for result in results
                ),

            "invalid_position_count":
                len(invalid),

            "first_tp_event_count":
                len(first_tp),

            "tp_crossed_but_stored_loss_count":
                len(tp_losses),

            "stored_total_pnl":
                stored_total,

            "hypothetical_full_tp_pnl_for_first_tp_events":
                hypothetical_tp_total,

            "hypothetical_value_is_not_execution_pnl":
                True,
        },

        "forensic_cross_check": {
            "forensic_report_present":
                forensic is not None,

            "forensic_trade_count":
                (
                    forensic
                    .get(
                        "summary",
                        {},
                    )
                    .get(
                        "trade_count"
                    )
                    if forensic
                    else None
                ),

            "forensic_tp_then_loss_count":
                (
                    forensic
                    .get(
                        "summary",
                        {},
                    )
                    .get(
                        "losses_reached_tp_then_lost"
                    )
                    if forensic
                    else None
                ),
        },

        "trades":
            results,

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

    json_output = (
        output
        / "intrabar_lifecycle_replay.json"
    )

    json_output.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    lines = [
        "# RAYMOND V2.8 Intrabar Paper Lifecycle Replay",
        "",
        "- Month: "
        + str(
            audit.get("month")
        ),

        "- Research only: true",
        "",

        "## Comparison",
        "",

        "- Audited trades: "
        + str(
            len(results)
        ),

        "- Valid replay trades: "
        + str(
            sum(
                result.get(
                    "status"
                ) == "OK"
                for result in results
            )
        ),

        "- First TP events: "
        + str(
            len(first_tp)
        ),

        "- TP crossed then stored loss: "
        + str(
            len(tp_losses)
        ),

        "- Invalid positions: "
        + str(
            len(invalid)
        ),

        "- Stored audited P/L: "
        + "{:.2f}".format(
            stored_total
        ),

        "- Hypothetical full-TP P/L for first TP events: "
        + "{:.2f}".format(
            hypothetical_tp_total
        ),

        "",

        "The hypothetical TP value is a price-path "
        "counterfactual only; it does not claim that "
        "an order was executed.",

        "",

        "## TP-crossed losses",
        "",

        "| Trade | Direction | Stored P/L | First event | Event time |",
        "|---|---|---:|---|---|",
    ]

    for result in tp_losses:
        lines.append(
            "| {trade_id} | {direction} | "
            "{pnl:.2f} | {event} | {time} |".format(
                trade_id=result[
                    "trade_id"
                ],
                direction=result[
                    "direction"
                ],
                pnl=result[
                    "stored_pnl"
                ],
                event=result.get(
                    "first_event"
                ),
                time=result.get(
                    "event_time"
                ),
            )
        )

    lines += [
        "",
        "## Safety",
        "",
        "Research-only. No production strategy, "
        "positions, orders, or live configuration "
        "were modified.",
    ]

    (
        output
        / "intrabar_lifecycle_replay.md"
    ).write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        "\n".join(lines)
    )


if __name__ == "__main__":
    main()
