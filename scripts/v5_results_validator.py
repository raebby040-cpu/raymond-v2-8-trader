"""
RAYMOND V2.8
V5 RESULTS VALIDATOR

Purpose
-------
Independent post-run validation of the V5 research package.

This validator does NOT optimize the strategy.

It checks whether the reported research results are:

1. Internally consistent
2. Accountable
3. Mathematically plausible
4. Free of obvious data-quality problems
5. Reasonably stable across walk-forward windows
6. Consistent with the stated XAUUSD contract model
7. Suitable for another round of research

IMPORTANT
---------
Research/backtest only.

This file:
- does NOT connect to MT5
- does NOT connect to Exness
- does NOT send broker orders
- does NOT modify live positions
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================================
# CONSTANTS
# ============================================================================

XAUUSD_CONTRACT_SIZE = 100.0
XAUUSD_PRICE_DECIMALS = 2

MAX_REASONABLE_LOT = 100.0
MIN_REASONABLE_LOT = 0.01

EPSILON = 1e-9


# ============================================================================
# GENERIC HELPERS
# ============================================================================

def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float safely."""

    try:
        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Convert a value to int safely."""

    try:
        return int(value)

    except (TypeError, ValueError):
        return default


def percent_change(
    start: float,
    end: float,
) -> float:
    """Calculate percentage change."""

    if abs(start) <= EPSILON:
        return 0.0

    return ((end - start) / start) * 100.0


def compound_returns(values: list[float]) -> float:
    """
    Compound percentage returns.

    Example:
        [10, -5]
        => (1.10 * 0.95 - 1) * 100
    """

    equity = 1.0

    for value in values:

        if not math.isfinite(value):
            continue

        equity *= 1.0 + value / 100.0

        if equity <= 0:
            return -100.0

    return (equity - 1.0) * 100.0


def load_json(path: Path) -> dict[str, Any] | None:
    """Load JSON if available."""

    if not path.exists():
        return None

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(handle)

    except Exception:
        return None


def find_first(
    root: Path,
    patterns: list[str],
) -> Path | None:
    """Find the first matching file."""

    for pattern in patterns:

        matches = list(root.rglob(pattern))

        if matches:
            return matches[0]

    return None


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    """Write formatted JSON."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            payload,
            handle,
            indent=2,
            default=str,
        )


# ============================================================================
# VALIDATION RESULT
# ============================================================================

class ValidationReport:

    def __init__(self) -> None:

        self.checks: list[dict[str, Any]] = []

        self.errors: list[str] = []

        self.warnings: list[str] = []

        self.information: list[str] = []

    def check(
        self,
        name: str,
        passed: bool,
        message: str,
        severity: str = "ERROR",
    ) -> None:

        record = {
            "name": name,
            "passed": bool(passed),
            "severity": severity,
            "message": message,
        }

        self.checks.append(record)

        if passed:

            self.information.append(
                f"PASS: {name} — {message}"
            )

        elif severity == "WARNING":

            self.warnings.append(
                f"WARNING: {name} — {message}"
            )

        else:

            self.errors.append(
                f"ERROR: {name} — {message}"
            )


# ============================================================================
# WALK-FORWARD VALIDATION
# ============================================================================

