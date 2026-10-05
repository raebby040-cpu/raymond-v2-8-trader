"""
RAYMOND V2.8 - MONTHLY TRADE AUDITOR

Phase 1 of the Strategy Auditor & Evolution Engine.

PURPOSE
-------
Analyze completed PAPER positions at the end of each month and
identify recurring reasons for losses and possible strategy
improvements.

IMPORTANT SAFETY RULES
----------------------
- PAPER/RESEARCH analysis only.
- Never sends broker orders.
- Never modifies positions.
- Never modifies active strategy parameters.
- Never automatically promotes a strategy candidate.
- Improvement candidates are recommendations for later backtesting.
- Holdout validation is required before any strategy promotion.

DATA SOURCE
-----------
The authoritative persistent Position table is used because it
contains the richest trade lifecycle information, including:

- entry / exit
- original SL
- TP
- P/L
- regime
- setup
- technical score
- confidence
- trade thesis
- break-even state
- partial-close state
- trailing state
- maximum profit
- maximum drawdown
- original 1R risk distance
- cumulative partial-close P/L

ACCOUNTING MODEL
----------------
For a position that has partial closes:

    total trade P/L =
        cumulative partial-close realized P/L
        +
        final remaining-position P/L

Example:

    1.00 XAUUSD lot BUY @ 4300

    close 0.50 @ 4310
        = +$500

    remaining 0.50 @ 4320
        = +$1,000

    total trade P/L
        = +$1,500

XAUUSD CONTRACT SIZE
--------------------
RAYMOND V2.8 uses:

    1.00 XAUUSD lot = 100 oz

Therefore:

    P/L =
        price movement × quantity × 100

R NORMALIZATION
---------------
Position.risk_1r is the authoritative original PRICE-DISTANCE
value representing 1R.

For XAUUSD:

    monetary 1R =
        risk_1r × original_quantity × 100

The auditor therefore uses persisted Position.risk_1r first.

For older positions where risk_1r was not persisted, the auditor
falls back to:

    abs(entry_price - initial_stop_loss)

This avoids accidentally deriving R from a moving/current stop-loss.

USAGE
-----
From repository root:

    python scripts/monthly_trade_audit.py

Optional:

    python scripts/monthly_trade_audit.py 2026-09

The optional argument audits a specific calendar month.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter, defaultdict
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

# Standard XAUUSD contract size used by RAYMOND V2.8.
XAUUSD_CONTRACT_SIZE = 100.0

OUTPUT_DIR = (
    Path("backtest_results")
    / "monthly_trade_audits"
)


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

    # Total economic P/L:
    #
    # cumulative partial-close P/L
    # +
    # final remaining-position P/L
    pnl: float

    # Explicit accounting components.
    partial_close_pnl: float
    final_position_pnl: float
    total_trade_pnl: float

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


@dataclass
class Candidate:
    category: str
    finding: str
    evidence: str
    suggested_test: str
    priority: str = "research"


# ============================================================
# HELPERS
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

    return text if text else default


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
        (len(ordered) - 1) * p
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


def safe_mean(
    values: Iterable[float],
) -> float | None:
    values = list(values)

    if not values:
        return None

    return statistics.mean(values)


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


def month_bounds(
    month_text: str | None,
) -> tuple[datetime, datetime, str]:
    """
    Return UTC month start and exclusive next-month boundary.
    """

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

    return (
        start,
        end,
        label,
    )


# ============================================================
# ACCOUNTING HELPERS
# ============================================================


def position_partial_close_pnl(
    position: Position,
) -> float:
    """
    Return cumulative realized P/L from partial closes.

    New accounting semantics:
        partial_close_pnl is cumulative.

    Legacy rows without this field/data safely return 0.
    """

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


def position_final_pnl(
    position: Position,
) -> float:
    """
    Return P/L belonging to the final/current position quantity.

    For a closed position this represents the P/L of the quantity
    that remained after any partial closes.
    """

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


def position_total_trade_pnl(
    position: Position,
) -> float:
    """
    Calculate complete economic P/L for one persisted position.

        total =
            cumulative partial-close P/L
            +
            final remaining-position P/L
    """

    partial_pnl = (
        position_partial_close_pnl(
            position
        )
    )

    final_pnl = (
        position_final_pnl(
            position
        )
    )

    return (
        partial_pnl
        + final_pnl
    )


# ============================================================
# POSITION -> AUDIT RECORD
# ============================================================


def position_to_trade(
    position: Position,
) -> TradeView:
    entry = (
        safe_float(
            position.entry_price
        )
        or 0.0
    )

    exit_price = safe_float(
        position.current_price
    )

    initial_sl = safe_float(
        position.initial_stop_loss
    )

    tp = safe_float(
        position.take_profit_1
    )

    # --------------------------------------------------------
    # CORRECTED P&L ACCOUNTING
    # --------------------------------------------------------
    #
    # position.pnl represents the final/current remaining
    # quantity.
    #
    # partial_close_pnl represents cumulative realized P/L
    # from partial closes.
    #
    # Total trade P/L must include both.
    #

    partial_close_pnl = (
        position_partial_close_pnl(
            position
        )
    )

    final_position_pnl = (
        position_final_pnl(
            position
        )
    )

    total_trade_pnl = (
        partial_close_pnl
        + final_position_pnl
    )

    # TradeView.pnl intentionally mirrors the COMPLETE
    # economic trade result.
    pnl = total_trade_pnl

    quantity = (
        safe_float(
            position.original_quantity
        )
        or safe_float(
            position.quantity
        )
        or 0.0
    )

    # --------------------------------------------------------
    # AUTHORITATIVE ORIGINAL 1R
    # --------------------------------------------------------
    #
    # risk_1r is intentionally stored as the original PRICE
    # DISTANCE between entry and original stop.
    #
    # It must be preferred over reconstructing risk from a
    # potentially changed/moved stop-loss.
    #
    # Older positions may not contain risk_1r, so the original
    # entry/SL calculation remains a compatibility fallback.

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
            and entry > 0
        ):
            risk_distance = abs(
                entry - initial_sl
            )

    max_profit = (
        safe_float(
            position.max_profit
        )
        or 0.0
    )

    max_drawdown = (
        safe_float(
            position.max_drawdown
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
        # XAUUSD:
        #
        #   1R monetary value =
        #       risk_1r × original quantity × 100
        #
        # risk_1r is PRICE DISTANCE, not a dollar amount.
        #
        # max_profit and max_drawdown are monetary values.

        initial_r_value = (
            risk_distance
            * quantity
            * XAUUSD_CONTRACT_SIZE
        )

        if initial_r_value > 0:
            max_profit_r = (
                max_profit
                / initial_r_value
            )

            max_drawdown_r = (
                max_drawdown
                / initial_r_value
            )

    # --------------------------------------------------------
    # OUTCOME
    # --------------------------------------------------------

    outcome = "BREAKEVEN"

    if pnl > 0:
        outcome = "WIN"
    elif pnl < 0:
        outcome = "LOSS"

    return TradeView(
        trade_id=safe_text(
            position.trade_id,
            safe_text(
                position.position_id
            ),
        ),
        symbol=safe_text(
            position.symbol,
            DEFAULT_SYMBOL,
        ),
        direction=enum_value(
            position.direction
        ).upper(),
        entry_price=entry,
        exit_price=exit_price,
        pnl=pnl,
        partial_close_pnl=partial_close_pnl,
        final_position_pnl=final_position_pnl,
        total_trade_pnl=total_trade_pnl,
        quantity=quantity,
        initial_stop_loss=initial_sl,
        take_profit=tp,
        regime=safe_text(
            position.regime
        ),
        setup=safe_text(
            position.setup
        ),
        technical_score=safe_float(
            position.technical_score
        ),
        confidence=safe_float(
            position.confidence
        ),
        trade_thesis=safe_text(
            position.trade_thesis,
            "not recorded",
        ),
        break_even_applied=bool(
            position.break_even_applied
        ),
        partial_close_applied=bool(
            position.partial_close_applied
        ),
        trailing_active=bool(
            position.trailing_active
        ),
        management_status=safe_text(
            position.management_status
        ),
        last_management_action=safe_text(
            position.last_management_action
        ),
        max_profit=max_profit,
        max_drawdown=max_drawdown,
        opened_at=iso(
            position.opened_at
        ),
        closed_at=iso(
            position.closed_at
        ),
        initial_risk_distance=risk_distance,
        max_profit_r=max_profit_r,
        max_drawdown_r=max_drawdown_r,
        outcome=outcome,
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
    Load closed persistent positions for the requested month.

    Only CLOSED positions are included in the monthly trade audit.
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
            position_to_trade(row)
            for row in rows
        ]

    finally:
        db.close()


# ============================================================
# BASIC PERFORMANCE
# ============================================================


def performance_summary(
    trades: list[TradeView],
) -> dict[str, Any]:
    """
    Calculate performance from COMPLETE economic trade P/L.

    This means partial-close realized P/L is already included in
    TradeView.pnl.
    """

    pnls = [
        trade.total_trade_pnl
        for trade in trades
    ]

    wins = [
        value
        for value in pnls
        if value > 0
    ]

    losses = [
        value
        for value in pnls
        if value < 0
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
# GROUP ANALYSIS
# ============================================================


def group_performance(
    trades: list[TradeView],
    attribute: str,
) -> list[dict[str, Any]]:
    groups: dict[
        str,
        list[TradeView],
    ] = defaultdict(list)

    for trade in trades:
        value = getattr(
            trade,
            attribute,
        )

        if isinstance(
            value,
            float,
        ):
            if not math.isfinite(
                value
            ):
                key = "unknown"
            else:
                key = str(value)
        else:
            key = safe_text(
                value
            )

        groups[key].append(
            trade
        )

    result = []

    for key, rows in groups.items():
        performance = (
            performance_summary(
                rows
            )
        )

        result.append(
            {
                "group": key,
                **performance,
            }
        )

    result.sort(
        key=lambda row: (
            row["total_pnl"]
            if row["total_pnl"]
            is not None
            else 0.0
        )
    )

    return result


def score_bucket(
    score: float | None,
) -> str:
    if score is None:
        return "unknown"

    if score < 60:
        return "<60"

    if score < 65:
        return "60-64"

    if score < 70:
        return "65-69"

    if score < 75:
        return "70-74"

    return "75+"


def confidence_bucket(
    confidence: float | None,
) -> str:
    if confidence is None:
        return "unknown"

    if confidence < 50:
        return "<50"

    if confidence < 60:
        return "50-59"

    if confidence < 70:
        return "60-69"

    if confidence < 80:
        return "70-79"

    return "80+"


def bucket_analysis(
    trades: list[TradeView],
) -> dict[str, Any]:
    score_groups = defaultdict(list)
    confidence_groups = defaultdict(list)

    for trade in trades:
        score_groups[
            score_bucket(
                trade.technical_score
            )
        ].append(trade)

        confidence_groups[
            confidence_bucket(
                trade.confidence
            )
        ].append(trade)

    return {
        "technical_score": [
            {
                "bucket": key,
                **performance_summary(
                    rows
                ),
            }
            for key, rows
            in sorted(
                score_groups.items()
            )
        ],
        "confidence": [
            {
                "bucket": key,
                **performance_summary(
                    rows
                ),
            }
            for key, rows
            in sorted(
                confidence_groups.items()
            )
        ],
    }


# ============================================================
# LOSS PATTERN ANALYSIS
# ============================================================


def loss_patterns(
    trades: list[TradeView],
) -> dict[str, Any]:
    losses = [
        trade
        for trade in trades
        if trade.outcome == "LOSS"
    ]

    if not losses:
        return {
            "loss_count": 0,
            "patterns": {},
        }

    patterns: dict[
        str,
        dict[str, Any],
    ] = {}

    attributes = [
        "direction",
        "regime",
        "setup",
        "management_status",
        "last_management_action",
    ]

    for attribute in attributes:
        counter = Counter(
            safe_text(
                getattr(
                    trade,
                    attribute,
                )
            )
            for trade in losses
        )

        patterns[attribute] = {
            key: value
            for key, value
            in counter.most_common()
        }

    return {
        "loss_count": len(
            losses
        ),
        "patterns": patterns,
    }


# ============================================================
# MANAGEMENT ANALYSIS
# ============================================================


def management_analysis(
    trades: list[TradeView],
) -> dict[str, Any]:
    result = {}

    for name, predicate in {
        "break_even_applied": (
            lambda t:
            t.break_even_applied
        ),
        "partial_close_applied": (
            lambda t:
            t.partial_close_applied
        ),
        "trailing_active": (
            lambda t:
            t.trailing_active
        ),
    }.items():

        selected = [
            trade
            for trade in trades
            if predicate(trade)
        ]

        not_selected = [
            trade
            for trade in trades
            if not predicate(trade)
        ]

        result[name] = {
            "applied": (
                performance_summary(
                    selected
                )
            ),
            "not_applied": (
                performance_summary(
                    not_selected
                )
            ),
        }

    return result


# ============================================================
# MFE / MAE STYLE ANALYSIS
# ============================================================


def excursion_analysis(
    trades: list[TradeView],
) -> dict[str, Any]:

    losers = [
        trade
        for trade in trades
        if trade.outcome == "LOSS"
    ]

    winners = [
        trade
        for trade in trades
        if trade.outcome == "WIN"
    ]

    loser_max_profit = [
        trade.max_profit_r
        for trade in losers
        if trade.max_profit_r is not None
    ]

    winner_max_drawdown = [
        trade.max_drawdown_r
        for trade in winners
        if trade.max_drawdown_r is not None
    ]

    profitable_first_count = sum(
        1
        for value in loser_max_profit
        if value > 0
    )

    return {
        "losing_trades_that_were_profitable_first": {
            "count": profitable_first_count,
            "percentage_of_losses": round(
                percentage(
                    profitable_first_count,
                    len(loser_max_profit),
                ),
                2,
            )
            if loser_max_profit
            else 0.0,
            "average_max_profit_r": round(
                safe_mean(
                    loser_max_profit
                ) or 0.0,
                4,
            ),
            "median_max_profit_r": round(
                statistics.median(
                    loser_max_profit
                )
                if loser_max_profit
                else 0.0,
                4,
            ),
        },
        "winning_trades_that_went_negative_first": {
            "count": sum(
                1
                for value in winner_max_drawdown
                if value < 0
            ),
            "average_max_drawdown_r": round(
                safe_mean(
                    winner_max_drawdown
                ) or 0.0,
                4,
            ),
        },
    }


# ============================================================
# AUTOMATIC IMPROVEMENT CANDIDATES
# ============================================================


def generate_candidates(
    trades: list[TradeView],
) -> list[Candidate]:

    candidates: list[
        Candidate
    ] = []

    if len(trades) < 8:
        return candidates

    losses = [
        trade
        for trade in trades
        if trade.outcome == "LOSS"
    ]

    # --------------------------------------------------------
    # LOW TECHNICAL SCORE
    # --------------------------------------------------------

    scored = [
        trade
        for trade in trades
        if trade.technical_score
        is not None
    ]

    low_score = [
        trade
        for trade in scored
        if trade.technical_score < 65
    ]

    high_score = [
        trade
        for trade in scored
        if trade.technical_score >= 65
    ]

    if (
        len(low_score) >= 4
        and len(high_score) >= 4
    ):

        low_wr = percentage(
            sum(
                1
                for t in low_score
                if t.pnl > 0
            ),
            len(low_score),
        )

        high_wr = percentage(
            sum(
                1
                for t in high_score
                if t.pnl > 0
            ),
            len(high_score),
        )

        if (
            low_wr + 15
            < high_wr
        ):
            candidates.append(
                Candidate(
                    category=(
                        "signal_selectivity"
                    ),
                    finding=(
                        "Lower technical-score "
                        "trades underperformed "
                        "higher-score trades."
                    ),
                    evidence=(
                        f"Score <65 win rate "
                        f"{low_wr:.1f}% vs "
                        f"score >=65 win rate "
                        f"{high_wr:.1f}%."
                    ),
                    suggested_test=(
                        "Backtest minimum "
                        "technical score "
                        "thresholds around "
                        "65-75."
                    ),
                    priority="high",
                )
            )

    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------

    direction_groups = {
        "BUY": [
            t
            for t in trades
            if t.direction == "BUY"
        ],
        "SELL": [
            t
            for t in trades
            if t.direction == "SELL"
        ],
    }

    for direction, rows in (
        direction_groups.items()
    ):

        if len(rows) < 5:
            continue

        wr = percentage(
            sum(
                1
                for t in rows
                if t.pnl > 0
            ),
            len(rows),
        )

        if wr < 25:
            candidates.append(
                Candidate(
                    category=(
                        "direction_filter"
                    ),
                    finding=(
                        f"{direction} trades "
                        "performed poorly "
                        "during the audited month."
                    ),
                    evidence=(
                        f"{len(rows)} trades, "
                        f"{wr:.1f}% win rate, "
                        f"{sum(t.pnl for t in rows):.2f} "
                        "total P/L."
                    ),
                    suggested_test=(
                        f"Test stronger "
                        f"{direction} confirmation "
                        "or stricter regime "
                        "requirements."
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

    for regime, rows in (
        regime_groups.items()
    ):

        if len(rows) < 5:
            continue

        pnl = sum(
            t.pnl
            for t in rows
        )

        wr = percentage(
            sum(
                1
                for t in rows
                if t.pnl > 0
            ),
            len(rows),
        )

        if pnl < 0 and wr < 35:
            candidates.append(
                Candidate(
                    category=(
                        "market_regime"
                    ),
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
    # PROFITABLE-FIRST LOSSES
    # --------------------------------------------------------

    profitable_first = [
        trade
        for trade in losses
        if (
            trade.max_profit_r
            is not None
            and trade.max_profit_r
            >= 0.5
        )
    ]

    if len(profitable_first) >= 3:
        candidates.append(
            Candidate(
                category=(
                    "profit_protection"
                ),
                finding=(
                    "Several losing trades "
                    "became meaningfully "
                    "profitable before reversing."
                ),
                evidence=(
                    f"{len(profitable_first)} "
                    "losing trades reached "
                    "at least approximately "
                    "+0.5R before closing."
                ),
                suggested_test=(
                    "Backtest earlier "
                    "break-even, partial-profit, "
                    "or trailing protection."
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
            trade.confidence
            is not None
            and trade.confidence >= 70
        )
    ]

    if len(high_confidence) >= 4:
        candidates.append(
            Candidate(
                category=(
                    "confidence_calibration"
                ),
                finding=(
                    "High-confidence signals "
                    "still produced repeated losses."
                ),
                evidence=(
                    f"{len(high_confidence)} "
                    "losses had confidence "
                    ">=70."
                ),
                suggested_test=(
                    "Investigate whether "
                    "confidence is properly "
                    "calibrated against actual "
                    "outcomes before using it "
                    "as a stronger entry filter."
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
    """
    Provide an explicit accounting reconciliation for the audit.

    This makes it possible to see whether the audited month contains
    partial-close activity and exactly how much P/L came from it.
    """

    cumulative_partial_pnl = sum(
        trade.partial_close_pnl
        for trade in trades
    )

    final_position_pnl = sum(
        trade.final_position_pnl
        for trade in trades
    )

    total_trade_pnl = sum(
        trade.total_trade_pnl
        for trade in trades
    )

    reconstructed_total = (
        cumulative_partial_pnl
        + final_position_pnl
    )

    reconciliation_difference = (
        total_trade_pnl
        - reconstructed_total
    )

    partial_close_trades = [
        trade
        for trade in trades
        if (
            trade.partial_close_applied
            or abs(
                trade.partial_close_pnl
            ) > 1e-12
        )
    ]

    return {
        "partial_close_pnl": round(
            cumulative_partial_pnl,
            4,
        ),
        "final_remaining_position_pnl": round(
            final_position_pnl,
            4,
        ),
        "total_trade_pnl": round(
            total_trade_pnl,
            4,
        ),
        "reconstructed_total_pnl": round(
            reconstructed_total,
            4,
        ),
        "reconciliation_difference": round(
            reconciliation_difference,
            10,
        ),
        "partial_close_trade_count": len(
            partial_close_trades
        ),
        "accounting_reconciled": (
            abs(
                reconciliation_difference
            )
            < 1e-8
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

    losses = [
        trade
        for trade in trades
        if trade.outcome == "LOSS"
    ]

    accounting = (
        accounting_summary(
            trades
        )
    )

    report = {
        "report_type": (
            "RAYMOND_MONTHLY_TRADE_AUDIT"
        ),
        "version": "1.2",
        "research_only": True,
        "live_trading_changed": False,
        "symbol": symbol,
        "month": month,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "accounting": accounting,

        "risk_normalization": {
            "method": "persisted_risk_1r",
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
                "Position.risk_1r is treated as "
                "the original price-distance value "
                "for 1R. For XAUUSD, monetary 1R "
                "equals price distance × original "
                "quantity × 100."
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
            asdict(candidate)
            for candidate
            in generate_candidates(
                trades
            )
        ],

        "loss_trade_ids": [
            trade.trade_id
            for trade in losses
        ],

        "trades": [
            asdict(trade)
            for trade in trades
        ],
    }

    return report


# ============================================================
# MARKDOWN RENDERING
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

    p = report[
        "performance"
    ]

    a = report[
        "accounting"
    ]

    lines = [
        "# RAYMOND V2.8 Monthly Trade Audit",
        "",
        f"**Month:** {report['month']}",
        f"**Symbol:** {report['symbol']}",
        "**Mode:** PAPER / RESEARCH ONLY",
        "",
        "## Performance",
        "",
        f"- Trades: {p['total_trades']}",
        f"- Wins: {p['winning_trades']}",
        f"- Losses: {p['losing_trades']}",
        f"- Win rate: {p['win_rate_pct']:.2f}%",
        f"- Total P/L: {money(p['total_pnl'])}",
        f"- Profit factor: {p['profit_factor']}",
        f"- Average trade: {money(p['average_trade'])}",
        f"- Average win: {money(p['average_win'])}",
        f"- Average loss: {money(p['average_loss'])}",
        f"- Best trade: {money(p['best_trade'])}",
        f"- Worst trade: {money(p['worst_trade'])}",
        "",
        "## Accounting Reconciliation",
        "",
        f"- Partial-close realized P/L: "
        f"{money(a['partial_close_pnl'])}",
        f"- Final remaining-position P/L: "
        f"{money(a['final_remaining_position_pnl'])}",
        f"- Total trade P/L: "
        f"{money(a['total_trade_pnl'])}",
        f"- Reconstructed total P/L: "
        f"{money(a['reconstructed_total_pnl'])}",
        f"- Reconciliation difference: "
        f"{money(a['reconciliation_difference'])}",
        f"- Partial-close trades: "
        f"{a['partial_close_trade_count']}",
        f"- Accounting reconciled: "
        f"{a['accounting_reconciled']}",
        "",
        "## Direction",
        "",
        "| Direction | Trades | Win Rate | P/L | PF |",
        "|---|---:|---:|---:|---:|",
    ]

    for row in report[
        "direction_analysis"
    ]:
        lines.append(
            "| "
            f"{row['group']} | "
            f"{row['total_trades']} | "
            f"{row['win_rate_pct']:.1f}% | "
            f"{money(row['total_pnl'])} | "
            f"{row['profit_factor']} |"
        )

    lines.extend(
        [
            "",
            "## Regime Analysis",
            "",
            "| Regime | Trades | Win Rate | P/L |",
            "|---|---:|---:|---:|",
        ]
    )

    for row in report[
        "regime_analysis"
    ]:
        lines.append(
            "| "
            f"{row['group']} | "
            f"{row['total_trades']} | "
            f"{row['win_rate_pct']:.1f}% | "
            f"{money(row['total_pnl'])} |"
        )

    lines.extend(
        [
            "",
            "## Setup Analysis",
            "",
            "| Setup | Trades | Win Rate | P/L |",
            "|---|---:|---:|---:|",
        ]
    )

    for row in report[
        "setup_analysis"
    ]:
        lines.append(
            "| "
            f"{row['group']} | "
            f"{row['total_trades']} | "
            f"{row['win_rate_pct']:.1f}% | "
            f"{money(row['total_pnl'])} |"
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
            "No statistically useful "
            "candidate was generated from "
            "this month's sample."
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
            "- Original 1R uses persisted Position.risk_1r when available.",
            "- Legacy positions fall back to entry price vs original stop-loss.",
            "- XAUUSD monetary 1R uses a 100-unit contract size.",
            "- R calculations use original quantity, not reduced quantity after a partial close.",
            "- R calculations do not use a moving/current stop-loss.",
            "",
            "## Accounting Rules",
            "",
            "- Partial-close P/L is treated as realized P/L.",
            "- position.partial_close_pnl is interpreted as cumulative partial-close P/L.",
            "- position.pnl represents the final/current remaining-position P/L.",
            "- Total economic trade P/L equals partial-close P/L plus final remaining-position P/L.",
            "- Partial-close P/L is never counted twice.",
            "",
            "## Safety",
            "",
            "- This report does not change the active strategy.",
            "- No broker orders are created.",
            "- No positions are modified.",
            "- Candidates must be backtested before consideration.",
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

    except ValueError as exc:
        print(
            f"ERROR: {exc}"
        )

        return 1

    print(
        "RAYMOND V2.8 MONTHLY TRADE AUDITOR"
    )

    print(
        "RESEARCH ONLY: YES"
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
        "ACCOUNTING: "
        "PARTIAL REALIZED PNL + FINAL REMAINING PNL"
    )

    print(
        "RISK NORMALIZATION: "
        "PERSISTED risk_1r FIRST"
    )

    print(
        "XAUUSD CONTRACT SIZE: "
        f"{XAUUSD_CONTRACT_SIZE}"
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

    print("")
    print(
        "AUDIT COMPLETE"
    )

    print(
        f"Trades: "
        f"{report['performance']['total_trades']}"
    )

    print(
        f"Win rate: "
        f"{report['performance']['win_rate_pct']:.2f}%"
    )

    print(
        f"Total P/L: "
        f"{money(report['performance']['total_pnl'])}"
    )

    print(
        f"Partial-close P/L: "
        f"{money(report['accounting']['partial_close_pnl'])}"
    )

    print(
        f"Final-position P/L: "
        f"{money(report['accounting']['final_remaining_position_pnl'])}"
    )

    print(
        f"Accounting reconciled: "
        f"{report['accounting']['accounting_reconciled']}"
    )

    print(
        f"Profit factor: "
        f"{report['performance']['profit_factor']}"
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
