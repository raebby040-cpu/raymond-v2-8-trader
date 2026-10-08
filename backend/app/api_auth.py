"""
RAYMOND v2.8 API Authentication

Private API authentication for broker/execution endpoints.

Security rules:
- Disabled by default only for local development.
- Production must provide RAYMOND_API_AUTH_TOKEN.
- Token must be at least 32 characters.
- Uses constant-time comparison.
- Never logs or returns the token.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


TOKEN_ENV = "RAYMOND_API_AUTH_TOKEN"
MIN_TOKEN_LENGTH = 32


def _configured_token() -> str:
    token = os.getenv(TOKEN_ENV, "").strip()

    if not token:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "API_AUTH_NOT_CONFIGURED",
                "message": (
                    "RAYMOND_API_AUTH_TOKEN is not configured."
                ),
            },
        )

    if len(token) < MIN_TOKEN_LENGTH:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "API_AUTH_TOKEN_TOO_SHORT",
                "message": (
                    "RAYMOND_API_AUTH_TOKEN must contain at least "
                    f"{MIN_TOKEN_LENGTH} characters."
                ),
            },
        )

    return token


async def require_api_auth(
    authorization: str | None = Header(
        default=None,
    ),
) -> dict:
    """
    Require:

        Authorization: Bearer <token>
    """

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "AUTHENTICATION_REQUIRED",
                "message": "Bearer authentication is required.",
            },
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    scheme, separator, supplied = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not supplied.strip()
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "INVALID_AUTHORIZATION_HEADER",
                "message": (
                    "Authorization must use Bearer authentication."
                ),
            },
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    expected = _configured_token()

    if not hmac.compare_digest(
        supplied.strip(),
        expected,
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "INVALID_API_TOKEN",
                "message": "API authentication failed.",
            },
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return {
        "authenticated": True,
    }


__all__ = [
    "require_api_auth",
              ]
