"""
RAYMOND v2.8 - Automatic Paper Entry Worker

Stage 17.6

ADDITIVE ONLY.

This worker automatically invokes the EXISTING RAYMOND paper-entry
pipeline on a schedule.

It does NOT:
- replace the 9 brains
- replace indicators
- replace AI scoring
- replace the Risk Engine
- replace position sizing
- replace the Paper Execution Gateway
- create a second execution system
- contact MT5
- contact a live broker
- enable live trading
- bypass risk controls
- directly create database positions

Architecture:

    Fresh XAUUSD market data
            ↓
    Existing TradingPipelineService
            ↓
    Existing AI decision
            ↓
       WAIT / BUY / SELL
            ↓
       Existing Step 14
            ↓
       Existing Risk Engine
            ↓
    Existing Paper Execution Gateway
            ↓
    Existing Step 16 persistence

IMPORTANT:

The worker is an ORCHESTRATOR only.

All actual trading decisions, risk checks, sizing, execution and
paper-position persistence remain inside the existing RAYMOND
pipeline.

Safety:
- Paper only
- Live trading disabled
- One evaluation at a time
- Exceptions are isolated to the current cycle
- WAIT never creates an order
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

try:
    from .online_market_api import _fetch_chart
    from .trading_pipeline_service import (
        PaperRiskState,
        TradingPipelineService,
        TradingPipelineServiceError,
    )
    from .risk_engine import SymbolSpecification
except ImportError:
    from online_market_api import _fetch_chart
    from trading_pipeline_service import (
        PaperRiskState,
        TradingPipelineService,
        TradingPipelineServiceError,
    )
    from risk_engine import SymbolSpecification


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutomaticEntryWorkerConfig:
    """
    Configuration for the automatic paper-entry worker.
    """

    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    candle_limit: int = 100
    interval_seconds: float = 30.0
    enabled: bool = True

    def validate(self) -> None:
        if not self.symbol.strip():
            raise ValueError(
                "symbol must not be empty"
            )

        if not self.timeframe.strip():
            raise ValueError(
                "timeframe must not be empty"
            )

        if self.candle_limit < 60:
            raise ValueError(
                "candle_limit must be at least 60"
            )

        if self.interval_seconds <= 0:
            raise ValueError(
                "interval_seconds must be greater than zero"
            )


@dataclass(frozen=True)
class AutomaticEntryWorkerResult:
    """
    Result of one automatic entry evaluation cycle.
    """

    symbol: str
    timeframe: str
    action: str
    direction: Optional[str]
    signal: Optional[str]
    confidence: Optional[float]
    technical_score: Optional[float]
    current_price: Optional[float]
    executed: bool
    execution_status: Optional[str]
    order_id: Optional[str]
    persisted: bool
    reason: str
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "action": self.action,
            "direction": self.direction,
            "signal": self.signal,
            "confidence": self.confidence,
            "technical_score": self.technical_score,
            "current_price": self.current_price,
            "executed": self.executed,
            "execution_status": self.execution_status,
            "order_id": self.order_id,
            "persisted": self.persisted,
            "reason": self.reason,
            "error": self.error,
        }


class AutomaticEntryWorker:
    """
    Automatic scheduler/orchestrator for the existing paper-entry
    pipeline.

    It deliberately delegates actual trading to
    TradingPipelineService.execute_paper().
    """

    def __init__(
        self,
        *,
        db,
        specification: SymbolSpecification,
        account_equity_provider,
        risk_state_provider,
        config: Optional[
            AutomaticEntryWorkerConfig
        ] = None,
        pipeline: Optional[
            TradingPipelineService
        ] = None,
    ) -> None:

        self.db = db

        self.specification = specification

        self.account_equity_provider = (
            account_equity_provider
        )

        self.risk_state_provider = (
            risk_state_provider
        )

        self.config = (
            config
            if config is not None
            else AutomaticEntryWorkerConfig()
        )

        self.config.validate()

        self.pipeline = (
            pipeline
            if pipeline is not None
            else TradingPipelineService()
        )

        self._stop_event = asyncio.Event()

        self._cycle_lock = asyncio.Lock()

        self._running = False

        self._last_result: Optional[
            AutomaticEntryWorkerResult
        ] = None

        self._last_error: Optional[str] = None

        self._cycles = 0

        self._executed_orders = 0

        self._risk_rejections = 0

        self._wait_decisions = 0

        self._failed_cycles = 0

    # ========================================================
    # STATUS
    # ========================================================

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_result(
        self,
    ) -> Optional[AutomaticEntryWorkerResult]:
        return self._last_result

    @property
    def last_error(
        self,
    ) -> Optional[str]:
        return self._last_error

    @property
    def cycles(self) -> int:
        return self._cycles

    @property
    def executed_orders(self) -> int:
        return self._executed_orders

    @property
    def risk_rejections(self) -> int:
        return self._risk_rejections

    @property
    def wait_decisions(self) -> int:
        return self._wait_decisions

    @property
    def failed_cycles(self) -> int:
        return self._failed_cycles

    # ========================================================
    # SAFE HELPERS
    # ========================================================

    @staticmethod
    def _enum_value(
        value: Any,
    ) -> Any:

        if value is None:
            return None

        return getattr(
            value,
            "value",
            value,
        )

    @classmethod
    def _string_value(
        cls,
        value: Any,
    ) -> Optional[str]:

        value = cls._enum_value(value)

        if value is None:
            return None

        text = str(value).strip()

        if not text:
            return None

        return text

    @staticmethod
    def _float_or_none(
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _extract_current_price(
        chart: dict[str, Any],
    ) -> Optional[float]:
        """
        Extract a valid current price from the public feed.
        """

        for key in (
            "price",
            "current_price",
            "close",
        ):

            candidate = chart.get(key)

            if candidate is None:
                continue

            try:
                value = float(candidate)

            except (
                TypeError,
                ValueError,
            ):
                continue

            if value > 0:
                return value

        candles = chart.get(
            "candles"
        ) or []

        if candles:

            last = candles[-1]

            if isinstance(
                last,
                dict,
            ):

                candidate = last.get(
                    "close"
                )

                if candidate is not None:

                    try:
                        value = float(
                            candidate
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        value = 0.0

                    if value > 0:
                        return value

        return None

    @classmethod
    def _decision_direction(
        cls,
        decision: Any,
    ) -> Optional[str]:

        return cls._string_value(
            getattr(
                decision,
                "direction",
                None,
            )
        )

    @classmethod
    def _decision_signal(
        cls,
        decision: Any,
    ) -> Optional[str]:

        return cls._string_value(
            getattr(
                decision,
                "signal",
                None,
            )
        )

    @classmethod
    def _decision_confidence(
        cls,
        decision: Any,
    ) -> Optional[float]:

        return cls._float_or_none(
            getattr(
                decision,
                "confidence",
                None,
            )
        )

    @classmethod
    def _decision_score(
        cls,
        decision: Any,
    ) -> Optional[float]:

        return cls._float_or_none(
            getattr(
                decision,
                "technical_score",
                None,
            )
        )

    # ========================================================
    # MARKET DATA
    # ========================================================

    async def _fetch_market_data(
        self,
    ) -> tuple[
        dict[str, Any],
        list[dict[str, Any]],
    ]:

        chart = await _fetch_chart(
            self.config.symbol,
            self.config.timeframe,
            self.config.candle_limit,
        )

        if not isinstance(
            chart,
            dict,
        ):
            raise TradingPipelineServiceError(
                "Online market feed returned an invalid response."
            )

        candles = chart.get(
            "candles"
        ) or []

        if not isinstance(
            candles,
            list,
        ):
            raise TradingPipelineServiceError(
                "Online market feed returned invalid candles."
            )

        if len(candles) < 60:
            raise TradingPipelineServiceError(
                "Insufficient candles for automatic entry."
            )

        return chart, candles

    # ========================================================
    # MAIN CYCLE
    # ========================================================

    async def evaluate_once(
        self,
    ) -> AutomaticEntryWorkerResult:

        if not self.config.enabled:

            return AutomaticEntryWorkerResult(
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                action="disabled",
                direction=None,
                signal=None,
                confidence=None,
                technical_score=None,
                current_price=None,
                executed=False,
                execution_status=None,
                order_id=None,
                persisted=False,
                reason=(
                    "Automatic entry worker is disabled."
                ),
            )

        if self._cycle_lock.locked():

            return AutomaticEntryWorkerResult(
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                action="skipped",
                direction=None,
                signal=None,
                confidence=None,
                technical_score=None,
                current_price=None,
                executed=False,
                execution_status=None,
                order_id=None,
                persisted=False,
                reason=(
                    "Previous automatic entry cycle "
                    "is still running."
                ),
            )

        async with self._cycle_lock:

            self._cycles += 1

            self._last_error = None

            try:

                # ------------------------------------------------
                # 1. FRESH MARKET DATA
                # ------------------------------------------------

                chart, candles = (
                    await self._fetch_market_data()
                )

                current_price = (
                    self._extract_current_price(
                        chart
                    )
                )

                # ------------------------------------------------
                # 2. EXISTING AI DECISION
                # ------------------------------------------------

                decision = (
                    self.pipeline.evaluate_decision(
                        symbol=self.config.symbol,
                        timeframe=self.config.timeframe,
                        candles=candles,
                    )
                )

                direction = (
                    self._decision_direction(
                        decision
                    )
                )

                signal = (
                    self._decision_signal(
                        decision
                    )
                )

                confidence = (
                    self._decision_confidence(
                        decision
                    )
                )

                technical_score = (
                    self._decision_score(
                        decision
                    )
                )

                normalized_direction = (
                    direction.lower()
                    if direction
                    else ""
                )

                normalized_signal = (
                    signal.lower()
                    if signal
                    else ""
                )

                # ------------------------------------------------
                # 3. WAIT / NEUTRAL = NO ENTRY
                # ------------------------------------------------

                if (
                    normalized_direction
                    in {
                        "wait",
                        "neutral",
                        "none",
                    }
                    or normalized_signal
                    in {
                        "wait",
                        "neutral",
                    }
                ):

                    self._wait_decisions += 1

                    result = (
                        AutomaticEntryWorkerResult(
                            symbol=self.config.symbol,
                            timeframe=self.config.timeframe,
                            action="wait",
                            direction=direction,
                            signal=signal,
                            confidence=confidence,
                            technical_score=technical_score,
                            current_price=current_price,
                            executed=False,
                            execution_status=None,
                            order_id=None,
                            persisted=False,
                            reason=(
                                "Existing RAYMOND decision "
                                "is WAIT/NEUTRAL. "
                                "No paper order was submitted."
                            ),
                        )
                    )

                    self._last_result = result

                    return result

                # ------------------------------------------------
                # 4. ONLY BUY / SELL MAY PROCEED
                # ------------------------------------------------

                if normalized_direction not in {
                    "buy",
                    "sell",
                }:

                    result = (
                        AutomaticEntryWorkerResult(
                            symbol=self.config.symbol,
                            timeframe=self.config.timeframe,
                            action="no_entry",
                            direction=direction,
                            signal=signal,
                            confidence=confidence,
                            technical_score=technical_score,
                            current_price=current_price,
                            executed=False,
                            execution_status=None,
                            order_id=None,
                            persisted=False,
                            reason=(
                                "Existing RAYMOND decision "
                                "did not produce BUY or SELL."
                            ),
                        )
                    )

                    self._last_result = result

                    return result

                # ------------------------------------------------
                # 5. EXISTING PAPER ACCOUNT STATE
                # ------------------------------------------------

                account_equity = (
                    self.account_equity_provider()
                )

                account_equity = float(
                    account_equity
                )

                if account_equity <= 0:
                    raise TradingPipelineServiceError(
                        "Paper account equity must be greater than zero."
                    )

                risk_state = (
                    self.risk_state_provider()
                )

                if not isinstance(
                    risk_state,
                    PaperRiskState,
                ):
                    raise TradingPipelineServiceError(
                        "risk_state_provider must return "
                        "PaperRiskState."
                    )

                # ------------------------------------------------
                # 6. EXISTING FULL PAPER PIPELINE
                # ------------------------------------------------
                #
                # This is the critical part.
                #
                # No new risk calculation.
                # No new position sizing.
                # No direct gateway call.
                #
                # The existing execute_paper() owns:
                #
                # AI → Step 14 → Risk Engine
                # → sizing → Paper Execution Gateway
                #
                # ------------------------------------------------

                execution_result = (
                    await self.pipeline.execute_paper(
                        symbol=self.config.symbol,
                        timeframe=self.config.timeframe,
                        candles=candles,
                        specification=self.specification,
                        account_equity=account_equity,
                        risk_state=risk_state,
                    )
                )

                # ------------------------------------------------
                # 7. INSPECT EXISTING STEP 14 RESULT
                # ------------------------------------------------

                execution = getattr(
                    execution_result,
                    "execution_result",
                    None,
                )

                risk_decision = getattr(
                    execution_result,
                    "risk_decision",
                    None,
                )

                execution_status = (
                    self._string_value(
                        getattr(
                            execution,
                            "status",
                            None,
                        )
                    )
                )

                order_id = (
                    self._string_value(
                        getattr(
                            execution,
                            "order_id",
                            None,
                        )
                    )
                )

                execution_type = (
                    self._string_value(
                        getattr(
                            execution,
                            "execution_type",
                            None,
                        )
                    )
                )

                if execution_type:
                    execution_type = (
                        execution_type.lower()
                    )

                executed = (
                    execution is not None
                    and execution_type == "paper"
                    and execution_status
                    in {
                        "accepted",
                        "filled",
                    }
                )

                # ------------------------------------------------
                # 8. RISK REJECTION
                # ------------------------------------------------

                if (
                    risk_decision is not None
                    and not bool(
                        getattr(
                            risk_decision,
                            "allowed",
                            False,
                        )
                    )
                ):

                    self._risk_rejections += 1

                    risk_reason = (
                        getattr(
                            risk_decision,
                            "reason",
                            None,
                        )
                        or "Risk Engine rejected the paper entry."
                    )

                    result = (
                        AutomaticEntryWorkerResult(
                            symbol=self.config.symbol,
                            timeframe=self.config.timeframe,
                            action="risk_rejected",
                            direction=direction,
                            signal=signal,
                            confidence=confidence,
                            technical_score=technical_score,
                            current_price=current_price,
                            executed=False,
                            execution_status=execution_status,
                            order_id=order_id,
                            persisted=False,
                            reason=str(
                                risk_reason
                            ),
                        )
                    )

                    self._last_result = result

                    return result

                # ------------------------------------------------
                # 9. EXECUTION NOT ACCEPTED
                # ------------------------------------------------

                if not executed:

                    message = (
                        getattr(
                            execution_result,
                            "message",
                            None,
                        )
                        or getattr(
                            execution,
                            "message",
                            None,
                        )
                        or "Paper entry was not executed."
                    )

                    result = (
                        AutomaticEntryWorkerResult(
                            symbol=self.config.symbol,
                            timeframe=self.config.timeframe,
                            action="rejected",
                            direction=direction,
                            signal=signal,
                            confidence=confidence,
                            technical_score=technical_score,
                            current_price=current_price,
                            executed=False,
                            execution_status=execution_status,
                            order_id=order_id,
                            persisted=False,
                            reason=str(
                                message
                            ),
                        )
                    )

                    self._last_result = result

                    return result

                # ------------------------------------------------
                # 10. SUCCESSFUL PAPER ENTRY
                # ------------------------------------------------

                self._executed_orders += 1

                # Step 15/16 persistence is performed by the
                # existing application pipeline.
                #
                # We report successful paper execution here.
                #
                persisted = True

                result = (
                    AutomaticEntryWorkerResult(
                        symbol=self.config.symbol,
                        timeframe=self.config.timeframe,
                        action="paper_entry",
                        direction=direction,
                        signal=signal,
                        confidence=confidence,
                        technical_score=technical_score,
                        current_price=current_price,
                        executed=True,
                        execution_status=execution_status,
                        order_id=order_id,
                        persisted=persisted,
                        reason=(
                            "Existing RAYMOND paper-entry "
                            "pipeline accepted the trade."
                        ),
                    )
                )

                self._last_result = result

                return result

            except Exception as exc:

                self._failed_cycles += 1

                self._last_error = str(
                    exc
                )

                logger.exception(
                    "RAYMOND automatic entry cycle "
                    "failed safely."
                )

                result = (
                    AutomaticEntryWorkerResult(
                        symbol=self.config.symbol,
                        timeframe=self.config.timeframe,
                        action="error",
                        direction=None,
                        signal=None,
                        confidence=None,
                        technical_score=None,
                        current_price=None,
                        executed=False,
                        execution_status=None,
                        order_id=None,
                        persisted=False,
                        reason=(
                            "Automatic entry cycle "
                            "failed safely."
                        ),
                        error=str(
                            exc
                        ),
                    )
                )

                self._last_result = result

                return result

    # ========================================================
    # SCHEDULED LOOP
    # ========================================================

    async def run(
        self,
    ) -> None:
        """
        Run the automatic entry loop until stopped.
        """

        if self._running:

            logger.warning(
                "RAYMOND automatic entry worker "
                "is already running."
            )

            return

        self._running = True

        self._stop_event.clear()

        logger.info(
            "RAYMOND Stage 17.6: automatic paper-entry "
            "worker started (%s / %s / %.0fs / PAPER ONLY)",
            self.config.symbol,
            self.config.timeframe,
            self.config.interval_seconds,
        )

        try:

            while not self._stop_event.is_set():

                cycle_started = (
                    asyncio.get_running_loop().time()
                )

                result = await self.evaluate_once()

                logger.info(
                    "RAYMOND Stage 17.6 entry cycle: "
                    "action=%s direction=%s signal=%s "
                    "confidence=%s score=%s "
                    "executed=%s status=%s "
                    "order_id=%s persisted=%s",
                    result.action,
                    result.direction,
                    result.signal,
                    result.confidence,
                    result.technical_score,
                    result.executed,
                    result.execution_status,
                    result.order_id,
                    result.persisted,
                )

                elapsed = (
                    asyncio.get_running_loop().time()
                    - cycle_started
                )

                remaining = max(
                    0.0,
                    self.config.interval_seconds
                    - elapsed,
                )

                if remaining <= 0:
                    continue

                try:

                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=remaining,
                    )

                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:

            logger.info(
                "RAYMOND Stage 17.6 automatic entry "
                "worker cancelled."
            )

            raise

        finally:

            self._running = False

            logger.info(
                "RAYMOND Stage 17.6 automatic paper-entry "
                "worker stopped."
            )

    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
    ) -> None:

        self._stop_event.set()

        self._running = False


__all__ = [
    "AutomaticEntryWorker",
    "AutomaticEntryWorkerConfig",
    "AutomaticEntryWorkerResult",
]
