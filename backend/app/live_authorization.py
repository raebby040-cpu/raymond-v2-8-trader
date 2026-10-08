"""
RAYMOND v2.8 - Explicit LIVE Trading Authorization

STEP 17.8B

This module provides the missing authorization layer between:

    verified broker account
        ->
    explicit LIVE authorization
        ->
    LIVE execution gateway

SAFETY:
- Disabled by default.
- Does not arm the LIVE safety gate.
- Does not enable LIVE_TRADING_ENABLED.
- Does not submit broker orders.
- Requires a separately configured authorization token.
- Requires the broker account to be selected, connected, verified,
  and trading-enabled.
- Authorization is revoked automatically by broker account
  connect/disconnect/select/update flows.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

try:
    from .broker_accounts import (
        BrokerAccount,
        SessionLocal,
        _serialize,
    )
except ImportError:
    from broker_accounts import (
        BrokerAccount,
        SessionLocal,
        _serialize,
    )


MIN_AUTH_TOKEN_LENGTH = 32

AUTHORIZATION_ENV = (
    "RAYMOND_LIVE_AUTHORIZATION_ENABLED"
)

AUTH_TOKEN_ENV = (
    "RAYMOND_LIVE_AUTH_TOKEN"
)


# ============================================================
# CONFIGURATION
# ============================================================

def _authorization_enabled() -> bool:
    """
    LIVE authorization remains disabled unless explicitly enabled.

    Default:
        false
    """

    return (
        os.getenv(
            AUTHORIZATION_ENV,
            "false",
        ).strip().lower()
        == "true"
    )


def _configured_auth_token() -> Optional[str]:
    """
    Read the authorization token from the environment.

    Never expose the actual token through an API response.
    """

    token = os.getenv(
        AUTH_TOKEN_ENV,
        "",
    ).strip()

    if len(token) < MIN_AUTH_TOKEN_LENGTH:
        return None

    return token


def _token_is_valid(
    supplied_token: Optional[str],
) -> bool:
    configured = _configured_auth_token()

    if not configured:
        return False

    if not supplied_token:
        return False

    return hmac.compare_digest(
        supplied_token,
        configured,
    )


# ============================================================
# REQUEST MODEL
# ============================================================

class LiveAuthorizationRequest(BaseModel):
    """
    Explicit authorization request.

    The token may be supplied in the request body when using
    a trusted backend integration.

    The HTTP header is preferred.
    """

    token: str = Field(
        min_length=1,
        max_length=500,
    )


# ============================================================
# SAFE STATUS
# ============================================================

def authorization_configuration_status() -> dict:
    """
    Return safe configuration metadata.

    Never returns the authorization secret.
    """

    configured = (
        _configured_auth_token()
        is not None
    )

    return {
        "authorization_enabled": (
            _authorization_enabled()
        ),
        "token_configured": configured,
        "minimum_token_length": (
            MIN_AUTH_TOKEN_LENGTH
        ),
    }


# ============================================================
# ACCOUNT LOOKUP
# ============================================================

def _get_account(
    db,
    account_id: str,
) -> BrokerAccount:

    account = (
        db.query(BrokerAccount)
        .filter(
            BrokerAccount.account_id
            == account_id
        )
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Broker account not found.",
        )

    return account


# ============================================================
# AUTHORIZATION VALIDATION
# ============================================================

def _validate_account_for_live(
    account: BrokerAccount,
) -> None:
    """
    Validate every account condition required before
    an account can receive explicit LIVE authorization.

    This function NEVER submits an order.
    """

    if not account.selected:
        raise HTTPException(
            status_code=409,
            detail=(
                "The broker account must be selected "
                "before LIVE authorization."
            ),
        )

    if not account.connection_status == "connected":
        raise HTTPException(
            status_code=409,
            detail=(
                "The broker account is not connected."
            ),
        )

    if not account.account_verified:
        raise HTTPException(
            status_code=409,
            detail=(
                "The broker account has not been verified."
            ),
        )

    if not account.trading_allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                "Broker trading permissions are not enabled."
            ),
        )


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/live-authorization",
    tags=["LIVE Authorization"],
)


# ============================================================
# STATUS
# ============================================================

@router.get("/configuration")
def live_authorization_configuration():
    """
    Return safe authorization configuration state.
    """

    return {
        "status": "ok",
        **authorization_configuration_status(),
    }


@router.get("/account/{account_id}")
def live_authorization_account_status(
    account_id: str,
):
    """
    Return the LIVE authorization state of one account.

    No secret is returned.
    """

    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        return {
            "status": "ok",
            "account": _serialize(
                account
            ),
            "authorization_requirements": {
                "selected": bool(
                    account.selected
                ),
                "connected": (
                    account.connection_status
                    == "connected"
                ),
                "account_verified": bool(
                    account.account_verified
                ),
                "trading_allowed": bool(
                    account.trading_allowed
                ),
                "authorization_enabled": (
                    _authorization_enabled()
                ),
                "token_configured": (
                    _configured_auth_token()
                    is not None
                ),
            },
        }

    finally:
        db.close()


# ============================================================
# AUTHORIZE
# ============================================================

@router.post(
    "/account/{account_id}/authorize"
)
def authorize_live_trading(
    account_id: str,
    payload: LiveAuthorizationRequest,
    x_raymond_live_auth_token: Optional[str] =
        Header(
            default=None,
            alias="X-Raymond-Live-Auth-Token",
        ),
):
    """
    Explicitly authorize a verified broker account
    for LIVE execution.

    SAFETY:
    - Feature is disabled by default.
    - Requires authorization secret.
    - Requires selected/connected/verified/trading-enabled account.
    - Does NOT arm the separate LIVE safety gate.
    - Does NOT submit any broker order.
    """

    if not _authorization_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "LIVE account authorization is "
                "currently disabled."
            ),
        )

    supplied_token = (
        x_raymond_live_auth_token
        or payload.token
    )

    if not _token_is_valid(
        supplied_token
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Invalid LIVE authorization token."
            ),
        )

    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        _validate_account_for_live(
            account
        )

        account.live_trading_authorized = 1
        account.updated_at = (
            datetime.utcnow()
        )
        account.last_error = None

        db.commit()
        db.refresh(account)

        return {
            "status": "live_authorized",
            "account": _serialize(
                account
            ),
            "live_authorized": True,
            "order_created": False,
            "execution_started": False,
        }

    finally:
        db.close()


# ============================================================
# REVOKE
# ============================================================

@router.post(
    "/account/{account_id}/revoke"
)
def revoke_live_trading(
    account_id: str,
):
    """
    Immediately revoke account-level LIVE authorization.

    This does NOT close existing broker positions.
    """

    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        account.live_trading_authorized = 0
        account.updated_at = (
            datetime.utcnow()
        )

        db.commit()
        db.refresh(account)

        return {
            "status": "live_revoked",
            "account": _serialize(
                account
            ),
            "live_authorized": False,
            "positions_closed": False,
        }

    finally:
        db.close()
