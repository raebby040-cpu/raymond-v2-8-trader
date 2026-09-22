#!/usr/bin/env python3
"""
RAYMOND v2.8 - Full XAUUSD H1 historical backtest runner.

Run from the repository root:
    PYTHONPATH=backend python scripts/run_xauusd_backtest.py \
      --data /path/to/xauusd_h1_2003_2025_normalized.csv \
      --out results/xauusd_h1_2003_2025_baseline

For a realistic-cost pass:
    PYTHONPATH=backend python scripts/run_xauusd_backtest.py \
      --data /path/to/xauusd_h1_2003_2025_normalized.csv \
      --out results/xauusd_h1_2003_2025_costs \
      --spread 0.38 \
      --slippage 0.05 \
      --commission 0.0
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import pandas as pd

from app.backtest_engine import BacktestConfig, BacktestEngine
from app.risk_engine import RiskEngine, SymbolSpecification


def production_xauusd_spec() -> SymbolSpecification:
    # Exact production XAUUSD specification used by online_main.py.
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


def load_candles(path: Path) -> list[dict]:
    df = pd.read_csv(path)

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns: {sorted(missing)}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    if df["timestamp"].duplicated().any():
        raise SystemExit("Duplicate timestamps detected.")

    if (
        (df[["open", "high", "low", "close"]] <= 0).any().any()
        or
        (df["high"] < df[["open", "close"]].max(axis=1)).any()
        or
        (df["low"] > df[["open", "close"]].min(axis=1)).any()
    ):
        raise SystemExit("Invalid OHLC data detected.")

    candles = []
    for row in df.itertuples(index=False):
        candles.append({
            "time": row.timestamp.isoformat(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume),
        })
    return candles


def write_outputs(result, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

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
        "trades": result.trades,
        "equity_curve": result.equity_curve,
    }

    (out_dir / "result.json").write_text(
        json.dumps(result_dict, indent=2),
        encoding="utf-8",
    )

    with (out_dir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        if result.trades:
            writer = csv.DictWriter(f, fieldnames=result.trades[0].keys())
            writer.writeheader()
            writer.writerows(result.trades)

    print(json.dumps({
        k: result_dict[k]
        for k in (
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
        )
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--starting-balance", type=float, default=10_000.0)
    parser.add_argument("--spread", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--commission", type=float, default=0.0)
    args = parser.parse_args()

    data_path = Path(args.data)
    out_dir = Path(args.out)

    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")

    candles = load_candles(data_path)

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

    engine = BacktestEngine(config=config)
    result = engine.run(
        candles=candles,
        specification=production_xauusd_spec(),
    )

    write_outputs(result, out_dir)


if __name__ == "__main__":
    main()
