"""
RAYMOND v2.8 - V5 Multi-Objective Strategy Optimizer

Research only.
No MT5, Exness, broker orders, or live trading.

IMPORTANT:
- Uses the canonical v5_execution_engine for backtest/P&L evaluation.
- Does NOT contain a second independent trade simulator.
- XAUUSD accounting therefore remains centralized in the execution engine.
- Optimizes candidate parameters without changing the underlying strategy logic.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Import canonical execution engine
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from v5_execution_engine import run_backtest


# ---------------------------------------------------------------------------
# Research constants
# ---------------------------------------------------------------------------

STRATEGY_FAMILIES = [
    "TREND_CONTINUATION",
    "PULLBACK_RETEST",
    "BREAKOUT",
    "LIQUIDITY_REVERSAL",
    "RANGE_MEAN_REVERSION",
    "MOMENTUM_EXPANSION",
]

REGIMES = [
    "BULL_TREND",
    "BEAR_TREND",
    "RANGE",
    "VOLATILITY_COMPRESSION",
    "VOLATILITY_EXPANSION",
    "TRANSITION",
]


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    strategy_family: str
    regime: str
    minimum_score: float
    risk_reward: float
    atr_stop_multiplier: float
    risk_per_trade: float
    max_trades_per_week: int
    break_even_r: float
    trailing_start_r: float
    trailing_distance_r: float


# ---------------------------------------------------------------------------
# Parameter grid
# ---------------------------------------------------------------------------

def build_grid() -> Iterable[Candidate]:
    """
    Full V5 research grid.

    6 families
    x 6 regimes
    x 5 signal thresholds
    x 6 RR values
    x 5 ATR stop values
    x 4 risk values
    x 3 weekly trade limits
    x 2 BE values
    x 3 trailing-start values
    x 3 trailing-distance values

    = 622,080 candidates.
    """

    parameter_grid = itertools.product(
        STRATEGY_FAMILIES,
        REGIMES,
        [55, 60, 65, 70, 75],
        [1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
        [0.8, 1.0, 1.2, 1.4, 1.6],
        [0.01, 0.015, 0.02, 0.025],
        [3, 5, 8],
        [0.8, 1.0],
        [1.5, 2.0, 2.5],
        [0.75, 1.0, 1.25],
    )

    for values in parameter_grid:
        yield Candidate(
            strategy_family=values[0],
            regime=values[1],
            minimum_score=float(values[2]),
            risk_reward=float(values[3]),
            atr_stop_multiplier=float(values[4]),
            risk_per_trade=float(values[5]),
            max_trades_per_week=int(values[6]),
            break_even_r=float(values[7]),
            trailing_start_r=float(values[8]),
            trailing_distance_r=float(values[9]),
        )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def find_ohlcv_columns(df: pd.DataFrame) -> Dict[str, str]:
    aliases = {
        "timestamp": [
            "timestamp",
            "time",
            "datetime",
            "date",
            "Date",
        ],
        "open": ["open", "Open"],
        "high": ["high", "High"],
        "low": ["low", "Low"],
        "close": ["close", "Close"],
        "volume": ["volume", "Volume", "tick_volume", "Tick Volume"],
    }

    result: Dict[str, str] = {}

    normalized = {str(c).strip().lower(): c for c in df.columns}

    for key, names in aliases.items():
        for name in names:
            lookup = str(name).strip().lower()
            if lookup in normalized:
                result[key] = normalized[lookup]
                break

    required = ["timestamp", "open", "high", "low", "close"]
    missing = [x for x in required if x not in result]

    if missing:
        raise ValueError(
            f"Missing required OHLCV columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    return result


def load_market_data(path: str) -> pd.DataFrame:
    source = Path(path)

    if not source.exists():
        raise FileNotFoundError(f"Market data file not found: {source}")

    df = pd.read_csv(source)

    columns = find_ohlcv_columns(df)

    rename_map = {
        columns["timestamp"]: "timestamp",
        columns["open"]: "open",
        columns["high"]: "high",
        columns["low"]: "low",
        columns["close"]: "close",
    }

    if "volume" in columns:
        rename_map[columns["volume"]] = "volume"

    df = df.rename(columns=rename_map)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    for column in ["open", "high", "low", "close"]:
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
    df = df.drop_duplicates(subset=["timestamp"])
    df = df.reset_index(drop=True)

    if df.empty:
        raise ValueError("Market data is empty after normalization.")

    if (df["high"] < df["low"]).any():
        raise ValueError("Invalid OHLC data: high < low detected.")

    if (df["open"] <= 0).any() or (df["high"] <= 0).any():
        raise ValueError("Invalid market data: non-positive prices detected.")

    return df


# ---------------------------------------------------------------------------
# Period slicing
# ---------------------------------------------------------------------------

def slice_period(
    df: pd.DataFrame,
    start: Optional[str],
    end: Optional[str],
) -> pd.DataFrame:
    result = df.copy()

    if start:
        start_ts = pd.Timestamp(start, tz="UTC")
        result = result[result["timestamp"] >= start_ts]

    if end:
        end_ts = pd.Timestamp(end, tz="UTC")

        # Treat date-only end values as inclusive through the day.
        if len(str(end)) <= 10:
            end_ts = end_ts + pd.Timedelta(days=1)

        result = result[result["timestamp"] < end_ts]

    result = result.reset_index(drop=True)

    if result.empty:
        raise ValueError(
            f"No market data available for period "
            f"{start or '-inf'} -> {end or '+inf'}"
        )

    return result


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

def _number(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except (TypeError, ValueError):
        pass

    return default


def extract_metric(
    result: Any,
    names: List[str],
    default: float = 0.0,
) -> float:
    """
    Extract a metric from either a dict or an object.

    This keeps the optimizer tolerant of the canonical engine's result
    representation without implementing another simulation.
    """

    if isinstance(result, dict):
        containers = [
            result,
            result.get("metrics", {}),
            result.get("summary", {}),
            result.get("performance", {}),
        ]
    else:
        containers = [
            getattr(result, "__dict__", {}),
        ]

        metrics = getattr(result, "metrics", None)
        if isinstance(metrics, dict):
            containers.append(metrics)

    for container in containers:
        if not isinstance(container, dict):
            continue

        for name in names:
            if name in container:
                return _number(container[name], default)

    return default


def extract_trades(result: Any) -> int:
    if isinstance(result, dict):
        for key in [
            "trades",
            "trade_count",
            "number_of_trades",
            "total_trades",
        ]:
            if key in result:
                value = result[key]
                if isinstance(value, list):
                    return len(value)
                return int(_number(value))

        for key in ["metrics", "summary"]:
            nested = result.get(key)
            if isinstance(nested, dict):
                for name in [
                    "trades",
                    "trade_count",
                    "number_of_trades",
                    "total_trades",
                ]:
                    if name in nested:
                        return int(_number(nested[name]))

    for attr in [
        "trades",
        "trade_count",
        "number_of_trades",
        "total_trades",
    ]:
        value = getattr(result, attr, None)

        if isinstance(value, list):
            return len(value)

        if value is not None:
            return int(_number(value))

    return 0


def extract_return(result: Any) -> float:
    return extract_metric(
        result,
        [
            "return_pct",
            "total_return_pct",
            "net_return_pct",
            "profit_pct",
            "return_percent",
        ],
        0.0,
    )


def extract_net_profit(result: Any) -> float:
    return extract_metric(
        result,
        [
            "net_profit",
            "net_pnl",
            "profit",
            "total_profit",
            "pnl",
        ],
        0.0,
    )


def extract_profit_factor(result: Any) -> float:
    return extract_metric(
        result,
        [
            "profit_factor",
            "pf",
        ],
        0.0,
    )


def extract_drawdown(result: Any) -> float:
    return extract_metric(
        result,
        [
            "max_drawdown_pct",
            "maximum_drawdown_pct",
            "drawdown_pct",
            "max_dd_pct",
        ],
        0.0,
    )


def extract_win_rate(result: Any) -> float:
    return extract_metric(
        result,
        [
            "win_rate",
            "win_rate_pct",
        ],
        0.0,
    )


def extract_expectancy(result: Any) -> float:
    return extract_metric(
        result,
        [
            "expectancy",
            "expectancy_r",
            "avg_trade",
            "average_trade",
        ],
        0.0,
    )


# ---------------------------------------------------------------------------
# Consistency
# ---------------------------------------------------------------------------

def calculate_consistency(result: Any) -> float:
    """
    Returns a 0-1 consistency score.

    If the execution engine exposes weekly returns, use them.
    Otherwise return a neutral value rather than fabricating data.
    """

    weekly_returns = None

    if isinstance(result, dict):
        for key in [
            "weekly_returns",
            "week_returns",
            "weekly_return_series",
        ]:
            value = result.get(key)
            if isinstance(value, (list, tuple, np.ndarray)):
                weekly_returns = value
                break

        if weekly_returns is None:
            for key in ["metrics", "summary"]:
                nested = result.get(key)
                if isinstance(nested, dict):
                    for name in [
                        "weekly_returns",
                        "week_returns",
                        "weekly_return_series",
                    ]:
                        value = nested.get(name)
                        if isinstance(value, (list, tuple, np.ndarray)):
                            weekly_returns = value
                            break

    if weekly_returns is None:
        return 0.5

    values = pd.to_numeric(
        pd.Series(weekly_returns),
        errors="coerce",
    ).dropna()

    if len(values) == 0:
        return 0.5

    positive_rate = float((values > 0).mean())

    return max(
        0.0,
        min(
            1.0,
            positive_rate,
        ),
    )


# ---------------------------------------------------------------------------
# Canonical execution call
# ---------------------------------------------------------------------------

def evaluate_candidate(
    candidate: Candidate,
    data: pd.DataFrame,
    starting_balance: float = 1000.0,
    spread: float = 0.30,
    slippage: float = 0.05,
    weekly_loss_limit: float = -0.09,
) -> Dict[str, Any]:
    """
    Evaluate one candidate through the canonical execution engine.

    IMPORTANT:
    There is intentionally NO local trade simulator here.
    """

    result = run_backtest(
        df=data,
        strategy_family=candidate.strategy_family,
        regime=candidate.regime,
        minimum_score=candidate.minimum_score,
        risk_reward=candidate.risk_reward,
        atr_stop_multiplier=candidate.atr_stop_multiplier,
        risk_per_trade=candidate.risk_per_trade,
        max_trades_per_week=candidate.max_trades_per_week,
        break_even_r=candidate.break_even_r,
        break_even_lock_r=0.0,
        trailing_start_r=candidate.trailing_start_r,
        trailing_distance_r=candidate.trailing_distance_r,
        weekly_loss_limit=weekly_loss_limit,
        starting_balance=starting_balance,
        spread=spread,
        slippage=slippage,
    )

    trades = extract_trades(result)
    net_profit = extract_net_profit(result)
    return_pct = extract_return(result)
    profit_factor = extract_profit_factor(result)
    drawdown = extract_drawdown(result)
    win_rate = extract_win_rate(result)
    expectancy = extract_expectancy(result)
    consistency = calculate_consistency(result)

    # Guard against invalid PF values.
    if not math.isfinite(profit_factor):
        profit_factor = 0.0

    # Positive PF is useful, but PF below 1 must remain penalized.
    pf_score = max(0.0, min(3.0, profit_factor))

    # Log-growth proxy. This does not replace the actual engine return.
    ending_balance = starting_balance + net_profit

    if starting_balance > 0 and ending_balance > 0:
        log_growth = math.log(ending_balance / starting_balance)
    else:
        log_growth = -10.0

    # Reward positive growth, profitability and consistency.
    growth_score = max(-2.0, min(2.0, log_growth))

    expectancy_score = max(
        -1.0,
        min(
            1.0,
            expectancy,
        ),
    )

    sample_score = min(
        1.0,
        math.sqrt(max(0, trades) / 100.0),
    )

    # Drawdown is a percentage in the canonical metrics.
    drawdown_penalty = max(
        0.0,
        min(
            1.0,
            abs(drawdown) / 50.0,
        ),
    )

    # Multi-objective research score.
    score = (
        0.45 * growth_score
        + 0.20 * ((pf_score - 1.0) / 2.0)
        + 0.10 * expectancy_score
        + 0.10 * consistency
        + 0.10 * sample_score
        - 0.20 * drawdown_penalty
    )

    metrics = {
        **asdict(candidate),
        "trades": trades,
        "net_profit": net_profit,
        "return_pct": return_pct,
        "profit_factor": profit_factor,
        "max_drawdown_pct": drawdown,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "consistency": consistency,
        "score": score,
    }

    return metrics


# ---------------------------------------------------------------------------
# Ranking / Pareto frontier
# ---------------------------------------------------------------------------

def pareto_frontier(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    objectives = [
        "return_pct",
        "profit_factor",
        "expectancy",
    ]

    for column in objectives + ["max_drawdown_pct"]:
        if column not in frame.columns:
            return frame.copy()

    rows = frame.reset_index(drop=True)
    keep = np.ones(len(rows), dtype=bool)

    for i in range(len(rows)):
        if not keep[i]:
            continue

        a = rows.iloc[i]

        for j in range(len(rows)):
            if i == j:
                continue

            b = rows.iloc[j]

            a_no_worse = (
                b["return_pct"] >= a["return_pct"]
                and b["profit_factor"] >= a["profit_factor"]
                and b["expectancy"] >= a["expectancy"]
                and b["max_drawdown_pct"] <= a["max_drawdown_pct"]
            )

            b_strictly_better = (
                b["return_pct"] > a["return_pct"]
                or b["profit_factor"] > a["profit_factor"]
                or b["expectancy"] > a["expectancy"]
                or b["max_drawdown_pct"] < a["max_drawdown_pct"]
            )

            if a_no_worse and b_strictly_better:
                keep[i] = False
                break

    return rows.loc[keep].copy()


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------

def select_best(
    frame: pd.DataFrame,
) -> pd.Series:
    if frame.empty:
        raise ValueError("No valid candidates were produced.")

    ranked = frame.sort_values(
        by=[
            "score",
            "profit_factor",
            "return_pct",
            "expectancy",
        ],
        ascending=[
            False,
            False,
            False,
            False,
        ],
    )

    return ranked.iloc[0]


# ---------------------------------------------------------------------------
# Main optimizer
# ---------------------------------------------------------------------------

def run_optimizer(
    data: pd.DataFrame,
    output_dir: Path,
    max_candidates: Optional[int],
    starting_balance: float,
    spread: float,
    slippage: float,
    weekly_loss_limit: float,
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates = build_grid()

    records: List[Dict[str, Any]] = []

    processed = 0

    for candidate in candidates:
        if (
            max_candidates is not None
            and processed >= max_candidates
        ):
            break

        try:
            metrics = evaluate_candidate(
                candidate=candidate,
                data=data,
                starting_balance=starting_balance,
                spread=spread,
                slippage=slippage,
                weekly_loss_limit=weekly_loss_limit,
            )

            metrics["status"] = "OK"

        except Exception as exc:
            metrics = {
                **asdict(candidate),
                "trades": 0,
                "net_profit": 0.0,
                "return_pct": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "win_rate": 0.0,
                "expectancy": 0.0,
                "consistency": 0.0,
                "score": -999.0,
                "status": "ERROR",
                "error": str(exc),
            }

        records.append(metrics)
        processed += 1

        if processed % 25 == 0:
            print(
                f"Evaluated {processed} candidates",
                flush=True,
            )

    if not records:
        raise RuntimeError("No candidates were evaluated.")

    results = pd.DataFrame(records)

    results.to_csv(
        output_dir / "v5_optimizer_candidates.csv",
        index=False,
    )

    valid = results[
        results["status"] == "OK"
    ].copy()

    if valid.empty:
        raise RuntimeError(
            "All optimizer candidates failed. "
            "Check v5_execution_engine.py integration."
        )

    valid = valid.sort_values(
        by="score",
        ascending=False,
    ).reset_index(drop=True)

    valid["rank"] = np.arange(
        1,
        len(valid) + 1,
    )

    valid.to_csv(
        output_dir / "v5_optimizer_ranked.csv",
        index=False,
    )

    frontier = pareto_frontier(valid)

    frontier.to_csv(
        output_dir / "v5_optimizer_pareto_frontier.csv",
        index=False,
    )

    best = select_best(valid)

    selected_config = {
        "strategy_family": best["strategy_family"],
        "regime": best["regime"],
        "minimum_score": float(best["minimum_score"]),
        "risk_reward": float(best["risk_reward"]),
        "atr_stop_multiplier": float(best["atr_stop_multiplier"]),
        "risk_per_trade": float(best["risk_per_trade"]),
        "max_trades_per_week": int(best["max_trades_per_week"]),
        "break_even_r": float(best["break_even_r"]),
        "trailing_start_r": float(best["trailing_start_r"]),
        "trailing_distance_r": float(best["trailing_distance_r"]),
    }

    with open(
        output_dir / "v5_selected_config.json",
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            selected_config,
            handle,
            indent=2,
        )

    report = {
        "status": "completed",
        "engine": "canonical_v5_execution_engine",
        "data_start": str(data["timestamp"].min()),
        "data_end": str(data["timestamp"].max()),
        "rows": int(len(data)),
        "candidates_requested": (
            622080
            if max_candidates is None
            else max_candidates
        ),
        "candidates_evaluated": int(processed),
        "valid_candidates": int(len(valid)),
        "pareto_candidates": int(len(frontier)),
        "starting_balance": float(starting_balance),
        "spread": float(spread),
        "slippage": float(slippage),
        "weekly_loss_limit": float(weekly_loss_limit),
        "selected_candidate": selected_config,
        "selected_metrics": {
            key: (
                float(best[key])
                if isinstance(
                    best[key],
                    (float, np.floating),
                )
                else (
                    int(best[key])
                    if isinstance(
                        best[key],
                        (int, np.integer),
                    )
                    else best[key]
                )
            )
            for key in [
                "trades",
                "net_profit",
                "return_pct",
                "profit_factor",
                "max_drawdown_pct",
                "win_rate",
                "expectancy",
                "consistency",
                "score",
            ]
        },
    }

    with open(
        output_dir / "v5_optimizer_report.json",
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            report,
            handle,
            indent=2,
            default=str,
        )

    summary = f"""
