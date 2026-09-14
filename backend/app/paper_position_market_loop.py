"""
RAYMOND v2.8 - Paper Position Market Loop

Stage 17.3
Automatic market-price polling for persistent paper-position management.

SAFETY
------
This component is PAPER ONLY.

It:
- obtains the latest public market price,
- feeds that price into PaperPositionManager,
- updates persistent paper-position state,
- allows the existing management engine to evaluate
  break-even, trailing-stop, and partial-close decisions.

It NEVER:
- places broker orders,
- contacts MetaTrader 5 for execution,
- contacts Exness for execution,
- enables live trading,
- bypasses Step 14 Risk Engine,
- creates real broker positions.

The loop is deliberately isolated from main.py so the core
application remains unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.orm import Session

try:
    from .paper_position_manager import (
        PaperManagementResult,
        PaperPositionManagementError,
        PaperPositionManager,
    )
except ImportError:
    from paper_position_manager import (
        PaperManagementResult,
        PaperPositionManagementError,
        PaperPositionManager,
    )


logger = logging.getLogger(__name__)


PriceProvider = Callable[[str], Awaitable[float]]


@dataclass(frozen=True)
class PaperPositionMarketLoopConfig:
    """
    Configuration for the automatic paper-position market loop.
    """

    symbol: str = "XAUUSD"

    interval_seconds: float = 30.0

    enabled: bool = True

    minimum_price: float = 0.000001

    @classmethod
    def from_values(
        cls,
        *,
        symbol: str = "XAUUSD",
        interval_seconds: float = 30.0,
        enabled: bool = True,
    ) -> "PaperPositionMarketLoopConfig":
        normalized_symbol = str(symbol).strip().upper()

        if not normalized_symbol:
            raise ValueError("symbol is required")

        interval = float(interval_seconds)

        if interval <= 0:
            raise ValueError(
                "interval_seconds must be greater than zero"
            )

        return cls(
            symbol=normalized_symbol,
            interval_seconds=interval,
            enabled=bool(enabled),
        )


@dataclass(frozen=True)
class PaperPositionMarketLoopResult:
    """
    Result from one market-loop cycle.
    """

    symbol: str

    current_price: float

    count: int

    results: tuple[dict[str, Any], ...]

    timestamp: str

    success: bool = True

    paper_only: bool = True

    read_only: bool = True

    live_trading_enabled: bool = False

    execution_authorized: bool = False

    broker_orders_allowed: bool = False

    mt5_execution_allowed: bool = False

    risk_engine_bypass: bool = False

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the result safely.
        """

        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "count": self.count,
            "results": list(self.results),
            "timestamp": self.timestamp,
            "success": self.success,
            "safety": {
                "paper_only": self.paper_only,
                "read_only": self.read_only,
                "live_trading_enabled": self.live_trading_enabled,
                "execution_authorized": self.execution_authorized,
                "broker_orders_allowed": self.broker_orders_allowed,
                "mt5_execution_allowed": self.mt5_execution_allowed,
                "risk_engine_bypass": self.risk_engine_bypass,
            },
        }


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_price(price: Any) -> float:
    """
    Validate and normalize a market price.
    """

    try:
        normalized = float(price)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "market price must be numeric"
        ) from exc

    if normalized <= 0:
        raise ValueError(
            "market price must be greater than zero"
        )

    return normalized


