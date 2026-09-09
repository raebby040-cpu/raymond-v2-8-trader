"""
MetaTrader 5 connection service for Raymond V2.8 Trader.

Step 1A:
- Connect to an installed MetaTrader 5 terminal.
- Read account information.
- Read terminal information.
- Read symbol ticks.
- Read open positions.
- Provide a simple heartbeat.

IMPORTANT:
This file does NOT place, modify, or close trades.
Live trading remains disabled until the execution gateway is
implemented and explicitly enabled.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


class MT5ServiceError(Exception):
    """Raised when an MT5 service operation fails."""


@dataclass
class MT5ConnectionConfig:
    """Configuration used to connect to MetaTrader 5."""

    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    terminal_path: Optional[str] = None
    timeout_ms: int = 60000
    portable: bool = False

    @classmethod
    def from_environment(cls) -> "MT5ConnectionConfig":
        """Load MT5 configuration from environment variables."""

        login_raw = os.getenv("MT5_LOGIN") or os.getenv("MT5_ACCOUNT")

        login: Optional[int] = None

        if login_raw:
            try:
                login = int(login_raw)
            except ValueError as exc:
                raise MT5ServiceError(
                    "MT5_LOGIN/MT5_ACCOUNT must be a valid integer."
                ) from exc

        return cls(
            login=login,
            password=os.getenv("MT5_PASSWORD") or None,
            server=os.getenv("MT5_SERVER") or None,
            terminal_path=os.getenv("MT5_TERMINAL_PATH") or None,
            timeout_ms=int(os.getenv("MT5_TIMEOUT_MS", "60000")),
            portable=os.getenv("MT5_PORTABLE", "false").lower()
            in {"1", "true", "yes", "on"},
        )


class MT5Service:
    """
    Safe wrapper around the official MetaTrader5 Python package.

    This service only handles:
    - initialization
    - connection status
    - account information
    - terminal information
    - market tick information
    - open positions
    - heartbeat
    - shutdown

    It intentionally contains NO trade execution methods.
    """

    def __init__(self, config: Optional[MT5ConnectionConfig] = None):
        self.config = config or MT5ConnectionConfig.from_environment()
        self._connected = False

    @property
    def connected(self) -> bool:
        """Return whether this service believes MT5 is connected."""
        return self._connected

    def _require_package(self) -> None:
        """Make sure the MetaTrader5 package is installed."""

        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed. "
                "Install it with: pip install MetaTrader5"
            )

    async def initialize(self) -> dict[str, Any]:
        """
        Initialize and connect to MetaTrader 5.

        No trades are placed by this method.
        """

        self._require_package()

        def _initialize() -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "timeout": self.config.timeout_ms,
                "portable": self.config.portable,
            }

            if self.config.login is not None:
                kwargs["login"] = self.config.login

            if self.config.password:
                kwargs["password"] = self.config.password

            if self.config.server:
                kwargs["server"] = self.config.server

            try:
                if self.config.terminal_path:
                    success = mt5.initialize(
                        self.config.terminal_path,
                        **kwargs,
                    )
                else:
                    success = mt5.initialize(**kwargs)
            except Exception as exc:
                self._connected = False
                raise MT5ServiceError(
                    f"MT5 initialization failed: {exc}"
                ) from exc

            if not success:
                error = mt5.last_error()
                self._connected = False

                raise MT5ServiceError(
                    f"MT5 initialization failed: {error}"
                )

            account = mt5.account_info()

            if account is None:
                error = mt5.last_error()
                self._connected = False
                mt5.shutdown()

                raise MT5ServiceError(
                    f"MT5 connected but account information "
                    f"could not be retrieved: {error}"
                )

            self._connected = True

            return {
                "connected": True,
                "login": getattr(account, "login", None),
                "server": getattr(account, "server", None),
                "name": getattr(account, "name", None),
                "currency": getattr(account, "currency", None),
            }

        return await asyncio.to_thread(_initialize)

    async def shutdown(self) -> None:
        """Disconnect from MetaTrader 5."""

        if mt5 is None:
            self._connected = False
            return

        def _shutdown() -> None:
            try:
                mt5.shutdown()
            finally:
                self._connected = False

        await asyncio.to_thread(_shutdown)

    async def get_account_info(self) -> dict[str, Any]:
        """Return the current MT5 trading account information."""

        self._require_package()

        def _get_account_info() -> dict[str, Any]:
            account = mt5.account_info()

            if account is None:
                error = mt5.last_error()
                self._connected = False

                raise MT5ServiceError(
                    f"Could not retrieve MT5 account information: {error}"
                )

            self._connected = True

            return account._asdict()

        return await asyncio.to_thread(_get_account_info)

    async def get_terminal_info(self) -> dict[str, Any]:
        """Return information about the connected MT5 terminal."""

        self._require_package()

        def _get_terminal_info() -> dict[str, Any]:
            terminal = mt5.terminal_info()

            if terminal is None:
                error = mt5.last_error()

                raise MT5ServiceError(
                    f"Could not retrieve MT5 terminal information: {error}"
                )

            return terminal._asdict()

        return await asyncio.to_thread(_get_terminal_info)

    async def get_symbol_tick(self, symbol: str) -> dict[str, Any]:
        """
        Return the latest tick for a symbol.

        Example:
            XAUUSD
        """

        self._require_package()

        if not symbol or not symbol.strip():
            raise MT5ServiceError("Symbol cannot be empty.")

        symbol = symbol.strip().upper()

        def _get_tick() -> dict[str, Any]:
            tick = mt5.symbol_info_tick(symbol)

            if tick is None:
                error = mt5.last_error()

                raise MT5ServiceError(
                    f"Could not retrieve tick for {symbol}: {error}"
                )

            return tick._asdict()

        return await asyncio.to_thread(_get_tick)

    async def get_positions(
        self,
        symbol: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Return open MT5 positions.

        If symbol is supplied, only positions for that symbol
        are returned.
        """

        self._require_package()

        if symbol:
            symbol = symbol.strip().upper()

        def _get_positions() -> list[dict[str, Any]]:
            if symbol:
                positions = mt5.positions_get(symbol=symbol)
            else:
                positions = mt5.positions_get()

            if positions is None:
                error = mt5.last_error()

                # MT5 can return None when there are no positions
                # or when an error occurs. We expose the error clearly.
                raise MT5ServiceError(
                    f"Could not retrieve MT5 positions: {error}"
                )

            return [position._asdict() for position in positions]

        return await asyncio.to_thread(_get_positions)

    async def heartbeat(self) -> dict[str, Any]:
        """
        Check whether MT5 is responding.

        This does not place or modify any trades.
        """

        self._require_package()

        def _heartbeat() -> dict[str, Any]:
            terminal = mt5.terminal_info()
            account = mt5.account_info()

            if terminal is None or account is None:
                error = mt5.last_error()
                self._connected = False

                return {
                    "ok": False,
                    "connected": False,
                    "error": str(error),
                }

            self._connected = True

            return {
                "ok": True,
                "connected": True,
                "login": getattr(account, "login", None),
                "server": getattr(account, "server", None),
                "trade_allowed": getattr(
                    terminal,
                    "trade_allowed",
                    None,
                ),
            }

        return await asyncio.to_thread(_heartbeat)


# Process-level service instance.
#
# FastAPI will use this instance in Step 1B.
mt5_service = MT5Service()