RAYMOND v2.8 V5 OPTIMIZER
==========================

Status: completed

Execution engine:
canonical v5_execution_engine.py

Data:
Start: {data["timestamp"].min()}
End:   {data["timestamp"].max()}
Rows:  {len(data)}

Candidates evaluated:
{processed}

Valid candidates:
{len(valid)}

Pareto candidates:
{len(frontier)}

SELECTED CANDIDATE
------------------
Strategy family:       {best["strategy_family"]}
Regime:                {best["regime"]}
Minimum score:         {best["minimum_score"]}
Risk/reward:           {best["risk_reward"]}
ATR stop multiplier:   {best["atr_stop_multiplier"]}
Risk per trade:        {best["risk_per_trade"]}
Max trades/week:       {best["max_trades_per_week"]}
Break-even R:          {best["break_even_r"]}
Trailing start R:      {best["trailing_start_r"]}
Trailing distance R:   {best["trailing_distance_r"]}

RESULT
------
Trades:                {best["trades"]}
Net profit:            {best["net_profit"]:.4f}
Return %:              {best["return_pct"]:.4f}
Profit factor:         {best["profit_factor"]:.4f}
Maximum drawdown %:    {best["max_drawdown_pct"]:.4f}
Win rate:              {best["win_rate"]:.4f}
Expectancy:            {best["expectancy"]:.6f}
Consistency:           {best["consistency"]:.4f}
Research score:        {best["score"]:.6f}

