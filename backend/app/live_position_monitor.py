"""
RAYMOND v2.8 - Live Position Monitor & Protection

STEP 17.6

Monitors REAL broker positions after live execution.

Responsibilities:

- Read actual MT5 positions
- Compare them with Raymond's registered live positions
- Verify symbol
- Verify side
- Verify volume
- Verify position ticket
- Verify stop-loss
- Verify take-profit
- Detect missing positions
- Detect orphan positions
- Detect broker-side protection changes
- Detect unprotected positions
- Fail closed when monitoring is unhealthy
- Provide a protection status API

IMPORTANT:

This module does NOT open trades.

This module does NOT enable live trading.

This module does NOT modify SL/TP yet.

Break-even and trailing protection will be added only after
the basic real-position monitoring layer is proven.

For now, a protection mismatch blocks NEW live orders.

The monitor is intentionally fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .live_reconciliation import (
        registered_live_positions,
        reconcile_live_positions,
    )
    from .mt5_service import (
        MT5ServiceError,
        mt5_service,
    )
except ImportError:
    from live_reconciliation import (
        registered_live_positions,
        reconcile_live_positions,
    )
    from mt5_service import (
        MT5ServiceError,
        mt5_service,
    )


DEFAULT_MAGIC = 28001703

# Broker values are floating-point values, so use a small tolerance
# instead of requiring exact binary equality.
PRICE_TOLERANCE = 0.000001
VOLUME_TOLERANCE = 0.00000001


class LivePositionMonitorError(RuntimeError):
    """Raised when live-position monitoring cannot safely complete."""


@dataclass(frozen=True)
class ProtectionIssue:
    code: str
    severity: str
    message: str
    symbol: Optional[str] = None
    position_ticket: Optional[int] = None


_monitor_lock = Lock()

_last_run_at: Optional[datetime] = None
_last_error: Optional[str] = None
_last_result: Optional[Dict[str, Any]] = None
_monitor_healthy = False
_new_orders_allowed = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_side(value: Any) -> str:
    """
    Normalize Raymond and MT5 side representations.

    MT5 position type:
        0 = BUY
        1 = SELL
    """

    if isinstance(value, str):
        normalized = value.upper().strip()

        if normalized in {"BUY", "LONG"}:
            return "BUY"

        if normalized in {"SELL", "SHORT"}:
            return "SELL"

    numeric = _safe_int(value)

    if numeric == 0:
        return "BUY"

    if numeric == 1:
        return "SELL"

    return "UNKNOWN"


def _position_ticket(position: Dict[str, Any]) -> Optional[int]:
    return _safe_int(
        position.get("ticket")
    )


def _registered_ticket(position: Dict[str, Any]) -> Optional[int]:
    return _safe_int(
        position.get("position_ticket")
    )


def _prices_match(
    first: Optional[float],
    second: Optional[float],
    tolerance: float = PRICE_TOLERANCE,
) -> bool:
    if first is None or second is None:
        return False

    return abs(first - second) <= tolerance


def _volumes_match(
    first: Optional[float],
    second: Optional[float],
) -> bool:
    if first is None or second is None:
        return False

    return abs(first - second) <= VOLUME_TOLERANCE


def _protection_is_present(
    stop_loss: Optional[float],
    take_profit: Optional[float],
) -> bool:
    return (
        stop_loss is not None
        and stop_loss > 0
        and take_profit is not None
        and take_profit > 0
    )


def _position_matches_registration(
    registered: Dict[str, Any],
    broker: Dict[str, Any],
) -> List[ProtectionIssue]:
    issues: List[ProtectionIssue] = []

    registered_symbol = str(
        registered.get("symbol", "")
    ).strip()

    broker_symbol = str(
        broker.get("symbol", "")
    ).strip()

    registered_side = _normalize_side(
        registered.get("side")
    )

    broker_side = _normalize_side(
        broker.get("type")
    )

    registered_volume = _safe_float(
        registered.get("volume")
    )

    broker_volume = _safe_float(
        broker.get("volume")
    )

    registered_sl = _safe_float(
        registered.get("stop_loss")
    )

    registered_tp = _safe_float(
        registered.get("take_profit")
    )

    broker_sl = _safe_float(
        broker.get("sl")
    )

    broker_tp = _safe_float(
        broker.get("tp")
    )

    ticket = _position_ticket(broker)

    if registered_symbol != broker_symbol:
        issues.append(
            ProtectionIssue(
                code="SYMBOL_MISMATCH",
                severity="critical",
                message=(
                    f"Raymond registered symbol {registered_symbol!r}, "
                    f"but broker reports {broker_symbol!r}."
                ),
                symbol=broker_symbol or registered_symbol,
                position_ticket=ticket,
            )
        )

    if registered_side != broker_side:
        issues.append(
            ProtectionIssue(
                code="SIDE_MISMATCH",
                severity="critical",
                message=(
                    f"Raymond registered side {registered_side}, "
                    f"but broker reports {broker_side}."
                ),
                symbol=broker_symbol or registered_symbol,
                position_ticket=ticket,
            )
        )

    if not _volumes_match(
        registered_volume,
        broker_volume,
    ):
        issues.append(
            ProtectionIssue(
                code="VOLUME_MISMATCH",
                severity="critical",
                message=(
                    "Raymond registered volume "
                    f"{registered_volume}, but broker reports "
                    f"{broker_volume}."
                ),
                symbol=broker_symbol or registered_symbol,
                position_ticket=ticket,
            )
        )

    if not _protection_is_present(
        broker_sl,
        broker_tp,
    ):
        issues.append(
            ProtectionIssue(
                code="UNPROTECTED_POSITION",
                severity="critical",
                message=(
                    "Broker position does not have both a valid "
                    "stop-loss and take-profit."
                ),
                symbol=broker_symbol or registered_symbol,
                position_ticket=ticket,
            )
        )

    if not _prices_match(
        registered_sl,
        broker_sl,
    ):
        issues.append(
            ProtectionIssue(
                code="STOP_LOSS_MISMATCH",
                severity="critical",
                message=(
                    f"Raymond registered SL {registered_sl}, "
                    f"but broker reports {broker_sl}."
                ),
                symbol=broker_symbol or registered_symbol,
                position_ticket=ticket,
            )
        )

    if not _prices_match(
        registered_tp,
        broker_tp,
    ):
        issues.append(
            ProtectionIssue(
                code="TAKE_PROFIT_MISMATCH",
                severity="critical",
                message=(
                    f"Raymond registered TP {registered_tp}, "
                    f"but broker reports {broker_tp}."
                ),
                symbol=broker_symbol or registered_symbol,
                position_ticket=ticket,
            )
        )

    return issues


def _serialize_issue(
    issue: ProtectionIssue,
) -> Dict[str, Any]:
    return {
        "code": issue.code,
        "severity": issue.severity,
        "message": issue.message,
        "symbol": issue.symbol,
        "position_ticket": issue.position_ticket,
    }


async def _load_broker_positions(
    *,
    symbol: Optional[str] = None,
) -> List[Dict[str, Any]]:
    try:
        positions = await mt5_service.get_positions(
            symbol=symbol,
        )
    except MT5ServiceError as exc:
        raise LivePositionMonitorError(
            f"Unable to read broker positions: {exc}"
        ) from exc
    except Exception as exc:
        raise LivePositionMonitorError(
            f"Unexpected broker-position error: {exc}"
        ) from exc

    if positions is None:
        return []

    if not isinstance(positions, list):
        raise LivePositionMonitorError(
            "Broker returned an invalid positions payload."
        )

    return positions


async def inspect_live_positions(
    *,
    symbol: Optional[str] = None,
    magic: int = DEFAULT_MAGIC,
) -> Dict[str, Any]:
    """
    Perform one complete protection inspection.

    This function does not change broker state.
    """

    normalized_symbol = (
        symbol.strip()
        if symbol and symbol.strip()
        else None
    )

    if magic < 0:
        raise LivePositionMonitorError(
            "Magic number cannot be negative."
        )

    registered = registered_live_positions()

    # Only Raymond positions with the requested magic are relevant.
    registered_for_magic = [
        item
        for item in registered
        if _safe_int(item.get("magic", DEFAULT_MAGIC)) == magic
    ]

    if normalized_symbol:
        registered_for_magic = [
            item
            for item in registered_for_magic
            if str(item.get("symbol", "")).strip()
            == normalized_symbol
        ]

    broker_positions = await _load_broker_positions(
        symbol=normalized_symbol,
    )

    broker_for_magic: List[Dict[str, Any]] = []

    for position in broker_positions:
        position_magic = _safe_int(
            position.get("magic")
        )

        if position_magic != magic:
            continue

        broker_for_magic.append(position)

    issues: List[ProtectionIssue] = []

    registered_by_ticket: Dict[int, Dict[str, Any]] = {}
    registered_without_ticket: List[Dict[str, Any]] = []

    for item in registered_for_magic:
        ticket = _registered_ticket(item)

        if ticket is None:
            registered_without_ticket.append(item)
            continue

        registered_by_ticket[ticket] = item

    broker_by_ticket: Dict[int, Dict[str, Any]] = {}

    for position in broker_for_magic:
        ticket = _position_ticket(position)

        if ticket is None:
            issues.append(
                ProtectionIssue(
                    code="BROKER_POSITION_WITHOUT_TICKET",
                    severity="critical",
                    message=(
                        "Broker returned a Raymond position without "
                        "a valid position ticket."
                    ),
                    symbol=str(
                        position.get("symbol", "")
                    ).strip() or None,
                    position_ticket=None,
                )
            )
            continue

        broker_by_ticket[ticket] = position

    matched_tickets = set()

    # ------------------------------------------------------------
    # Compare registered Raymond positions against broker positions.
    # ------------------------------------------------------------

    for ticket, registered_position in registered_by_ticket.items():
        broker_position = broker_by_ticket.get(ticket)

        if broker_position is None:
            issues.append(
                ProtectionIssue(
                    code="POSITION_MISSING_AT_BROKER",
                    severity="critical",
                    message=(
                        f"Raymond registered position {ticket}, "
                        "but that position was not found at the broker."
                    ),
                    symbol=str(
                        registered_position.get("symbol", "")
                    ).strip() or None,
                    position_ticket=ticket,
                )
            )
            continue

        matched_tickets.add(ticket)

        issues.extend(
            _position_matches_registration(
                registered_position,
                broker_position,
            )
        )

    # ------------------------------------------------------------
    # Registered positions without broker ticket.
    # ------------------------------------------------------------

    for registered_position in registered_without_ticket:
        issues.append(
            ProtectionIssue(
                code="REGISTERED_POSITION_WITHOUT_TICKET",
                severity="critical",
                message=(
                    "Raymond has a live position registration without "
                    "a broker position ticket."
                ),
                symbol=str(
                    registered_position.get("symbol", "")
                ).strip() or None,
                position_ticket=None,
            )
        )

    # ------------------------------------------------------------
    # Broker positions that Raymond does not know about.
    # ------------------------------------------------------------

    for ticket, broker_position in broker_by_ticket.items():
        if ticket in matched_tickets:
            continue

        issues.append(
            ProtectionIssue(
                code="ORPHAN_BROKER_POSITION",
                severity="critical",
                message=(
                    f"Broker position {ticket} has Raymond magic {magic} "
                    "but is not registered in Raymond."
                ),
                symbol=str(
                    broker_position.get("symbol", "")
                ).strip() or None,
                position_ticket=ticket,
            )
        )

    critical_count = sum(
        1
        for issue in issues
        if issue.severity == "critical"
    )

    warning_count = sum(
        1
        for issue in issues
        if issue.severity == "warning"
    )

    safe = critical_count == 0

    return {
        "safe": safe,
        "safe_for_new_live_orders": safe,
        "symbol": normalized_symbol,
        "magic": magic,
        "registered_positions": len(
            registered_for_magic
        ),
        "broker_positions": len(
            broker_for_magic
        ),
        "matched_positions": len(
            matched_tickets
        ),
        "critical_issues": critical_count,
        "warning_issues": warning_count,
        "issues": [
            _serialize_issue(issue)
            for issue in issues
        ],
        "timestamp": _utc_now().isoformat(),
    }


async def monitor_live_positions(
    *,
    symbol: Optional[str] = None,
    magic: int = DEFAULT_MAGIC,
) -> Dict[str, Any]:
    """
    Execute one monitoring cycle.

    The result becomes the authoritative in-process protection state.

    If the broker cannot be checked, the monitor becomes unhealthy and
    NEW live orders are blocked.
    """

    global _last_run_at
    global _last_error
    global _last_result
    global _monitor_healthy
    global _new_orders_allowed

    now = _utc_now()

    with _monitor_lock:
        _last_run_at = now
        _last_error = None
        _monitor_healthy = False
        _new_orders_allowed = False

    try:
        result = await inspect_live_positions(
            symbol=symbol,
            magic=magic,
        )

        healthy = True
        safe = bool(
            result.get(
                "safe_for_new_live_orders",
                False,
            )
        )

        with _monitor_lock:
            _last_result = result
            _monitor_healthy = healthy
            _new_orders_allowed = (
                healthy and safe
            )

        return {
            "status": "healthy" if healthy else "unhealthy",
            "monitor_healthy": healthy,
            "new_live_orders_allowed": (
                healthy and safe
            ),
            "result": result,
            "timestamp": now.isoformat(),
        }

    except Exception as exc:
        error_message = str(exc)

        fail_closed_result = {
            "safe": False,
            "safe_for_new_live_orders": False,
            "symbol": symbol,
            "magic": magic,
            "registered_positions": 0,
            "broker_positions": 0,
            "matched_positions": 0,
            "critical_issues": 1,
            "warning_issues": 0,
            "issues": [
                {
                    "code": "MONITOR_FAILURE",
                    "severity": "critical",
                    "message": (
                        "Live position monitoring failed. "
                        "New live orders are blocked."
                    ),
                    "symbol": symbol,
                    "position_ticket": None,
                }
            ],
            "timestamp": now.isoformat(),
        }

        with _monitor_lock:
            _last_error = error_message
            _last_result = fail_closed_result
            _monitor_healthy = False
            _new_orders_allowed = False

        raise LivePositionMonitorError(
            "Live position monitor failed closed: "
            f"{error_message}"
        ) from exc


def protection_status() -> Dict[str, Any]:
    """
    Return the current process-local protection state.
    """

    with _monitor_lock:
        return {
            "monitor_healthy": _monitor_healthy,
            "new_live_orders_allowed": _new_orders_allowed,
            "last_run_at": (
                _last_run_at.isoformat()
                if _last_run_at is not None
                else None
            ),
            "last_error": _last_error,
            "last_result": _last_result,
            "fail_closed": True,
            "timestamp": _utc_now().isoformat(),
        }


def require_position_protection_safe() -> None:
    """
    Hard gate for code that wants to place another live order.
    """

    with _monitor_lock:
        allowed = _new_orders_allowed
        healthy = _monitor_healthy

    if not healthy:
        raise PermissionError(
            "Live position monitor is not healthy."
        )

    if not allowed:
        raise PermissionError(
            "Live position protection is unsafe. "
            "New live orders are blocked."
        )


class MonitorRequest(BaseModel):
    symbol: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    magic: int = Field(
        default=DEFAULT_MAGIC,
        ge=0,
    )


router = APIRouter(
    prefix="/api/live-position-monitor",
    tags=["Live Position Monitor"],
)


@router.get("/status")
async def get_monitor_status():
    return {
        "status": "ok",
        "monitor": protection_status(),
    }


@router.get("/positions")
async def get_monitored_positions(
    symbol: Optional[str] = None,
    magic: int = DEFAULT_MAGIC,
):
    try:
        result = await inspect_live_positions(
            symbol=symbol,
            magic=magic,
        )

        return {
            "status": "ok",
            "monitor": result,
        }

    except LivePositionMonitorError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "LIVE_POSITION_MONITOR_FAILED",
                "message": str(exc),
                "fail_closed": True,
                "timestamp": _utc_now().isoformat(),
            },
        ) from exc


@router.post("/run")
async def run_monitor(
    request: MonitorRequest,
):
    try:
        result = await monitor_live_positions(
            symbol=request.symbol,
            magic=request.magic,
        )

        return {
            "status": "completed",
            "monitor": result,
        }

    except LivePositionMonitorError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "LIVE_POSITION_MONITOR_FAILED",
                "message": str(exc),
                "new_live_orders_allowed": False,
                "fail_closed": True,
                "timestamp": _utc_now().isoformat(),
            },
        ) from exc


@router.post("/check-protection")
async def check_protection(
    request: MonitorRequest,
):
    try:
        result = await inspect_live_positions(
            symbol=request.symbol,
            magic=request.magic,
        )

        if not result.get(
            "safe_for_new_live_orders",
            False,
        ):
            return {
                "status": "unsafe",
                "new_live_orders_allowed": False,
                "monitor": result,
            }

        return {
            "status": "safe",
            "new_live_orders_allowed": True,
            "monitor": result,
        }

    except LivePositionMonitorError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "LIVE_PROTECTION_CHECK_FAILED",
                "message": str(exc),
                "new_live_orders_allowed": False,
                "fail_closed": True,
                "timestamp": _utc_now().isoformat(),
            },
        ) from exc


@router.post("/require-safe")
async def require_safe():
    try:
        require_position_protection_safe()

        return {
            "status": "safe",
            "new_live_orders_allowed": True,
            "fail_closed": True,
            "timestamp": _utc_now().isoformat(),
        }

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "LIVE_PROTECTION_UNSAFE",
                "message": str(exc),
                "new_live_orders_allowed": False,
                "fail_closed": True,
                "timestamp": _utc_now().isoformat(),
            },
        ) from exc
