"""
RAYMOND v2.8 - Stage 17.6 Automatic Paper Entry Worker

Purpose
-------
Continuously evaluates the existing RAYMOND trading pipeline using the
online XAUUSD paper-market feed.

When the existing AI/Risk pipeline authorizes a BUY or SELL, execution
is delegated to the existing paper-only execution gateway.

This version additionally exposes detailed risk diagnostics so that
automatic-entry failures are observable instead of appearing only as:

    executed=False

Safety
------
- PAPER ONLY.
- Never sends broker orders.
- Never enables MT5 execution.
- Never bypasses the Risk Engine.
- Never creates a second paper account.
- Never creates a second position repository.
- Reuses the existing Stage 15 persistence path.
- WAIT / NEUTRAL decisions do not create orders.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .online_market_api import _fetch_chart
from .trading_pipeline_service import (
    PaperRiskState,
    TradingPipelineService,
)
from .risk_engine import SymbolSpecification


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutomaticEntryWorkerConfig:
    """Configuration for the automatic paper-entry loop."""

    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    candle_limit: int = 100
    interval_seconds: float = 30.0
    enabled: bool = True


class AutomaticEntryWorker:
    """
    Stage 17.6 automatic paper-entry worker.

    The worker delegates:

    - market analysis
    - AI decision
    - Risk Engine validation
    - position sizing
    - paper execution

    to the existing TradingPipelineService.

    It does not implement a second trading engine.
    """

    def __init__(
        self,
        *,
        db: Any,
        specification: SymbolSpecification,
        account_equity_provider: Callable[
            [],
            float | Awaitable[float],
        ],
        risk_state_provider: Callable[
            [],
            PaperRiskState | Awaitable[PaperRiskState],
        ],
        config: Optional[AutomaticEntryWorkerConfig] = None,
        pipeline: Optional[TradingPipelineService] = None,
    ) -> None:
        self.db = db
        self.specification = specification
        self.account_equity_provider = account_equity_provider
        self.risk_state_provider = risk_state_provider
        self.config = config or AutomaticEntryWorkerConfig()
        self.pipeline = pipeline or TradingPipelineService()

        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None

    async def _resolve(
        self,
        value: Any,
    ) -> Any:
        """Resolve either a normal value or an awaitable."""

        if inspect.isawaitable(value):
            return await value

        return value

    async def _fetch_market_chart(
        self,
    ) -> list[dict[str, Any]]:
        """Fetch and validate fresh online market candles."""

        chart = await _fetch_chart(
            self.config.symbol,
            self.config.timeframe,
            self.config.candle_limit,
        )

        if isinstance(chart, dict):
            candles = chart.get("candles")

            if candles is None:
                candles = chart.get("bars")
        else:
            candles = chart

        if not isinstance(candles, list):
            raise RuntimeError(
                "Online market feed returned an invalid candle payload"
            )

        if not candles:
            raise RuntimeError(
                "Online market feed returned no candles"
            )

        normalized: list[dict[str, Any]] = []

        for candle in candles:
            if not isinstance(candle, dict):
                raise RuntimeError(
                    "Online market feed returned a non-dictionary candle"
                )

            required = (
                "open",
                "high",
                "low",
                "close",
            )

            if any(
                candle.get(field) is None
                for field in required
            ):
                raise RuntimeError(
                    "Online market feed returned an incomplete candle"
                )

            normalized.append(candle)

        return normalized

    @staticmethod
    def _get_value(
        obj: Any,
        *names: str,
        default: Any = None,
    ) -> Any:
        """Read an attribute or mapping value safely."""

        for name in names:
            if obj is None:
                continue

            if isinstance(obj, dict):
                if name in obj:
                    return obj[name]

            value = getattr(
                obj,
                name,
                None,
            )

            if value is not None:
                return value

        return default

    @staticmethod
    def _normalize_enum_value(
        value: Any,
    ) -> str:
        """Normalize Enum-like values to lowercase strings."""

        if value is None:
            return ""

        raw = getattr(
            value,
            "value",
            value,
        )

        return str(raw).strip().lower()

    @classmethod
    def _decision_action(
        cls,
        decision: Any,
    ) -> str:
        """Return the normalized decision action."""

        action = cls._get_value(
            decision,
            "action",
            "signal",
            "decision",
            default="WAIT",
        )

        return str(action).strip().upper()

    @classmethod
    def _decision_direction(
        cls,
        decision: Any,
    ) -> str:
        """Return the normalized trade direction."""

        direction = cls._get_value(
            decision,
            "direction",
            "signal",
            "action",
            default="",
        )

        return str(direction).strip().upper()

    @classmethod
    def _decision_signal(
        cls,
        decision: Any,
    ) -> str:
        """Return the displayed signal."""

        signal = cls._get_value(
            decision,
            "signal",
            "action",
            default="WAIT",
        )

        return str(signal).strip().upper()

    @classmethod
    def _decision_confidence(
        cls,
        decision: Any,
    ) -> Any:
        return cls._get_value(
            decision,
            "confidence",
            "confidence_score",
            default=None,
        )

    @classmethod
    def _decision_score(
        cls,
        decision: Any,
    ) -> Any:
        return cls._get_value(
            decision,
            "score",
            "technical_score",
            default=None,
        )

    @classmethod
    def _decision_proposal(
        cls,
        decision: Any,
    ) -> Any:
        return cls._get_value(
            decision,
            "proposal",
            default=None,
        )

    @classmethod
    def _risk_diagnostics(
        cls,
        result: Any,
    ) -> dict[str, Any]:
        """
        Extract Risk Engine diagnostics from Step14Result.

        This is read-only telemetry.

        It does not modify:
        - risk limits
        - position sizing
        - execution
        - account balance
        """

        risk_decision = cls._get_value(
            result,
            "risk_decision",
            "risk",
            default=None,
        )

        diagnostics: dict[str, Any] = {
            "risk_allowed": None,
            "risk_reason": None,
            "risk_amount": None,
            "daily_loss_limit": None,
            "total_exposure_limit": None,
            "proposed_exposure": None,
            "risk_open_positions": None,
        }

        if risk_decision is None:
            return diagnostics

        diagnostics["risk_allowed"] = cls._get_value(
            risk_decision,
            "allowed",
            default=None,
        )

        diagnostics["risk_reason"] = cls._get_value(
            risk_decision,
            "reason",
            default=None,
        )

        diagnostics["risk_amount"] = cls._get_value(
            risk_decision,
            "risk_amount",
            default=None,
        )

        diagnostics["daily_loss_limit"] = cls._get_value(
            risk_decision,
            "daily_loss_limit",
            default=None,
        )

        diagnostics["total_exposure_limit"] = cls._get_value(
            risk_decision,
            "total_exposure_limit",
            default=None,
        )

        diagnostics["proposed_exposure"] = cls._get_value(
            risk_decision,
            "proposed_exposure",
            default=None,
        )

        diagnostics["risk_open_positions"] = cls._get_value(
            risk_decision,
            "open_positions",
            default=None,
        )

        return diagnostics

    @classmethod
    def _proposal_diagnostics(
        cls,
        decision: Any,
    ) -> dict[str, Any]:
        """
        Extract the AI trade proposal.

        This lets us see whether the problem is caused by:
        - entry price
        - stop loss
        - take profit
        - R:R
        - direction
        """

        proposal = cls._decision_proposal(
            decision
        )

        if proposal is None:
            return {
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward": None,
                "proposal_direction": None,
            }

        return {
            "entry_price": cls._get_value(
                proposal,
                "entry_price",
                default=None,
            ),
            "stop_loss": cls._get_value(
                proposal,
                "stop_loss",
                default=None,
            ),
            "take_profit": cls._get_value(
                proposal,
                "take_profit",
                default=None,
            ),
            "risk_reward": cls._get_value(
                proposal,
                "risk_reward",
                default=None,
            ),
            "proposal_direction": cls._get_value(
                proposal,
                "direction",
                default=None,
            ),
        }

    async def _persist_execution(
        self,
        result: Any,
    ) -> tuple[bool, Any]:
        """
        Persist an accepted paper execution through Stage 15.
        """

        execution_result = self._get_value(
            result,
            "execution_result",
            default=None,
        )

        if execution_result is None:
            return False, None

        execution_type = self._normalize_enum_value(
            self._get_value(
                execution_result,
                "execution_type",
                default="",
            )
        )

        status = self._normalize_enum_value(
            self._get_value(
                execution_result,
                "status",
                default="",
            )
        )

        # Absolute safety gate:
        # only paper executions may reach persistence.
        if execution_type != "paper":
            logger.error(
                "RAYMOND Stage 17.6 persistence blocked: "
                "execution_type=%s is not paper",
                execution_type,
            )

            return False, None

        if status not in {
            "accepted",
            "filled",
        }:
            logger.warning(
                "RAYMOND Stage 17.6 persistence skipped: "
                "paper execution status=%s",
                status,
            )

            return False, None

        try:
            from .main import (
                persist_step15_paper_execution,
            )

        except Exception:
            logger.exception(
                "RAYMOND Stage 17.6 could not import "
                "the existing Stage 15 persistence helper"
            )

            return False, None

        try:
            persisted = persist_step15_paper_execution(
                result
            )

            persisted = await self._resolve(
                persisted
            )

            if persisted is None:
                logger.error(
                    "RAYMOND Stage 17.6 paper execution "
                    "was accepted but persistence "
                    "returned None"
                )

                return False, None

            return True, persisted

        except Exception:
            logger.exception(
                "RAYMOND Stage 17.6 failed to persist "
                "accepted paper execution"
            )

            return False, None

    async def run_once(
        self,
    ) -> Any:
        """
        Execute one complete automatic-entry cycle.

        Flow:

            Online XAUUSD market
                    ↓
            Technical indicators
                    ↓
                AI decision
                    ↓
              Risk Engine
                    ↓
             Paper execution
                    ↓
             Stage 15 persistence
        """

        if not self.config.enabled:
            return None

        candles = await self._fetch_market_chart()

        # AI decision for telemetry.
        decision = self.pipeline.evaluate_decision(
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            candles=candles,
        )

        action = self._decision_action(
            decision
        )

        direction = self._decision_direction(
            decision
        )

        signal = self._decision_signal(
            decision
        )

        confidence = self._decision_confidence(
            decision
        )

        score = self._decision_score(
            decision
        )

        proposal_info = self._proposal_diagnostics(
            decision
        )

        # WAIT / NEUTRAL decisions must never create orders.
        if action not in {
            "BUY",
            "SELL",
        }:
            logger.info(
                "RAYMOND Stage 17.6 entry cycle: "
                "action=%s direction=%s signal=%s "
                "confidence=%s score=%s "
                "executed=False status=not_executed "
                "order_id=None persisted=False "
                "risk_allowed=None risk_reason=%s",
                action,
                direction,
                signal,
                confidence,
                score,
                "non_trade_decision",
            )

            return decision

        # Canonical persistent paper equity.
        account_equity = await self._resolve(
            self.account_equity_provider()
        )

        # Canonical persistent paper risk state.
        risk_state = await self._resolve(
            self.risk_state_provider()
        )

        if not isinstance(
            risk_state,
            PaperRiskState,
        ):
            raise TypeError(
                "risk_state_provider must return PaperRiskState"
            )

        # Execute through the existing paper-only pipeline.
        result = await self.pipeline.execute_paper(
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            candles=candles,
            specification=self.specification,
            account_equity=float(
                account_equity
            ),
            risk_state=risk_state,
        )

        execution_result = self._get_value(
            result,
            "execution_result",
            default=None,
        )

        executed = (
            execution_result is not None
        )

        status = self._get_value(
            execution_result,
            "status",
            default=None,
        )

        order_id = self._get_value(
            execution_result,
            "order_id",
            "trade_id",
            default=None,
        )

        position_size = self._get_value(
            result,
            "position_size",
            default=None,
        )

        risk_info = self._risk_diagnostics(
            result
        )

        persisted = False
        persisted_trade = None

        if executed:
            (
                persisted,
                persisted_trade,
            ) = await self._persist_execution(
                result
            )

        # --------------------------------------------------
        # Detailed automatic-entry telemetry.
        #
        # This is the critical diagnostic output.
        # --------------------------------------------------

        logger.info(
            "RAYMOND Stage 17.6 entry diagnostics: "
            "symbol=%s timeframe=%s "
            "action=%s direction=%s signal=%s "
            "confidence=%s score=%s "
            "equity=%s "
            "open_positions=%s "
            "daily_loss=%s "
            "current_exposure=%s "
            "entry=%s "
            "sl=%s "
            "tp=%s "
            "rr=%s "
            "position_size=%s "
            "risk_allowed=%s "
            "risk_reason=%s "
            "risk_amount=%s "
            "proposed_exposure=%s "
            "execution_status=%s "
            "order_id=%s "
            "executed=%s "
            "persisted=%s",
            self.config.symbol,
            self.config.timeframe,
            action,
            direction,
            signal,
            confidence,
            score,
            float(account_equity),
            risk_state.open_positions,
            risk_state.daily_loss,
            risk_state.total_exposure,
            proposal_info["entry_price"],
            proposal_info["stop_loss"],
            proposal_info["take_profit"],
            proposal_info["risk_reward"],
            position_size,
            risk_info["risk_allowed"],
            risk_info["risk_reason"],
            risk_info["risk_amount"],
            risk_info["proposed_exposure"],
            status,
            order_id,
            executed,
            persisted,
        )

        # Keep the original concise status line as well.
        logger.info(
            "RAYMOND Stage 17.6 entry cycle: "
            "action=%s direction=%s signal=%s "
            "confidence=%s score=%s "
            "executed=%s status=%s "
            "order_id=%s persisted=%s",
            action,
            direction,
            signal,
            confidence,
            score,
            executed,
            status,
            order_id,
            persisted,
        )

        return {
            "decision": decision,
            "result": result,
            "execution_result": execution_result,
            "persisted": persisted,
            "persisted_trade": persisted_trade,
            "diagnostics": {
                "equity": float(account_equity),
                "open_positions": risk_state.open_positions,
                "daily_loss": risk_state.daily_loss,
                "current_exposure": risk_state.total_exposure,
                "position_size": position_size,
                **proposal_info,
                **risk_info,
            },
        }

    async def run(
        self,
    ) -> None:
        """Run continuously until stop() is requested."""

        logger.info(
            "RAYMOND Stage 17.6 automatic "
            "paper-entry worker started: "
            "symbol=%s timeframe=%s interval=%ss "
            "enabled=%s",
            self.config.symbol,
            self.config.timeframe,
            self.config.interval_seconds,
            self.config.enabled,
        )

        self._stop_event.clear()

        while not self._stop_event.is_set():

            try:
                await self.run_once()

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "RAYMOND Stage 17.6 automatic "
                    "entry cycle failed"
                )

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=max(
                        1.0,
                        float(
                            self.config.interval_seconds
                        ),
                    ),
                )

            except asyncio.TimeoutError:
                continue

        logger.info(
            "RAYMOND Stage 17.6 automatic "
            "paper-entry worker stopped"
        )

    async def start(
        self,
    ) -> None:
        """Start the worker as a background task."""

        if (
            self._task is not None
            and not self._task.done()
        ):
            return

        self._stop_event.clear()

        self._task = asyncio.create_task(
            self.run(),
            name=(
                "raymond-stage-17-6-"
                "automatic-entry"
            ),
        )

    async def stop(
        self,
    ) -> None:
        """Stop the worker cleanly."""

        self._stop_event.set()

        task = self._task

        if task is None:
            return

        if not task.done():

            try:
                await task

            except asyncio.CancelledError:
                pass

        self._task = None

    @property
    def running(
        self,
    ) -> bool:
        """Return whether the background worker is running."""

        return (
            self._task is not None
            and not self._task.done()
)