IMPORTANT
---------
This optimizer does not contain an independent P&L simulator.

Every candidate is evaluated through:
scripts/v5_execution_engine.py

Therefore optimizer P&L and canonical execution-engine P&L
use the same execution/accounting implementation.
""".strip()

    with open(
        output_dir / "summary.txt",
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(summary + "\n")

    print(summary)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Raymond V2.8 V5 canonical-engine optimizer"
    )

    parser.add_argument(
        "--data",
        required=True,
        help="Normalized XAUUSD H1 CSV",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Optimizer output directory",
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=None,
        help=(
            "Maximum number of candidates to evaluate. "
            "Use a small number for integration tests. "
            "Omit for the full 622,080-candidate grid."
        ),
    )

    parser.add_argument(
        "--starting-balance",
        type=float,
        default=1000.0,
    )

    parser.add_argument(
        "--spread",
        type=float,
        default=0.30,
    )

    parser.add_argument(
        "--slippage",
        type=float,
        default=0.05,
    )

    parser.add_argument(
        "--weekly-loss-limit",
        type=float,
        default=-0.09,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Loading XAUUSD market data...", flush=True)

    data = load_market_data(args.data)

    print(
        f"Loaded {len(data)} rows "
        f"from {data['timestamp'].min()} "
        f"to {data['timestamp'].max()}",
        flush=True,
    )

    run_optimizer(
        data=data,
        output_dir=Path(args.output),
        max_candidates=args.max_candidates,
        starting_balance=args.starting_balance,
        spread=args.spread,
        slippage=args.slippage,
        weekly_loss_limit=args.weekly_loss_limit,
    )


if __name__ == "__main__":
    main()
