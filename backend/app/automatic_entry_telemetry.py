"""
RAYMOND v2.8 - Automatic Paper Entry Telemetry

Stage 17.6 runtime telemetry wrapper.

This module:
- Observes the existing automatic paper-entry worker.
- Records the latest AI decision.
- Records Risk Engine approval/rejection.
- Records the Risk Engine rejection reason.
- Records the paper execution result.
- Exposes read-only telemetry through FastAPI.
- Does NOT create broker orders.
- Does NOT enable live trading.
- Does NOT bypass the Risk Engine.
- Does NOT modify the underlying trading strategy.

The existing AutomaticEntryWorker remains responsible for:

    market data
        -> AI decision
        -> Risk Engine
        -> paper execution
        -> persistence
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter

from .automatic_entry_worker import AutomaticEntryWorker

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/online",
    tags=["Automatic Paper Entry"],
)


_ACTIVE_WORKER: Optional["TelemetryAutomaticEntryWorker"] = None


def _utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _safe_value(value: Any) -> Any:
    """Convert simple runtime values into JSON-safe values."""

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if hasattr(value, "value"):
        try:
            return value.value
        except Exception:
            pass

    return str(value)


class TelemetryAutomaticEntryWorker(AutomaticEntryWorker):
    """
    AutomaticEntryWorker with read-only runtime telemetry.

    The parent worker performs the actual Stage 17.6 processing.

    This subclass only observes the result and records telemetry.

    IMPORTANT:
        This class does not change:
        - AI decision logic
        - Risk Engine limits
        - position sizing
        - execution permissions
        - broker permissions
        - live-trading state
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        global _ACTIVE_WORKER
        _ACTIVE_WORKER = self

        # Cycle information.
        self._last_cycle_at: Optional[str] = None
        self._cycles_completed: int = 0

        # AI decision telemetry.
        self._last_decision: Optional[str] = None
        self._last_direction: Optional[str] = None
        self._last_signal: Optional[str] = None
        self._last_confidence: Optional[float] = None
        self._last_score: Optional[float] = None

        # Risk Engine telemetry.
        self._last_risk_allowed: Optional[bool] = None
        self._last_risk_reason: Optional[str] = None
        self._last_risk_amount: Optional[float] = None
        self._last_proposed_exposure: Optional[float] = None
        self._last_open_positions: Optional[int] = None
        self._last_max_open_positions: Optional[int] = None
        self._last_daily_loss: Optional[float] = None
        self._last_daily_loss_limit: Optional[float] = None
        self._last_total_exposure: Optional[float] = None
        self._last_max_total_exposure: Optional[float] = None

        # Execution telemetry.
        self._last_execution_status: Optional[str] = None
        self._last_order_id: Optional[str] = None
        self._last_persisted: Optional[bool] = None
        self._paper_trades_created: int = 0

        # Error telemetry.
        self._last_error: Optional[str] = None

    async def run_once(self) -> Any:
        """
        Run the original worker cycle and record its outcome.

        No trading behavior is changed here.
        """

        self._last_cycle_at = _utc_now()
        self._last_error = None

        try:
            result = await super().run_once()

            self._cycles_completed += 1

            self._capture_result(result)

            return result

        except Exception as exc:
            self._last_error = str(exc)
            self._last_execution_status = "error"

            logger.exception(
                "RAYMOND Stage 17.6 telemetry: entry cycle failed"
            )

            raise

    def _capture_result(self, result: Any) -> None:
        """
        Extract safe telemetry from the existing worker result.

        This method is deliberately read-only.
        """

        try:
            decision = result

            execution_result: Any = None
            persisted: Optional[bool] = None
            risk_decision: Any = None

            # ---------------------------------------------------------
            # Normal dictionary-style worker result.
            # ---------------------------------------------------------

            if isinstance(result, dict):

                decision = result.get(
                    "decision",
                    result.get(
                        "ai_decision",
                        result,
                    ),
                )

                execution_result = result.get(
                    "execution_result"
                )

                persisted_value = result.get(
                    "persisted"
                )

                if isinstance(
                    persisted_value,
                    bool,
                ):
                    persisted = persisted_value

                # Some implementations may return the Step 14
                # result under "result".
                pipeline_result = result.get(
                    "result"
                )

                if pipeline_result is not None:
                    risk_decision = self._extract_any(
                        pipeline_result,
                        (
                            "risk_decision",
                            "risk",
                        ),
                    )

                # Also support a directly returned risk decision.
                if risk_decision is None:
                    risk_decision = self._extract_any(
                        result,
                        (
                            "risk_decision",
                            "risk",
                        ),
                    )

            else:
                # -----------------------------------------------------
                # Object-style worker result.
                # -----------------------------------------------------

                risk_decision = self._extract_any(
                    result,
                    (
                        "risk_decision",
                        "risk",
                    ),
                )

                execution_result = self._extract_any(
                    result,
                    (
                        "execution_result",
                        "execution",
                    ),
                )

                persisted_value = self._extract_any(
                    result,
                    (
                        "persisted",
                    ),
                )

                if isinstance(
                    persisted_value,
                    bool,
                ):
                    persisted = persisted_value

            # ---------------------------------------------------------
            # AI decision telemetry.
            # ---------------------------------------------------------

            self._last_decision = (
                self._extract_action(decision)
            )

            self._last_direction = (
                self._extract_direction(decision)
            )

            self._last_signal = (
                self._extract_signal(decision)
            )

            self._last_confidence = (
                self._extract_number(
                    decision,
                    "confidence",
                )
            )

            self._last_score = (
                self._extract_number(
                    decision,
                    "technical_score",
                )
            )

            if self._last_score is None:
                self._last_score = (
                    self._extract_number(
                        decision,
                        "score",
                    )
                )

            # ---------------------------------------------------------
            # Risk Engine telemetry.
            # ---------------------------------------------------------

            self._capture_risk_decision(
                risk_decision
            )

            # ---------------------------------------------------------
            # Execution telemetry.
            # ---------------------------------------------------------

            if execution_result is not None:

                self._capture_execution(
                    execution_result,
                    persisted,
                )

            else:

                action = (
                    self._last_decision or ""
                ).upper()

                if action == "WAIT":

                    self._last_execution_status = (
                        "not_executed"
                    )

                    self._last_order_id = None
                    self._last_persisted = False

                elif action in {"BUY", "SELL"}:

                    # IMPORTANT:
                    #
                    # If the Risk Engine rejected the trade,
                    # report that explicitly instead of simply
                    # reporting "not_executed".

                    if (
                        self._last_risk_allowed
                        is False
                    ):
                        self._last_execution_status = (
                            "risk_rejected"
                        )

                    else:
                        self._last_execution_status = (
                            "not_executed"
                        )

                    self._last_order_id = None
                    self._last_persisted = persisted

                else:

                    self._last_execution_status = (
                        "not_executed"
                    )

        except Exception as exc:

            logger.warning(
                "RAYMOND Stage 17.6 telemetry "
                "capture failed: %s",
                exc,
            )

    def _capture_risk_decision(
        self,
        risk_decision: Any,
    ) -> None:
        """
        Capture Risk Engine information.

        This method does not alter or override the Risk Engine
        decision.
        """

        if risk_decision is None:

            self._last_risk_allowed = None
            self._last_risk_reason = None
            self._last_risk_amount = None
            self._last_proposed_exposure = None
            self._last_open_positions = None
            self._last_max_open_positions = None
            self._last_daily_loss = None
            self._last_daily_loss_limit = None
            self._last_total_exposure = None
            self._last_max_total_exposure = None

            return

        self._last_risk_allowed = (
            self._extract_bool(
                risk_decision,
                "allowed",
            )
        )

        self._last_risk_reason = (
            self._extract_first_string(
                risk_decision,
                (
                    "reason",
                    "rejection_reason",
                    "message",
                    "error",
                ),
            )
        )

        self._last_risk_amount = (
            self._extract_first_number(
                risk_decision,
                (
                    "risk_amount",
                    "risk",
                    "risk_value",
                ),
            )
        )

        self._last_proposed_exposure = (
            self._extract_first_number(
                risk_decision,
                (
                    "proposed_exposure",
                    "exposure",
                    "proposed_exposure_percent",
                ),
            )
        )

        self._last_open_positions = (
            self._extract_first_int(
                risk_decision,
                (
                    "open_positions",
                    "current_open_positions",
                ),
            )
        )

        self._last_max_open_positions = (
            self._extract_first_int(
                risk_decision,
                (
                    "max_open_positions",
                    "maximum_open_positions",
                ),
            )
        )

        self._last_daily_loss = (
            self._extract_first_number(
                risk_decision,
                (
                    "daily_loss",
                    "current_daily_loss",
                    "daily_loss_percent",
                ),
            )
        )

        self._last_daily_loss_limit = (
            self._extract_first_number(
                risk_decision,
                (
                    "max_daily_loss",
                    "max_daily_loss_percent",
                    "daily_loss_limit",
                ),
            )
        )

        self._last_total_exposure = (
            self._extract_first_number(
                risk_decision,
                (
                    "total_exposure",
                    "current_exposure",
                    "exposure_percent",
                ),
            )
        )

        self._last_max_total_exposure = (
            self._extract_first_number(
                risk_decision,
                (
                    "max_total_exposure",
                    "max_total_exposure_percent",
                    "exposure_limit",
                ),
            )
        )

    def _capture_execution(
        self,
        execution_result: Any,
        persisted: Optional[bool],
    ) -> None:
        """Capture paper execution information without altering it."""

        status = self._extract_any(
            execution_result,
            (
                "status",
                "execution_status",
                "state",
            ),
        )

        order_id = self._extract_any(
            execution_result,
            (
                "order_id",
                "id",
                "ticket",
            ),
        )

        executed = self._extract_any(
            execution_result,
            (
                "executed",
                "filled",
                "success",
            ),
        )

        self._last_order_id = (
            str(order_id)
            if order_id is not None
            else None
        )

        if isinstance(
            executed,
            bool,
        ):

            if executed:

                self._last_execution_status = (
                    str(status)
                    if status is not None
                    else "executed"
                )

                if persisted:
                    self._paper_trades_created += 1

            else:

                self._last_execution_status = (
                    str(status)
                    if status is not None
                    else "not_executed"
                )

        else:

            self._last_execution_status = (
                str(status)
                if status is not None
                else "completed"
            )

        self._last_persisted = persisted

    @staticmethod
    def _extract_any(
        obj: Any,
        names: tuple[str, ...],
    ) -> Any:
        """
        Read a value from either a dictionary or an object.
        """

        if obj is None:
            return None

        if isinstance(
            obj,
            dict,
        ):

            for name in names:

                if name in obj:
                    return obj[name]

        for name in names:

            try:
                value = getattr(
                    obj,
                    name,
                )

            except Exception:
                continue

            if value is not None:
                return value

        return None

    @classmethod
    def _extract_action(
        cls,
        obj: Any,
    ) -> Optional[str]:

        value = cls._extract_any(
            obj,
            (
                "action",
                "decision",
            ),
        )

        if value is None:
            return None

        return _safe_value(value)

    @classmethod
    def _extract_direction(
        cls,
        obj: Any,
    ) -> Optional[str]:

        value = cls._extract_any(
            obj,
            (
                "direction",
            ),
        )

        if value is None:
            return None

        return _safe_value(value)

    @classmethod
    def _extract_signal(
        cls,
        obj: Any,
    ) -> Optional[str]:

        value = cls._extract_any(
            obj,
            (
                "signal",
            ),
        )

        if value is None:
            return None

        return _safe_value(value)

    @classmethod
    def _extract_bool(
        cls,
        obj: Any,
        name: str,
    ) -> Optional[bool]:

        value = cls._extract_any(
            obj,
            (name,),
        )

        if isinstance(
            value,
            bool,
        ):
            return value

        return None

    @classmethod
    def _extract_string(
        cls,
        obj: Any,
        name: str,
    ) -> Optional[str]:

        value = cls._extract_any(
            obj,
            (name,),
        )

        if value is None:
            return None

        return str(
            _safe_value(value)
        )

    @classmethod
    def _extract_first_string(
        cls,
        obj: Any,
        names: tuple[str, ...],
    ) -> Optional[str]:

        for name in names:

            value = cls._extract_string(
                obj,
                name,
            )

            if value is not None:
                return value

        return None

    @classmethod
    def _extract_number(
        cls,
        obj: Any,
        name: str,
    ) -> Optional[float]:

        value = cls._extract_any(
            obj,
            (name,),
        )

        if value is None:
            return None

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @classmethod
    def _extract_first_number(
        cls,
        obj: Any,
        names: tuple[str, ...],
    ) -> Optional[float]:

        for name in names:

            value = cls._extract_number(
                obj,
                name,
            )

            if value is not None:
                return value

        return None

    @classmethod
    def _extract_first_int(
        cls,
        obj: Any,
        names: tuple[str, ...],
    ) -> Optional[int]:

        for name in names:

            value = cls._extract_any(
                obj,
                (name,),
            )

            if value is None:
                continue

            try:
                return int(value)

            except (
                TypeError,
                ValueError,
            ):
                continue

        return None

    def status(self) -> dict[str, Any]:
        """
        Return read-only Stage 17.6 runtime telemetry.
        """

        config = getattr(
            self,
            "config",
            None,
        )

        symbol = getattr(
            config,
            "symbol",
            "XAUUSD",
        )

        timeframe = getattr(
            config,
            "timeframe",
            "M15",
        )

        interval_seconds = getattr(
            config,
            "interval_seconds",
            30.0,
        )

        enabled = getattr(
            config,
            "enabled",
            True,
        )

        running = bool(
            self.running
        )

        return {
            "status": (
                "running"
                if running
                else "stopped"
            ),

            "enabled": bool(
                enabled
            ),

            "running": running,

            "symbol": symbol,

            "timeframe": timeframe,

            "interval_seconds": float(
                interval_seconds
            ),

            "paper_only": True,

            # -----------------------------------------------------
            # Cycle.
            # -----------------------------------------------------

            "last_cycle_at": (
                self._last_cycle_at
            ),

            "cycles_completed": (
                self._cycles_completed
            ),

            # -----------------------------------------------------
            # AI decision.
            # -----------------------------------------------------

            "last_decision": (
                self._last_decision
            ),

            "last_direction": (
                self._last_direction
            ),

            "last_signal": (
                self._last_signal
            ),

            "last_confidence": (
                self._last_confidence
            ),

            "last_score": (
                self._last_score
            ),

            # -----------------------------------------------------
            # Risk Engine.
            # -----------------------------------------------------

            "last_risk_allowed": (
                self._last_risk_allowed
            ),

            "last_risk_reason": (
                self._last_risk_reason
            ),

            "last_risk_amount": (
                self._last_risk_amount
            ),

            "last_proposed_exposure": (
                self._last_proposed_exposure
            ),

            "last_open_positions": (
                self._last_open_positions
            ),

            "last_max_open_positions": (
                self._last_max_open_positions
            ),

            "last_daily_loss": (
                self._last_daily_loss
            ),

            "last_daily_loss_limit": (
                self._last_daily_loss_limit
            ),

            "last_total_exposure": (
                self._last_total_exposure
            ),

            "last_max_total_exposure": (
                self._last_max_total_exposure
            ),

            # -----------------------------------------------------
            # Execution.
            # -----------------------------------------------------

            "last_execution_status": (
                self._last_execution_status
            ),

            "last_order_id": (
                self._last_order_id
            ),

            "last_persisted": (
                self._last_persisted
            ),

            "paper_trades_created": (
                self._paper_trades_created
            ),

            # -----------------------------------------------------
            # Error.
            # -----------------------------------------------------

            "last_error": (
                self._last_error
            ),

            # -----------------------------------------------------
            # HARD SAFETY STATE.
            #
            # These remain permanently false.
            # -----------------------------------------------------

            "execution_authorized": False,

            "broker_orders_allowed": False,

            "live_trading_enabled": False,

            "mt5_execution_allowed": False,

            "risk_engine_bypass": False,
        }


