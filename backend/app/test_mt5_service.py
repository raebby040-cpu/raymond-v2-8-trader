"""
RAYMOND v2.8 - MetaTrader 5 Connection and Market Data Service

Step 2:
- Connect to MT5
- Verify account and terminal
- Read live ticks
- Discover broker symbols
- Read live OHLC candles
- Read open positions
- Provide connection heartbeat

IMPORTANT:
This module does NOT place, modify, or close trades.
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
            timeout_ms=int(
                os.getenv("MT5_TIMEOUT_MS", "60000")
            ),
            portable=os.getenv(
                "MT5_PORTABLE",
                "false",
            ).lower() == "true",
        )


class MT5Service:
    """
    Safe wrapper around the MetaTrader5 Python API.

    Step 2 contains market-data reads only.
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
                "Install it in the environment where the MT5 "
                "terminal runs."
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

    # ========================================================
    # INITIALIZE
    # ========================================================

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
                f"MT5 initialization failed: "
                f"{self._last_error()}"
            )

        account = mt5.account_info()
        terminal = mt5.terminal_info()

        if account is None:
            self._connected = False

            raise MT5ServiceError(
                "MT5 account verification failed: "
                f"{self._last_error()}"
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
        return await asyncio.to_thread(
            self._initialize_sync
        )

    # ========================================================
    # SHUTDOWN
    # ========================================================

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
        return await asyncio.to_thread(
            self._shutdown_sync
        )

    # ========================================================
    # ACCOUNT
    # ========================================================

    def _account_info_sync(self) -> Dict[str, Any]:
        self._require_package()

        account = mt5.account_info()

        if account is None:
            self._connected = False

            raise MT5ServiceError(
                "MT5 account_info failed: "
                f"{self._last_error()}"
            )

        return self._to_dict(account)

    async def get_account_info(self) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._account_info_sync
        )

    # ========================================================
    # TERMINAL
    # ========================================================

    def _terminal_info_sync(self) -> Dict[str, Any]:
        self._require_package()

        terminal = mt5.terminal_info()

        if terminal is None:
            raise MT5ServiceError(
                "MT5 terminal_info failed: "
                f"{self._last_error()}"
            )

        return self._to_dict(terminal)

    async def get_terminal_info(self) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._terminal_info_sync
        )

    # ========================================================
    # SYMBOL DISCOVERY
    # ========================================================

    def _symbols_sync(
        self,
        query: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        self._require_package()

        if query:
            symbols = mt5.symbols_get(
                group=f"*{query.upper()}*"
            )
        else:
            symbols = mt5.symbols_get()

        if symbols is None:
            raise MT5ServiceError(
                "MT5 symbols_get failed: "
                f"{self._last_error()}"
            )

        result = []

        for symbol in symbols:
            data = self._to_dict(symbol)

            result.append(
                {
                    "name": data.get("name"),
                    "description": data.get(
                        "description"
                    ),
                    "path": data.get("path"),
                    "currency_base": data.get(
                        "currency_base"
                    ),
                    "currency_profit": data.get(
                        "currency_profit"
                    ),
                    "digits": data.get("digits"),
                    "point": data.get("point"),
                    "visible": data.get("visible"),
                    "select": data.get("select"),
                    "trade_mode": data.get(
                        "trade_mode"
                    ),
                }
            )

        return result

    async def get_symbols(
        self,
        query: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """
        Return symbols available from the connected broker.

        Example queries:
        XAU
        GOLD
        EURUSD
        """
        return await asyncio.to_thread(
            self._symbols_sync,
            query,
        )

    def _find_gold_symbols_sync(
        self,
    ) -> list[Dict[str, Any]]:
        self._require_package()

        symbols = mt5.symbols_get()

        if symbols is None:
            raise MT5ServiceError(
                "Unable to discover broker symbols: "
                f"{self._last_error()}"
            )

        candidates = []

        for symbol in symbols:
            data = self._to_dict(symbol)
            name = str(
                data.get("name") or ""
            ).upper()
            description = str(
                data.get("description") or ""
            ).upper()

            score = 0

            if name == "XAUUSD":
                score += 100

            if "XAUUSD" in name:
                score += 80

            if "XAU" in name:
                score += 50

            if "GOLD" in name:
                score += 40

            if "GOLD" in description:
                score += 20

            if score <= 0:
                continue

            candidates.append(
                {
                    "name": data.get("name"),
                    "description": data.get(
                        "description"
                    ),
                    "score": score,
                    "visible": data.get(
                        "visible"
                    ),
                    "select": data.get(
                        "select"
                    ),
                    "digits": data.get(
                        "digits"
                    ),
                    "point": data.get(
                        "point"
                    ),
                }
            )

        candidates.sort(
            key=lambda item: (
                -item["score"],
                str(item["name"]),
            )
        )

        return candidates

    async def find_gold_symbols(
        self,
    ) -> list[Dict[str, Any]]:
        """
        Discover broker-specific gold/XAUUSD symbols.
        """
        return await asyncio.to_thread(
            self._find_gold_symbols_sync
        )

    # ========================================================
    # CURRENT TICK
    # ========================================================

    def _tick_sync(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        self._require_package()

        symbol = symbol.strip()

        if not symbol:
            raise MT5ServiceError(
                "Symbol is required"
            )

        if not mt5.symbol_select(
            symbol,
            True,
        ):
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

        data = self._to_dict(tick)

        bid = float(data.get("bid") or 0.0)
        ask = float(data.get("ask") or 0.0)

        last = float(
            data.get("last") or 0.0
        )

        if last <= 0:
            last = (
                (bid + ask) / 2
                if bid > 0 and ask > 0
                else 0.0
            )

        spread = (
            ask - bid
            if ask > 0 and bid > 0
            else 0.0
        )

        return {
            "symbol": symbol,
            "time": data.get("time"),
            "time_msc": data.get(
                "time_msc"
            ),
            "bid": bid,
            "ask": ask,
            "last": last,
            "spread": spread,
            "volume": data.get(
                "volume"
            ),
            "volume_real": data.get(
                "volume_real"
            ),
            "flags": data.get("flags"),
        }

    async def get_symbol_tick(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._tick_sync,
            symbol,
        )

    # ========================================================
    # OHLC CANDLES
    # ========================================================

    def _timeframe_value(
        self,
        timeframe: str,
    ):
        self._require_package()

        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M2": mt5.TIMEFRAME_M2,
            "M3": mt5.TIMEFRAME_M3,
            "M4": mt5.TIMEFRAME_M4,
            "M5": mt5.TIMEFRAME_M5,
            "M6": mt5.TIMEFRAME_M6,
            "M10": mt5.TIMEFRAME_M10,
            "M12": mt5.TIMEFRAME_M12,
            "M15": mt5.TIMEFRAME_M15,
            "M20": mt5.TIMEFRAME_M20,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H2": mt5.TIMEFRAME_H2,
            "H3": mt5.TIMEFRAME_H3,
            "H4": mt5.TIMEFRAME_H4,
            "H6": mt5.TIMEFRAME_H6,
            "H8": mt5.TIMEFRAME_H8,
            "H12": mt5.TIMEFRAME_H12,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }

        normalized = timeframe.strip().upper()

        if normalized not in mapping:
            raise MT5ServiceError(
                f"Unsupported timeframe: {timeframe}"
            )

        return mapping[normalized]

    def _candles_sync(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[Dict[str, Any]]:
        self._require_package()

        if not symbol:
            raise MT5ServiceError(
                "Symbol is required"
            )

        if limit < 1 or limit > 5000:
            raise MT5ServiceError(
                "limit must be between 1 and 5000"
            )

        symbol = symbol.strip()

        if not mt5.symbol_select(
            symbol,
            True,
        ):
            raise MT5ServiceError(
                f"Unable to select symbol {symbol}: "
                f"{self._last_error()}"
            )

        timeframe_value = self._timeframe_value(
            timeframe
        )

        rates = mt5.copy_rates_from_pos(
            symbol,
            timeframe_value,
            0,
            limit,
        )

        if rates is None:
            raise MT5ServiceError(
                f"Unable to read candles for {symbol}: "
                f"{self._last_error()}"
            )

        candles = []

        for rate in rates:
            candles.append(
                {
                    "time": int(
                        rate["time"]
                    ),
                    "open": float(
                        rate["open"]
                    ),
                    "high": float(
                        rate["high"]
                    ),
                    "low": float(
                        rate["low"]
                    ),
                    "close": float(
                        rate["close"]
                    ),
                    "tick_volume": int(
                        rate["tick_volume"]
                    ),
                    "spread": int(
                        rate["spread"]
                    ),
                    "real_volume": int(
                        rate["real_volume"]
                    ),
                }
            )

        return candles

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "H1",
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        return await asyncio.to_thread(
            self._candles_sync,
            symbol,
            timeframe,
            limit,
        )

    # ========================================================
    # OPEN POSITIONS
    # ========================================================

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
                "MT5 positions_get failed: "
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
        return await asyncio.to_thread(
            self._positions_sync,
            symbol,
        )

    # ========================================================
    # HEARTBEAT
    # ========================================================

    def _heartbeat_sync(
        self,
    ) -> Dict[str, Any]:
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
            "account_login": getattr(
                account,
                "login",
                None,
            ),
            "server": getattr(
                account,
                "server",
                None,
            ),
            "trade_allowed": getattr(
                terminal,
                "trade_allowed",
                None,
            ),
            "tradeapi_disabled": getattr(
                terminal,
                "tradeapi_disabled",
                None,
            ),
        }

    async def heartbeat(
        self,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._heartbeat_sync
        )


# Global service instance.
mt5_service = MT5Service()
