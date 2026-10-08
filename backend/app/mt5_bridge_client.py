"""
Raymond v2.8 - Remote MT5 Bridge Client
========================================

Render-side client for communicating with the separate MT5 execution bridge.

The actual MetaTrader 5 terminal does NOT run inside the Render container.

Architecture:

    Raymond Backend (Render)
            |
            | authenticated HTTPS
            v
    MT5 Execution Bridge
            |
            v
    MetaTrader 5 Terminal
            |
            v
    Broker DEMO account

Safety:
- Bridge is optional.
- No bridge = no broker execution.
- Requests fail closed.
- This client does not enable live trading.
- DEMO/REAL authorization remains enforced by the execution layers.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx


class MT5BridgeError(RuntimeError):
    """Raised when the remote MT5 bridge cannot complete an operation."""


class MT5BridgeClient:
    """Authenticated client for the Raymond MT5 execution bridge."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("MT5_BRIDGE_URL", "")
        ).strip().rstrip("/")

        self.api_key = (
            api_key
            or os.getenv("MT5_BRIDGE_API_KEY", "")
        ).strip()

        self.timeout = timeout or float(
            os.getenv("MT5_BRIDGE_TIMEOUT_SECONDS", "10")
        )

    @property
    def configured(self) -> bool:
        """Return whether a bridge URL and API key are configured."""
        return bool(
            self.base_url
            and self.api_key
        )

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise MT5BridgeError(
                "MT5 bridge API key is not configured."
            )

        return {
            "X-MT5-Bridge-Key": self.api_key,
            "Accept": "application/json",
        }

    def _require_configured(self) -> None:
        if not self.base_url:
            raise MT5BridgeError(
                "MT5 bridge URL is not configured."
            )

        if not self.api_key:
            raise MT5BridgeError(
                "MT5 bridge API key is not configured."
            )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self._require_configured()

        url = f"{self.base_url}{path}"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(),
                    **kwargs,
                )
        except httpx.TimeoutException as exc:
            raise MT5BridgeError(
                "MT5 bridge request timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise MT5BridgeError(
                f"Unable to reach MT5 bridge: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {
                "detail": response.text
            }

        if response.status_code >= 400:
            detail = payload.get(
                "detail",
                f"HTTP {response.status_code}",
            )

            raise MT5BridgeError(
                f"MT5 bridge rejected request: {detail}"
            )

        if not isinstance(payload, dict):
            raise MT5BridgeError(
                "MT5 bridge returned an invalid response."
            )

        return payload

    async def health(self) -> dict[str, Any]:
        """
        Read public bridge health.

        This endpoint does not require the bridge API key.
        """
        if not self.base_url:
            return {
                "available": False,
                "configured": False,
                "reason": "MT5 bridge URL is not configured",
            }

        url = f"{self.base_url}/health"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.get(url)

            if response.status_code >= 400:
                return {
                    "available": False,
                    "configured": True,
                    "status_code": response.status_code,
                    "reason": response.text,
                }

            payload = response.json()

            if not isinstance(payload, dict):
                return {
                    "available": False,
                    "configured": True,
                    "reason": "Invalid bridge health response",
                }

            return {
                "available": True,
                "configured": True,
                "bridge": payload,
            }

        except (httpx.RequestError, ValueError):
            return {
                "available": False,
                "configured": True,
                "reason": "MT5 bridge is unreachable",
            }

    async def status(self) -> dict[str, Any]:
        """Read authenticated bridge and MT5 status."""
        return await self._request(
            "GET",
            "/api/status",
        )

    async def account(self) -> dict[str, Any]:
        """Read the connected MT5 DEMO account."""
        return await self._request(
            "GET",
            "/api/account",
        )

    async def symbol(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """Read broker-specific symbol specification."""
        if not symbol.strip():
            raise MT5BridgeError(
                "Symbol cannot be empty."
            )

        return await self._request(
            "GET",
            f"/api/symbol/{symbol.strip()}",
        )

    async def tick(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """Read the current MT5 market tick."""
        if not symbol.strip():
            raise MT5BridgeError(
                "Symbol cannot be empty."
            )

        return await self._request(
            "GET",
            f"/api/tick/{symbol.strip()}",
        )

    async def positions(self) -> dict[str, Any]:
        """Read current MT5 positions."""
        return await self._request(
            "GET",
            "/api/positions",
        )

    async def last_error(self) -> dict[str, Any]:
        """Read the latest MT5 bridge error."""
        return await self._request(
            "GET",
            "/api/last-error",
        )

    async def verify_demo_connection(
        self,
        symbol: str = "XAUUSD",
    ) -> dict[str, Any]:
        """
        Perform a read-only DEMO connectivity verification.

        No order is submitted.
        """
        health = await self.health()

        if not health.get("available"):
            return {
                "verified": False,
                "stage": "bridge_health",
                "reason": health.get(
                    "reason",
                    "MT5 bridge unavailable",
                ),
            }

        try:
            status = await self.status()
        except MT5BridgeError as exc:
            return {
                "verified": False,
                "stage": "bridge_status",
                "reason": str(exc),
            }

        account = status.get("account") or {}

        if account.get("is_demo") is not True:
            return {
                "verified": False,
                "stage": "account",
                "reason": (
                    "Connected MT5 account is not verified as DEMO."
                ),
                "status": status,
            }

        if status.get("real_accounts_allowed") is not False:
            return {
                "verified": False,
                "stage": "safety",
                "reason": (
                    "Bridge did not report REAL accounts as blocked."
                ),
                "status": status,
            }

        try:
            symbol_info = await self.symbol(symbol)
            tick_info = await self.tick(symbol)
        except MT5BridgeError as exc:
            return {
                "verified": False,
                "stage": "market",
                "reason": str(exc),
            }

        bid = tick_info.get("bid")
        ask = tick_info.get("ask")

        if not isinstance(bid, (int, float)):
            return {
                "verified": False,
                "stage": "tick",
                "reason": "Invalid bid price.",
            }

        if not isinstance(ask, (int, float)):
            return {
                "verified": False,
                "stage": "tick",
                "reason": "Invalid ask price.",
            }

        if bid <= 0 or ask <= 0:
            return {
                "verified": False,
                "stage": "tick",
                "reason": "Invalid non-positive market price.",
            }

        return {
            "verified": True,
            "stage": "complete",
            "demo_account": True,
            "real_accounts_allowed": False,
            "account": account,
            "symbol": symbol_info,
            "tick": tick_info,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

mt5_bridge_client = MT5BridgeClient()
