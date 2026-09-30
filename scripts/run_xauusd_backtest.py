#!/usr/bin/env python3
"""
RAYMOND v2.8 - XAUUSD H1 historical backtest runner.

This runner is deliberately defensive.

It validates the historical dataset before the production
BacktestEngine is called and emits progress information so a
GitHub Actions run cannot appear completely frozen.

Example:

    PYTHONPATH=backend python scripts/run_xauusd_backtest.py \
      --data data/historical/xauusd_h1_2024_2025_normalized.csv \
      --out backtest_results \
      --starting-balance 10000 \
      --spread 0.30 \
      --slippage 0.05 \
      --commission 0.0 \
      --progress-every 1000

IMPORTANT
---------
This file does not place broker orders.

It does not connect to MT5.

It does not connect to Exness.

It does not enable live trading.

It only feeds historical candles into the RAYMOND
BacktestEngine.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

from app.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
)
from app.risk_engine import (
    RiskEngine,
    SymbolSpecification,
)


def production_xauusd_spec() -> SymbolSpecification:
    """
    Return the production XAUUSD symbol specification used
    by the RAYMOND risk layer.
    """

    return SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        volume_limit=100.0,
        trade_mode=RiskEngine.TRADE_MODE_FULL,
        trade_execution_mode=0,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="USD",
        spread=30,
        spread_float=True,
    )


def validate_dataframe(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate and normalize the complete historical dataframe
    before converting it to the engine's candle representation.
    """

    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing = required - set(df.columns)

    if missing:
        raise SystemExit(
            "Missing required columns: "
            f"{sorted(missing)}"
        )

    if df.empty:
        raise SystemExit(
            "Historical dataset contains zero rows."
        )

    # ---------------------------------------------------------
    # Timestamp
    # ---------------------------------------------------------

    df = df.copy()

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    invalid_timestamp_count = int(
        df["timestamp"].isna().sum()
    )

    if invalid_timestamp_count:
        raise SystemExit(
            "Historical dataset contains "
            f"{invalid_timestamp_count} invalid timestamps."
        )

    # ---------------------------------------------------------
    # Numeric fields
    # ---------------------------------------------------------

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    invalid_numeric = df[
        numeric_columns
    ].isna().any(axis=1)

    invalid_numeric_count = int(
        invalid_numeric.sum()
    )

    if invalid_numeric_count:
        raise SystemExit(
            "Historical dataset contains "
            f"{invalid_numeric_count} rows with invalid "
            "numeric values."
        )

    # ---------------------------------------------------------
    # Sort
    # ---------------------------------------------------------

    df = df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # Duplicate timestamps
    # ---------------------------------------------------------

    duplicate_count = int(
        df["timestamp"].duplicated().sum()
    )

    if duplicate_count:
        print(
            f"Removing {duplicate_count} duplicate candles.",
            flush=True,
        )

        df = df.drop_duplicates(
            subset=["timestamp"],
            keep="first",
        ).reset_index(drop=True)

    # ---------------------------------------------------------
    # Chronological validation
    # ---------------------------------------------------------

    if not df["timestamp"].is_monotonic_increasing:
        raise SystemExit(
            "Historical timestamps are not chronological."
        )

    if df["timestamp"].duplicated().any():
        raise SystemExit(
            "Duplicate timestamps remain after cleanup."
        )

    # ---------------------------------------------------------
    # OHLC validation
    # ---------------------------------------------------------

    invalid_ohlc = (
        (df["open"] <= 0)
        | (df["high"] <= 0)
        | (df["low"] <= 0)
        | (df["close"] <= 0)
        | (df["high"] < df["low"])
        | (df["open"] < df["low"])
        | (df["open"] > df["high"])
        | (df["close"] < df["low"])
        | (df["close"] > df["high"])
    )

    invalid_ohlc_count = int(
        invalid_ohlc.sum()
    )

    if invalid_ohlc_count:
        raise SystemExit(
            "Invalid OHLC rows detected: "
            f"{invalid_ohlc_count}"
        )

    return df


