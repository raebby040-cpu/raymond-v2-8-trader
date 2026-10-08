"""
RAYMOND v2.8 - Live Safety & Arming Gate

STEP 17.4A

Independent safety layer for real-money execution.

IMPORTANT:

This module does NOT enable live trading by itself.

Live execution requires BOTH:

1. LIVE_TRADING_ENABLED=true
2. Raymond live execution is explicitly ARMED

The arming state is intentionally stored only in process memory.

Therefore:

- Restarting the backend automatically disarms live trading.
- Deploying a new version automatically disarms live trading.
- A missing arm token prevents arming.
- Disarming immediately blocks new live orders.
- No broker password is stored or returned here.

This is an additional safety layer, not a replacement for:
- authentication
- broker account verification
- MT5 health checks
- risk validation
- emergency stop
- order validation
- execution verification
- reconciliation
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import os
import secrets
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field


# ============================================================
# CONSTANTS
# ============================================================

DEFAULT_ARM_TOKEN_ENV = "RAYMOND_LIVE_ARM_TOKEN"

MIN_ARM_TOKEN_LENGTH = 32


# ============================================================
# INTERNAL STATE
# ============================================================

_state_lock = Lock()

_armed = False
_armed_at: Optional[datetime] = None
_armed_by: Optional[str] = None


# ============================================================
# TOKEN HELPERS
# ============================================================

def _configured_arm_token() -> Optional[str]:
    """
    Read the live-arm token from the environment.

    No default token is ever provided.

    A missing token means live arming is impossible.
    """

    token = os.getenv(
        DEFAULT_ARM_TOKEN_ENV,
        "",
    ).strip()

    if not token:
        return None

    if len(token) < MIN_ARM_TOKEN_LENGTH:
        return None

    return token


def _token_is_valid(
    supplied_token: Optional[str],
) -> bool:
    """
    Constant-time token comparison.

    Returns False when:
    - no token is configured
    - no token is supplied
    - the supplied token is incorrect
    """

    configured = _configured_arm_token()

    if not configured:
        return False

    if not supplied_token:
        return False

    return hmac.compare_digest(
        supplied_token,
        configured,
    )


def generate_arm_token() -> str:
    """
    Generate a cryptographically strong token.

    This helper is intended for administrators generating
    a value to place in the server environment.

    The generated value is never persisted by this module.
    """

    return secrets.token_urlsafe(48)


def token_configuration_status() -> dict:
    """
    Return safe information about token configuration.

    The actual token is NEVER returned.
    """

    configured = _configured_arm_token()

    return {
        "configured": configured is not None,
        "minimum_length": MIN_ARM_TOKEN_LENGTH,
        "environment_variable": DEFAULT_ARM_TOKEN_ENV,
    }


# ============================================================
# ARM / DISARM STATE
# ============================================================

def arm_live_trading(
    *,
    token: str,
    armed_by: str = "api",
) -> dict:
    """
    Explicitly arm live execution.

    Arming succeeds only when a sufficiently strong server-side
    arm token is configured and the supplied token matches it.
    """

    if not _token_is_valid(token):
        raise PermissionError(
            "Invalid or missing live-arm token."
        )

    global _armed
    global _armed_at
    global _armed_by

    now = datetime.now(
        timezone.utc
    )

    with _state_lock:
        _armed = True
        _armed_at = now
        _armed_by = (
            armed_by.strip()
            if armed_by
            else "api"
        )

    return live_safety_status()


def disarm_live_trading(
    *,
    reason: str = "manual_disarm",
) -> dict:
    """
    Immediately disarm live execution.

    This does NOT close existing broker positions.

    Existing positions require the separate reconciliation /
    position-protection layer.
    """

    global _armed
    global _armed_at
    global _armed_by

    with _state_lock:
        _armed = False
        _armed_at = None
        _armed_by = None

    status = live_safety_status()

    status["disarm_reason"] = reason

    return status


def is_live_armed() -> bool:
    """
    Return the current in-memory arming state.
    """

    with _state_lock:
        return bool(_armed)


def require_live_armed() -> None:
    """
    Fail closed unless Raymond is explicitly armed.
    """

    if not is_live_armed():
        raise PermissionError(
            "Raymond live execution is not armed."
        )


# ============================================================
# STATUS
# ============================================================

def live_safety_status() -> dict:
    """
    Return safe live-safety state.

    No secret values are returned.
    """

    with _state_lock:
        armed = bool(_armed)
        armed_at = _armed_at
        armed_by = _armed_by

    configured = (
        _configured_arm_token()
        is not None
    )

    return {
        "armed": armed,
        "arm_token_configured": configured,
        "armed_at": (
            armed_at.isoformat()
            if armed_at is not None
            else None
        ),
        "armed_by": armed_by,
        "restart_behavior": (
            "backend restart automatically disarms live execution"
        ),
        "fail_closed": True,
        "timestamp": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }


# ============================================================
# COMBINED SAFETY STATUS
# ============================================================

def combined_live_gate_status(
    *,
    environment_enabled: bool,
) -> dict:
    """
    Report the two top-level live gates.

    This does not replace the broker/risk/emergency checks
    performed by the execution gateway.
    """

    armed = is_live_armed()

    return {
        "environment_enabled": bool(
            environment_enabled
        ),
        "explicitly_armed": armed,
        "execution_gate_open": (
            bool(environment_enabled)
            and armed
        ),
        "fail_closed": True,
    }


# ============================================================
# API MODELS
# ============================================================

class LiveArmRequest(BaseModel):
    token: str = Field(
        min_length=1,
        max_length=500,
    )

    armed_by: str = Field(
        default="api",
        min_length=1,
        max_length=100,
    )


class LiveDisarmRequest(BaseModel):
    reason: str = Field(
        default="manual_disarm",
        min_length=1,
        max_length=200,
    )


# ============================================================
# API ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/live-safety",
    tags=["Live Safety"],
)


@router.get("/status")
async def get_live_safety_status():
    """
    Read the current live-safety state.

    Safe for dashboard status display.
    """

    return {
        "status": "ok",
        "safety": live_safety_status(),
    }


@router.get("/token-status")
async def get_token_status():
    """
    Report whether the server has a validly sized arm-token
    configuration.

    The actual secret is never returned.
    """

    return {
        "status": "ok",
        "token": token_configuration_status(),
    }


@router.post("/arm")
async def arm_live(
    request: LiveArmRequest,
    x_raymond_live_arm_token: Optional[str] = Header(
        default=None,
        alias="X-Raymond-Live-Arm-Token",
    ),
):
    """
    Explicitly arm live execution.

    The token may be supplied either:
    - in the request body, or
    - through X-Raymond-Live-Arm-Token.

    Header value takes precedence.

    IMPORTANT:
    This endpoint only arms Raymond's in-memory execution gate.

    It does NOT bypass:
    - broker verification
    - account authorization
    - MT5 checks
    - risk checks
    - emergency stop
    - order validation
    """

    supplied_token = (
        x_raymond_live_arm_token
        or request.token
    )

    try:
        safety = arm_live_trading(
            token=supplied_token,
            armed_by=request.armed_by,
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "LIVE_ARM_DENIED",
                "message": str(exc),
                "timestamp": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            },
        ) from exc

    return {
        "status": "armed",
        "safety": safety,
        "warning": (
            "Live execution is armed. Every live order "
            "must still pass all broker, MT5, emergency-stop, "
            "risk, validation and verification gates."
        ),
    }


@router.post("/disarm")
async def disarm_live(
    request: LiveDisarmRequest,
):
    """
    Immediately disarm new live execution.

    This endpoint does not close existing positions.
    """

    safety = disarm_live_trading(
        reason=request.reason,
    )

    return {
        "status": "disarmed",
        "safety": safety,
    }


@router.post("/emergency-disarm")
async def emergency_disarm():
    """
    Immediate local disarm endpoint.

    This only blocks NEW live orders.

    It deliberately does not attempt to close broker positions.
    Position closure belongs to the independent emergency-stop /
    position-protection system.
    """

    safety = disarm_live_trading(
        reason="emergency_disarm",
    )

    return {
        "status": "disarmed",
        "emergency": True,
        "safety": safety,
    }
