"""
RAYMOND v2.8 - Exness API Connector

Demo-first Exness API transport layer.

IMPORTANT:
- This connector does NOT replace the existing MT5 connector.
- Demo-only mode is enabled by default.
- API credentials must come from environment variables.
- Never put an Exness API token in GitHub or source code.
- Endpoint paths are configurable because the exact API endpoints must
  come from Exness documentation/account access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


class ExnessAPIError(RuntimeError):
    """Raised when an Exness API operation cannot be completed."""


@dataclass(frozen=True)
class ExnessAPIConfig:
    """Configuration for the Exness API connector."""

    enabled: bool = False
    demo_only: bool = True
    api_token: Optional[str] = None
    account_id: Optional[str] = None
    account_type: str = "demo"

    base_url: str = ""

    health_path: str = ""
    account_path: str = ""
    positions_path: str = ""
    quote_path: str = ""
    order_path: str = ""
    close_path: str = ""
    modify_path: str = ""

    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "ExnessAPIConfig":
        """Build configuration from environment variables."""

        enabled = os.getenv(
            "EXNESS_API_ENABLED",
            "false",
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        demo_only = os.getenv(
            "EXNESS_DEMO_ONLY",
            "true",
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        return cls(
            enabled=enabled,
            demo_only=demo_only,
            api_token=os.getenv("EXNESS_API_TOKEN"),
            account_id=os.getenv("EXNESS_ACCOUNT_ID"),
            account_type=os.getenv(
                "EXNESS_ACCOUNT_TYPE",
                "demo",
            ).strip().lower(),
            base_url=os.getenv(
                "EXNESS_API_BASE_URL",
                "",
            ).strip().rstrip("/"),
            health_path=os.getenv(
                "EXNESS_API_HEALTH_PATH",
                "",
            ).strip(),
            account_path=os.getenv(
                "EXNESS_API_ACCOUNT_PATH",
                "",
            ).strip(),
            positions_path=os.getenv(
                "EXNESS_API_POSITIONS_PATH",
                "",
            ).strip(),
            quote_path=os.getenv(
                "EXNESS_API_QUOTE_PATH",
                "",
            ).strip(),
            order_path=os.getenv(
                "EXNESS_API_ORDER_PATH",
                "",
            ).strip(),
            close_path=os.getenv(
                "EXNESS_API_CLOSE_PATH",
                "",
            ).strip(),
            modify_path=os.getenv(
                "EXNESS_API_MODIFY_PATH",
                "",
            ).strip(),
            timeout_seconds=float(
                os.getenv(
                    "EXNESS_API_TIMEOUT_SECONDS",
                    "10",
                )
            ),
        )


class ExnessAPIClient:
    """
    Exness API client used by RAYMOND.

    This class deliberately keeps the transport layer separate from
    the existing MT5 service and the RAYMOND trading pipeline.

    Live execution is not enabled by this connector.
    """

    def __init__(
        self,
        config: Optional[ExnessAPIConfig] = None,
    ) -> None:
        self.config = config or ExnessAPIConfig.from_env()

    def _ensure_enabled(self) -> None:
        """Validate basic connector configuration."""

        if not self.config.enabled:
            raise ExnessAPIError(
                "Exness API connector is disabled. "
                "Set EXNESS_API_ENABLED=true after configuration."
            )

        if not self.config.api_token:
            raise ExnessAPIError(
                "EXNESS_API_TOKEN is not configured. "
                "Never put the token in source code or GitHub."
            )

        if not self.config.base_url:
            raise ExnessAPIError(
                "EXNESS_API_BASE_URL is not configured."
            )

    def _path(
        self,
        configured_path: str,
        operation: str,
    ) -> str:
        """Require an explicitly configured API endpoint."""

        if not configured_path:
            raise ExnessAPIError(
                f"Exness {operation} endpoint is not configured. "
                "Use the endpoint documented by Exness."
            )

        return configured_path

    def _url(self, path: str) -> str:
        """Build an absolute endpoint URL."""

        if path.startswith(
            (
                "http://",
                "https://",
            )
        ):
            return path

        return (
            f"{self.config.base_url}/"
            f"{path.lstrip('/')}"
        )

    def _headers(self) -> Dict[str, str]:
        """Build authenticated HTTP headers."""

        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": (
                f"Bearer {self.config.api_token}"
            ),
            "User-Agent": (
                "RAYMOND-v2.8-Exness-Connector/1.0"
            ),
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send one authenticated API request."""

        self._ensure_enabled()

        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds
            ) as client:
                response = await client.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=json,
                    params=params,
                )
        except httpx.RequestError as exc:
            raise ExnessAPIError(
                f"Exness API network error: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {
                "raw": response.text,
            }

        if response.status_code >= 400:
            raise ExnessAPIError(
                "Exness API returned "
                f"HTTP {response.status_code}: {payload}"
            )

        if isinstance(payload, dict):
            return payload

        return {
            "data": payload,
        }

    async def health(self) -> Dict[str, Any]:
        """Check Exness API connectivity."""

        return await self._request(
            "GET",
            self._path(
                self.config.health_path,
                "health",
            ),
        )

    async def get_account_info(self) -> Dict[str, Any]:
        """Retrieve account information."""

        return await self._request(
            "GET",
            self._path(
                self.config.account_path,
                "account",
            ),
        )

    async def get_open_positions(self) -> Dict[str, Any]:
        """Retrieve open positions."""

        return await self._request(
            "GET",
            self._path(
                self.config.positions_path,
                "positions",
            ),
        )

    async def get_quote(
        self,
        symbol: str = "XAUUSD",
    ) -> Dict[str, Any]:
        """Retrieve a market quote."""

        return await self._request(
            "GET",
            self._path(
                self.config.quote_path,
                "quote",
            ),
            params={
                "symbol": symbol,
            },
        )

    def _ensure_trade_safety(self) -> None:
        """
        Prevent accidental live execution.

        During Step 11A, demo-only mode must remain enabled.
        """

        if (
            self.config.demo_only
            and self.config.account_type != "demo"
        ):
            raise ExnessAPIError(
                "Demo-only mode is enabled, but "
                "EXNESS_ACCOUNT_TYPE is not 'demo'."
            )

        live_enabled = os.getenv(
            "LIVE_TRADING_ENABLED",
            "false",
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        if (
            not self.config.demo_only
            and not live_enabled
        ):
            raise ExnessAPIError(
                "Live trading is disabled by RAYMOND. "
                "Refusing the operation."
            )

    async def place_order(
        self,
        order: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Place an Exness order.

        This method remains protected by demo/live safety gates.
        """

        self._ensure_enabled()
        self._ensure_trade_safety()

        if not isinstance(order, dict) or not order:
            raise ExnessAPIError(
                "Order payload must be a non-empty object."
            )

        return await self._request(
            "POST",
            self._path(
                self.config.order_path,
                "order",
            ),
            json=order,
        )

    async def close_position(
        self,
        position_id: str,
    ) -> Dict[str, Any]:
        """Close an Exness position."""

        self._ensure_enabled()
        self._ensure_trade_safety()

        if not position_id:
            raise ExnessAPIError(
                "position_id is required."
            )

        return await self._request(
            "POST",
            self._path(
                self.config.close_path,
                "close",
            ),
            json={
                "position_id": position_id,
            },
        )

    async def modify_position(
        self,
        position_id: str,
        *,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Modify stop-loss and/or take-profit."""

        self._ensure_enabled()
        self._ensure_trade_safety()

        if not position_id:
            raise ExnessAPIError(
                "position_id is required."
            )

        if (
            stop_loss is None
            and take_profit is None
        ):
            raise ExnessAPIError(
                "At least one of stop_loss or "
                "take_profit is required."
            )

        payload: Dict[str, Any] = {
            "position_id": position_id,
        }

        if stop_loss is not None:
            payload["stop_loss"] = stop_loss

        if take_profit is not None:
            payload["take_profit"] = take_profit

        return await self._request(
            "POST",
            self._path(
                self.config.modify_path,
                "modify",
            ),
            json=payload,
        )


exness_api_client = ExnessAPIClient()
