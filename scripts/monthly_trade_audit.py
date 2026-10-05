"""
RAYMOND V2.8 - MONTHLY TRADE AUDITOR

Research-only monthly audit of completed PAPER positions.

IMPORTANT SAFETY RULES
----------------------
- Research / paper analysis only.
- Never sends broker orders.
- Never modifies positions.
- Never modifies the active strategy.
- Never promotes strategy candidates automatically.
- Improvement candidates are recommendations only.
- Holdout validation is required before strategy promotion.

HISTORICAL ACCOUNTING MODEL
----------------------------

The auditor independently recalculates historical XAUUSD P/L.

It does NOT use Position.pnl as the authoritative historical P/L.

For XAUUSD:

    1.00 lot = 100 oz

Therefore:

    BUY P/L =
        (exit_price - entry_price)
        * quantity
        * 100

    SELL P/L =
        (entry_price - exit_price)
        * quantity
        * 100

For a trade with one persisted partial close:

    partial P/L =
        price movement from entry to partial close
        * partial quantity
        * 100

    final P/L =
        price movement from entry to final exit
        * remaining quantity
        * 100

    total trade P/L =
        partial P/L + final P/L

The persisted Position.pnl and Position.partial_close_pnl fields
are used only as stored-accounting comparison values.

RISK NORMALIZATION
------------------

Position.risk_1r is preferred because it represents the original
price-distance value for 1R.

Fallback:

    abs(entry_price - initial_stop_loss)

For XAUUSD:

    monetary 1R =
        risk_distance * original_quantity * 100

The current/moving stop is never used to redefine original 1R.

PARTIAL CLOSE LIMITATION
------------------------

The current Position model stores one partial-close execution:

    partial_close_price
    partial_close_quantity

and a cumulative:

    partial_close_pnl

Therefore this auditor can independently reconstruct a persisted
single partial-close execution.

If historical data contains multiple partial-close executions but
does not preserve each execution separately, the database does not
contain enough information to reconstruct every individual execution
from raw fields alone. The auditor therefore records the limitation
instead of inventing data.

USAGE
-----

    python scripts/monthly_trade_audit.py

or:

    python scripts/monthly_trade_audit.py 2026-09
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from backend.app.database import SessionLocal
    from backend.app.models import Position, PositionStatus
except ImportError:
    from app.database import SessionLocal
    from app.models import Position, PositionStatus


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_SYMBOL = "XAUUSD"

# RAYMOND V2.8 XAUUSD contract size.
XAUUSD_CONTRACT_SIZE = 100.0

OUTPUT_DIR = (
    Path("backtest_results")
    / "monthly_trade_audits"
)

RECONCILIATION_TOLERANCE = 0.01


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class TradeView:
    trade_id: str
    symbol: str
    direction: str

    entry_price: float
    exit_price: float | None

    # Independently recalculated complete economic P/L.
    pnl: float

    # Independently recalculated components.
    partial_close_pnl: float
    final_position_pnl: float
    total_trade_pnl: float

    # Persisted/stored values are retained only for comparison.
    stored_partial_close_pnl: float
    stored_final_position_pnl: float
    stored_total_trade_pnl: float

    # Difference between corrected and stored accounting.
    pnl_correction: float

    quantity: float

    initial_stop_loss: float | None
    take_profit: float | None

    regime: str
    setup: str

    technical_score: float | None
    confidence: float | None

    trade_thesis: str

    break_even_applied: bool
    partial_close_applied: bool
    trailing_active: bool

    management_status: str
    last_management_action: str

    max_profit: float
    max_drawdown: float

    opened_at: str | None
    closed_at: str | None

    initial_risk_distance: float | None

    max_profit_r: float | None
    max_drawdown_r: float | None

    outcome: str

    accounting_method: str
    accounting_warning: str | None


@dataclass
class Candidate:
    category: str
    finding: str
    evidence: str
    suggested_test: str
    priority: str = "research"


# ============================================================
# GENERIC HELPERS
# ============================================================

def safe_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        result = float(value)

        if not math.isfinite(result):
            return None

        return result

    except (
        TypeError,
        ValueError,
    ):
        return None


def safe_text(
    value: Any,
    default: str = "unknown",
) -> str:
    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return text


def enum_value(
    value: Any,
) -> str:
    if value is None:
        return "unknown"

    return safe_text(
        getattr(
            value,
            "value",
            value,
        )
    )


def iso(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return safe_text(value)


def percentage(
    numerator: float,
    denominator: float,
) -> float:
    if denominator == 0:
        return 0.0

    return (
        numerator
        / denominator
        * 100.0
    )


def safe_mean(
    values: Iterable[float],
) -> float | None:
    values = list(values)

    if not values:
        return None

    return statistics.mean(values)


def percentile(
    values: list[float],
    p: float,
) -> float | None:
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (
        (len(ordered) - 1)
        * p
    )

    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    fraction = position - lower

    return (
        ordered[lower]
        + (
            ordered[upper]
            - ordered[lower]
        )
        * fraction
    )


def month_bounds(
    month_text: str | None,
) -> tuple[
    datetime,
    datetime,
    str,
]:
    if month_text:
        parts = month_text.split("-")

        if len(parts) != 2:
            raise ValueError(
                "Month must use YYYY-MM format."
            )

        year = int(parts[0])
        month = int(parts[1])

        if month < 1 or month > 12:
            raise ValueError(
                "Month must be between 01 and 12."
            )

        start = datetime(
            year,
            month,
            1,
            tzinfo=timezone.utc,
        )

    else:
        now = datetime.now(
            timezone.utc
        )

        start = datetime(
            now.year,
            now.month,
            1,
            tzinfo=timezone.utc,
        )

    if start.month == 12:
        end = datetime(
            start.year + 1,
            1,
            1,
            tzinfo=timezone.utc,
        )
    else:
        end = datetime(
            start.year,
            start.month + 1,
            1,
            tzinfo=timezone.utc,
        )

    label = (
        f"{start.year:04d}-"
        f"{start.month:02d}"
    )

    return start, end, label


# ============================================================
# POSITION FIELD HELPERS
# ============================================================

def original_quantity(
    position: Position,
) -> float:
    quantity = safe_float(
        getattr(
            position,
            "original_quantity",
            None,
        )
    )

    if quantity is None or quantity <= 0:
        quantity = safe_float(
            getattr(
                position,
                "quantity",
                None,
            )
        )

    return quantity or 0.0


def partial_quantity(
    position: Position,
) -> float:
    value = safe_float(
        getattr(
            position,
            "partial_close_quantity",
            None,
        )
    )

    if value is None or value <= 0:
        return 0.0

    return value


def partial_close_price(
    position: Position,
) -> float | None:
    return safe_float(
        getattr(
            position,
            "partial_close_price",
            None,
        )
    )


def final_exit_price(
    position: Position,
) -> float | None:
    """
    The lifecycle stores the latest/final market price in current_price
    when a position is closed.

    For closed positions this is the final exit price used by the
    corrected historical accounting.
    """

    value = safe_float(
        getattr(
            position,
            "current_price",
            None,
        )
    )

    if value is not None:
        return value

    return None


def direction_text(
    position: Position,
) -> str:
    direction = enum_value(
        getattr(
            position,
            "direction",
            None,
        )
    ).upper()

    if direction in {
        "BUY",
        "SELL",
    }:
        return direction

    return direction


# ============================================================
# XAUUSD PRICE P/L ENGINE
# ============================================================

def calculate_price_pnl(
    *,
    direction: str,
    entry_price: float,
    exit_price: float,
    quantity: float,
    contract_size: float = XAUUSD_CONTRACT_SIZE,
) -> float:
    """
    Independently calculate monetary P/L from raw trade economics.

    BUY:
        (exit - entry) * quantity * contract_size

    SELL:
        (entry - exit) * quantity * contract_size
    """

    if quantity <= 0:
        return 0.0

    if direction == "BUY":
        price_difference = (
            exit_price
            - entry_price
        )

    elif direction == "SELL":
        price_difference = (
            entry_price
            - exit_price
        )

    else:
        raise ValueError(
            f"Unsupported trade direction: {direction}"
        )

    return (
        price_difference
        * quantity
        * contract_size
    )


def calculate_partial_close_pnl(
    position: Position,
) -> tuple[
    float,
    str | None,
]:
    """
    Independently reconstruct the persisted partial-close execution.

    Returns:
        (pnl, warning)
    """

    quantity = partial_quantity(
        position
    )

    close_price = partial_close_price(
        position
    )

    entry_price = safe_float(
        getattr(
            position,
            "entry_price",
            None,
        )
    )

    if quantity <= 0:
        return 0.0, None

    if close_price is None:
        return (
            0.0,
            "Partial-close quantity exists but "
            "partial_close_price is missing; "
            "partial P/L cannot be independently reconstructed.",
        )

    if entry_price is None:
        return (
            0.0,
            "Partial-close data exists but "
            "entry_price is missing.",
        )

    direction = direction_text(
        position
    )

    try:
        pnl = calculate_price_pnl(
            direction=direction,
            entry_price=entry_price,
            exit_price=close_price,
            quantity=quantity,
        )

    except ValueError as exc:
        return (
            0.0,
            str(exc),
        )

    return pnl, None


def calculate_remaining_quantity(
    position: Position,
) -> tuple[
    float,
    str | None,
]:
    """
    Reconstruct the quantity belonging to the final exit.

    The closed Position row can have remaining_quantity=0 because the
    final close consumes the remaining quantity. Therefore we do not
    blindly use a zero stored value.

    We reconstruct:

        original quantity - persisted partial-close quantity

    for a position with one partial close.

    Without a partial close, the final quantity is the original
    quantity.
    """

    original = original_quantity(
        position
    )

    partial = partial_quantity(
        position
    )

    if original <= 0:
        return (
            0.0,
            "Original trade quantity is missing or invalid.",
        )

    if partial <= 0:
        return original, None

    remaining = (
        original
        - partial
    )

    if remaining < -1e-9:
        return (
            0.0,
            "Partial-close quantity exceeds "
            "original quantity; final quantity "
            "cannot be reconstructed safely.",
        )

    return max(
        0.0,
        remaining,
    ), None


def calculate_final_position_pnl(
    position: Position,
) -> tuple[
    float,
    float,
    str | None,
]:
    """
    Independently calculate P/L for the quantity remaining after a
    persisted partial close.

    Returns:

        final_pnl
        final_quantity
        warning
    """

    entry_price = safe_float(
        getattr(
            position,
            "entry_price",
            None,
        )
    )

    exit_price = final_exit_price(
        position
    )

    if entry_price is None:
        return (
            0.0,
            0.0,
            "Entry price is missing.",
        )

    if exit_price is None:
        return (
            0.0,
            0.0,
            "Final exit price is missing.",
        )

    quantity, quantity_warning = (
        calculate_remaining_quantity(
            position
        )
    )

    if quantity <= 0:
        return (
            0.0,
            quantity,
            quantity_warning,
        )

    direction = direction_text(
        position
    )

    try:
        pnl = calculate_price_pnl(
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
        )

    except ValueError as exc:
        return (
            0.0,
            quantity,
            str(exc),
        )

    return (
        pnl,
        quantity,
        quantity_warning,
    )


# ============================================================
# STORED ACCOUNTING
# ============================================================

def stored_partial_close_pnl(
    position: Position,
) -> float:
    return (
        safe_float(
            getattr(
                position,
                "partial_close_pnl",
                None,
            )
        )
        or 0.0
    )


def stored_final_position_pnl(
    position: Position,
) -> float:
    return (
        safe_float(
            getattr(
                position,
                "pnl",
                None,
            )
        )
        or 0.0
    )


def stored_total_trade_pnl(
    position: Position,
) -> float:
    return (
        stored_partial_close_pnl(
            position
        )
        + stored_final_position_pnl(
            position
        )
    )


# ============================================================
# CORRECTED HISTORICAL ACCOUNTING
# ============================================================

def audited_position_accounting(
    position: Position,
) -> dict[str, Any]:
    """
    Independently reconstruct the trade economics.

    This is the critical correction.

    The historical audit does NOT treat Position.pnl as authoritative.
    """

    partial_pnl, partial_warning = (
        calculate_partial_close_pnl(
            position
        )
    )

    (
        final_pnl,
        final_quantity,
        final_warning,
    ) = calculate_final_position_pnl(
        position
    )

    total_pnl = (
        partial_pnl
        + final_pnl
    )

    stored_partial = (
        stored_partial_close_pnl(
            position
        )
    )

    stored_final = (
        stored_final_position_pnl(
            position
        )
    )

    stored_total = (
        stored_total_trade_pnl(
            position
        )
    )

    correction = (
        total_pnl
        - stored_total
    )

    warnings = []

    if partial_warning:
        warnings.append(
            partial_warning
        )

    if final_warning:
        warnings.append(
            final_warning
        )

    warning = (
        " | ".join(warnings)
        if warnings
        else None
    )

    return {
        "partial_close_pnl": partial_pnl,
        "final_position_pnl": final_pnl,
        "total_trade_pnl": total_pnl,
        "final_quantity": final_quantity,
        "stored_partial_close_pnl": stored_partial,
        "stored_final_position_pnl": stored_final,
        "stored_total_trade_pnl": stored_total,
        "pnl_correction": correction,
        "warning": warning,
    }


# ============================================================
# POSITION -> TRADE VIEW
# ============================================================

def position_to_trade(
    position: Position,
) -> TradeView:
    entry_price = (
        safe_float(
            getattr(
                position,
                "entry_price",
                None,
            )
        )
        or 0.0
    )

    exit_price = final_exit_price(
        position
    )

    initial_sl = safe_float(
        getattr(
            position,
            "initial_stop_loss",
            None,
        )
    )

    take_profit = safe_float(
        getattr(
            position,
            "take_profit_1",
            None,
        )
    )

    quantity = original_quantity(
        position
    )

    accounting = (
        audited_position_accounting(
            position
        )
    )

    partial_pnl = accounting[
        "partial_close_pnl"
    ]

    final_pnl = accounting[
        "final_position_pnl"
    ]

    total_pnl = accounting[
        "total_trade_pnl"
    ]

    stored_partial = accounting[
        "stored_partial_close_pnl"
    ]

    stored_final = accounting[
        "stored_final_position_pnl"
    ]

    stored_total = accounting[
        "stored_total_trade_pnl"
    ]

    correction = accounting[
        "pnl_correction"
    ]

    # --------------------------------------------------------
    # ORIGINAL 1R
    # --------------------------------------------------------

    risk_distance = safe_float(
        getattr(
            position,
            "risk_1r",
            None,
        )
    )

    if (
        risk_distance is None
        or risk_distance <= 0
    ):
        if (
            initial_sl is not None
            and entry_price > 0
        ):
            risk_distance = abs(
                entry_price
                - initial_sl
            )

    max_profit = (
        safe_float(
            getattr(
                position,
                "max_profit",
                None,
            )
        )
        or 0.0
    )

    max_drawdown = (
        safe_float(
            getattr(
                position,
                "max_drawdown",
                None,
            )
        )
        or 0.0
    )

    max_profit_r = None
    max_drawdown_r = None

    if (
        risk_distance is not None
        and risk_distance > 0
        and quantity > 0
    ):
        monetary_one_r = (
            risk_distance
            * quantity
            * XAUUSD_CONTRACT_SIZE
        )

        if monetary_one_r > 0:
            max_profit_r = (
                max_profit
                / monetary_one_r
            )

            max_drawdown_r = (
                max_drawdown
                / monetary_one_r
            )

    # --------------------------------------------------------
    # OUTCOME
    # --------------------------------------------------------

    if total_pnl > 0:
        outcome = "WIN"
    elif total_pnl < 0:
        outcome = "LOSS"
    else:
        outcome = "BREAKEVEN"

    # --------------------------------------------------------
    # ACCOUNTING METHOD
    # --------------------------------------------------------

    has_partial = (
        partial_quantity(position)
        > 0
    )

    if has_partial:
        accounting_method = (
            "independent_raw_price_recalculation_"
            "with_persisted_partial_execution"
        )
    else:
        accounting_method = (
            "independent_raw_price_recalculation"
        )

    return TradeView(
        trade_id=safe_text(
            getattr(
                position,
                "trade_id",
                None,
            ),
            safe_text(
                getattr(
                    position,
                    "position_id",
                    None,
                )
            ),
        ),
        symbol=safe_text(
            getattr(
                position,
                "symbol",
                None,
            ),
            DEFAULT_SYMBOL,
        ),
        direction=direction_text(
            position
        ),
        entry_price=entry_price,
        exit_price=exit_price,

        pnl=total_pnl,

        partial_close_pnl=partial_pnl,
        final_position_pnl=final_pnl,
        total_trade_pnl=total_pnl,

        stored_partial_close_pnl=stored_partial,
        stored_final_position_pnl=stored_final,
        stored_total_trade_pnl=stored_total,

        pnl_correction=correction,

        quantity=quantity,

        initial_stop_loss=initial_sl,
        take_profit=take_profit,

        regime=safe_text(
            getattr(
                position,
                "regime",
                None,
            )
        ),
        setup=safe_text(
            getattr(
                position,
                "setup",
                None,
            )
        ),

        technical_score=safe_float(
            getattr(
                position,
                "technical_score",
                None,
            )
        ),
        confidence=safe_float(
            getattr(
                position,
                "confidence",
                None,
            )
        ),

        trade_thesis=safe_text(
            getattr(
                position,
                "trade_thesis",
                None,
            ),
            "not recorded",
        ),

        break_even_applied=bool(
            getattr(
                position,
                "break_even_applied",
                False,
            )
        ),

        partial_close_applied=bool(
            getattr(
                position,
                "partial_close_applied",
                False,
            )
        ),

        trailing_active=bool(
            getattr(
                position,
                "trailing_active",
                False,
            )
        ),

        management_status=safe_text(
            getattr(
                position,
                "management_status",
                None,
            )
        ),

        last_management_action=safe_text(
            getattr(
                position,
                "last_management_action",
                None,
            )
        ),

        max_profit=max_profit,
        max_drawdown=max_drawdown,

        opened_at=iso(
            getattr(
                position,
                "opened_at",
                None,
            )
        ),

        closed_at=iso(
            getattr(
                position,
                "closed_at",
                None,
            )
        ),

        initial_risk_distance=risk_distance,

        max_profit_r=max_profit_r,
        max_drawdown_r=max_drawdown_r,

        outcome=outcome,

        accounting_method=accounting_method,
        accounting_warning=accounting[
            "warning"
        ],
    )


# ============================================================
# DATABASE LOAD
# ============================================================

def load_closed_positions(
    start: datetime,
    end: datetime,
    symbol: str,
) -> list[TradeView]:
    """
    Load authoritative closed paper positions.

    This remains read-only.
    """

    db = SessionLocal()

    try:
        rows = (
            db.query(Position)
            .filter(
                Position.status
                == PositionStatus.CLOSED
            )
            .filter(
                Position.symbol
                == symbol
            )
            .filter(
                Position.closed_at
                >= start.replace(
                    tzinfo=None
                )
            )
            .filter(
                Position.closed_at
                < end.replace(
                    tzinfo=None
                )
            )
            .order_by(
                Position.closed_at.asc()
            )
            .all()
        )

        return [
            position_to_trade(
                row
            )
            for row in rows
        ]

    finally:
        db.close()


# ============================================================
# PERFORMANCE
# ============================================================

def performance_summary(
    trades: list[TradeView],
) -> dict[str, Any]:
    pnls = [
        trade.total_trade_pnl
        for trade in trades
    ]

    wins = [
        pnl
        for pnl in pnls
        if pnl > 0
    ]

    losses = [
        pnl
        for pnl in pnls
        if pnl < 0
    ]

    gross_profit = sum(wins)

    gross_loss = abs(
        sum(losses)
    )

    profit_factor = None

    if gross_loss > 0:
        profit_factor = (
            gross_profit
            / gross_loss
        )

    return {
        "total_trades": len(
            trades
        ),
        "winning_trades": len(
            wins
        ),
        "losing_trades": len(
            losses
        ),
        "breakeven_trades": (
            len(trades)
            - len(wins)
            - len(losses)
        ),
        "win_rate_pct": round(
            percentage(
                len(wins),
                len(trades),
            ),
            2,
        ),
        "total_pnl": round(
            sum(pnls),
            4,
        ),
        "gross_profit": round(
            gross_profit,
            4,
        ),
        "gross_loss": round(
            gross_loss,
            4,
        ),
        "profit_factor": (
            round(
                profit_factor,
                4,
            )
            if profit_factor is not None
            else None
        ),
        "average_trade": round(
            safe_mean(pnls) or 0.0,
            4,
        ),
        "average_win": round(
            safe_mean(wins) or 0.0,
            4,
        ),
        "average_loss": round(
            safe_mean(losses) or 0.0,
            4,
        ),
        "median_trade": round(
            statistics.median(pnls)
            if pnls
            else 0.0,
            4,
        ),
        "best_trade": round(
            max(pnls)
            if pnls
            else 0.0,
            4,
        ),
        "worst_trade": round(
            min(pnls)
            if pnls
            else 0.0,
            4,
        ),
    }


# ============================================================
# GROUP PERFORMANCE
# ============================================================

def group_performance(
    trades: list[TradeView],
    attribute: str,
) -> list[dict[str, Any]]:
    groups = defaultdict(list)

    for trade in trades:
        value = getattr(
            trade,
            attribute,
        )

        key = safe_text(
            value
        )

        groups[key].append(
            trade
        )

    result = []

    for key, rows in groups.items():
        pnls = [
            trade.total_trade_pnl
            for trade in rows
        ]

        wins = [
            pnl
            for pnl in pnls
            if pnl > 0
        ]

        losses = [
            pnl
            for pnl in pnls
            if pnl < 0
        ]

        gross_profit = sum(wins)
        gross_loss = abs(
            sum(losses)
        )

        pf = None

        if gross_loss > 0:
            pf = (
                gross_profit
                / gross_loss
            )

        result.append(
            {
                "group": key,
                "total_trades": len(
                    rows
                ),
                "winning_trades": len(
                    wins
                ),
                "losing_trades": len(
                    losses
                ),
                "breakeven_trades": (
                    len(rows)
                    - len(wins)
                    - len(losses)
                ),
                "win_rate_pct": round(
                    percentage(
                        len(wins),
                        len(rows),
                    ),
                    2,
                ),
                "total_pnl": round(
                    sum(pnls),
                    4,
                ),
                "gross_profit": round(
                    gross_profit,
                    4,
                ),
                "gross_loss": round(
                    gross_loss,
                    4,
                ),
                "profit_factor": (
                    round(
                        pf,
                        4,
                    )
                    if pf is not None
                    else 0.0
                ),
                "average_trade": round(
                    safe_mean(pnls)
                    or 0.0,
                    4,
                ),
                "average_win": round(
                    safe_mean(wins)
                    or 0.0,
                    4,
                ),
                "average_loss": round(
                    safe_mean(losses)
                    or 0.0,
                    4,
                ),
                "median_trade": round(
                    statistics.median(
                        pnls
                    )
                    if pnls
                    else 0.0,
                    4,
                ),
                "best_trade": round(
                    max(pnls)
                    if pnls
                    else 0.0,
                    4,
                ),
                "worst_trade": round(
                    min(pnls)
                    if pnls
                    else 0.0,
                    4,
                ),
            }
        )

    return result


# ============================================================
# SCORE / CONFIDENCE ANALYSIS
# ============================================================

def technical_score_bucket(
    score: float | None,
) -> str:
    if score is None:
        return "unknown"

    if score >= 75:
        return "75+"

    if score >= 60:
        return "60-74"

    return "<60"


def confidence_bucket(
    confidence: float | None,
) -> str:
    if confidence is None:
        return "unknown"

    if confidence >= 80:
        return "80+"

    if confidence >= 70:
        return "70-79"

    if confidence >= 60:
        return "60-69"

    return "<60"


def bucket_performance(
    trades: list[TradeView],
    bucket_function,
    attribute: str,
) -> list[dict[str, Any]]:
    groups = defaultdict(list)

    for trade in trades:
        value = getattr(
            trade,
            attribute,
        )

        key = bucket_function(
            value
        )

        groups[key].append(
            trade
        )

    result = []

    for key, rows in groups.items():
        pnls = [
            trade.total_trade_pnl
            for trade in rows
        ]

        wins = [
            pnl
            for pnl in pnls
            if pnl > 0
        ]

        losses = [
            pnl
            for pnl in pnls
            if pnl < 0
        ]

        result.append(
            {
                "bucket": key,
                "total_trades": len(
                    rows
                ),
                "winning_trades": len(
                    wins
                ),
                "losing_trades": len(
                    losses
                ),
                "breakeven_trades": (
                    len(rows)
                    - len(wins)
                    - len(losses)
                ),
                "win_rate_pct": round(
                    percentage(
                        len(wins),
                        len(rows),
                    ),
                    2,
                ),
                "total_pnl": round(
                    sum(pnls),
                    4,
                ),
            }
        )

    return result


def bucket_analysis(
    trades: list[TradeView],
) -> dict[str, Any]:
    return {
        "technical_score": (
            bucket_performance(
                trades,
                technical_score_bucket,
                "technical_score",
            )
        ),
        "confidence": (
            bucket_performance(
                trades,
                confidence_bucket,
                "confidence",
            )
        ),
    }


# ============================================================
# LOSS PATTERNS
# ============================================================

def loss_patterns(
    trades: list[TradeView],
) -> dict[str, Any]:
    losses = [
        trade
        for trade in trades
        if trade.total_trade_pnl < 0
    ]

    direction = defaultdict(int)
    regime = defaultdict(int)
    setup = defaultdict(int)
    management_status = defaultdict(int)
    last_action = defaultdict(int)

    for trade in losses:
        direction[
            trade.direction
        ] += 1

        regime[
            trade.regime
        ] += 1

        setup[
            trade.setup
        ] += 1

        management_status[
            trade.management_status
        ] += 1

        last_action[
            trade.last_management_action
        ] += 1

    return {
        "loss_count": len(
            losses
        ),
        "patterns": {
            "direction": dict(
                direction
            ),
            "regime": dict(
                regime
            ),
            "setup": dict(
                setup
            ),
            "management_status": dict(
                management_status
            ),
            "last_management_action": dict(
                last_action
            ),
        },
    }


# ============================================================
# MANAGEMENT ANALYSIS
# ============================================================

def management_group(
    trades: list[TradeView],
    attribute: str,
) -> dict[str, Any]:
    groups = {
        "applied": [],
        "not_applied": [],
    }

    for trade in trades:
        value = bool(
            getattr(
                trade,
                attribute,
            )
        )

        if value:
            groups["applied"].append(
                trade
            )
        else:
            groups["not_applied"].append(
                trade
            )

    result = {}

    for key, rows in groups.items():
        pnls = [
            trade.total_trade_pnl
            for trade in rows
        ]

        wins = [
            pnl
            for pnl in pnls
            if pnl > 0
        ]

        losses = [
            pnl
            for pnl in pnls
            if pnl < 0
        ]

        result[key] = {
            "total_trades": len(
                rows
            ),
            "winning_trades": len(
                wins
            ),
            "losing_trades": len(
                losses
            ),
            "breakeven_trades": (
                len(rows)
                - len(wins)
                - len(losses)
            ),
            "win_rate_pct": round(
                percentage(
                    len(wins),
                    len(rows),
                ),
                2,
            ),
            "total_pnl": round(
                sum(pnls),
                4,
            ),
        }

    return result


def management_analysis(
    trades: list[TradeView],
) -> dict[str, Any]:
    return {
        "break_even_applied": (
            management_group(
                trades,
                "break_even_applied",
            )
        ),
        "partial_close_applied": (
            management_group(
                trades,
                "partial_close_applied",
            )
        ),
        "trailing_active": (
            management_group(
                trades,
                "trailing_active",
            )
        ),
    }


# ============================================================
# EXCURSION ANALYSIS
# ============================================================

def excursion_analysis(
    trades: list[TradeView],
) -> dict[str, Any]:
    losses = [
        trade
        for trade in trades
        if trade.total_trade_pnl < 0
    ]

    wins = [
        trade
        for trade in trades
        if trade.total_trade_pnl > 0
    ]

    profitable_first = [
        trade
        for trade in losses
        if (
            trade.max_profit_r
            is not None
            and trade.max_profit_r > 0
        )
    ]

    negative_first = [
        trade
        for trade in wins
        if (
            trade.max_drawdown_r
            is not None
            and trade.max_drawdown_r > 0
        )
    ]

    profitable_values = [
        trade.max_profit_r
        for trade in profitable_first
        if trade.max_profit_r is not None
    ]

    negative_values = [
        trade.max_drawdown_r
        for trade in negative_first
        if trade.max_drawdown_r is not None
    ]

    return {
        "losing_trades_that_were_profitable_first": {
            "count": len(
                profitable_first
            ),
            "percentage_of_losses": round(
                percentage(
                    len(profitable_first),
                    len(losses),
                ),
                2,
            ),
            "average_max_profit_r": round(
                safe_mean(
                    profitable_values
                )
                or 0.0,
                4,
            ),
            "median_max_profit_r": round(
                statistics.median(
                    profitable_values
                )
                if profitable_values
                else 0.0,
                4,
            ),
        },
        "winning_trades_that_went_negative_first": {
            "count": len(
                negative_first
            ),
            "average_max_drawdown_r": round(
                safe_mean(
                    negative_values
                )
                or 0.0,
                4,
            ),
        },
    }


# ============================================================
# IMPROVEMENT CANDIDATES
# ============================================================

def generate_candidates(
    trades: list[TradeView],
) -> list[Candidate]:
    candidates = []

    losses = [
        trade
        for trade in trades
        if trade.total_trade_pnl < 0
    ]

    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------

    direction_groups = defaultdict(list)

    for trade in trades:
        direction_groups[
            trade.direction
        ].append(trade)

    for direction, rows in direction_groups.items():
        if len(rows) < 5:
            continue

        wins = sum(
            1
            for trade in rows
            if trade.total_trade_pnl > 0
        )

        wr = percentage(
            wins,
            len(rows),
        )

        pnl = sum(
            trade.total_trade_pnl
            for trade in rows
        )

        if wr < 25:
            candidates.append(
                Candidate(
                    category="direction_filter",
                    finding=(
                        f"{direction} trades "
                        "performed poorly "
                        "during the audited month."
                    ),
                    evidence=(
                        f"{len(rows)} trades, "
                        f"{wr:.1f}% win rate, "
                        f"{pnl:.2f} total P/L."
                    ),
                    suggested_test=(
                        f"Test stronger {direction} "
                        "confirmation or stricter "
                        "regime requirements."
                    ),
                    priority="research",
                )
            )

    # --------------------------------------------------------
    # REGIME
    # --------------------------------------------------------

    regime_groups = defaultdict(list)

    for trade in trades:
        regime_groups[
            trade.regime
        ].append(trade)

    for regime, rows in regime_groups.items():
        if len(rows) < 5:
            continue

        wins = sum(
            1
            for trade in rows
            if trade.total_trade_pnl > 0
        )

        wr = percentage(
            wins,
            len(rows),
        )

        pnl = sum(
            trade.total_trade_pnl
            for trade in rows
        )

        if pnl < 0 and wr < 35:
            candidates.append(
                Candidate(
                    category="market_regime",
                    finding=(
                        f"Regime '{regime}' "
                        "was persistently weak."
                    ),
                    evidence=(
                        f"{len(rows)} trades, "
                        f"{wr:.1f}% win rate, "
                        f"P/L {pnl:.2f}."
                    ),
                    suggested_test=(
                        "Test requiring stronger "
                        "higher-timeframe regime "
                        "alignment before entry."
                    ),
                    priority="high",
                )
            )

    # --------------------------------------------------------
    # PROFIT PROTECTION
    # --------------------------------------------------------

    profitable_first = [
        trade
        for trade in losses
        if (
            trade.max_profit_r
            is not None
            and trade.max_profit_r >= 0.5
        )
    ]

    if len(profitable_first) >= 3:
        candidates.append(
            Candidate(
                category="profit_protection",
                finding=(
                    "Several losing trades "
                    "became meaningfully "
                    "profitable before reversing."
                ),
                evidence=(
                    f"{len(profitable_first)} losing "
                    "trades reached at least "
                    "approximately +0.5R."
                ),
                suggested_test=(
                    "Backtest earlier break-even, "
                    "partial-profit, or trailing "
                    "protection."
                ),
                priority="high",
            )
        )

    # --------------------------------------------------------
    # HIGH CONFIDENCE LOSSES
    # --------------------------------------------------------

    high_confidence = [
        trade
        for trade in losses
        if (
            trade.confidence is not None
            and trade.confidence >= 70
        )
    ]

    if len(high_confidence) >= 4:
        candidates.append(
            Candidate(
                category="confidence_calibration",
                finding=(
                    "High-confidence signals "
                    "still produced repeated losses."
                ),
                evidence=(
                    f"{len(high_confidence)} losses "
                    "had confidence >=70."
                ),
                suggested_test=(
                    "Investigate whether confidence "
                    "is properly calibrated against "
                    "actual outcomes before using "
                    "it as a stronger entry filter."
                ),
                priority="research",
            )
        )

    return candidates


# ============================================================
# ACCOUNTING RECONCILIATION
# ============================================================

def accounting_summary(
    trades: list[TradeView],
) -> dict[str, Any]:
    corrected_partial = sum(
        trade.partial_close_pnl
        for trade in trades
    )

    corrected_final = sum(
        trade.final_position_pnl
        for trade in trades
    )

    corrected_total = sum(
        trade.total_trade_pnl
        for trade in trades
    )

    reconstructed_total = (
        corrected_partial
        + corrected_final
    )

    stored_partial = sum(
        trade.stored_partial_close_pnl
        for trade in trades
    )

    stored_final = sum(
        trade.stored_final_position_pnl
        for trade in trades
    )

    stored_total = sum(
        trade.stored_total_trade_pnl
        for trade in trades
    )

    correction_total = (
        corrected_total
        - stored_total
    )

    differences = [
        trade
        for trade in trades
        if abs(
            trade.pnl_correction
        )
        > RECONCILIATION_TOLERANCE
    ]

    warnings = [
        trade
        for trade in trades
        if trade.accounting_warning
    ]

    partial_close_trades = [
        trade
        for trade in trades
        if (
            trade.partial_close_applied
            or abs(
                trade.partial_close_pnl
            ) > 1e-12
            or abs(
                trade.stored_partial_close_pnl
            ) > 1e-12
        )
    ]

    return {
        # Corrected accounting.
        "partial_close_pnl": round(
            corrected_partial,
            4,
        ),
        "final_remaining_position_pnl": round(
            corrected_final,
            4,
        ),
        "total_trade_pnl": round(
            corrected_total,
            4,
        ),
        "reconstructed_total_pnl": round(
            reconstructed_total,
            4,
        ),

        # Old stored accounting retained for audit comparison.
        "stored_partial_close_pnl": round(
            stored_partial,
            4,
        ),
        "stored_final_position_pnl": round(
            stored_final,
            4,
        ),
        "stored_total_trade_pnl": round(
            stored_total,
            4,
        ),

        # Difference between corrected and old stored accounting.
        "historical_pnl_correction": round(
            correction_total,
            4,
        ),

        "trades_with_pnl_correction": len(
            differences
        ),

        "trades_with_accounting_warning": len(
            warnings
        ),

        "partial_close_trade_count": len(
            partial_close_trades
        ),

        # Corrected components must reconcile exactly.
        "reconciliation_difference": round(
            corrected_total
            - reconstructed_total,
            10,
        ),

        "accounting_reconciled": (
            abs(
                corrected_total
                - reconstructed_total
            )
            < 1e-8
        ),

        "independent_historical_recalculation": True,

        "stored_pnl_used_as_authoritative": False,

        "contract_size": (
            XAUUSD_CONTRACT_SIZE
        ),
    }


# ============================================================
# REPORT GENERATION
# ============================================================

def build_report(
    trades: list[TradeView],
    month: str,
    symbol: str,
) -> dict[str, Any]:

    performance = (
        performance_summary(
            trades
        )
    )

    accounting = (
        accounting_summary(
            trades
        )
    )

    candidates = (
        generate_candidates(
            trades
        )
    )

    losses = [
        trade
        for trade in trades
        if trade.total_trade_pnl < 0
    ]

    report = {
        "report_type": (
            "RAYMOND_MONTHLY_TRADE_AUDIT"
        ),

        "version": "2.0",

        "research_only": True,

        "live_trading_changed": False,

        "symbol": symbol,

        "month": month,

        "generated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "accounting": accounting,

        "risk_normalization": {
            "method": (
                "persisted_risk_1r"
            ),
            "fallback": (
                "abs(entry_price - "
                "initial_stop_loss)"
            ),
            "contract_size": (
                XAUUSD_CONTRACT_SIZE
                if symbol.upper()
                == "XAUUSD"
                else None
            ),
            "description": (
                "Position.risk_1r is treated "
                "as the original price-distance "
                "value for 1R. For XAUUSD, "
                "monetary 1R equals price distance "
                "times original quantity times 100."
            ),
        },

        "historical_accounting": {
            "method": (
                "independent_raw_price_recalculation"
            ),
            "contract_size": (
                XAUUSD_CONTRACT_SIZE
            ),
            "stored_position_pnl_authoritative": (
                False
            ),
            "partial_close_method": (
                "entry_to_partial_close_price "
                "times partial quantity "
                "times contract size"
            ),
            "final_position_method": (
                "entry_to_final_exit_price "
                "times reconstructed remaining "
                "quantity times contract size"
            ),
            "total_method": (
                "independently recalculated partial "
                "P/L plus independently recalculated "
                "final remaining-position P/L"
            ),
        },

        "performance": performance,

        "direction_analysis": (
            group_performance(
                trades,
                "direction",
            )
        ),

        "regime_analysis": (
            group_performance(
                trades,
                "regime",
            )
        ),

        "setup_analysis": (
            group_performance(
                trades,
                "setup",
            )
        ),

        "score_and_confidence": (
            bucket_analysis(
                trades
            )
        ),

        "loss_patterns": (
            loss_patterns(
                trades
            )
        ),

        "management_analysis": (
            management_analysis(
                trades
            )
        ),

        "excursion_analysis": (
            excursion_analysis(
                trades
            )
        ),

        "improvement_candidates": [
            asdict(
                candidate
            )
            for candidate in candidates
        ],

        "loss_trade_ids": [
            trade.trade_id
            for trade in losses
        ],

        "accounting_warnings": [
            {
                "trade_id": trade.trade_id,
                "warning": trade.accounting_warning,
            }
            for trade in trades
            if trade.accounting_warning
        ],

        "trades_with_corrections": [
            {
                "trade_id": trade.trade_id,
                "stored_total_pnl": (
                    round(
                        trade.stored_total_trade_pnl,
                        4,
                    )
                ),
                "corrected_total_pnl": (
                    round(
                        trade.total_trade_pnl,
                        4,
                    )
                ),
                "correction": (
                    round(
                        trade.pnl_correction,
                        4,
                    )
                ),
            }
            for trade in trades
            if abs(
                trade.pnl_correction
            )
            > RECONCILIATION_TOLERANCE
        ],

        "trades": [
            asdict(
                trade
            )
            for trade in trades
        ],

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

    return report


# ============================================================
# MARKDOWN
# ============================================================

def money(
    value: Any,
) -> str:
    number = (
        safe_float(value)
        or 0.0
    )

    return f"{number:,.2f}"


def render_markdown(
    report: dict[str, Any],
) -> str:

    performance = report[
        "performance"
    ]

    accounting = report[
        "accounting"
    ]

    lines = [
        "# RAYMOND V2.8 Monthly Trade Audit",
        "",
        f"**Month:** {report['month']}",
        f"**Symbol:** {report['symbol']}",
        "**Mode:** PAPER / RESEARCH ONLY",
        "",
        "## Historical Accounting",
        "",
        "The historical P/L in this audit was independently "
        "recalculated from persisted trade execution fields.",
        "",
        "- Stored `Position.pnl` was NOT treated as authoritative.",
        "- XAUUSD contract size: **100 oz per lot**.",
        "- P/L uses entry price, exit price, direction and quantity.",
        "- Partial-close P/L is independently reconstructed when the "
        "partial-close price and quantity are available.",
        "- Final remaining-position P/L is independently reconstructed.",
        "",
        f"- Corrected partial-close P/L: "
        f"{money(accounting['partial_close_pnl'])}",
        f"- Corrected final-position P/L: "
        f"{money(accounting['final_remaining_position_pnl'])}",
        f"- **Corrected total P/L: "
        f"{money(accounting['total_trade_pnl'])}**",
        "",
        f"- Previously stored total P/L: "
        f"{money(accounting['stored_total_trade_pnl'])}",
        f"- Historical P/L correction: "
        f"{money(accounting['historical_pnl_correction'])}",
        f"- Trades requiring P/L correction: "
        f"{accounting['trades_with_pnl_correction']}",
        f"- Accounting reconciliation: "
        f"{accounting['accounting_reconciled']}",
        "",
        "## Performance",
        "",
        f"- Trades: {performance['total_trades']}",
        f"- Wins: {performance['winning_trades']}",
        f"- Losses: {performance['losing_trades']}",
        f"- Win rate: {performance['win_rate_pct']:.2f}%",
        f"- Total P/L: {money(performance['total_pnl'])}",
        f"- Gross profit: {money(performance['gross_profit'])}",
        f"- Gross loss: {money(performance['gross_loss'])}",
        f"- Profit factor: {performance['profit_factor']}",
        f"- Average trade: {money(performance['average_trade'])}",
        f"- Average win: {money(performance['average_win'])}",
        f"- Average loss: {money(performance['average_loss'])}",
        f"- Median trade: {money(performance['median_trade'])}",
        f"- Best trade: {money(performance['best_trade'])}",
        f"- Worst trade: {money(performance['worst_trade'])}",
        "",
        "## Direction Analysis",
        "",
        "| Direction | Trades | Wins | Losses | Win Rate | P/L | PF |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for row in report[
        "direction_analysis"
    ]:
        lines.append(
            "| "
            f"{row['group']} | "
            f"{row['total_trades']} | "
            f"{row['winning_trades']} | "
            f"{row['losing_trades']} | "
            f"{row['win_rate_pct']:.1f}% | "
            f"{money(row['total_pnl'])} | "
            f"{row['profit_factor']} |"
        )

    lines.extend(
        [
            "",
            "## Regime Analysis",
            "",
            "| Regime | Trades | Wins | Losses | Win Rate | P/L |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )

    for row in report[
        "regime_analysis"
    ]:
        lines.append(
            "| "
            f"{row['group']} | "
            f"{row['total_trades']} | "
            f"{row['winning_trades']} | "
            f"{row['losing_trades']} | "
            f"{row['win_rate_pct']:.1f}% | "
            f"{money(row['total_pnl'])} |"
        )

    lines.extend(
        [
            "",
            "## Setup Analysis",
            "",
            "| Setup | Trades | Wins | Losses | Win Rate | P/L |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )

    for row in report[
        "setup_analysis"
    ]:
        lines.append(
            "| "
            f"{row['group']} | "
            f"{row['total_trades']} | "
            f"{row['winning_trades']} | "
            f"{row['losing_trades']} | "
            f"{row['win_rate_pct']:.1f}% | "
            f"{money(row['total_pnl'])} |"
        )

    lines.extend(
        [
            "",
            "## Accounting Corrections",
            "",
        ]
    )

    corrections = report[
        "trades_with_corrections"
    ]

    if not corrections:
        lines.append(
            "No stored-vs-recalculated P/L differences "
            f"greater than ${RECONCILIATION_TOLERANCE:.2f}."
        )
    else:
        lines.extend(
            [
                "| Trade | Stored P/L | Corrected P/L | Correction |",
                "|---|---:|---:|---:|",
            ]
        )

        for row in corrections:
            lines.append(
                "| "
                f"{row['trade_id']} | "
                f"{money(row['stored_total_pnl'])} | "
                f"{money(row['corrected_total_pnl'])} | "
                f"{money(row['correction'])} |"
            )

    lines.extend(
        [
            "",
            "## Improvement Candidates",
            "",
        ]
    )

    candidates = report[
        "improvement_candidates"
    ]

    if not candidates:
        lines.append(
            "No statistically useful candidate "
            "was generated from this month's sample."
        )
    else:
        for index, candidate in enumerate(
            candidates,
            start=1,
        ):
            lines.extend(
                [
                    f"### {index}. "
                    f"{candidate['category']}",
                    "",
                    f"**Finding:** "
                    f"{candidate['finding']}",
                    "",
                    f"**Evidence:** "
                    f"{candidate['evidence']}",
                    "",
                    f"**Suggested test:** "
                    f"{candidate['suggested_test']}",
                    "",
                    f"**Priority:** "
                    f"{candidate['priority']}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Risk Normalization",
            "",
            "- Original 1R uses persisted `Position.risk_1r` when available.",
            "- Legacy positions fall back to entry price versus original stop.",
            "- XAUUSD monetary 1R uses 100 oz per lot.",
            "- R uses original quantity, not reduced quantity after a partial close.",
            "- Moving/current stop-loss does not redefine original 1R.",
            "",
            "## Accounting Rules",
            "",
            "- Historical P/L is independently recalculated.",
            "- Stored `Position.pnl` is comparison data, not authoritative audit data.",
            "- Stored `partial_close_pnl` is comparison data, not authoritative audit data.",
            "- Partial-close P/L is calculated from entry, partial-close price and partial quantity.",
            "- Final remaining P/L is calculated from entry, final exit price and reconstructed remaining quantity.",
            "- Total trade P/L equals corrected partial P/L plus corrected final P/L.",
            "- Corrected components are reconciled before the report is accepted.",
            "",
            "## Safety",
            "",
            "- Research-only.",
            "- Read-only.",
            "- No broker orders are created.",
            "- No positions are modified.",
            "- No active strategy parameters are changed.",
            "- No strategy candidate is automatically promoted.",
            "- Any improvement must be tested separately.",
            "- Unseen/holdout validation is required before promotion.",
            "",
        ]
    )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    requested_month = (
        sys.argv[1]
        if len(sys.argv) > 1
        else None
    )

    try:
        (
            start,
            end,
            month,
        ) = month_bounds(
            requested_month
        )

    except (
        ValueError,
        TypeError,
    ) as exc:
        print(
            f"ERROR: {exc}"
        )

        return 1

    print(
        "RAYMOND V2.8 MONTHLY TRADE AUDITOR"
    )

    print(
        "VERSION: 2.0"
    )

    print(
        "RESEARCH ONLY: YES"
    )

    print(
        "READ ONLY: YES"
    )

    print(
        "LIVE TRADING CHANGED: NO"
    )

    print(
        f"SYMBOL: {DEFAULT_SYMBOL}"
    )

    print(
        f"MONTH: {month}"
    )

    print(
        "XAUUSD CONTRACT SIZE: "
        f"{XAUUSD_CONTRACT_SIZE}"
    )

    print(
        "HISTORICAL P/L SOURCE: "
        "INDEPENDENT RAW PRICE RECALCULATION"
    )

    print(
        "STORED Position.pnl AUTHORITATIVE: NO"
    )

    print(
        "Loading closed paper positions..."
    )

    trades = load_closed_positions(
        start=start,
        end=end,
        symbol=DEFAULT_SYMBOL,
    )

    print(
        f"Closed positions found: "
        f"{len(trades)}"
    )

    report = build_report(
        trades=trades,
        month=month,
        symbol=DEFAULT_SYMBOL,
    )

    output_dir = (
        OUTPUT_DIR
        / month
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        output_dir
        / "audit.json"
    )

    md_path = (
        output_dir
        / "audit.md"
    )

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    md_path.write_text(
        render_markdown(
            report
        ),
        encoding="utf-8",
    )

    performance = report[
        "performance"
    ]

    accounting = report[
        "accounting"
    ]

    print("")
    print(
        "AUDIT COMPLETE"
    )

    print(
        f"Trades: "
        f"{performance['total_trades']}"
    )

    print(
        f"Wins: "
        f"{performance['winning_trades']}"
    )

    print(
        f"Losses: "
        f"{performance['losing_trades']}"
    )

    print(
        f"Win rate: "
        f"{performance['win_rate_pct']:.2f}%"
    )

    print(
        f"CORRECTED TOTAL P/L: "
        f"{money(performance['total_pnl'])}"
    )

    print(
        f"Stored historical P/L: "
        f"{money(accounting['stored_total_trade_pnl'])}"
    )

    print(
        f"HISTORICAL P/L CORRECTION: "
        f"{money(accounting['historical_pnl_correction'])}"
    )

    print(
        f"Corrected partial-close P/L: "
        f"{money(accounting['partial_close_pnl'])}"
    )

    print(
        f"Corrected final-position P/L: "
        f"{money(accounting['final_remaining_position_pnl'])}"
    )

    print(
        f"Trades with P/L corrections: "
        f"{accounting['trades_with_pnl_correction']}"
    )

    print(
        f"Accounting reconciled: "
        f"{accounting['accounting_reconciled']}"
    )

    print(
        f"Accounting warnings: "
        f"{accounting['trades_with_accounting_warning']}"
    )

    print(
        f"Profit factor: "
        f"{performance['profit_factor']}"
    )

    print(
        "Improvement candidates: "
        f"{len(report['improvement_candidates'])}"
    )

    print("")
    print(
        f"JSON: {json_path}"
    )

    print(
        f"REPORT: {md_path}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