def validate_walk_forward(
    root: Path,
    report: ValidationReport,
) -> dict[str, Any]:
    """Validate walk-forward windows."""

    path = find_first(
        root,
        [
            "v5_walk_forward_windows.csv",
            "*walk_forward_windows.csv",
        ],
    )

    if path is None:

        report.check(
            "walk_forward_file",
            False,
            "Walk-forward windows file was not found.",
        )

        return {}

    try:

        df = pd.read_csv(path)

    except Exception as exc:

        report.check(
            "walk_forward_read",
            False,
            f"Could not read {path}: {exc}",
        )

        return {}

    required = [
        "window",
        "test_return_pct",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    report.check(
        "walk_forward_columns",
        not missing,
        (
            "Required columns are present."
            if not missing
            else f"Missing columns: {missing}"
        ),
    )

    if missing:
        return {}

    report.check(
        "walk_forward_rows",
        len(df) > 0,
        f"Found {len(df)} walk-forward rows.",
    )

    if len(df) == 0:
        return {}

    test_returns = pd.to_numeric(
        df["test_return_pct"],
        errors="coerce",
    ).dropna()

    positive_rate = (
        float((test_returns > 0).mean()) * 100.0
        if len(test_returns)
        else 0.0
    )

    median_return = (
        float(test_returns.median())
        if len(test_returns)
        else 0.0
    )

    worst_return = (
        float(test_returns.min())
        if len(test_returns)
        else 0.0
    )

    compound_return = compound_returns(
        test_returns.tolist()
    )

    pf = None

    if "test_profit_factor" in df.columns:

        pf_values = pd.to_numeric(
            df["test_profit_factor"],
            errors="coerce",
        ).dropna()

        if len(pf_values):
            pf = float(pf_values.mean())

    report.check(
        "positive_test_windows",
        positive_rate >= 50.0,
        (
            f"{positive_rate:.2f}% of test windows are profitable."
        ),
        severity="WARNING",
    )

    report.check(
        "median_test_return",
        median_return > 0.0,
        (
            f"Median unseen-test return is "
            f"{median_return:.4f}%."
        ),
        severity="WARNING",
    )

    report.check(
        "worst_test_return",
        worst_return > -100.0,
        (
            f"Worst unseen-test return is "
            f"{worst_return:.4f}%."
        ),
    )

    return {
        "file": str(path),
        "windows": int(len(df)),
        "positive_test_window_rate_pct": positive_rate,
        "median_test_return_pct": median_return,
        "worst_test_return_pct": worst_return,
        "compound_test_return_pct": compound_return,
        "average_test_profit_factor": pf,
    }


# ============================================================================
# ROBUSTNESS REPORT VALIDATION
# ============================================================================

def validate_robustness(
    root: Path,
    report: ValidationReport,
) -> dict[str, Any]:
    """Validate the robustness analyzer output."""

    path = find_first(
        root,
        [
            "v5_robustness_report.json",
            "*robustness_report.json",
        ],
    )

    if path is None:

        report.check(
            "robustness_report",
            False,
            "Robustness report was not found.",
        )

        return {}

    payload = load_json(path)

    if payload is None:

        report.check(
            "robustness_json",
            False,
            f"Could not parse {path}.",
        )

        return {}

    report.check(
        "robustness_json",
        True,
        "Robustness JSON is readable.",
    )

    verdict = str(
        payload.get(
            "verdict",
            payload.get(
                "classification",
                "UNKNOWN",
            ),
        )
    ).upper()

    report.check(
        "robustness_verdict",
        verdict not in {
            "",
            "UNKNOWN",
            "NONE",
        },
        f"Robustness verdict: {verdict}",
        severity="WARNING",
    )

    return {
        "file": str(path),
        "verdict": verdict,
    }


# ============================================================================
# TRADE JOURNAL VALIDATION
# ============================================================================

def locate_trade_file(
    root: Path,
) -> Path | None:
    """Locate the most likely trade journal."""

    patterns = [
        "trades.csv",
        "trade_journal.csv",
        "v5_trades.csv",
        "unseen_test_trades.csv",
        "*trades.csv",
    ]

    return find_first(
        root,
        patterns,
    )


def validate_trade_journal(
    root: Path,
    report: ValidationReport,
) -> dict[str, Any]:
    """Validate trade-level data where available."""

    path = locate_trade_file(root)

    if path is None:

        report.check(
            "trade_journal",
            False,
            "No trade journal CSV was found.",
            severity="WARNING",
        )

        return {}

    try:

        df = pd.read_csv(path)

    except Exception as exc:

        report.check(
            "trade_journal_read",
            False,
            f"Could not read {path}: {exc}",
        )

        return {}

    report.check(
        "trade_journal_rows",
        len(df) > 0,
        f"Trade journal contains {len(df):,} rows.",
        severity="WARNING",
    )

    if len(df) == 0:
        return {}

    # ------------------------------------------------------------
    # P&L column discovery
    # ------------------------------------------------------------

    pnl_column = None

    for candidate in [
        "net_pnl",
        "net_profit",
        "pnl",
        "profit",
        "profit_loss",
        "realized_pnl",
    ]:

        if candidate in df.columns:
            pnl_column = candidate
            break

    if pnl_column is not None:

        pnl = pd.to_numeric(
            df[pnl_column],
            errors="coerce",
        )

        invalid = int(
            pnl.isna().sum()
        )

        report.check(
            "trade_pnl_values",
            invalid == 0,
            (
                f"All {len(pnl):,} trade P&L values "
                "are numeric."
                if invalid == 0
                else f"{invalid} invalid P&L values found."
            ),
        )

    else:

        pnl = None

        report.check(
            "trade_pnl_column",
            False,
            "No recognized trade P&L column was found.",
            severity="WARNING",
        )

    # ------------------------------------------------------------
    # Duplicate trade IDs
    # ------------------------------------------------------------

    id_column = None

    for candidate in [
        "trade_id",
        "id",
        "position_id",
    ]:

        if candidate in df.columns:
            id_column = candidate
            break

    duplicate_ids = 0

    if id_column is not None:

        duplicate_ids = int(
            df[id_column].duplicated().sum()
        )

        report.check(
            "duplicate_trade_ids",
            duplicate_ids == 0,
            (
                "No duplicate trade IDs found."
                if duplicate_ids == 0
                else f"{duplicate_ids} duplicate trade IDs found."
            ),
        )

    # ------------------------------------------------------------
    # Lot validation
    # ------------------------------------------------------------

    lot_column = None

    for candidate in [
        "lots",
        "lot_size",
        "volume",
        "position_size",
    ]:

        if candidate in df.columns:

            lot_column = candidate
            break

    invalid_lots = 0

    if lot_column is not None:

        lots = pd.to_numeric(
            df[lot_column],
            errors="coerce",
        )

        invalid_lots = int(
            (
                lots.notna()
                & (
                    (lots < MIN_REASONABLE_LOT)
                    | (lots > MAX_REASONABLE_LOT)
                )
            ).sum()
        )

        report.check(
            "lot_sizes",
            invalid_lots == 0,
            (
                "Lot sizes are within the research limits."
                if invalid_lots == 0
                else (
                    f"{invalid_lots} trades have "
                    "implausible lot sizes."
                )
            ),
        )

    # ------------------------------------------------------------
    # Price columns
    # ------------------------------------------------------------

    entry_column = None
    exit_column = None

    for candidate in [
        "entry_price",
        "entry",
        "open_price",
    ]:

        if candidate in df.columns:
            entry_column = candidate
            break

    for candidate in [
        "exit_price",
        "exit",
        "close_price",
    ]:

        if candidate in df.columns:
            exit_column = candidate
            break

    if entry_column and exit_column and pnl_column and lot_column:

        entry = pd.to_numeric(
            df[entry_column],
            errors="coerce",
        )

        exit_price = pd.to_numeric(
            df[exit_column],
            errors="coerce",
        )

        lots = pd.to_numeric(
            df[lot_column],
            errors="coerce",
        )

        reported_pnl = pd.to_numeric(
            df[pnl_column],
            errors="coerce",
        )

        side_column = None

        for candidate in [
            "side",
            "direction",
            "trade_side",
        ]:

            if candidate in df.columns:
                side_column = candidate
                break

        if side_column:

            side = (
                df[side_column]
                .astype(str)
                .str.upper()
            )

            direction = side.map(
                lambda value: (
                    -1.0
                    if value in {
                        "SELL",
                        "SHORT",
                    }
                    else 1.0
                )
            )

        else:

            direction = pd.Series(
                1.0,
                index=df.index,
            )

            report.check(
                "trade_direction",
                False,
                "No trade direction column found; "
                "P&L reconstruction cannot be fully verified.",
                severity="WARNING",
            )

        expected_pnl = (
            (exit_price - entry)
            * XAUUSD_CONTRACT_SIZE
            * lots
            * direction
        )

        valid = (
            entry.notna()
            & exit_price.notna()
            & lots.notna()
            & reported_pnl.notna()
            & expected_pnl.notna()
        )

        if valid.any():

            differences = (
                reported_pnl[valid]
                - expected_pnl[valid]
            ).abs()

            tolerance = (
                0.02
                + expected_pnl[valid].abs() * 0.005
            )

            mismatches = int(
                (differences > tolerance).sum()
            )

            report.check(
                "xauusd_pnl_reconstruction",
                mismatches == 0,
                (
                    "Reported P&L is consistent with "
                    "1 lot = 100 oz within tolerance."
                    if mismatches == 0
                    else (
                        f"{mismatches} trades differ from "
                        "the XAUUSD contract reconstruction."
                    )
                ),
            )

    # ------------------------------------------------------------
    # Basic P&L statistics
    # ------------------------------------------------------------

    if pnl is not None:

        pnl_clean = pnl.dropna()

        wins = int(
            (pnl_clean > EPSILON).sum()
        )

        losses = int(
            (pnl_clean < -EPSILON).sum()
        )

        breakeven = int(
            (
                pnl_clean.abs()
                <= EPSILON
            ).sum()
        )

        gross_profit = float(
            pnl_clean[pnl_clean > 0].sum()
        )

        gross_loss = float(
            pnl_clean[pnl_clean < 0].sum()
        )

        profit_factor = (
            gross_profit / abs(gross_loss)
            if abs(gross_loss) > EPSILON
            else float("inf")
        )

        report.check(
            "trade_accounting_counts",
            wins + losses + breakeven == len(pnl_clean),
            (
                f"Wins={wins}, losses={losses}, "
                f"breakeven={breakeven}."
            ),
        )

        return {
            "file": str(path),
            "trades": int(len(pnl_clean)),
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "net_pnl": float(pnl_clean.sum()),
        }

    return {
        "file": str(path),
        "trades": int(len(df)),
    }


# ============================================================================
# EQUITY VALIDATION
# ============================================================================

def validate_equity(
    root: Path,
    report: ValidationReport,
) -> dict[str, Any]:
    """Validate an equity curve when available."""

    path = find_first(
        root,
        [
            "equity_curve.csv",
            "equity.csv",
            "v5_equity_curve.csv",
            "*equity_curve.csv",
        ],
    )

    if path is None:

        report.check(
            "equity_curve",
            False,
            "No equity curve was found.",
            severity="WARNING",
        )

        return {}

    try:

        df = pd.read_csv(path)

    except Exception as exc:

        report.check(
            "equity_curve_read",
            False,
            f"Could not read {path}: {exc}",
        )

        return {}

    equity_column = None

    for candidate in [
        "equity",
        "balance",
        "account_equity",
        "ending_balance",
    ]:

        if candidate in df.columns:

            equity_column = candidate
            break

    if equity_column is None:

        report.check(
            "equity_column",
            False,
            "No recognized equity column found.",
            severity="WARNING",
        )

        return {}

    equity = pd.to_numeric(
        df[equity_column],
        errors="coerce",
    ).dropna()

    report.check(
        "equity_values",
        len(equity) > 0 and equity.notna().all(),
        f"Validated {len(equity):,} equity observations.",
    )

    if len(equity) == 0:
        return {}

    report.check(
        "positive_equity",
        bool((equity > 0).all()),
        "All equity observations are positive.",
    )

    running_max = equity.cummax()

    drawdown = (
        equity / running_max - 1.0
    ) * 100.0

    max_drawdown = float(
        drawdown.min()
    )

    return {
        "file": str(path),
        "observations": int(len(equity)),
        "starting_equity": float(equity.iloc[0]),
        "ending_equity": float(equity.iloc[-1]),
        "max_drawdown_pct": max_drawdown,
    }


# ============================================================================
# ACCOUNTING RECONCILIATION
# ============================================================================

def validate_accounting(
    trade_stats: dict[str, Any],
    equity_stats: dict[str, Any],
    report: ValidationReport,
) -> dict[str, Any]:
    """Check ending equity against starting equity + P&L."""

    if not trade_stats or not equity_stats:

        report.check(
            "accounting_reconciliation",
            False,
            "Trade and equity data were insufficient "
            "for full reconciliation.",
            severity="WARNING",
        )

        return {}

    start = safe_float(
        equity_stats.get(
            "starting_equity"
        )
    )

    end = safe_float(
        equity_stats.get(
            "ending_equity"
        )
    )

    net_pnl = safe_float(
        trade_stats.get(
            "net_pnl"
        )
    )

    expected_end = (
        start + net_pnl
    )

    difference = (
        end - expected_end
    )

    tolerance = (
        0.05
        + abs(expected_end) * 0.0001
    )

    report.check(
        "accounting_reconciliation",
        abs(difference) <= tolerance,
        (
            f"Ending equity={end:.8f}; "
            f"expected={expected_end:.8f}; "
            f"difference={difference:.8f}."
        ),
    )

    return {
        "starting_equity": start,
        "ending_equity": end,
        "net_trade_pnl": net_pnl,
        "expected_ending_equity": expected_end,
        "difference": difference,
        "tolerance": tolerance,
    }


# ============================================================================
# DATA QUALITY
# ============================================================================

def validate_market_data(
    root: Path,
    report: ValidationReport,
) -> dict[str, Any]:
    """Validate normalized market data."""

    candidates = list(
        root.rglob(
            "xauusd_h1_2024_2026_normalized.csv"
        )
    )

    if not candidates:

        candidates = list(
            root.rglob(
                "*xauusd*h1*.csv"
            )
        )

    if not candidates:

        report.check(
            "market_data",
            False,
            "Normalized XAUUSD H1 data was not found.",
            severity="WARNING",
        )

        return {}

    path = candidates[0]

    try:

        df = pd.read_csv(path)

    except Exception as exc:

        report.check(
            "market_data_read",
            False,
            f"Could not read {path}: {exc}",
        )

        return {}

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

    report.check(
        "market_data_columns",
        not missing,
        (
            "Required market columns are present."
            if not missing
            else f"Missing columns: {missing}"
        ),
    )

    if missing:
        return {}

    timestamps = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    report.check(
        "market_timestamps",
        not timestamps.isna().any(),
        "All market timestamps are valid.",
    )

    report.check(
        "market_timestamp_order",
        timestamps.is_monotonic_increasing,
        "Market timestamps are monotonically increasing.",
    )

    report.check(
        "market_duplicate_timestamps",
        not timestamps.duplicated().any(),
        "No duplicate market timestamps found.",
    )

    numeric = {}

    for column in [
        "open",
        "high",
        "low",
        "close",
    ]:

        numeric[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    invalid_numeric = sum(
        int(series.isna().sum())
        for series in numeric.values()
    )

    report.check(
        "market_numeric_values",
        invalid_numeric == 0,
        (
            "All OHLC values are numeric."
            if invalid_numeric == 0
            else (
                f"{invalid_numeric} invalid OHLC values found."
            )
        ),
    )

    invalid_ohlc = (
        (numeric["high"] < numeric["low"])
        | (numeric["high"] < numeric["open"])
        | (numeric["high"] < numeric["close"])
        | (numeric["low"] > numeric["open"])
        | (numeric["low"] > numeric["close"])
    )

    report.check(
        "ohlc_structure",
        not invalid_ohlc.any(),
        "OHLC candle relationships are valid.",
    )

    return {
        "file": str(path),
        "rows": int(len(df)),
        "start": str(timestamps.min()),
        "end": str(timestamps.max()),
    }


# ============================================================================
# LOOK-AHEAD RISK CHECKS
# ============================================================================

def validate_lookahead_artifacts(
    root: Path,
    report: ValidationReport,
) -> dict[str, Any]:
    """
    Look for obvious timestamp/feature columns that could indicate
    future data being used.

    This is NOT a proof that look-ahead bias is absent.
    """

    signal_files = list(
        root.rglob(
            "*signal*.csv"
        )
    )

    suspicious_columns: list[str] = []

    future_words = [
        "future",
        "next",
        "forward",
        "lookahead",
        "look_ahead",
        "target",
    ]

    for path in signal_files:

        try:
            df = pd.read_csv(
                path,
                nrows=5,
            )

        except Exception:
            continue

        for column in df.columns:

            lower = str(column).lower()

            if any(
                word in lower
                for word in future_words
            ):

                suspicious_columns.append(
                    f"{path.name}:{column}"
                )

    report.check(
        "lookahead_column_scan",
        len(suspicious_columns) == 0,
        (
            "No obviously suspicious future-looking "
            "feature columns were detected."
            if not suspicious_columns
            else (
                "Potential future-looking columns: "
                + ", ".join(suspicious_columns[:20])
            )
        ),
        severity="WARNING",
    )

    return {
        "signal_files_scanned": len(signal_files),
        "suspicious_columns": suspicious_columns,
    }


# ============================================================================
# FINAL VERDICT
# ============================================================================

def determine_verdict(
    report: ValidationReport,
    walk_forward: dict[str, Any],
    robustness: dict[str, Any],
    trade_stats: dict[str, Any],
    equity_stats: dict[str, Any],
) -> str:
    """Determine a conservative validation verdict."""

    hard_errors = len(
        report.errors
    )

    warnings = len(
        report.warnings
    )

    if hard_errors > 0:

        return "INVALID_RESULTS"

    robustness_verdict = str(
        robustness.get(
            "verdict",
            "",
        )
    ).upper()

    positive_rate = safe_float(
        walk_forward.get(
            "positive_test_window_rate_pct"
        )
    )

    median_return = safe_float(
        walk_forward.get(
            "median_test_return_pct"
        )
    )

    pf = safe_float(
        walk_forward.get(
            "average_test_profit_factor"
        )
    )

    if not pf and trade_stats:

        pf = safe_float(
            trade_stats.get(
                "profit_factor"
            )
        )

    max_dd = safe_float(
        equity_stats.get(
            "max_drawdown_pct"
        )
    )

    # Strong validation result.
    if (
        robustness_verdict == "ROBUST"
        and positive_rate >= 60.0
        and median_return > 0.0
        and pf > 1.0
        and max_dd > -35.0
    ):

        return "VALIDATED_FOR_NEXT_RESEARCH_STAGE"

    # Promising but not enough evidence.
    if (
        positive_rate >= 50.0
        and median_return > 0.0
        and pf > 1.0
    ):

        return "PROMISING_BUT_NEEDS_MORE_TESTING"

    # Some evidence but unstable.
    if (
        positive_rate >= 40.0
        or median_return > 0.0
        or pf > 1.0
    ):

        return "UNSTABLE_EDGE"

    if warnings > 0:

        return "INSUFFICIENT_EVIDENCE"

    return "NO_VALIDATED_EDGE"


# ============================================================================
# REPORT WRITER
# ============================================================================

def create_summary(
    output: Path,
    final_verdict: str,
    report: ValidationReport,
    walk_forward: dict[str, Any],
    robustness: dict[str, Any],
    trade_stats: dict[str, Any],
    equity_stats: dict[str, Any],
    accounting: dict[str, Any],
) -> None:
    """Write human-readable summary."""

    lines: list[str] = []

    lines.append(
        "RAYMOND V2.8 V5 RESULTS VALIDATION"
    )

    lines.append(
        "=" * 55
    )

    lines.append("")

    lines.append(
        f"FINAL VERDICT: {final_verdict}"
    )

    lines.append("")

    lines.append(
        "IMPORTANT: This validator does not prove that "
        "a strategy will perform live."
    )

    lines.append("")

    lines.append(
        "WALK-FORWARD"
    )

    lines.append(
        "-" * 30
    )

    lines.append(
        "Windows: "
        f"{walk_forward.get('windows', 'N/A')}"
    )

    lines.append(
        "Positive test-window rate: "
        f"{safe_float(walk_forward.get('positive_test_window_rate_pct')):.2f}%"
    )

    lines.append(
        "Median unseen-test return: "
        f"{safe_float(walk_forward.get('median_test_return_pct')):.4f}%"
    )

    lines.append(
        "Worst unseen-test return: "
        f"{safe_float(walk_forward.get('worst_test_return_pct')):.4f}%"
    )

    lines.append(
        "Compounded test return: "
        f"{safe_float(walk_forward.get('compound_test_return_pct')):.4f}%"
    )

    lines.append(
        "Average test profit factor: "
        f"{safe_float(walk_forward.get('average_test_profit_factor')):.4f}"
    )

    lines.append("")

    lines.append(
        "ROBUSTNESS"
    )

    lines.append(
        "-" * 30
    )

    lines.append(
        "Reported verdict: "
        f"{robustness.get('verdict', 'N/A')}"
    )

    lines.append("")

    if trade_stats:

        lines.append(
            "TRADE JOURNAL"
        )

        lines.append(
            "-" * 30
        )

        lines.append(
            f"Trades: {trade_stats.get('trades', 'N/A')}"
        )

        lines.append(
            f"Wins: {trade_stats.get('wins', 'N/A')}"
        )

        lines.append(
            f"Losses: {trade_stats.get('losses', 'N/A')}"
        )

        lines.append(
            f"Breakeven: {trade_stats.get('breakeven', 'N/A')}"
        )

        lines.append(
            f"Gross profit: {safe_float(trade_stats.get('gross_profit')):.4f}"
        )

        lines.append(
            f"Gross loss: {safe_float(trade_stats.get('gross_loss')):.4f}"
        )

        lines.append(
            f"Profit factor: {safe_float(trade_stats.get('profit_factor')):.4f}"
        )

        lines.append(
            f"Net P&L: {safe_float(trade_stats.get('net_pnl')):.4f}"
        )

        lines.append("")

    if equity_stats:

        lines.append(
            "EQUITY"
        )

        lines.append(
            "-" * 30
        )

        lines.append(
            f"Starting equity: "
            f"{safe_float(equity_stats.get('starting_equity')):.4f}"
        )

        lines.append(
            f"Ending equity: "
            f"{safe_float(equity_stats.get('ending_equity')):.4f}"
        )

        lines.append(
            f"Maximum drawdown: "
            f"{safe_float(equity_stats.get('max_drawdown_pct')):.4f}%"
        )

        lines.append("")

    if accounting:

        lines.append(
            "ACCOUNTING RECONCILIATION"
        )

        lines.append(
            "-" * 30
        )

        lines.append(
            f"Expected ending equity: "
            f"{safe_float(accounting.get('expected_ending_equity')):.8f}"
        )

        lines.append(
            f"Actual ending equity: "
            f"{safe_float(accounting.get('ending_equity')):.8f}"
        )

        lines.append(
            f"Difference: "
            f"{safe_float(accounting.get('difference')):.8f}"
        )

        lines.append("")

    lines.append(
        "VALIDATION CHECKS"
    )

    lines.append(
        "-" * 30
    )

    lines.append(
        f"Checks: {len(report.checks)}"
    )

    lines.append(
        f"Errors: {len(report.errors)}"
    )

    lines.append(
        f"Warnings: {len(report.warnings)}"
    )

    lines.append("")

    for item in report.information:

        lines.append(
            item
        )

    for item in report.warnings:

        lines.append(
            item
        )

    for item in report.errors:

        lines.append(
            item
        )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    (output / "summary.txt").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Validate Raymond V2.8 V5 "
            "research/backtest results."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help=(
            "Root directory containing the "
            "V5 research package."
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        help=(
            "Directory where validation "
            "reports will be written."
        ),
    )

    args = parser.parse_args()

    root = Path(
        args.input
    ).resolve()

    output = Path(
        args.output
    ).resolve()

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not root.exists():

        raise SystemExit(
            f"Input directory does not exist: {root}"
        )

    print("")
    print("=" * 70)
    print("RAYMOND V2.8 V5 RESULTS VALIDATOR")
    print("=" * 70)
    print("")
    print(f"Input:  {root}")
    print(f"Output: {output}")
    print("")

    report = ValidationReport()

    market_data = validate_market_data(
        root,
        report,
    )

    walk_forward = validate_walk_forward(
        root,
        report,
    )

    robustness = validate_robustness(
        root,
        report,
    )

    trade_stats = validate_trade_journal(
        root,
        report,
    )

    equity_stats = validate_equity(
        root,
        report,
    )

    accounting = validate_accounting(
        trade_stats,
        equity_stats,
        report,
    )

    lookahead = validate_lookahead_artifacts(
        root,
        report,
    )

    final_verdict = determine_verdict(
        report,
        walk_forward,
        robustness,
        trade_stats,
        equity_stats,
    )

    payload = {
        "validator": "RAYMOND_V2_8_V5_RESULTS_VALIDATOR",
        "version": "1.0",
        "research_only": True,
        "live_trading_enabled": False,
        "contract_model": {
            "symbol": "XAUUSD",
            "contract_size_oz_per_lot": XAUUSD_CONTRACT_SIZE,
            "price_decimals": XAUUSD_PRICE_DECIMALS,
        },
        "final_verdict": final_verdict,
        "market_data": market_data,
        "walk_forward": walk_forward,
        "robustness": robustness,
        "trade_statistics": trade_stats,
        "equity_statistics": equity_stats,
        "accounting_reconciliation": accounting,
        "lookahead_scan": lookahead,
        "validation": {
            "total_checks": len(report.checks),
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "passed": sum(
                1
                for check in report.checks
                if check["passed"]
            ),
            "checks": report.checks,
        },
    }

    write_json(
        output / "v5_results_validation.json",
        payload,
    )

    create_summary(
        output,
        final_verdict,
        report,
        walk_forward,
        robustness,
        trade_stats,
        equity_stats,
        accounting,
    )

    print("")
    print("=" * 70)
    print(
        f"FINAL VERDICT: {final_verdict}"
    )
    print("=" * 70)
    print("")

    print(
        f"Checks:   {len(report.checks)}"
    )

    print(
        f"Passed:   {sum(1 for c in report.checks if c['passed'])}"
    )

    print(
        f"Warnings: {len(report.warnings)}"
    )

    print(
        f"Errors:   {len(report.errors)}"
    )

    print("")

    print(
        f"Summary: {output / 'summary.txt'}"
    )

    print(
        f"JSON:    {output / 'v5_results_validation.json'}"
    )

    print("")

    # Do not fail the workflow merely because the strategy
    # is weak. Weak research results are valid research results.
    #
    # The workflow should fail only when the output itself
    # is structurally invalid.

    if final_verdict == "INVALID_RESULTS":

        print(
            "Validation failed because structural "
            "errors were detected."
        )

        return 1

    print(
        "Validation completed."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
