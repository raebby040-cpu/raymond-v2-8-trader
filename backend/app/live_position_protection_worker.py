"""
RAYMOND v2.8 - Continuous Live Position Protection Worker

STEP 17.6E

Continuously runs the live position protection engine.

Responsibilities:

- Periodically inspect Raymond-owned live positions
- Run break-even protection
- Run trailing-stop protection
- Verify broker connectivity
- Fail closed on protection errors
- Never create new orders
- Never enable live trading
- Keep protection disabled by default

IMPORTANT:

This worker does NOT open trades.

It does NOT enable LIVE_TRADING_ENABLED.

It only modifies existing Raymond-owned positions when:

    RAYMOND_POSITION_PROTECTION_ENABLED=true

AND the protection engine itself permits the modification.

Recommended deployment sequence:

1. Install worker.
2. Run with protection disabled.
3. Run demo-account E2E testing.
4. Validate dry-run calculations.
5. Enable actual protection on DEMO.
6. Validate broker modifications.
7. Only then consider production.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Optional


try:
    from .live_position_protection import (
        LivePositionProtectionError,
        protect_live_positions,
        protection_config,
    )

    from .live_position_monitor import (
        LivePositionMonitorError,
        monitor_live_positions,
    )

    from .live_reconciliation import (
        reconcile_live_positions,
    )

    from .mt5_service import (
        mt5_service,
    )

except ImportError:

    from live_position_protection import (
        LivePositionProtectionError,
        protect_live_positions,
        protection_config,
    )

    from live_position_monitor import (
        LivePositionMonitorError,
        monitor_live_positions,
    )

    from live_reconciliation import (
        reconcile_live_positions,
    )

    from mt5_service import (
        mt5_service,
    )


DEFAULT_SYMBOL = "XAUUSD"

DEFAULT_MAGIC = 28001703

DEFAULT_INTERVAL_SECONDS = 5.0


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _env_bool(
    name: str,
    default: bool = False,
) -> bool:

    value = os.getenv(
        name,
        "true" if default else "false",
    )

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_float(
    name: str,
    default: float,
) -> float:

    value = os.getenv(name)

    if value is None:
        return default

    try:

        result = float(value)

        if result <= 0:
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):

        return default


class LivePositionProtectionWorker:
    """
    Continuous protection worker.

    The worker is independently enabled through:

        RAYMOND_LIVE_PROTECTION_WORKER_ENABLED

    Actual broker SL/TP modification is independently controlled by:

        RAYMOND_POSITION_PROTECTION_ENABLED

    Therefore enabling the worker does not automatically enable
    broker modification.
    """

    def __init__(
        self,
        *,
        symbol: str = DEFAULT_SYMBOL,
        magic: int = DEFAULT_MAGIC,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ):

        self.symbol = (
            symbol.strip()
            if symbol
            else DEFAULT_SYMBOL
        )

        self.magic = int(magic)

        self.interval_seconds = max(
            float(interval_seconds),
            1.0,
        )

        self._task: Optional[
            asyncio.Task
        ] = None

        self._stop_event = asyncio.Event()

        self.running = False

        self.last_cycle_at: Optional[str] = None

        self.last_success_at: Optional[str] = None

        self.last_error: Optional[str] = None

        self.last_result: Optional[
            dict[str, Any]
        ] = None

        self.cycles = 0

        self.successful_cycles = 0

        self.failed_cycles = 0

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:

        config = protection_config()

        worker_enabled = _env_bool(
            "RAYMOND_LIVE_PROTECTION_WORKER_ENABLED",
            False,
        )

        return {
            "running": self.running,

            "worker_enabled": worker_enabled,

            "symbol": self.symbol,

            "magic": self.magic,

            "interval_seconds": (
                self.interval_seconds
            ),

            "protection_enabled": (
                config["enabled"]
            ),

            "break_even_enabled": (
                config["break_even_enabled"]
            ),

            "trailing_enabled": (
                config["trailing_enabled"]
            ),

            "last_cycle_at": (
                self.last_cycle_at
            ),

            "last_success_at": (
                self.last_success_at
            ),

            "last_error": (
                self.last_error
            ),

            "last_result": (
                self.last_result
            ),

            "cycles": self.cycles,

            "successful_cycles": (
                self.successful_cycles
            ),

            "failed_cycles": (
                self.failed_cycles
            ),

            "fail_closed": True,

            "timestamp": _utc_now(),
        }

    # ------------------------------------------------------------------
    # START
    # ------------------------------------------------------------------

    def start(self) -> bool:

        if self.running:
            return False

        if (
            self._task is not None
            and not self._task.done()
        ):
            return False

        self._stop_event.clear()

        self._task = asyncio.create_task(
            self.run()
        )

        self.running = True

        return True

    # ------------------------------------------------------------------
    # STOP
    # ------------------------------------------------------------------

    async def stop(self) -> None:

        self._stop_event.set()

        task = self._task

        if task is None:

            self.running = False

            return

        if task is not asyncio.current_task():

            task.cancel()

            try:

                await task

            except asyncio.CancelledError:

                pass

        self._task = None

        self.running = False

    # ------------------------------------------------------------------
    # ONE PROTECTION CYCLE
    # ------------------------------------------------------------------

    async def run_cycle(self) -> dict[str, Any]:

        self.cycles += 1

        self.last_cycle_at = _utc_now()

        # --------------------------------------------------------------
        # MT5 connection check
        # --------------------------------------------------------------

        if not mt5_service.connected:

            raise LivePositionProtectionError(
                "MT5 is not connected."
            )

        # --------------------------------------------------------------
        # Inspect current broker positions.
        # --------------------------------------------------------------

        monitor_result = (
            await monitor_live_positions(
                symbol=self.symbol,
                magic=self.magic,
            )
        )

        if not monitor_result.get(
            "monitor_healthy",
            False,
        ):

            raise LivePositionProtectionError(
                "Live position monitor is unhealthy."
            )

        protection_safe = bool(
            monitor_result.get(
                "new_live_orders_allowed",
                False,
            )
        )

        monitor_details = (
            monitor_result.get(
                "result",
                {},
            )
        )

        critical_issues = int(
            monitor_details.get(
                "critical_issues",
                0,
            )
            or 0
        )

        # --------------------------------------------------------------
        # Determine whether actual broker modification is enabled.
        # --------------------------------------------------------------

        config = protection_config()

        modification_enabled = bool(
            config["enabled"]
        )

        # --------------------------------------------------------------
        # Fail closed when the monitor reports critical problems.
        # --------------------------------------------------------------

        if (
            not protection_safe
            and critical_issues > 0
        ):

            result = {
                "status": "blocked",

                "reason": (
                    "Position monitor detected a critical "
                    "protection/reconciliation issue."
                ),

                "monitor": monitor_result,

                "protection": None,

                "modification_enabled": (
                    modification_enabled
                ),

                "timestamp": _utc_now(),
            }

            self.last_result = result

            return result

        # --------------------------------------------------------------
        # Protection evaluation.
        #
        # When actual modification is disabled, force dry-run.
        # --------------------------------------------------------------

        protection_result = (
            await protect_live_positions(
                symbol=self.symbol,
                magic=self.magic,
                dry_run=(
                    not modification_enabled
                ),
            )
        )

        # --------------------------------------------------------------
        # Count modifications safely.
        # --------------------------------------------------------------

        modified_count = 0

        if isinstance(
            protection_result,
            dict,
        ):

            try:

                modified_count = int(
                    protection_result.get(
                        "modified_count",
                        0,
                    )
                    or 0
                )

            except (
                TypeError,
                ValueError,
            ):

                modified_count = 0

        # --------------------------------------------------------------
        # Post-modification verification.
        # --------------------------------------------------------------

        verification = None

        if (
            modification_enabled
            and modified_count > 0
        ):

            verification = (
                await monitor_live_positions(
                    symbol=self.symbol,
                    magic=self.magic,
                )
            )

            if not verification.get(
                "monitor_healthy",
                False,
            ):

                raise LivePositionProtectionError(
                    "Protection modification completed, "
                    "but post-modification monitoring failed."
                )

            if not verification.get(
                "new_live_orders_allowed",
                False,
            ):

                raise LivePositionProtectionError(
                    "Protection modification completed, "
                    "but post-modification protection state "
                    "is unsafe."
                )

        # --------------------------------------------------------------
        # Final reconciliation.
        # --------------------------------------------------------------

        reconciliation = (
            await reconcile_live_positions(
                symbol=self.symbol,
                magic=self.magic,
            )
        )

        reconciliation_safe = bool(
            reconciliation.safe_for_new_live_orders
        )

        if not reconciliation_safe:

            raise LivePositionProtectionError(
                "Post-protection reconciliation is unsafe."
            )

        result = {
            "status": "completed",

            "symbol": self.symbol,

            "magic": self.magic,

            "monitor": monitor_result,

            "protection": protection_result,

            "post_modification_monitor": (
                verification
            ),

            "reconciliation": {
                "safe_for_new_live_orders": (
                    reconciliation_safe
                ),
            },

            "modification_enabled": (
                modification_enabled
            ),

            "dry_run": (
                not modification_enabled
            ),

            "timestamp": _utc_now(),
        }

        self.last_result = result

        return result

    # ------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------

    async def run(self) -> None:

        self.running = True

        try:

            while not self._stop_event.is_set():

                try:

                    result = await self.run_cycle()

                    self.last_success_at = _utc_now()

                    self.last_error = None

                    self.successful_cycles += 1

                    modified_count = 0

                    protection = result.get(
                        "protection"
                    )

                    if isinstance(
                        protection,
                        dict,
                    ):

                        try:

                            modified_count = int(
                                protection.get(
                                    "modified_count",
                                    0,
                                )
                                or 0
                            )

                        except (
                            TypeError,
                            ValueError,
                        ):

                            modified_count = 0

                    print(
                        "RAYMOND 17.6E: "
                        "live protection cycle completed "
                        f"status={result.get('status')} "
                        f"modified={modified_count}"
                    )

                except asyncio.CancelledError:

                    raise

                except (
                    LivePositionProtectionError,
                    LivePositionMonitorError,
                ) as exc:

                    self.failed_cycles += 1

                    self.last_error = str(exc)

                    print(
                        "RAYMOND 17.6E: "
                        "live protection cycle failed closed: "
                        f"{exc}"
                    )

                except Exception as exc:

                    self.failed_cycles += 1

                    self.last_error = str(exc)

                    print(
                        "RAYMOND 17.6E: "
                        "unexpected protection worker error "
                        f"— fail closed: {exc}"
                    )

                try:

                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.interval_seconds,
                    )

                except asyncio.TimeoutError:

                    pass

        finally:

            self.running = False

    # ------------------------------------------------------------------
    # MANUAL SINGLE CYCLE
    # ------------------------------------------------------------------

    async def run_once(
        self,
    ) -> dict[str, Any]:

        """
        Execute one protection cycle without starting
        the continuous background worker.
        """

        return await self.run_cycle()


# ----------------------------------------------------------------------
# DEFAULT WORKER
# ----------------------------------------------------------------------

_default_worker: Optional[
    LivePositionProtectionWorker
] = None


def get_live_position_protection_worker(
) -> LivePositionProtectionWorker:

    global _default_worker

    if _default_worker is None:

        interval = _env_float(
            "RAYMOND_LIVE_PROTECTION_INTERVAL_SECONDS",
            DEFAULT_INTERVAL_SECONDS,
        )

        try:

            magic = int(
                os.getenv(
                    "RAYMOND_LIVE_PROTECTION_MAGIC",
                    str(DEFAULT_MAGIC),
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            magic = DEFAULT_MAGIC

        _default_worker = (
            LivePositionProtectionWorker(
                symbol=os.getenv(
                    "RAYMOND_LIVE_PROTECTION_SYMBOL",
                    DEFAULT_SYMBOL,
                ),
                magic=magic,
                interval_seconds=interval,
            )
        )

    return _default_worker


def protection_worker_status() -> dict[str, Any]:

    return (
        get_live_position_protection_worker()
        .status()
    )


async def start_live_position_protection_worker() -> bool:

    if not _env_bool(
        "RAYMOND_LIVE_PROTECTION_WORKER_ENABLED",
        False,
    ):

        print(
            "RAYMOND 17.6E: "
            "live protection worker disabled by configuration."
        )

        return False

    worker = (
        get_live_position_protection_worker()
    )

    started = worker.start()

    if started:

        config = protection_config()

        print(
            "RAYMOND 17.6E: "
            "live protection worker started "
            f"symbol={worker.symbol} "
            f"interval={worker.interval_seconds}s "
            f"modification_enabled="
            f"{config['enabled']}"
        )

    return started


async def stop_live_position_protection_worker() -> None:

    if _default_worker is None:

        return

    await _default_worker.stop()

    print(
        "RAYMOND 17.6E: "
        "live protection worker stopped."
)
