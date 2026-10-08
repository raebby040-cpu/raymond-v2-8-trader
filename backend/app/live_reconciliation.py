"""
RAYMOND v2.8 - Live Position Reconciliation

STEP 17.5

Compares Raymond's persistent live-position records with the
actual positions reported by MetaTrader 5.

Purpose:

    Raymond state
          |
          v
    Live Reconciliation
          |
          +--> MT5 actual positions
          |
          +--> Detect missing positions
          +--> Detect orphan positions
          +--> Detect volume mismatch
          +--> Detect side mismatch
          +--> Detect SL mismatch
          +--> Detect TP mismatch
          |
          v
    Safe / Mismatch

IMPORTANT:

This module NEVER places orders.

This module NEVER modifies broker positions.

A mismatch is fail-closed for NEW live orders.

The reconciliation state is intentionally held in process
memory for now. A future production-hardening step should
centralize this state in PostgreSQL/Redis so multiple Render
instances share exactly one reconciliation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .mt5_service import (
        MT5ServiceError,
        mt5_service,
    )
except ImportError:
    from mt5_service import (
        MT5ServiceError,
        mt5_service,
    )


# ============================================================
# CONSTANTS
# ============================================================

DEFAULT_RAYMOND_MAGIC = 28001703

PRICE_TOLERANCE = 1e-6

VOLUME_TOLERANCE = 1e-8


# ============================================================
# ERRORS
# ============================================================

class ReconciliationError(RuntimeError):
    """
    Raised when reconciliation cannot safely determine the
    actual broker state.
    """


# ============================================================
# RECONCILIATION RESULT
# ============================================================

@dataclass(frozen=True)
class ReconciliationResult:
    status: str

    safe_for_new_live_orders: bool

    broker_position_count: int

    raymond_position_count: int

    matched_count: int

    mismatch_count: int

    orphan_count: int

    missing_count: int

    mismatches: list[dict]

    timestamp: str


# ============================================================
# PROCESS SAFETY STATE
# ============================================================

_state_lock = Lock()

_reconciliation_safe = False

_last_result: Optional[ReconciliationResult] = None

_last_error: Optional[str] = None

_last_run_at: Optional[datetime] = None


# ============================================================
# REQUEST MODELS
# ============================================================

class ReconciliationRequest(BaseModel):
    symbol: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    magic: int = Field(
        default=DEFAULT_RAYMOND_MAGIC,
        ge=0,
    )


# ============================================================
# HELPERS
# ============================================================

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _position_ticket(position: dict) -> Optional[int]:
    value = position.get("ticket")

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _position_symbol(position: dict) -> str:
    return str(
        position.get("symbol", "")
    ).strip()


def _position_magic(position: dict) -> Optional[int]:
    value = position.get("magic")

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _position_side(position: dict) -> Optional[str]:
    """
    MT5 position types:

        BUY  = 0
        SELL = 1
    """

    value = position.get("type")

    try:
        value = int(value)
    except (TypeError, ValueError):
        return None

    if value == 0:
        return "BUY"

    if value == 1:
        return "SELL"

    return None


def _position_volume(position: dict) -> Optional[float]:
    value = position.get("volume")

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_price(
    position: dict,
) -> Optional[float]:
    value = position.get("price_open")

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_sl(
    position: dict,
) -> Optional[float]:
    value = position.get("sl")

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_tp(
    position: dict,
) -> Optional[float]:
    value = position.get("tp")

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_float(
    left: Optional[float],
    right: Optional[float],
    tolerance: float,
) -> bool:
    if left is None or right is None:
        return left is None and right is None

    return abs(
        float(left) - float(right)
    ) <= tolerance


def _safe_position_summary(
    position: dict,
) -> dict:
    """
    Serialize only reconciliation-safe fields.

    No credentials are included.
    """

    return {
        "ticket": _position_ticket(position),
        "symbol": _position_symbol(position),
        "magic": _position_magic(position),
        "side": _position_side(position),
        "volume": _position_volume(position),
        "price_open": _position_price(position),
        "sl": _position_sl(position),
        "tp": _position_tp(position),
    }


# ============================================================
# RAYMOND LIVE POSITION REGISTRY
# ============================================================
#
# This registry is the bridge between the live execution gateway
# and reconciliation.
#
# It deliberately contains only the information required to
# verify a broker position.
#
# It is process-local for this stage.
#
# Production hardening will move this registry into the
# authoritative PostgreSQL database.
# ============================================================

_registry_lock = Lock()

_live_registry: dict[str, dict] = {}


def register_live_position(
    *,
    client_order_id: str,
    symbol: str,
    side: str,
    volume: float,
    stop_loss: float,
    take_profit: float,
    position_ticket: Optional[int],
    magic: int = DEFAULT_RAYMOND_MAGIC,
) -> dict:
    """
    Register a successfully verified Raymond live position.

    This does NOT modify MT5.

    It only records what Raymond believes it opened.
    """

    if not client_order_id:
        raise ReconciliationError(
            "client_order_id is required."
        )

    if not symbol:
        raise ReconciliationError(
            "symbol is required."
        )

    normalized_side = str(
        side
    ).upper().strip()

    if normalized_side not in {
        "BUY",
        "SELL",
    }:
        raise ReconciliationError(
            "side must be BUY or SELL."
        )

    if volume <= 0:
        raise ReconciliationError(
            "volume must be greater than zero."
        )

    record = {
        "client_order_id": client_order_id,
        "symbol": symbol,
        "side": normalized_side,
        "volume": float(volume),
        "stop_loss": float(stop_loss),
        "take_profit": float(take_profit),
        "position_ticket": (
            int(position_ticket)
            if position_ticket is not None
            else None
        ),
        "magic": int(magic),
        "registered_at": _utc_now().isoformat(),
    }

    with _registry_lock:
        _live_registry[
            client_order_id
        ] = record

    return dict(record)


def unregister_live_position(
    client_order_id: str,
) -> bool:
    """
    Remove a live-position record after a confirmed close.
    """

    with _registry_lock:
        return (
            _live_registry.pop(
                client_order_id,
                None,
            )
            is not None
        )


def registered_live_positions() -> list[dict]:
    with _registry_lock:
        return [
            dict(item)
            for item in _live_registry.values()
        ]


# ============================================================
# BROKER POSITION FILTER
# ============================================================

def _raymond_broker_positions(
    positions: list[dict],
    magic: int,
    symbol: Optional[str] = None,
) -> list[dict]:
    result = []

    normalized_symbol = (
        symbol.strip()
        if symbol
        else None
    )

    for position in positions:

        position_magic = _position_magic(
            position
        )

        if position_magic != magic:
            continue

        position_symbol = _position_symbol(
            position
        )

        if (
            normalized_symbol
            and position_symbol
            != normalized_symbol
        ):
            continue

        result.append(position)

    return result


# ============================================================
# POSITION MATCHING
# ============================================================

def _match_registered_position(
    record: dict,
    broker_positions: list[dict],
) -> Optional[dict]:
    """
    Prefer exact MT5 position-ticket matching.

    If a ticket is unavailable, fall back to:

        symbol + side + volume

    This is intentionally conservative.
    """

    expected_ticket = record.get(
        "position_ticket"
    )

    if expected_ticket is not None:

        for position in broker_positions:

            ticket = _position_ticket(
                position
            )

            if ticket == int(
                expected_ticket
            ):
                return position

        return None

    expected_symbol = str(
        record.get(
            "symbol",
            "",
        )
    )

    expected_side = str(
        record.get(
            "side",
            "",
        )
    ).upper()

    expected_volume = float(
        record.get(
            "volume",
            0.0,
        )
    )

    for position in broker_positions:

        if (
            _position_symbol(position)
            != expected_symbol
        ):
            continue

        if (
            _position_side(position)
            != expected_side
        ):
            continue

        broker_volume = _position_volume(
            position
        )

        if not _same_float(
            broker_volume,
            expected_volume,
            VOLUME_TOLERANCE,
        ):
            continue

        return position

    return None


# ============================================================
# SINGLE POSITION VALIDATION
# ============================================================

def _validate_match(
    record: dict,
    broker_position: dict,
) -> list[dict]:

    mismatches = []

    expected_symbol = str(
        record.get(
            "symbol",
            "",
        )
    )

    actual_symbol = _position_symbol(
        broker_position
    )

    if expected_symbol != actual_symbol:

        mismatches.append(
            {
                "type": "symbol_mismatch",
                "expected": expected_symbol,
                "actual": actual_symbol,
            }
        )

    expected_side = str(
        record.get(
            "side",
            "",
        )
    ).upper()

    actual_side = _position_side(
        broker_position
    )

    if expected_side != actual_side:

        mismatches.append(
            {
                "type": "side_mismatch",
                "expected": expected_side,
                "actual": actual_side,
            }
        )

    expected_volume = float(
        record.get(
            "volume",
            0.0,
        )
    )

    actual_volume = _position_volume(
        broker_position
    )

    if not _same_float(
        actual_volume,
        expected_volume,
        VOLUME_TOLERANCE,
    ):

        mismatches.append(
            {
                "type": "volume_mismatch",
                "expected": expected_volume,
                "actual": actual_volume,
            }
        )

    expected_sl = record.get(
        "stop_loss"
    )

    actual_sl = _position_sl(
        broker_position
    )

    if not _same_float(
        actual_sl,
        expected_sl,
        PRICE_TOLERANCE,
    ):

        mismatches.append(
            {
                "type": "stop_loss_mismatch",
                "expected": expected_sl,
                "actual": actual_sl,
            }
        )

    expected_tp = record.get(
        "take_profit"
    )

    actual_tp = _position_tp(
        broker_position
    )

    if not _same_float(
        actual_tp,
        expected_tp,
        PRICE_TOLERANCE,
    ):

        mismatches.append(
            {
                "type": "take_profit_mismatch",
                "expected": expected_tp,
                "actual": actual_tp,
            }
        )

    return mismatches


# ============================================================
# RECONCILIATION
# ============================================================

async def reconcile_live_positions(
    *,
    symbol: Optional[str] = None,
    magic: int = DEFAULT_RAYMOND_MAGIC,
) -> ReconciliationResult:

    global _reconciliation_safe
    global _last_result
    global _last_error
    global _last_run_at

    started_at = _utc_now()

    try:

        # ----------------------------------------------------
        # BROKER STATE
        # ----------------------------------------------------

        broker_positions = (
            await mt5_service.get_positions(
                symbol=symbol
            )
        )

        raymond_broker_positions = (
            _raymond_broker_positions(
                broker_positions,
                magic=magic,
                symbol=symbol,
            )
        )

        # ----------------------------------------------------
        # RAYMOND STATE
        # ----------------------------------------------------

        raymond_records = (
            registered_live_positions()
        )

        if symbol:
            raymond_records = [
                record
                for record in raymond_records
                if str(
                    record.get(
                        "symbol",
                        "",
                    )
                ).strip()
                == symbol.strip()
            ]

        raymond_position_count = len(
            raymond_records
        )

        broker_position_count = len(
            raymond_broker_positions
        )

        mismatches = []

        matched_count = 0

        missing_count = 0

        matched_tickets = set()

        # ----------------------------------------------------
        # RAYMOND -> BROKER
        # ----------------------------------------------------

        for record in raymond_records:

            broker_position = (
                _match_registered_position(
                    record,
                    raymond_broker_positions,
                )
            )

            if broker_position is None:

                missing_count += 1

                mismatches.append(
                    {
                        "type": "missing_broker_position",
                        "client_order_id": (
                            record.get(
                                "client_order_id"
                            )
                        ),
                        "expected": dict(
                            record
                        ),
                        "actual": None,
                    }
                )

                continue

            ticket = _position_ticket(
                broker_position
            )

            if ticket is not None:
                matched_tickets.add(
                    ticket
                )

            position_mismatches = (
                _validate_match(
                    record,
                    broker_position,
                )
            )

            if position_mismatches:

                for mismatch in position_mismatches:

                    mismatches.append(
                        {
                            **mismatch,
                            "client_order_id": (
                                record.get(
                                    "client_order_id"
                                )
                            ),
                            "position_ticket": ticket,
                        }
                    )

            else:
                matched_count += 1

        # ----------------------------------------------------
        # BROKER -> RAYMOND
        # ----------------------------------------------------

        orphan_count = 0

        for broker_position in (
            raymond_broker_positions
        ):

            ticket = _position_ticket(
                broker_position
            )

            if (
                ticket is not None
                and ticket in matched_tickets
            ):
                continue

            # If a registered record has no ticket,
            # determine whether it was already matched
            # by symbol/side/volume.
            fallback_match = False

            for record in raymond_records:

                if (
                    record.get(
                        "position_ticket"
                    )
                    is not None
                ):
                    continue

                if (
                    _match_registered_position(
                        record,
                        [broker_position],
                    )
                    is not None
                ):
                    fallback_match = True
                    break

            if fallback_match:
                continue

            orphan_count += 1

            mismatches.append(
                {
                    "type": "orphan_broker_position",
                    "position_ticket": ticket,
                    "expected": None,
                    "actual": (
                        _safe_position_summary(
                            broker_position
                        )
                    ),
                }
            )

        # ----------------------------------------------------
        # FINAL STATE
        # ----------------------------------------------------

        safe = len(
            mismatches
        ) == 0

        status = (
            "reconciled"
            if safe
            else "mismatch"
        )

        result = ReconciliationResult(
            status=status,

            safe_for_new_live_orders=safe,

            broker_position_count=(
                broker_position_count
            ),

            raymond_position_count=(
                raymond_position_count
            ),

            matched_count=matched_count,

            mismatch_count=len(
                mismatches
            ),

            orphan_count=orphan_count,

            missing_count=missing_count,

            mismatches=mismatches,

            timestamp=started_at.isoformat(),
        )

        with _state_lock:

            _reconciliation_safe = safe

            _last_result = result

            _last_error = None

            _last_run_at = started_at

        return result

    except MT5ServiceError as exc:

        with _state_lock:

            _reconciliation_safe = False

            _last_error = str(exc)

            _last_run_at = started_at

        raise ReconciliationError(
            f"Unable to reconcile broker positions: {exc}"
        ) from exc

    except Exception as exc:

        with _state_lock:

            _reconciliation_safe = False

            _last_error = str(exc)

            _last_run_at = started_at

        raise ReconciliationError(
            f"Live reconciliation failed: {exc}"
        ) from exc


# ============================================================
# SAFETY ACCESS
# ============================================================

def reconciliation_is_safe() -> bool:
    with _state_lock:
        return bool(
            _reconciliation_safe
        )


def require_reconciliation_safe() -> None:
    """
    Fail closed unless reconciliation has successfully
    completed and found no mismatches.
    """

    if not reconciliation_is_safe():
        raise PermissionError(
            "Live reconciliation is not safe. "
            "New live orders are blocked until broker "
            "and Raymond position state is reconciled."
        )


def reconciliation_status() -> dict:

    with _state_lock:

        result = _last_result

        last_error = _last_error

        last_run_at = _last_run_at

        safe = _reconciliation_safe

    return {
        "safe_for_new_live_orders": bool(
            safe
        ),

        "has_result": result is not None,

        "last_error": last_error,

        "last_run_at": (
            last_run_at.isoformat()
            if last_run_at is not None
            else None
        ),

        "result": (
            {
                "status": result.status,
                "broker_position_count": (
                    result.broker_position_count
                ),
                "raymond_position_count": (
                    result.raymond_position_count
                ),
                "matched_count": (
                    result.matched_count
                ),
                "mismatch_count": (
                    result.mismatch_count
                ),
                "orphan_count": (
                    result.orphan_count
                ),
                "missing_count": (
                    result.missing_count
                ),
                "mismatches": result.mismatches,
                "timestamp": result.timestamp,
            }
            if result is not None
            else None
        ),

        "fail_closed": True,

        "timestamp": _utc_now().isoformat(),
    }


# ============================================================
# API ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/live-reconciliation",
    tags=["Live Reconciliation"],
)


@router.get("/status")
async def get_reconciliation_status():
    return {
        "status": "ok",
        "reconciliation": (
            reconciliation_status()
        ),
    }


@router.get("/registered")
async def get_registered_positions():
    return {
        "status": "ok",
        "positions": (
            registered_live_positions()
        ),
        "count": len(
            registered_live_positions()
        ),
    }


@router.post("/run")
async def run_reconciliation(
    request: ReconciliationRequest,
):

    try:

        result = (
            await reconcile_live_positions(
                symbol=request.symbol,
                magic=request.magic,
            )
        )

        return {
            "status": result.status,

            "safe_for_new_live_orders": (
                result.safe_for_new_live_orders
            ),

            "broker_position_count": (
                result.broker_position_count
            ),

            "raymond_position_count": (
                result.raymond_position_count
            ),

            "matched_count": (
                result.matched_count
            ),

            "mismatch_count": (
                result.mismatch_count
            ),

            "orphan_count": (
                result.orphan_count
            ),

            "missing_count": (
                result.missing_count
            ),

            "mismatches": (
                result.mismatches
            ),

            "timestamp": result.timestamp,
        }

    except ReconciliationError as exc:

        raise HTTPException(
            status_code=503,

            detail={
                "error": (
                    "RECONCILIATION_FAILED"
                ),

                "message": str(exc),

                "safe_for_new_live_orders": False,

                "timestamp": (
                    _utc_now().isoformat()
                ),
            },
        ) from exc


@router.post("/clear")
async def clear_reconciliation_state():
    """
    Clear reconciliation state.

    This does NOT modify broker positions.

    Clearing the state intentionally makes the live system
    unsafe until another successful reconciliation occurs.
    """

    global _reconciliation_safe
    global _last_result
    global _last_error
    global _last_run_at

    with _state_lock:

        _reconciliation_safe = False

        _last_result = None

        _last_error = (
            "Reconciliation state manually cleared."
        )

        _last_run_at = _utc_now()

    return {
        "status": "cleared",

        "safe_for_new_live_orders": False,

        "fail_closed": True,

        "timestamp": (
            _utc_now().isoformat()
        ),
}
