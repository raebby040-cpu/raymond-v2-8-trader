"""
RAYMOND v2.8 - Live Position Protection Engine

STEP 17.6D

Real MT5 position protection layer.

Responsibilities:

- Inspect Raymond-owned live positions
- Protect existing SL/TP
- Break-even protection
- Trailing-stop protection
- Broker stop-distance validation
- Never widen an existing stop-loss
- Only modify Raymond-owned positions
- Fail closed on broker/API errors
- Provide protection status and manual execution endpoints

IMPORTANT:

This module does NOT open new trades.

This module does NOT enable live trading.

This module only modifies EXISTING Raymond-owned positions.

Automatic protection is DISABLED by default.

Enable explicitly with:

RAYMOND_POSITION_PROTECTION_ENABLED=true

Break-even:

RAYMOND_BREAK_EVEN_ENABLED=true

Trailing:

RAYMOND_TRAILING_ENABLED=true

The production system should run this protection cycle repeatedly
from a controlled worker/scheduler after demo-account E2E testing.

Never rely on this module alone as the sole emergency protection.
Broker-side SL must already exist on every live position.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import os
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


try:
    from .live_reconciliation import (
        registered_live_positions,
    )
    from .mt5_service import (
        MT5ServiceError,
        mt5,
        mt5_service,
    )
except ImportError:
    from live_reconciliation import (
        registered_live_positions,
    )
    from mt5_service import (
        MT5ServiceError,
        mt5,
        mt5_service,
    )


DEFAULT_MAGIC = 28001703

PRICE_TOLERANCE = 0.000001
MIN_PRICE_CHANGE = 0.000001


class LivePositionProtectionError(RuntimeError):
    """Raised when live position protection cannot safely complete."""


@dataclass(frozen=True)
class ProtectionAction:
    position_ticket: int
    symbol: str
    action: str
    old_stop_loss: Optional[float]
    new_stop_loss: Optional[float]
    take_profit: Optional[float]
    reason: str
    applied: bool
    error: Optional[str] = None


_lock = Lock()

_last_run_at: Optional[datetime] = None
_last_error: Optional[str] = None
_last_result: Optional[Dict[str, Any]] = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env_bool(
    name: str,
    default: bool = False,
) -> bool:
    value = os.getenv(
        name,
        "true" if default else "false",
    )

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_float(
    name: str,
    default: float,
) -> float:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def protection_config() -> Dict[str, Any]:
    """
    Read protection configuration.

    Defaults intentionally keep automatic modification disabled.
    """

    break_even_r = _env_float(
        "RAYMOND_BREAK_EVEN_R",
        1.0,
    )

    break_even_offset = _env_float(
        "RAYMOND_BREAK_EVEN_OFFSET",
        0.0,
    )

    trailing_distance = _env_float(
        "RAYMOND_TRAILING_DISTANCE",
        2.0,
    )

    return {
        "enabled": _env_bool(
            "RAYMOND_POSITION_PROTECTION_ENABLED",
            False,
        ),
        "break_even_enabled": _env_bool(
            "RAYMOND_BREAK_EVEN_ENABLED",
            False,
        ),
        "break_even_r": max(
            break_even_r,
            0.0,
        ),
        "break_even_offset": max(
            break_even_offset,
            0.0,
        ),
        "trailing_enabled": _env_bool(
            "RAYMOND_TRAILING_ENABLED",
            False,
        ),
        "trailing_distance": max(
            trailing_distance,
            0.0,
        ),
    }


def _safe_int(
    value: Any,
) -> Optional[int]:

    if value is None:
        return None

    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def _safe_float(
    value: Any,
) -> Optional[float]:

    if value is None:
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def _normalize_side(
    value: Any,
) -> str:

    if isinstance(value, str):

        normalized = (
            value.upper()
            .strip()
        )

        if normalized in {
            "BUY",
            "LONG",
        }:
            return "BUY"

        if normalized in {
            "SELL",
            "SHORT",
        }:
            return "SELL"

    numeric = _safe_int(value)

    if numeric == 0:
        return "BUY"

    if numeric == 1:
        return "SELL"

    return "UNKNOWN"


def _is_better_stop(
    side: str,
    current_sl: Optional[float],
    candidate_sl: float,
) -> bool:

    if candidate_sl <= 0:
        return False

    if current_sl is None or current_sl <= 0:
        return True

    if side == "BUY":
        return candidate_sl > current_sl + MIN_PRICE_CHANGE

    if side == "SELL":
        return candidate_sl < current_sl - MIN_PRICE_CHANGE

    return False


def _normalize_price(
    price: float,
    digits: int,
) -> float:

    return round(
        float(price),
        max(
            int(digits),
            0,
        ),
    )


async def _get_symbol_spec(
    symbol: str,
) -> Dict[str, Any]:

    try:
        return await mt5_service.get_symbol_specification(
            symbol
        )

    except MT5ServiceError as exc:
        raise LivePositionProtectionError(
            f"Unable to read symbol specification "
            f"for {symbol}: {exc}"
        ) from exc


async def _get_tick(
    symbol: str,
) -> Dict[str, Any]:

    try:
        return await mt5_service.get_symbol_tick(
            symbol
        )

    except MT5ServiceError as exc:
        raise LivePositionProtectionError(
            f"Unable to read current price for "
            f"{symbol}: {exc}"
        ) from exc


def _minimum_stop_distance(
    specification: Dict[str, Any],
) -> float:

    point = _safe_float(
        specification.get("point")
    )

    stops_level = _safe_int(
        specification.get(
            "trade_stops_level"
        )
    )

    if point is None or point <= 0:
        return 0.0

    if stops_level is None or stops_level <= 0:
        return 0.0

    return (
        point
        * stops_level
    )


def _candidate_is_broker_valid(
    *,
    side: str,
    candidate_sl: float,
    bid: float,
    ask: float,
    minimum_distance: float,
) -> bool:

    if candidate_sl <= 0:
        return False

    if side == "BUY":

        return (
            candidate_sl < bid
            and (
                minimum_distance <= 0
                or (
                    bid
                    - candidate_sl
                    >= minimum_distance
                )
            )
        )

    if side == "SELL":

        return (
            candidate_sl > ask
            and (
                minimum_distance <= 0
                or (
                    candidate_sl
                    - ask
                    >= minimum_distance
                )
            )
        )

    return False


async def _modify_position_sl_tp(
    *,
    ticket: int,
    symbol: str,
    stop_loss: float,
    take_profit: float,
) -> Dict[str, Any]:

    if mt5 is None:
        raise LivePositionProtectionError(
            "MetaTrader5 package is not installed."
        )

    if not mt5_service.connected:
        raise LivePositionProtectionError(
            "MT5 is not connected."
        )

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": int(ticket),
        "sl": float(stop_loss),
        "tp": float(take_profit),
    }

    try:

        result = await asyncio.to_thread(
            mt5.order_send,
            request,
        )

    except Exception as exc:

        raise LivePositionProtectionError(
            f"MT5 SL/TP modification failed: {exc}"
        ) from exc

    if result is None:

        raise LivePositionProtectionError(
            "MT5 SL/TP modification returned no result."
        )

    if hasattr(
        result,
        "_asdict",
    ):
        data = dict(
            result._asdict()
        )
    else:
        data = {}

    retcode = data.get(
        "retcode"
    )

    success_codes = {
        int(
            getattr(
                mt5,
                "TRADE_RETCODE_DONE",
                10009,
            )
        ),
        int(
            getattr(
                mt5,
                "TRADE_RETCODE_DONE_PARTIAL",
                getattr(
                    mt5,
                    "TRADE_RETCODE_DONE",
                    10009,
                ),
            )
        ),
    }

    if (
        retcode is None
        or int(retcode)
        not in success_codes
    ):

        raise LivePositionProtectionError(
            "Broker rejected SL/TP modification. "
            f"retcode={retcode}, "
            f"comment={data.get('comment')}"
        )

    return data


def _calculate_risk_distance(
    *,
    side: str,
    entry_price: float,
    stop_loss: float,
) -> float:

    if side == "BUY":

        return (
            entry_price
            - stop_loss
        )

    if side == "SELL":

        return (
            stop_loss
            - entry_price
        )

    return 0.0


def _calculate_current_profit_distance(
    *,
    side: str,
    entry_price: float,
    bid: float,
    ask: float,
) -> float:

    current_price = (
        bid
        if side == "SELL"
        else ask
    )

    if side == "BUY":

        return (
            current_price
            - entry_price
        )

    if side == "SELL":

        return (
            entry_price
            - current_price
        )

    return 0.0


def _calculate_break_even_stop(
    *,
    side: str,
    entry_price: float,
    offset: float,
) -> float:

    if side == "BUY":

        return (
            entry_price
            + offset
        )

    if side == "SELL":

        return (
            entry_price
            - offset
        )

    return 0.0


def _calculate_trailing_stop(
    *,
    side: str,
    bid: float,
    ask: float,
    trailing_distance: float,
) -> float:

    if side == "BUY":

        return (
            bid
            - trailing_distance
        )

    if side == "SELL":

        return (
            ask
            + trailing_distance
        )

    return 0.0


async def _protect_one_position(
    *,
    registered: Dict[str, Any],
    broker: Dict[str, Any],
    config: Dict[str, Any],
    dry_run: bool,
) -> ProtectionAction:

    ticket = _safe_int(
        broker.get("ticket")
    )

    symbol = str(
        broker.get("symbol", "")
    ).strip()

    side = _normalize_side(
        broker.get("type")
    )

    if ticket is None:

        return ProtectionAction(
            position_ticket=-1,
            symbol=symbol,
            action="invalid_position",
            old_stop_loss=None,
            new_stop_loss=None,
            take_profit=None,
            reason="Broker position has no valid ticket.",
            applied=False,
            error="INVALID_POSITION_TICKET",
        )

    current_sl = _safe_float(
        broker.get("sl")
    )

    current_tp = _safe_float(
        broker.get("tp")
    )

    entry_price = _safe_float(
        broker.get("price_open")
    )

    if entry_price is None or entry_price <= 0:

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="blocked",
            old_stop_loss=current_sl,
            new_stop_loss=None,
            take_profit=current_tp,
            reason="Position has invalid entry price.",
            applied=False,
            error="INVALID_ENTRY_PRICE",
        )

    if side not in {
        "BUY",
        "SELL",
    }:

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="blocked",
            old_stop_loss=current_sl,
            new_stop_loss=None,
            take_profit=current_tp,
            reason="Unknown broker position side.",
            applied=False,
            error="UNKNOWN_POSITION_SIDE",
        )

    if current_tp is None or current_tp <= 0:

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="blocked",
            old_stop_loss=current_sl,
            new_stop_loss=None,
            take_profit=current_tp,
            reason="Position has no valid take-profit.",
            applied=False,
            error="MISSING_TAKE_PROFIT",
        )

    specification = await _get_symbol_spec(
        symbol
    )

    digits = _safe_int(
        specification.get("digits")
    )

    if digits is None:
        digits = 2

    tick = await _get_tick(
        symbol
    )

    bid = _safe_float(
        tick.get("bid")
    )

    ask = _safe_float(
        tick.get("ask")
    )

    if (
        bid is None
        or ask is None
        or bid <= 0
        or ask <= 0
    ):

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="blocked",
            old_stop_loss=current_sl,
            new_stop_loss=None,
            take_profit=current_tp,
            reason="Broker returned invalid bid/ask.",
            applied=False,
            error="INVALID_MARKET_PRICE",
        )

    minimum_distance = _minimum_stop_distance(
        specification
    )

    candidate_sl: Optional[float] = None
    reason = ""

    # ------------------------------------------------------------
    # Existing protection is mandatory.
    # ------------------------------------------------------------

    if (
        current_sl is None
        or current_sl <= 0
    ):

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="blocked",
            old_stop_loss=current_sl,
            new_stop_loss=None,
            take_profit=current_tp,
            reason=(
                "Position has no valid stop-loss. "
                "Automatic reconstruction is deliberately "
                "disabled because the original risk boundary "
                "must not be guessed."
            ),
            applied=False,
            error="MISSING_STOP_LOSS",
        )

    # ------------------------------------------------------------
    # Break-even calculation.
    # ------------------------------------------------------------

    if config["break_even_enabled"]:

        risk_distance = _calculate_risk_distance(
            side=side,
            entry_price=entry_price,
            stop_loss=current_sl,
        )

        if risk_distance > 0:

            profit_distance = (
                _calculate_current_profit_distance(
                    side=side,
                    entry_price=entry_price,
                    bid=bid,
                    ask=ask,
                )
            )

            break_even_trigger = (
                risk_distance
                * config["break_even_r"]
            )

            if (
                profit_distance
                >= break_even_trigger
            ):

                break_even_sl = (
                    _calculate_break_even_stop(
                        side=side,
                        entry_price=entry_price,
                        offset=config[
                            "break_even_offset"
                        ],
                    )
                )

                if _is_better_stop(
                    side,
                    current_sl,
                    break_even_sl,
                ):

                    candidate_sl = (
                        break_even_sl
                    )

                    reason = (
                        "BREAK_EVEN"
                    )

    # ------------------------------------------------------------
    # Trailing-stop calculation.
    # ------------------------------------------------------------

    if config["trailing_enabled"]:

        trailing_distance = config[
            "trailing_distance"
        ]

        if trailing_distance > 0:

            trailing_sl = (
                _calculate_trailing_stop(
                    side=side,
                    bid=bid,
                    ask=ask,
                    trailing_distance=(
                        trailing_distance
                    ),
                )
            )

            if (
                candidate_sl is None
                or _is_better_stop(
                    side,
                    candidate_sl,
                    trailing_sl,
                )
            ):

                if _is_better_stop(
                    side,
                    current_sl,
                    trailing_sl,
                ):

                    candidate_sl = (
                        trailing_sl
                    )

                    reason = (
                        "TRAILING_STOP"
                    )

    if candidate_sl is None:

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="no_change",
            old_stop_loss=current_sl,
            new_stop_loss=current_sl,
            take_profit=current_tp,
            reason=(
                "Current stop-loss is already at least "
                "as protective as the configured rules."
            ),
            applied=False,
        )

    candidate_sl = _normalize_price(
        candidate_sl,
        digits,
    )

    if not _candidate_is_broker_valid(
        side=side,
        candidate_sl=candidate_sl,
        bid=bid,
        ask=ask,
        minimum_distance=minimum_distance,
    ):

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="blocked",
            old_stop_loss=current_sl,
            new_stop_loss=candidate_sl,
            take_profit=current_tp,
            reason=(
                "Calculated protection stop violates "
                "the broker's current stop-distance rules."
            ),
            applied=False,
            error="BROKER_STOP_DISTANCE",
        )

    if not _is_better_stop(
        side,
        current_sl,
        candidate_sl,
    ):

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="no_change",
            old_stop_loss=current_sl,
            new_stop_loss=current_sl,
            take_profit=current_tp,
            reason=(
                "Candidate stop would not improve "
                "existing protection."
            ),
            applied=False,
        )

    if dry_run:

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="would_modify",
            old_stop_loss=current_sl,
            new_stop_loss=candidate_sl,
            take_profit=current_tp,
            reason=reason,
            applied=False,
        )

    try:

        await _modify_position_sl_tp(
            ticket=ticket,
            symbol=symbol,
            stop_loss=candidate_sl,
            take_profit=current_tp,
        )

    except LivePositionProtectionError as exc:

        return ProtectionAction(
            position_ticket=ticket,
            symbol=symbol,
            action="modification_failed",
            old_stop_loss=current_sl,
            new_stop_loss=candidate_sl,
            take_profit=current_tp,
            reason=reason,
            applied=False,
            error=str(exc),
        )

    return ProtectionAction(
        position_ticket=ticket,
        symbol=symbol,
        action="modified",
        old_stop_loss=current_sl,
        new_stop_loss=candidate_sl,
        take_profit=current_tp,
        reason=reason,
        applied=True,
    )


async def protect_live_positions(
    *,
    symbol: Optional[str] = None,
    magic: int = DEFAULT_MAGIC,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Execute one protection cycle.

    dry_run=True never modifies broker state.

    dry_run=False can modify SL on Raymond-owned positions,
    but only when protection is explicitly enabled.
    """

    global _last_run_at
    global _last_error
    global _last_result

    now = _utc_now()

    config = protection_config()

    if magic < 0:

        raise LivePositionProtectionError(
            "Magic number cannot be negative."
        )

    if not mt5_service.connected:

        raise LivePositionProtectionError(
            "MT5 is not connected."
        )

    registered = registered_live_positions()

    registered_for_magic = [
        item
        for item in registered
        if _safe_int(
            item.get(
                "magic",
                DEFAULT_MAGIC,
            )
        ) == magic
    ]

    if symbol:

        normalized_symbol = (
            symbol.strip()
        )

        registered_for_magic = [
            item
            for item in registered_for_magic
            if str(
                item.get(
                    "symbol",
                    "",
                )
            ).strip()
            == normalized_symbol
        ]

    try:

        broker_positions = (
            await mt5_service.get_positions(
                symbol=symbol,
            )
        )

    except MT5ServiceError as exc:

        with _lock:
            _last_run_at = now
            _last_error = str(exc)

        raise LivePositionProtectionError(
            f"Unable to read live positions: {exc}"
        ) from exc

    registered_by_ticket = {}

    for item in registered_for_magic:

        ticket = _safe_int(
            item.get(
                "position_ticket"
            )
        )

        if ticket is not None:
            registered_by_ticket[
                ticket
            ] = item

    broker_by_ticket = {}

    for position in broker_positions:

        position_magic = _safe_int(
            position.get("magic")
        )

        if position_magic != magic:
            continue

        ticket = _safe_int(
            position.get("ticket")
        )

        if ticket is None:
            continue

        broker_by_ticket[
            ticket
        ] = position

    actions: List[Dict[str, Any]] = []

    modified_count = 0
    blocked_count = 0
    unchanged_count = 0

    for ticket, registered_position in (
        registered_by_ticket.items()
    ):

        broker_position = (
            broker_by_ticket.get(ticket)
        )

        if broker_position is None:

            action = ProtectionAction(
                position_ticket=ticket,
                symbol=str(
                    registered_position.get(
                        "symbol",
                        "",
                    )
                ),
                action="missing_at_broker",
                old_stop_loss=_safe_float(
                    registered_position.get(
                        "stop_loss"
                    )
                ),
                new_stop_loss=None,
                take_profit=_safe_float(
                    registered_position.get(
                        "take_profit"
                    )
                ),
                reason=(
                    "Registered Raymond position "
                    "was not found at broker."
                ),
                applied=False,
                error="POSITION_MISSING",
            )

            blocked_count += 1

            actions.append(
                action.__dict__
            )

            continue

        action = await _protect_one_position(
            registered=registered_position,
            broker=broker_position,
            config=config,
            dry_run=dry_run,
        )

        actions.append(
            action.__dict__
        )

        if action.applied:
            modified_count += 1

        elif action.action in {
            "blocked",
            "modification_failed",
            "missing_at_broker",
        }:
            blocked_count += 1

        else:
            unchanged_count += 1

    result = {
        "status": (
            "completed"
            if blocked_count == 0
            else "completed_with_blocks"
        ),
        "enabled": config["enabled"],
        "dry_run": dry_run,
        "automatic_modification_allowed": (
            config["enabled"]
        ),
        "symbol": symbol,
        "magic": magic,
        "registered_positions": len(
            registered_for_magic
        ),
        "broker_positions": len(
            broker_by_ticket
        ),
        "modified_count": modified_count,
        "blocked_count": blocked_count,
        "unchanged_count": unchanged_count,
        "actions": actions,
        "configuration": config,
        "timestamp": now.isoformat(),
    }

    with _lock:
        _last_run_at = now
        _last_error = None
        _last_result = result

    return result