class PaperPositionMarketLoop:
    """
    Automatic paper-position management loop.

    The class itself does not create a background task until start()
    is called. This makes it easy to test safely.
    """

    def __init__(
        self,
        db: Session,
        price_provider: PriceProvider,
        config: Optional[PaperPositionMarketLoopConfig] = None,
        manager: Optional[PaperPositionManager] = None,
    ) -> None:
        self.db = db
        self.price_provider = price_provider
        self.config = (
            config
            or PaperPositionMarketLoopConfig()
        )
        self.manager = (
            manager
            or PaperPositionManager(db)
        )

        self._task: Optional[
            asyncio.Task[None]
        ] = None

        self._stop_event: Optional[
            asyncio.Event
        ] = None

        self._running = False

        self._last_result: Optional[
            PaperPositionMarketLoopResult
        ] = None

        self._last_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_result(
        self,
    ) -> Optional[PaperPositionMarketLoopResult]:
        return self._last_result

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def status(self) -> dict[str, Any]:
        """
        Return a safe status declaration.

        This method performs no market request and no
        position mutation.
        """

        return {
            "component": (
                "paper_position_market_loop"
            ),
            "symbol": self.config.symbol,
            "enabled": self.config.enabled,
            "running": self._running,
            "interval_seconds": (
                self.config.interval_seconds
            ),
            "last_error": self._last_error,
            "last_result": (
                self._last_result.to_dict()
                if self._last_result is not None
                else None
            ),
            "safety": {
                "paper_only": True,
                "read_only": True,
                "live_trading_enabled": False,
                "execution_authorized": False,
                "broker_orders_allowed": False,
                "mt5_execution_allowed": False,
                "risk_engine_bypass": False,
            },
            "timestamp": _utc(),
        }

    async def get_current_price(self) -> float:
        """
        Obtain and validate the current public market price.
        """

        price = await self.price_provider(
            self.config.symbol
        )

        return _validate_price(price)

    def evaluate_price(
        self,
        current_price: float,
    ) -> PaperPositionMarketLoopResult:
        """
        Run one management cycle using a supplied price.

        This synchronous method is intentionally exposed for
        tests and callers that already have a current price.
        """

        price = _validate_price(
            current_price
        )

        try:
            management_results: list[
                PaperManagementResult
            ] = self.manager.evaluate_symbol(
                self.config.symbol,
                price,
            )

            serialized_results = tuple(
                result.to_dict()
                for result in management_results
            )

            result = PaperPositionMarketLoopResult(
                symbol=self.config.symbol,
                current_price=price,
                count=len(
                    serialized_results
                ),
                results=serialized_results,
                timestamp=_utc(),
            )

            self._last_result = result
            self._last_error = None

            return result

        except PaperPositionManagementError:
            raise

        except Exception:
            logger.exception(
                "Paper position market cycle failed "
                "for %s",
                self.config.symbol,
            )
            raise

    async def run_once(
        self,
    ) -> PaperPositionMarketLoopResult:
        """
        Fetch the current public market price and run
        one management cycle.
        """

        if not self.config.enabled:
            raise RuntimeError(
                "paper position market loop is disabled"
            )

        try:
            current_price = (
                await self.get_current_price()
            )

            return self.evaluate_price(
                current_price
            )

        except Exception as exc:
            self._last_error = str(exc)

            logger.exception(
                "Paper position market loop "
                "cycle failed"
            )

            raise

    async def _run_loop(self) -> None:
        """
        Internal recurring loop.

        Errors are isolated to the individual cycle so
        one temporary market-data failure does not
        permanently kill the worker.
        """

        if self._stop_event is None:
            self._stop_event = asyncio.Event()

        while not self._stop_event.is_set():
            try:
                await self.run_once()

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                self._last_error = str(exc)

                logger.exception(
                    "Paper position market loop "
                    "cycle error"
                )

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=(
                        self.config.interval_seconds
                    ),
                )

            except asyncio.TimeoutError:
                continue

    def start(self) -> bool:
        """
        Start the background loop.

        Returns True when a new task was created.
        Returns False when already running or disabled.
        """

        if not self.config.enabled:
            return False

        if self._running:
            return False

        self._stop_event = asyncio.Event()

        self._task = asyncio.create_task(
            self._run_loop(),
            name=(
                "raymond-paper-position-market-loop"
            ),
        )

        self._running = True

        return True

    async def stop(self) -> bool:
        """
        Stop the background loop cleanly.
        """

        if not self._running:
            return False

        if self._stop_event is not None:
            self._stop_event.set()

        task = self._task

        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._task = None
        self._stop_event = None
        self._running = False

        return True

    async def close(self) -> None:
        """
        Alias for stop(), useful during application shutdown.
        """

        await self.stop()


__all__ = [
    "PaperPositionMarketLoop",
    "PaperPositionMarketLoopConfig",
    "PaperPositionMarketLoopResult",
    "PriceProvider",
  ]
