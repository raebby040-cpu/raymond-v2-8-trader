"""
RAYMOND v2.8 - MetaTrader 5 Connection Service

Step 1A:
- Connect to MT5
- Verify the trading account
- Read terminal/account information
- Read market ticks
- Read open positions
- Provide connection heartbeat

IMPORTANT:
This module does NOT place, modify, or close trades.
Trade execution will be added later behind the risk/execution gateway.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


class MT5ServiceError(RuntimeError):
    """Raised when an MT5 operation fails."""


class MT5ConnectionConfig:
    def __init__(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        terminal_path: Optional[str] = None,
        timeout_ms: int = 60000,
        portable: bool = False,
    ):
        self.login = login
        self.password = password
        self.server = server
        self.terminal_path = terminal_path
        self.timeout_ms = timeout_ms
        self.portable = portable

    @classmethod
    def from_env(cls) -> "MT5ConnectionConfig":
        raw_login = os.getenv("MT5_LOGIN") or os.getenv("MT5_ACCOUNT")

        login = None

        if raw_login:
            try:
                login = int(raw_login)
            except ValueError as exc:
                raise ValueError(
                    "MT5_LOGIN must be a numeric account login"
                ) from exc

        return cls(
            login=login,
            password=os.getenv("MT5_PASSWORD"),
            server=os.getenv("MT5_SERVER"),
            terminal_path=os.getenv("MT5_TERMINAL_PATH"),
            timeout_ms=int(os.getenv("MT5_TIMEOUT_MS", "60000")),
            portable=os.getenv("MT5_PORTABLE", "false").lower() == "true",
        )


class MT5Service:
    """
    Safe wrapper around the MetaTrader5 Python API.

    Step 1A intentionally contains no trading execution methods.
    """

    def __init__(
        self,
        config: Optional[MT5ConnectionConfig] = None,
    ):
        self.config = config or MT5ConnectionConfig.from_env()

        self._connected = False
        self._last_connected_at: Optional[datetime] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _require_package(self):
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed. "
                "Install it in the environment where the MT5 terminal runs."
            )

    def _last_error(self) -> str:
        if mt5 is None:
            return "MetaTrader5 package unavailable"

        try:
            return str(mt5.last_error())
        except Exception:
            return "Unknown MetaTrader5 error"

    @staticmethod
    def _to_dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}

        if hasattr(value, "_asdict"):
            return dict(value._asdict())

        if hasattr(value, "__dict__"):
            return dict(value.__dict__)

        return {"value": value}

    # ---------------------------------------------------------
    # INITIALIZE
    # ---------------------------------------------------------

    def _initialize_sync(self) -> Dict[str, Any]:
        self._require_package()

        kwargs: Dict[str, Any] = {
            "timeout": self.config.timeout_ms,
            "portable": self.config.portable,
        }

        if self.config.login is not None:
            kwargs["login"] = self.config.login

        if self.config.password:
            kwargs["password"] = self.config.password

        if self.config.server:
            kwargs["server"] = self.config.server

        if self.config.terminal_path:
            initialized = mt5.initialize(
                self.config.terminal_path,
                **kwargs,
            )
        else:
            initialized = mt5.initialize(**kwargs)

        if not initialized:
            self._connected = False

            raise MT5ServiceError(
                f"MT5 initialization failed: {self._last_error()}"
            )

        account = mt5.account_info()
        terminal = mt5.terminal_info()

        if account is None:
            self._connected = False

            raise MT5ServiceError(
                f"MT5 account verification failed: {self._last_error()}"
            )

        self._connected = True
        self._last_connected_at = datetime.now(timezone.utc)

        return {
            "connected": True,
            "timestamp": self._timestamp(),
            "account": self._to_dict(account),
            "terminal": self._to_dict(terminal),
        }

    async def initialize(self) -> Dict[str, Any]:
        """
        Connect to MT5 and verify that an account is available.
        """

        return await asyncio.to_thread(
            self._initialize_sync
        )

    # ---------------------------------------------------------
    # SHUTDOWN
    # ---------------------------------------------------------

    def _shutdown_sync(self) -> bool:
        if mt5 is None:
            self._connected = False
            return True

        try:
            mt5.shutdown()
        finally:
            self._connected = False

        return True

    async def shutdown(self) -> bool:
        """
        Disconnect from MT5.
        """

        return await asyncio.to_thread(
            self._shutdown_sync
        )

    # ---------------------------------------------------------
    # ACCOUNT
    # ---------------------------------------------------------

    def _account_info_sync(self) -> Dict[str, Any]:
        self._require_package()

        account = mt5.account_info()

        if account is None:
            self._connected = False

            raise MT5ServiceError(
                f"MT5 account_info failed: {self._last_error()}"
            )

        return self._to_dict(account)

    async def get_account_info(self) -> Dict[str, Any]:
        """
        Return current MT5 account information.
        """

        return await asyncio.to_thread(
            self._account_info_sync
        )

    # ---------------------------------------------------------
    # TERMINAL
    # ---------------------------------------------------------

    def _terminal_info_sync(self) -> Dict[str, Any]:
        self._require_package()

        terminal = mt5.terminal_info()

        if terminal is None:
            raise MT5ServiceError(
                f"MT5 terminal_info failed: {self._last_error()}"
            )

        return self._to_dict(terminal)

    async def get_terminal_info(self) -> Dict[str, Any]:
        """
        Return MT5 terminal status.
        """

        return await asyncio.to_thread(
            self._terminal_info_sync
        )

    # ---------------------------------------------------------
    # MARKET TICK
    # ---------------------------------------------------------

    def _tick_sync(self, symbol: str) -> Dict[str, Any]:
        self._require_package()

        symbol = symbol.upper()

        if not mt5.symbol_select(symbol, True):
            raise MT5ServiceError(
                f"Unable to select symbol {symbol}: "
                f"{self._last_error()}"
            )

        tick = mt5.symbol_info_tick(symbol)

        if tick is None:
            raise MT5ServiceError(
                f"Unable to read tick for {symbol}: "
                f"{self._last_error()}"
            )

        return self._to_dict(tick)

    async def get_symbol_tick(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Return the current bid/ask tick.
        """

        if not symbol:
            raise ValueError("symbol is required")

        return await asyncio.to_thread(
            self._tick_sync,
            symbol,
        )

    # ---------------------------------------------------------
    # OPEN POSITIONS
    # ---------------------------------------------------------

    def _positions_sync(
        self,
        symbol: Optional[str] = None,
    ) -> list[Dict[str, Any]]:

        self._require_package()

        if symbol:
            positions = mt5.positions_get(
                symbol=symbol.upper()
            )
        else:
            positions = mt5.positions_get()

        if positions is None:
            raise MT5ServiceError(
                f"MT5 positions_get failed: "
                f"{self._last_error()}"
            )

        return [
            self._to_dict(position)
            for position in positions
        ]

    async def get_positions(
        self,
        symbol: Optional[str] = None,
    ) -> list[Dict[str, Any]]:

        """
        Read open MT5 positions.

        This method does not modify positions.
        """

        return await asyncio.to_thread(
            self._positions_sync,
            symbol,
        )

    # ---------------------------------------------------------
    # HEARTBEAT
    # ---------------------------------------------------------

    def _heartbeat_sync(self) -> Dict[str, Any]:
        self._require_package()

        terminal = mt5.terminal_info()
        account = mt5.account_info()

        connected = (
            terminal is not None
            and account is not None
        )

        self._connected = connected

        return {
            "connected": connected,
            "timestamp": self._timestamp(),
            "last_error": (
                None
                if connected
                else self._last_error()
            ),
            "account_login": (
                getattr(account, "login", None)
            ),
            "server": (
                getattr(account, "server", None)
            ),
            "trade_allowed": (
                getattr(
                    terminal,
                    "trade_allowed",
                    None,
                )
            ),
            "tradeapi_disabled": (
                getattr(
                    terminal,
                    "tradeapi_disabled",
                    None,
                )
            ),
        }

    async def heartbeat(self) -> Dict[str, Any]:
        """
        Check whether MT5 and the account are reachable.
        """

        return await asyncio.to_thread(
            self._heartbeat_sync
        )


# One service instance for the FastAPI application.
mt5_service = MT5Service()