def protection_engine_status() -> Dict[str, Any]:

    with _lock:

        return {
            "enabled": protection_config()[
                "enabled"
            ],
            "configuration": protection_config(),
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


class ProtectionRequest(BaseModel):

    symbol: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    magic: int = Field(
        default=DEFAULT_MAGIC,
        ge=0,
    )

    dry_run: bool = Field(
        default=True
    )


router = APIRouter(
    prefix="/api/live-position-protection",
    tags=["Live Position Protection"],
)


@router.get("/status")
async def get_protection_status():

    return {
        "status": "ok",
        "protection": protection_engine_status(),
    }


@router.post("/run")
async def run_protection(
    request: ProtectionRequest,
):

    # A real modification must be explicitly enabled.
    if not request.dry_run:

        config = protection_config()

        if not config["enabled"]:

            raise HTTPException(
                status_code=403,
                detail={
                    "error": (
                        "LIVE_POSITION_PROTECTION_DISABLED"
                    ),
                    "message": (
                        "Real SL modification is disabled. "
                        "Set RAYMOND_POSITION_PROTECTION_ENABLED=true "
                        "only after the demo-account E2E test."
                    ),
                    "fail_closed": True,
                },
            )

    try:

        result = await protect_live_positions(
            symbol=request.symbol,
            magic=request.magic,
            dry_run=request.dry_run,
        )

        return {
            "status": "completed",
            "protection": result,
        }

    except LivePositionProtectionError as exc:

        raise HTTPException(
            status_code=503,
            detail={
                "error": (
                    "LIVE_POSITION_PROTECTION_FAILED"
                ),
                "message": str(exc),
                "fail_closed": True,
                "timestamp": (
                    _utc_now().isoformat()
                ),
            },
        ) from exc
