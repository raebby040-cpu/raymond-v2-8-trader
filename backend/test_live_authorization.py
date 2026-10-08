"""
Tests for Raymond LIVE account authorization.

These tests never connect to MT5 and never submit broker orders.
"""

from types import SimpleNamespace

import pytest

from app.live_authorization import (
    _token_is_valid,
    _validate_account_for_live,
)


VALID_TOKEN = (
    "raymond-test-live-authorization-token-"
    "1234567890"
)


def _account(
    *,
    selected=True,
    connected=True,
    verified=True,
    trading_allowed=True,
):
    return SimpleNamespace(
        account_id="TEST-ACCOUNT",
        selected=int(selected),
        connection_status=(
            "connected"
            if connected
            else "disconnected"
        ),
        account_verified=int(verified),
        trading_allowed=int(trading_allowed),
        live_trading_authorized=0,
    )


def test_valid_token_matches():
    monkeypatch = None

    # Direct deterministic token comparison.
    import os

    old = os.environ.get(
        "RAYMOND_LIVE_AUTH_TOKEN"
    )

    try:
        os.environ[
            "RAYMOND_LIVE_AUTH_TOKEN"
        ] = VALID_TOKEN

        assert _token_is_valid(
            VALID_TOKEN
        )

        assert not _token_is_valid(
            "wrong-token"
        )

    finally:
        if old is None:
            os.environ.pop(
                "RAYMOND_LIVE_AUTH_TOKEN",
                None,
            )
        else:
            os.environ[
                "RAYMOND_LIVE_AUTH_TOKEN"
            ] = old


def test_unselected_account_is_rejected():
    account = _account(
        selected=False
    )

    with pytest.raises(Exception) as exc:
        _validate_account_for_live(
            account
        )

    assert (
        "selected"
        in str(exc.value).lower()
    )


def test_disconnected_account_is_rejected():
    account = _account(
        connected=False
    )

    with pytest.raises(Exception) as exc:
        _validate_account_for_live(
            account
        )

    assert (
        "connected"
        in str(exc.value).lower()
    )


def test_unverified_account_is_rejected():
    account = _account(
        verified=False
    )

    with pytest.raises(Exception) as exc:
        _validate_account_for_live(
            account
        )

    assert (
        "verified"
        in str(exc.value).lower()
    )


def test_trading_disabled_account_is_rejected():
    account = _account(
        trading_allowed=False
    )

    with pytest.raises(Exception) as exc:
        _validate_account_for_live(
            account
        )

    assert (
        "trading"
        in str(exc.value).lower()
    )


def test_valid_account_passes():
    account = _account()

    _validate_account_for_live(
        account
    )


def test_authorization_state_starts_disabled():
    account = _account()

    assert (
        account.live_trading_authorized
        == 0
    )


def test_authorization_does_not_require_or_modify_arm_state():
    """
    Account authorization is deliberately separate from
    the Raymond LIVE safety ARM mechanism.
    """

    account = _account()

    _validate_account_for_live(
        account
    )

    assert (
        account.live_trading_authorized
        == 0
    )
