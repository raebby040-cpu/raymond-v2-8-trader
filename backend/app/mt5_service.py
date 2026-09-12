import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


class MT5ServiceError(RuntimeError):
    """Raised when an MT5 service operation cannot be completed."""


@dataclass
class MT5ConnectionConfig:
    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    terminal_path: Optional[str] = None
    timeout_ms: int = 60000
    portable: bool = False

    @classmethod
    def from_env(cls) -> "MT5ConnectionConfig":
        login_value = os.getenv("MT5_LOGIN") or os.getenv("MT5_ACCOUNT")

        login = None
        if login_value:
            login = int(login_value)

        timeout_ms = int(
            os.getenv("MT5_TIMEOUT_MS", "60000")
        )

        portable_value = os.getenv(
            "MT5_PORTABLE",
            "false",
        ).strip().lower()

        portable = portable_value in {
            "1",
            "true",
            "yes",
            "on",
        }

        return cls(
            login=login,
            password=os.getenv("MT5_PASSWORD"),
            server=os.getenv("MT5_SERVER"),
            terminal_path=os.getenv("MT5_TERMINAL_PATH"),
            timeout_ms=timeout_ms,
            portable=portable,
        )


class MT5Service:
    """Broker-neutral MT5 connection and market-data service."""

    TIMEFRAME_MAP = {
        "M1": "TIMEFRAME_M1",
        "M2": "TIMEFRAME_M2",
        "M3": "TIMEFRAME_M3",
        "M4": "TIMEFRAME_M4",
        "M5": "TIMEFRAME_M5",
        "M6": "TIMEFRAME_M6",
        "M10": "TIMEFRAME_M10",
        "M12": "TIMEFRAME_M12",
        "M15": "TIMEFRAME_M15",
        "M20": "TIMEFRAME_M20",
        "M30": "TIMEFRAME_M30",
        "H1": "TIMEFRAME_H1",
        "H2": "TIMEFRAME_H2",
        "H3": "TIMEFRAME_H3",
        "H4": "TIMEFRAME_H4",
        "H6": "TIMEFRAME_H6",
        "H8": "TIMEFRAME_H8",
        "H12": "TIMEFRAME_H12",
        "D1": "TIMEFRAME_D1",
        "W1": "TIMEFRAME_W1",
        "MN1": "TIMEFRAME_MN1",
    }

    def __init__(
        self,
        config: Optional[MT5ConnectionConfig] = None,
    ):
        self.config = config or MT5ConnectionConfig.from_env()
        self.connected = False

    @staticmethod
    def _to_dict(value: Any) -> dict:
        if value is None:
            return {}

        if hasattr(value, "_asdict"):
            return dict(value._asdict())

        if isinstance(value, dict):
            return dict(value)

        try:
            return dict(value)
        except (TypeError, ValueError):
            return {}

    async def initialize(self) -> bool:
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed."
            )

        def _initialize() -> bool:
            kwargs = {
                "timeout": self.config.timeout_ms,
                "portable": self.config.portable,
            }

            if self.config.login is not None:
                kwargs["login"] = self.config.login

            if self.config.password is not None:
                kwargs["password"] = self.config.password

            if self.config.server is not None:
                kwargs["server"] = self.config.server

            if self.config.terminal_path:
                return bool(
                    mt5.initialize(
                        self.config.terminal_path,
                        **kwargs,
                    )
                )

            return bool(
                mt5.initialize(**kwargs)
            )

        result = await asyncio.to_thread(_initialize)

        if not result:
            error = mt5.last_error()
            raise MT5ServiceError(
                f"MT5 initialization failed: {error}"
            )

        self.connected = True
        return True

    async def shutdown(self) -> bool:
        if mt5 is None:
            self.connected = False
            return True

        await asyncio.to_thread(mt5.shutdown)
        self.connected = False
        return True

    async def get_account_info(self) -> dict:
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed."
            )

        if not self.connected:
            raise MT5ServiceError(
                "MT5 is not connected."
            )

        info = await asyncio.to_thread(
            mt5.account_info
        )

        if info is None:
            raise MT5ServiceError(
                f"Unable to read MT5 account info: "
                f"{mt5.last_error()}"
            )

        return self._to_dict(info)

    async def get_terminal_info(self) -> dict:
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed."
            )

        if not self.connected:
            raise MT5ServiceError(
                "MT5 is not connected."
            )

        info = await asyncio.to_thread(
            mt5.terminal_info
        )

        if info is None:
            raise MT5ServiceError(
                f"Unable to read MT5 terminal info: "
                f"{mt5.last_error()}"
            )

        return self._to_dict(info)

    async def get_symbol_tick(
        self,
        symbol: str,
    ) -> dict:
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed."
            )

        if not self.connected:
            raise MT5ServiceError(
                "MT5 is not connected."
            )

        if not symbol:
            raise MT5ServiceError(
                "Symbol is required."
            )

        def _get_tick():
            if not mt5.symbol_select(
                symbol,
                True,
            ):
                return None

            return mt5.symbol_info_tick(
                symbol
            )

        tick = await asyncio.to_thread(
            _get_tick
        )

        if tick is None:
            raise MT5ServiceError(
                f"Unable to read tick for {symbol}: "
                f"{mt5.last_error()}"
            )

        return self._to_dict(tick)

    async def get_positions(
        self,
        symbol: Optional[str] = None,
    ) -> list[dict]:
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed."
            )

        if not self.connected:
            raise MT5ServiceError(
                "MT5 is not connected."
            )

        def _get_positions():
            if symbol:
                return mt5.positions_get(
                    symbol=symbol
                )

            return mt5.positions_get()

        positions = await asyncio.to_thread(
            _get_positions
        )

        if positions is None:
            error = mt5.last_error()

            if error and error[0] != 1:
                raise MT5ServiceError(
                    f"Unable to read MT5 positions: "
                    f"{error}"
                )

            return []

        return [
            self._to_dict(position)
            for position in positions
        ]

    async def get_symbols(
        self,
        query: Optional[str] = None,
    ) -> list[dict]:
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed."
            )

        if not self.connected:
            raise MT5ServiceError(
                "MT5 is not connected."
            )

        symbols = await asyncio.to_thread(
            mt5.symbols_get
        )

        if symbols is None:
            raise MT5ServiceError(
                f"Unable to read MT5 symbols: "
                f"{mt5.last_error()}"
            )

        result = []

        for symbol_info in symbols:
            data = self._to_dict(
                symbol_info
            )

            name = str(
                data.get("name", "")
            )

            if query and query.lower() not in name.lower():
                continue

            result.append(
                {
                    "name": name,
                    "description": data.get(
                        "description"
                    ),
                    "path": data.get("path"),
                    "visible": data.get(
                        "visible"
                    ),
                    "selected": data.get(
                        "select"
                    ),
                    "currency_base": data.get(
                        "currency_base"
                    ),
                    "currency_profit": data.get(
                        "currency_profit"
                    ),
                    "currency_margin": data.get(
                        "currency_margin"
                    ),
                }
            )

        return result

    async def find_gold_symbols(self) -> list[dict]:
        symbols = await self.get_symbols()

        scored = []

        for item in symbols:
            name = str(
                item.get("name", "")
            ).upper()

            score = 0

            if name == "XAUUSD":
                score = 100
            elif "XAUUSD" in name:
                score = 90
            elif name == "XAU":
                score = 80
            elif "XAU" in name:
                score = 70
            elif "GOLD" in name:
                score = 60

            if score > 0:
                enriched = dict(item)
                enriched["match_score"] = score
                scored.append(enriched)

        scored.sort(
            key=lambda item: (
                -item["match_score"],
                item["name"],
            )
        )

        return scored

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "M1",
        limit: int = 100,
    ) -> list[dict]:
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed."
            )

        if not self.connected:
            raise MT5ServiceError(
                "MT5 is not connected."
            )

        if not symbol:
            raise MT5ServiceError(
                "Symbol is required."
            )

        if timeframe not in self.TIMEFRAME_MAP:
            raise MT5ServiceError(
                f"Unsupported timeframe: {timeframe}"
            )

        if limit < 1:
            raise MT5ServiceError(
                "Limit must be greater than zero."
            )

        timeframe_name = self.TIMEFRAME_MAP[
            timeframe
        ]

        mt5_timeframe = getattr(
            mt5,
            timeframe_name,
            None,
        )

        if mt5_timeframe is None:
            raise MT5ServiceError(
                f"MT5 does not support timeframe "
                f"{timeframe}"
            )

        def _get_rates():
            if not mt5.symbol_select(
                symbol,
                True,
            ):
                return None

            return mt5.copy_rates_from_pos(
                symbol,
                mt5_timeframe,
                0,
                limit,
            )

        rates = await asyncio.to_thread(
            _get_rates
        )

        if rates is None:
            raise MT5ServiceError(
                f"Unable to read candles for "
                f"{symbol}: {mt5.last_error()}"
            )

        candles = []

        for row in rates:
            candles.append(
                {
                    "time": int(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "tick_volume": int(
                        row["tick_volume"]
                    ),
                    "spread": int(
                        row["spread"]
                    ),
                    "volume_real": float(
                        row["real_volume"]
                    ),
                }
            )

        return candles

    async def get_symbol_specification(
        self,
        symbol: str,
    ) -> dict:
        if mt5 is None:
            raise MT5ServiceError(
                "MetaTrader5 package is not installed."
            )

        if not self.connected:
            raise MT5ServiceError(
                "MT5 is not connected."
            )

        if not symbol:
            raise MT5ServiceError(
                "Symbol is required."
            )

        def _get_specification():
            if not mt5.symbol_select(
                symbol,
                True,
            ):
                return None

            return mt5.symbol_info(
                symbol
            )

        info = await asyncio.to_thread(
            _get_specification
        )

        if info is None:
            raise MT5ServiceError(
                f"Unable to read symbol specification "
                f"for {symbol}: {mt5.last_error()}"
            )

        data = self._to_dict(info)

        return {
            "symbol": data.get(
                "name",
                symbol,
            ),
            "digits": data.get(
                "digits"
            ),
            "point": data.get(
                "point"
            ),
            "spread": data.get(
                "spread"
            ),
            "spread_float": data.get(
                "spread_float"
            ),
            "tick_size": data.get(
                "trade_tick_size"
            ),
            "tick_value": data.get(
                "trade_tick_value"
            ),
            "tick_value_profit": data.get(
                "trade_tick_value_profit"
            ),
            "tick_value_loss": data.get(
                "trade_tick_value_loss"
            ),
            "contract_size": data.get(
                "trade_contract_size"
            ),
            "volume_min": data.get(
                "volume_min"
            ),
            "volume_max": data.get(
                "volume_max"
            ),
            "volume_step": data.get(
                "volume_step"
            ),
            "volume_limit": data.get(
                "volume_limit"
            ),
            "trade_mode": data.get(
                "trade_mode"
            ),
            "trade_execution_mode": data.get(
                "trade_exemode"
            ),
            "trade_stops_level": data.get(
                "trade_stops_level"
            ),
            "trade_freeze_level": data.get(
                "trade_freeze_level"
            ),
            "currency_base": data.get(
                "currency_base"
            ),
            "currency_profit": data.get(
                "currency_profit"
            ),
            "currency_margin": data.get(
                "currency_margin"
            ),
        }

    async def heartbeat(self) -> dict:
        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        result = {
            "connected": self.connected,
            "timestamp": timestamp,
        }

        if mt5 is None:
            result["last_error"] = (
                "MetaTrader5 package is not installed."
            )
            return result

        if not self.connected:
            result["last_error"] = (
                "MT5 is not connected."
            )
            return result

        try:
            account = await self.get_account_info()
            terminal = await self.get_terminal_info()

            result.update(
                {
                    "last_error": mt5.last_error(),
                    "account_login": account.get(
                        "login"
                    ),
                    "server": account.get(
                        "server"
                    ),
                    "trade_allowed": account.get(
                        "trade_allowed"
                    ),
                    "tradeapi_disabled": terminal.get(
                        "tradeapi_disabled"
                    ),
                }
            )

        except MT5ServiceError as exc:
            result["last_error"] = str(exc)

        return result


mt5_service = MT5Service()