def load_candles(
    path: Path,
) -> list[dict[str, Any]]:
    """
    Load and validate historical candles.

    The production BacktestEngine currently expects a complete
    in-memory sequence, so this function deliberately validates
    the entire input before execution begins.
    """

    print(
        f"Loading historical dataset: {path}",
        flush=True,
    )

    if not path.exists():
        raise SystemExit(
            f"Dataset not found: {path}"
        )

    if not path.is_file():
        raise SystemExit(
            f"Dataset path is not a file: {path}"
        )

    file_size = path.stat().st_size

    if file_size <= 1024:
        raise SystemExit(
            "Dataset file is empty or unexpectedly small."
        )

    print(
        f"Dataset size: {file_size:,} bytes",
        flush=True,
    )

    df = pd.read_csv(path)

    print(
        f"CSV rows loaded: {len(df):,}",
        flush=True,
    )

    df = validate_dataframe(df)

    print(
        f"Validated candles: {len(df):,}",
        flush=True,
    )

    print(
        f"First candle: {df['timestamp'].iloc[0]}",
        flush=True,
    )

    print(
        f"Last candle:  {df['timestamp'].iloc[-1]}",
        flush=True,
    )

    candles: list[dict[str, Any]] = []

    for row in df.itertuples(index=False):
        candles.append(
            {
                "timestamp": row.timestamp.isoformat(),
                "time": row.timestamp.isoformat(),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
        )

    return candles


def write_outputs(
    result: Any,
    out_dir: Path,
    *,
    elapsed_seconds: float,
) -> None:
    """
    Serialize the BacktestResult into stable JSON/CSV artifacts.
    """

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_dict = {
        "status": result.status,
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "start_time": result.start_time,
        "end_time": result.end_time,
        "starting_balance": result.starting_balance,
        "ending_balance": result.ending_balance,
        "net_profit": result.net_profit,
        "net_profit_percent": result.net_profit_percent,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "breakeven_trades": result.breakeven_trades,
        "win_rate_percent": result.win_rate_percent,
        "gross_profit": result.gross_profit,
        "gross_loss": result.gross_loss,
        "profit_factor": result.profit_factor,
        "total_execution_cost": result.total_execution_cost,
        "max_drawdown": result.max_drawdown,
        "max_drawdown_percent": result.max_drawdown_percent,
        "average_trade": result.average_trade,
        "average_win": result.average_win,
        "average_loss": result.average_loss,
        "bars_processed": result.bars_processed,
        "warmup_candles": result.warmup_candles,
        "elapsed_seconds": round(
            elapsed_seconds,
            3,
        ),
        "trades": result.trades,
        "equity_curve": result.equity_curve,
    }

    result_path = (
        out_dir / "result.json"
    )

    result_path.write_text(
        json.dumps(
            result_dict,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    trades_path = (
        out_dir / "trades.csv"
    )

    with trades_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file_handle:

        if result.trades:
            fieldnames = list(
                result.trades[0].keys()
            )

            writer = csv.DictWriter(
                file_handle,
                fieldnames=fieldnames,
            )

            writer.writeheader()
            writer.writerows(
                result.trades
            )
        else:
            file_handle.write("no_trades\n")

    # ---------------------------------------------------------
    # Human-readable summary
    # ---------------------------------------------------------

    summary_path = (
        out_dir / "summary.txt"
    )

    summary_lines = [
        "RAYMOND v2.8 XAUUSD H1 BACKTEST",
        "================================",
        f"Status: {result.status}",
        f"Symbol: {result.symbol}",
        f"Timeframe: {result.timeframe}",
        f"Start: {result.start_time}",
        f"End: {result.end_time}",
        "",
        f"Starting balance: {result.starting_balance}",
        f"Ending balance: {result.ending_balance}",
        f"Net profit: {result.net_profit}",
        f"Net profit %: {result.net_profit_percent}",
        "",
        f"Total trades: {result.total_trades}",
        f"Winning trades: {result.winning_trades}",
        f"Losing trades: {result.losing_trades}",
        f"Breakeven trades: {result.breakeven_trades}",
        f"Win rate %: {result.win_rate_percent}",
        "",
        f"Gross profit: {result.gross_profit}",
        f"Gross loss: {result.gross_loss}",
        f"Profit factor: {result.profit_factor}",
        "",
        f"Execution cost: {result.total_execution_cost}",
        f"Maximum drawdown: {result.max_drawdown}",
        f"Maximum drawdown %: {result.max_drawdown_percent}",
        "",
        f"Average trade: {result.average_trade}",
        f"Average win: {result.average_win}",
        f"Average loss: {result.average_loss}",
        "",
        f"Bars processed: {result.bars_processed}",
        f"Warmup candles: {result.warmup_candles}",
        f"Elapsed seconds: {elapsed_seconds:.3f}",
        "",
    ]

    summary_path.write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # Console output
    # ---------------------------------------------------------

    print(
        json.dumps(
            {
                key: result_dict[key]
                for key in (
                    "status",
                    "start_time",
                    "end_time",
                    "starting_balance",
                    "ending_balance",
                    "net_profit",
                    "net_profit_percent",
                    "total_trades",
                    "winning_trades",
                    "losing_trades",
                    "breakeven_trades",
                    "win_rate_percent",
                    "gross_profit",
                    "gross_loss",
                    "profit_factor",
                    "total_execution_cost",
                    "max_drawdown",
                    "max_drawdown_percent",
                    "average_trade",
                    "average_win",
                    "average_loss",
                    "bars_processed",
                    "warmup_candles",
                    "elapsed_seconds",
                )
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the RAYMOND v2.8 XAUUSD "
            "historical H1 backtest."
        )
    )

    parser.add_argument(
        "--data",
        required=True,
        help="Path to normalized XAUUSD CSV.",
    )

    parser.add_argument(
        "--out",
        required=True,
        help="Directory for backtest output.",
    )

    parser.add_argument(
        "--starting-balance",
        type=float,
        default=10_000.0,
    )

    parser.add_argument(
        "--spread",
        type=float,
        default=0.0,
        help="Spread in XAUUSD price units.",
    )

    parser.add_argument(
        "--slippage",
        type=float,
        default=0.0,
        help="Slippage in XAUUSD price units.",
    )

    parser.add_argument(
        "--commission",
        type=float,
        default=0.0,
        help=(
            "Commission per position-size unit, "
            "charged on entry and exit."
        ),
    )

    parser.add_argument(
        "--progress-every",
        type=int,
        default=1000,
        help=(
            "Progress heartbeat interval. "
            "The current production BacktestEngine "
            "does not expose per-candle callbacks, so "
            "this is retained as a runner configuration "
            "and is also used for preflight reporting."
        ),
    )

    args = parser.parse_args()

    if args.progress_every <= 0:
        raise SystemExit(
            "--progress-every must be greater than zero."
        )

    data_path = Path(
        args.data
    ).expanduser().resolve()

    out_dir = Path(
        args.out
    ).expanduser().resolve()

    print(
        "========================================",
        flush=True,
    )

    print(
        "RAYMOND v2.8 XAUUSD H1 BACKTEST",
        flush=True,
    )

    print(
        "========================================",
        flush=True,
    )

    print(
        f"Data: {data_path}",
        flush=True,
    )

    print(
        f"Output: {out_dir}",
        flush=True,
    )

    print(
        f"Starting balance: {args.starting_balance}",
        flush=True,
    )

    print(
        f"Spread: {args.spread}",
        flush=True,
    )

    print(
        f"Slippage: {args.slippage}",
        flush=True,
    )

    print(
        f"Commission: {args.commission}",
        flush=True,
    )

    print(
        f"Progress interval: {args.progress_every}",
        flush=True,
    )

    print(
        "========================================",
        flush=True,
    )

    # ---------------------------------------------------------
    # Load and validate data
    # ---------------------------------------------------------

    load_start = time.monotonic()

    candles = load_candles(
        data_path
    )

    load_elapsed = (
        time.monotonic()
        - load_start
    )

    print(
        f"Dataset preparation completed in "
        f"{load_elapsed:.2f} seconds.",
        flush=True,
    )

    # ---------------------------------------------------------
    # Preflight
    # ---------------------------------------------------------

    if len(candles) <= 50:
        raise SystemExit(
            "Insufficient historical data. "
            "At least 51 candles are required."
        )

    print(
        f"Backtest will process {len(candles):,} candles.",
        flush=True,
    )

    print(
        "The production engine will now begin.",
        flush=True,
    )

    print(
        "========================================",
        flush=True,
    )

    # ---------------------------------------------------------
    # Backtest configuration
    # ---------------------------------------------------------

    config = BacktestConfig(
        symbol="XAUUSD",
        timeframe="H1",
        starting_balance=args.starting_balance,
        warmup_candles=50,
        max_open_positions=1,
        execute_on_next_open=True,
        close_open_position_at_end=True,
        spread=args.spread,
        slippage=args.slippage,
        commission_per_unit=args.commission,
    )

    engine = BacktestEngine(
        config=config
    )

    specification = (
        production_xauusd_spec()
    )

    # ---------------------------------------------------------
    # Execute
    # ---------------------------------------------------------

    start_time = time.monotonic()

    try:
        result = engine.run(
            candles=candles,
            specification=specification,
        )

    except KeyboardInterrupt:
        print(
            "Backtest interrupted.",
            file=sys.stderr,
            flush=True,
        )
        raise

    except Exception as exc:
        elapsed = (
            time.monotonic()
            - start_time
        )

        # Save an explicit failure artifact so GitHub Actions
        # does not leave us with no useful diagnostic information.
        out_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        failure = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": round(
                elapsed,
                3,
            ),
            "dataset": str(data_path),
            "candles": len(candles),
        }

        (
            out_dir / "failure.json"
        ).write_text(
            json.dumps(
                failure,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            json.dumps(
                failure,
                indent=2,
            ),
            file=sys.stderr,
            flush=True,
        )

        raise

    elapsed = (
        time.monotonic()
        - start_time
    )

    print(
        "========================================",
        flush=True,
    )

    print(
        "BACKTEST COMPLETED",
        flush=True,
    )

    print(
        f"Elapsed time: {elapsed:.2f} seconds",
        flush=True,
    )

    print(
        "========================================",
        flush=True,
    )

    # ---------------------------------------------------------
    # Write final artifacts
    # ---------------------------------------------------------

    write_outputs(
        result,
        out_dir,
        elapsed_seconds=elapsed,
    )

    print(
        "========================================",
        flush=True,
    )

    print(
        "RESULT FILES CREATED",
        flush=True,
    )

    print(
        out_dir / "result.json",
        flush=True,
    )

    print(
        out_dir / "trades.csv",
        flush=True,
    )

    print(
        out_dir / "summary.txt",
        flush=True,
    )

    print(
        "========================================",
        flush=True,
    )


if __name__ == "__main__":
    main()