@router.get(
    "/automatic-entry-status"
)
async def automatic_entry_status() -> dict[str, Any]:
    """
    Read-only Stage 17.6 automatic-entry telemetry.

    This endpoint cannot create, modify, or close a trade.
    """

    worker = _ACTIVE_WORKER

    if worker is None:

        return {
            "status": "not_initialized",

            "enabled": True,

            "running": False,

            "symbol": "XAUUSD",

            "timeframe": "M15",

            "interval_seconds": 30.0,

            "paper_only": True,

            # -----------------------------------------------------
            # Cycle.
            # -----------------------------------------------------

            "last_cycle_at": None,

            "cycles_completed": 0,

            # -----------------------------------------------------
            # AI decision.
            # -----------------------------------------------------

            "last_decision": None,

            "last_direction": None,

            "last_signal": None,

            "last_confidence": None,

            "last_score": None,

            # -----------------------------------------------------
            # Risk Engine.
            # -----------------------------------------------------

            "last_risk_allowed": None,

            "last_risk_reason": None,

            "last_risk_amount": None,

            "last_proposed_exposure": None,

            "last_open_positions": None,

            "last_max_open_positions": None,

            "last_daily_loss": None,

            "last_daily_loss_limit": None,

            "last_total_exposure": None,

            "last_max_total_exposure": None,

            # -----------------------------------------------------
            # Execution.
            # -----------------------------------------------------

            "last_execution_status": None,

            "last_order_id": None,

            "last_persisted": None,

            "paper_trades_created": 0,

            # -----------------------------------------------------
            # Error.
            # -----------------------------------------------------

            "last_error": None,

            # -----------------------------------------------------
            # HARD SAFETY STATE.
            # -----------------------------------------------------

            "execution_authorized": False,

            "broker_orders_allowed": False,

            "live_trading_enabled": False,

            "mt5_execution_allowed": False,

            "risk_engine_bypass": False,
        }

    return worker.status()
