"""
RAYMOND v2.8 - MT5 DEMO Execution Worker

Continuous DEMO-only execution worker.

Safety:
- Disabled by default.
- Never authorizes LIVE trading.
- Requires the existing DEMO executor.
- Uses the frozen Raymond strategy.
- Uses the existing Risk Engine.
- Stops cleanly on application shutdown.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Optional

from .demo_mt5_execution import (
    DemoExecutionError,
    DemoExecutionResult,
    demo_mt5_execution_engine,
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_int(
    name: str,
    default: int,
    minimum: int,
) -> int:
    try:
        value = int(
            os.getenv(
                name,
                str(default),
            )
        )
    except (TypeError, ValueError):
        return default

    return max(
        minimum,
        value,
    )


class DemoExecutionWorker:
    """
    Background worker for controlled MT5 DEMO execution.

    The worker is deliberately opt-in.

    RAYMOND_MT5_DEMO_WORKER_ENABLED must be true before
    automatic DEMO execution can start.
    """

    def __init__(self) -> None:
        self.enabled = _env_bool(
            "RAYMOND_MT5_DEMO_WORKER_ENABLED",
            False,
        )

        self.interval_seconds = _env_int(
            "RAYMOND_MT5_DEMO_INTERVAL_SECONDS",
            30,
            5,
        )

        self.symbol = os.getenv(
            "RAYMOND_MT5_DEMO_SYMBOL",
            "XAUUSD",
        ).strip() or "XAUUSD"

        self.timeframe = os.getenv(
            "RAYMOND_MT5_DEMO_TIMEFRAME",
            "M15",
        ).strip().upper() or "M15"

        self.candle_limit = _env_int(
            "RAYMOND_MT5_DEMO_CANDLE_LIMIT",
            100,
            50,
        )

        self._task: Optional[
            asyncio.Task[None]
        ] = None

        self._stop_event = asyncio.Event()

        self._running = False

        self._last_result: Optional[
            dict[str, Any]
        ] = None

        self._last_error: Optional[str] = None

        self._last_run_at: Optional[str] = None

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _serialize_result(
        result: DemoExecutionResult,
    ) -> dict[str, Any]:
        return {
            "status": result.status,
            "execution_mode": result.execution_mode,
            "signal_id": result.signal_id,
            "symbol": result.symbol,
            "side": result.side,
            "volume": result.volume,
            "requested_price": result.requested_price,
            "executed_price": result.executed_price,
            "stop_loss": result.stop_loss,
            "take_profit": result.take_profit,
            "order_ticket": result.order_ticket,
            "deal_ticket": result.deal_ticket,
            "position_ticket": result.position_ticket,
            "broker_retcode": result.broker_retcode,
            "broker_comment": result.broker_comment,
            "verified": result.verified,
            "reason": result.reason,
            "timestamp": result.timestamp,
        }

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self._running,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "candle_limit": self.candle_limit,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self._last_run_at,
            "last_error": self._last_error,
            "last_result": self._last_result,
            "execution_mode": "demo",
            "live_authorization": False,
            "live_trading_enabled": False,
            "strategy_frozen": True,
        }

    # ------------------------------------------------------------------
    # SINGLE EXECUTION CYCLE
    # ------------------------------------------------------------------

    async def run_once(self) -> dict[str, Any]:
        """
        Execute one DEMO evaluation cycle.

        This method never executes LIVE orders.
        """

        self._last_run_at = self._utc_now()
        self._last_error = None

        try:
            result = (
                await demo_mt5_execution_engine
                .evaluate_and_execute(
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    candle_limit=self.candle_limit,
                )
            )

            serialized = self._serialize_result(
                result
            )

            self._last_result = serialized

            return serialized

        except DemoExecutionError as exc:
            self._last_error = str(exc)

            return {
                "status": "blocked",
                "execution_mode": "demo",
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "verified": False,
                "reason": str(exc),
                "timestamp": self._utc_now(),
            }

        except Exception as exc:
            # Fail closed.
            #
            # An unexpected worker error must never be interpreted
            # as permission to trade.
            self._last_error = (
                f"Unexpected DEMO worker error: {exc}"
            )

            return {
                "status": "error",
                "execution_mode": "demo",
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "verified": False,
                "reason": self._last_error,
                "timestamp": self._utc_now(),
            }

    # ------------------------------------------------------------------
    # WORKER LOOP
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Main worker loop.

        The worker exits when stop() is requested.
        """

        self._running = True

        try:
            while not self._stop_event.is_set():
                await self.run_once()

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=float(
                            self.interval_seconds
                        ),
                    )
                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            raise

        finally:
            self._running = False

    # ------------------------------------------------------------------
    # START / STOP
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the DEMO worker if explicitly enabled.

        Starting the worker never arms LIVE trading.
        """

        if not self.enabled:
            return

        if (
            self._task is not None
            and not self._task.done()
        ):
            return

        self._stop_event.clear()

        self._task = asyncio.create_task(
            self.run(),
            name="raymond-demo-execution-worker",
        )

    async def stop(self) -> None:
        """
        Stop the DEMO worker cleanly.
        """

        self._stop_event.set()

        task = self._task

        if task is None:
            self._running = False
            return

        if task is asyncio.current_task():
            self._task = None
            self._running = False
            return

        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            self._running = False


# ----------------------------------------------------------------------
# SINGLETON
# ----------------------------------------------------------------------

demo_execution_worker = DemoExecutionWorker()


# ----------------------------------------------------------------------
# PUBLIC LIFECYCLE HELPERS
# ----------------------------------------------------------------------

async def start_demo_execution_worker() -> None:
    """
    Start the global DEMO worker.

    Disabled by default through configuration.
    """

    await demo_execution_worker.start()


async def stop_demo_execution_worker() -> None:
    """
    Stop the global DEMO worker.
    """

    await demo_execution_worker.stop()


def demo_execution_worker_status() -> dict[str, Any]:
    """
    Return safe worker status for the dashboard/API.
    """

    return demo_execution_worker.status()


__all__ = [
    "DemoExecutionWorker",
    "demo_execution_worker",
    "start_demo_execution_worker",
    "stop_demo_execution_worker",
    "demo_execution_worker_status",
                  ]
