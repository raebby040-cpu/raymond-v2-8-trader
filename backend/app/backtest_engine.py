"""
RAYMOND v2.8 - Production Backtest Engine

Historical simulation for the canonical RAYMOND trading pipeline.

This version adds deterministic dynamic position management:

- 50% partial TP at +1R
- Break-even activation at +1R
- TP extension to +2.5R after +1.25R
- Trailing SL activation at +1.5R
- Trailing distance of 0.75R
- Persistent management state per open position
- Management-event audit trail
- Correct partial-realized-PnL accounting

IMPORTANT SAFETY RULES
----------------------
- This module never connects to MT5.
- This module never calls a broker.
- This module never enables live trading.
- This module never uses the PaperExecutionGateway.
- The existing indicator engine is reused.
- The existing AI decision engine is reused.
- The existing RiskEngine is reused.
- Historical candles are processed sequentially.
- Future candles are never supplied to the decision engine.
- If both SL and TP are touched inside one candle, SL is assumed first.
- Historical execution costs are explicit and deterministic.
- Historical daily-loss limits reset at trading-day boundaries.
- Price gaps through protective levels are executed at the achievable
  candle open rather than at an unavailable historical stop/target price.

POSITION MANAGEMENT TIMING
--------------------------
For each candle:

1. Existing SL/TP exit logic is checked first.
2. If the position survives the candle, management triggers are evaluated.
3. Any management changes become effective on the NEXT candle.

This deliberately avoids assuming an intrabar order of events that H1 OHLC
data cannot prove.

MANAGEMENT RULES
----------------
For BUY:
- +1.00R: realize 50% of remaining position at exactly +1R.
- +1.00R: move stop loss to entry.
- +1.25R: extend take profit to +2.5R.
- +1.50R: activate trailing stop.
- Trailing distance: 0.75R below the candle high.
- Trailing stop only moves in the protective direction.

For SELL:
- +1.00R: realize 50% of remaining position at exactly +1R.
- +1.00R: move stop loss to entry.
- +1.25R: extend take profit to +2.5R.
- +1.50R: activate trailing stop.
- Trailing distance: 0.75R above the candle low.
- Trailing stop only moves in the protective direction.

The initial risk R is permanently stored from the actual executed entry
price to the original rebased stop loss.

EXPOSURE MODEL
--------------
- The backtester models XAUUSD exposure using a configurable leverage
  assumption.
- The default backtest leverage is 200:1.
- This is a BACKTEST-ONLY assumption.
- It does not change live broker leverage.
- It does not connect to MT5 or Exness.
- Live trading risk controls must eventually use the actual broker/account
  margin requirements and leverage.

DIAGNOSTICS
-----------
The engine records:
- candles evaluated
- BUY decisions
- SELL decisions
- WAIT decisions
- confidence observations
- confluence observations
- decisions with proposals
- decisions without proposals
- zero/invalid position-size occurrences
- Risk Engine rejections
- accepted trade entries
- exception/rejection examples
- partial exits
- break-even activations
- TP extensions
- trailing activations
- trailing stop updates

The diagnostics do NOT change strategy thresholds or trading behaviour.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from math import isfinite
from typing import Any, Mapping, Optional, Sequence
from uuid import uuid4

from app.ai_trading_decision import (
    AIDirection,
    AITradingDecisionEngine,
)
from app.risk_engine import (
    RiskEngine,
    RiskEngineError,
    SymbolSpecification,
)
from app.technical_indicators import (
    TechnicalIndicatorError,
)
from app.trading_pipeline_service import (
    TradingPipelineService,
    TradingPipelineServiceError,
)


class BacktestEngineError(ValueError):
    """Raised when a backtest cannot be safely executed."""


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for one deterministic backtest."""

    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    starting_balance: float = 10_000.0

    warmup_candles: int = 50

    max_open_positions: int = 1

    execute_on_next_open: bool = True

    close_open_position_at_end: bool = True

    spread: float = 0.0
    slippage: float = 0.0
    commission_per_unit: float = 0.0

    # Backtest-only leverage assumption used when converting raw
    # XAUUSD notional value into modeled exposure for RiskEngine checks.
    exposure_leverage: float = 200.0

    # ---------------------------------------------------------
    # MTF entry confirmation (backtest-only)
    # ---------------------------------------------------------
    # The existing primary-timeframe RAYMOND strategy remains the
    # source of the trade direction. The lower timeframe can only
    # confirm or reject that already-valid setup.
    lower_timeframe: Optional[str] = None
    require_lower_timeframe_confirmation: bool = False
    lower_timeframe_min_confidence: float = 0.0
    lower_timeframe_min_confluence: float = 0.0

    # ---------------------------------------------------------
    # Profit protection (backtest-only)
    # ---------------------------------------------------------
    # Once a position reaches this R multiple, lock a small profit.
    # Existing +1R partial TP / break-even / trailing rules remain.
    profit_protection_enabled: bool = True
    profit_protection_trigger_r: float = 0.75
    profit_protection_lock_r: float = 0.10

    def validate(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise BacktestEngineError("symbol is required.")

        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise BacktestEngineError("timeframe is required.")

        if not isfinite(self.starting_balance):
            raise BacktestEngineError(
                "starting_balance must be finite."
            )

        if self.starting_balance <= 0:
            raise BacktestEngineError(
                "starting_balance must be greater than zero."
            )

        if self.warmup_candles < 50:
            raise BacktestEngineError(
                "warmup_candles must be at least 50."
            )

        if self.max_open_positions != 1:
            raise BacktestEngineError(
                "The production backtester currently supports exactly "
                "one open position."
            )

        for name, value in (
            ("spread", self.spread),
            ("slippage", self.slippage),
            ("commission_per_unit", self.commission_per_unit),
            ("exposure_leverage", self.exposure_leverage),
        ):
            if not isfinite(value):
                raise BacktestEngineError(
                    f"{name} must be finite."
                )

            if value < 0:
                raise BacktestEngineError(
                    f"{name} cannot be negative."
                )

        if self.exposure_leverage <= 0:
            raise BacktestEngineError(
                "exposure_leverage must be greater than zero."
            )

        if self.lower_timeframe is not None:
            if not isinstance(self.lower_timeframe, str) or not self.lower_timeframe.strip():
                raise BacktestEngineError(
                    "lower_timeframe must be a non-empty string when provided."
                )
            if self.lower_timeframe.strip().upper() == self.timeframe.strip().upper():
                raise BacktestEngineError(
                    "lower_timeframe must differ from the primary timeframe."
                )

        for name, value in (
            ("lower_timeframe_min_confidence", self.lower_timeframe_min_confidence),
            ("lower_timeframe_min_confluence", self.lower_timeframe_min_confluence),
            ("profit_protection_trigger_r", self.profit_protection_trigger_r),
            ("profit_protection_lock_r", self.profit_protection_lock_r),
        ):
            if not isfinite(value):
                raise BacktestEngineError(f"{name} must be finite.")
            if value < 0:
                raise BacktestEngineError(f"{name} cannot be negative.")

        if self.profit_protection_lock_r > self.profit_protection_trigger_r:
            raise BacktestEngineError(
                "profit_protection_lock_r cannot exceed profit_protection_trigger_r."
            )

        if self.require_lower_timeframe_confirmation and not self.lower_timeframe:
            raise BacktestEngineError(
                "lower_timeframe is required when lower-timeframe confirmation is enabled."
            )


@dataclass(frozen=True)
class BacktestTrade:
    """Immutable completed simulated trade."""

    trade_id: str
    symbol: str
    timeframe: str
    direction: str

    signal_time: Optional[str]
    entry_time: Optional[str]
    exit_time: Optional[str]

    signal_price: float
    entry_price: float
    exit_price: float

    stop_loss: float
    take_profit: float
    position_size: float

    pnl: float
    pnl_percent: float

    execution_cost: float

    exit_reason: str
    bars_held: int

    # Management audit information.
    initial_stop_loss: float = 0.0
    initial_take_profit: float = 0.0
    initial_position_size: float = 0.0
    remaining_position_size: float = 0.0
    initial_risk: float = 0.0

    partial_realized_pnl: float = 0.0

    break_even_active: bool = False
    partial_take_profit_taken: bool = False
    trailing_active: bool = False

    management_event_count: int = 0
    management_events: list[dict[str, Any]] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class BacktestEquityPoint:
    """One point on the simulated equity curve."""

    timestamp: Optional[str]
    balance: float
    equity: float
    drawdown: float
    drawdown_percent: float


@dataclass
class BacktestDiagnostics:
    """
    Diagnostic counters for understanding the strategy's historical
    decision flow.

    These values are observational only. They do not alter strategy
    decisions.
    """

    candles_evaluated: int = 0

    wait_decisions: int = 0
    buy_decisions: int = 0
    sell_decisions: int = 0

    decisions_with_proposal: int = 0
    decisions_without_proposal: int = 0

    missing_stop_loss: int = 0
    missing_take_profit: int = 0

    zero_position_size: int = 0

    risk_checks: int = 0
    risk_rejections: int = 0

    accepted_entries: int = 0

    confidence_observations: int = 0
    confluence_observations: int = 0

    minimum_confidence_observed: Optional[float] = None
    maximum_confidence_observed: Optional[float] = None

    minimum_confluence_observed: Optional[float] = None
    maximum_confluence_observed: Optional[float] = None

    partial_take_profits: int = 0
    break_even_activations: int = 0
    take_profit_extensions: int = 0
    trailing_activations: int = 0
    trailing_stop_updates: int = 0
    profit_protection_activations: int = 0
    lower_timeframe_checks: int = 0
    lower_timeframe_rejections: int = 0

    wait_reason_counts: dict[str, int] = field(
        default_factory=dict
    )

    risk_rejection_reason_counts: dict[str, int] = field(
        default_factory=dict
    )

    examples: list[dict[str, Any]] = field(
        default_factory=list
    )

    def record_wait(
        self,
        *,
        decision: Any,
        timestamp: Optional[str],
    ) -> None:
        self.wait_decisions += 1

        reason = self._extract_reason(decision)

        self.wait_reason_counts[reason] = (
            self.wait_reason_counts.get(reason, 0) + 1
        )

        self._record_decision_metrics(decision)

        self._add_example(
            {
                "type": "WAIT",
                "timestamp": timestamp,
                "reason": reason,
                "confidence": self._extract_numeric(
                    decision,
                    (
                        "confidence",
                        "confidence_score",
                    ),
                ),
                "confluence": self._extract_numeric(
                    decision,
                    (
                        "confluence",
                        "confluence_score",
                    ),
                ),
            }
        )

    def record_direction(
        self,
        *,
        decision: Any,
        timestamp: Optional[str],
    ) -> None:
        direction = getattr(
            decision,
            "direction",
            None,
        )

        if direction is AIDirection.BUY:
            self.buy_decisions += 1

        elif direction is AIDirection.SELL:
            self.sell_decisions += 1

        self._record_decision_metrics(decision)

    def record_risk_rejection(
        self,
        *,
        decision: Any,
        timestamp: Optional[str],
        risk_decision: Any,
    ) -> None:
        self.risk_rejections += 1

        reason = self._extract_reason(
            risk_decision
        )

        self.risk_rejection_reason_counts[reason] = (
            self.risk_rejection_reason_counts.get(reason, 0)
            + 1
        )

        self._add_example(
            {
                "type": "RISK_REJECTION",
                "timestamp": timestamp,
                "reason": reason,
                "direction": self._safe_value(
                    getattr(
                        decision,
                        "direction",
                        None,
                    )
                ),
                "confidence": self._extract_numeric(
                    decision,
                    (
                        "confidence",
                        "confidence_score",
                    ),
                ),
                "confluence": self._extract_numeric(
                    decision,
                    (
                        "confluence",
                        "confluence_score",
                    ),
                ),
            }
        )

    def record_missing_proposal(
        self,
        *,
        decision: Any,
        timestamp: Optional[str],
    ) -> None:
        self.decisions_without_proposal += 1

        self._add_example(
            {
                "type": "MISSING_PROPOSAL",
                "timestamp": timestamp,
                "direction": self._safe_value(
                    getattr(
                        decision,
                        "direction",
                        None,
                    )
                ),
            }
        )

    def record_zero_position_size(
        self,
        *,
        decision: Any,
        timestamp: Optional[str],
    ) -> None:
        self.zero_position_size += 1

        self._add_example(
            {
                "type": "ZERO_POSITION_SIZE",
                "timestamp": timestamp,
                "direction": self._safe_value(
                    getattr(
                        decision,
                        "direction",
                        None,
                    )
                ),
            }
        )

    def record_exception(
        self,
        *,
        timestamp: Optional[str],
        error: Exception,
    ) -> None:
        self._add_example(
            {
                "type": "ERROR",
                "timestamp": timestamp,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )

    def record_management(
        self,
        *,
        event: str,
        timestamp: Optional[str],
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        event_upper = event.upper()

        if event_upper == "PARTIAL_TAKE_PROFIT":
            self.partial_take_profits += 1

        elif event_upper == "BREAK_EVEN":
            self.break_even_activations += 1

        elif event_upper == "TAKE_PROFIT_EXTENSION":
            self.take_profit_extensions += 1

        elif event_upper == "TRAILING_ACTIVATED":
            self.trailing_activations += 1

        elif event_upper == "TRAILING_STOP_UPDATE":
            self.trailing_stop_updates += 1

        elif event_upper == "PROFIT_PROTECTION":
            self.profit_protection_activations += 1

        example = {
            "type": "MANAGEMENT",
            "event": event_upper,
            "timestamp": timestamp,
        }

        if details:
            example.update(details)

        self._add_example(example)

    def _record_decision_metrics(
        self,
        decision: Any,
    ) -> None:
        confidence = self._extract_numeric(
            decision,
            (
                "confidence",
                "confidence_score",
            ),
        )

        if confidence is not None:
            self.confidence_observations += 1

            if (
                self.minimum_confidence_observed is None
                or confidence
                < self.minimum_confidence_observed
            ):
                self.minimum_confidence_observed = confidence

            if (
                self.maximum_confidence_observed is None
                or confidence
                > self.maximum_confidence_observed
            ):
                self.maximum_confidence_observed = confidence

        confluence = self._extract_numeric(
            decision,
            (
                "confluence",
                "confluence_score",
                "confluence_strength",
            ),
        )

        if confluence is not None:
            self.confluence_observations += 1

            if (
                self.minimum_confluence_observed is None
                or confluence
                < self.minimum_confluence_observed
            ):
                self.minimum_confluence_observed = confluence

            if (
                self.maximum_confluence_observed is None
                or confluence
                > self.maximum_confluence_observed
            ):
                self.maximum_confluence_observed = confluence

    def _add_example(
        self,
        example: dict[str, Any],
    ) -> None:
        if len(self.examples) < 25:
            self.examples.append(example)

    @staticmethod
    def _extract_numeric(
        obj: Any,
        names: Sequence[str],
    ) -> Optional[float]:
        for name in names:
            try:
                value = getattr(
                    obj,
                    name,
                    None,
                )

                if value is None:
                    continue

                numeric = float(value)

                if isfinite(numeric):
                    return numeric

            except (
                TypeError,
                ValueError,
            ):
                continue

        return None

    @staticmethod
    def _extract_reason(
        obj: Any,
    ) -> str:
        reason_names = (
            "reason",
            "decision_reason",
            "rejection_reason",
            "message",
            "explanation",
        )

        for name in reason_names:
            try:
                value = getattr(
                    obj,
                    name,
                    None,
                )

                if value is not None:
                    text = str(value).strip()

                    if text:
                        return text[:300]

            except Exception:
                continue

        return "UNSPECIFIED"

    @staticmethod
    def _safe_value(
        value: Any,
    ) -> Optional[str]:
        if value is None:
            return None

        try:
            if hasattr(value, "value"):
                return str(value.value)

            return str(value)

        except Exception:
            return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    """Complete deterministic backtest result."""

    status: str
    symbol: str
    timeframe: str

    start_time: Optional[str]
    end_time: Optional[str]

    starting_balance: float
    ending_balance: float

    net_profit: float
    net_profit_percent: float

    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int

    win_rate_percent: float

    gross_profit: float
    gross_loss: float
    profit_factor: Optional[float]

    total_execution_cost: float

    max_drawdown: float
    max_drawdown_percent: float

    average_trade: float
    average_win: float
    average_loss: float

    bars_processed: int
    warmup_candles: int

    trades: list[dict[str, Any]]
    equity_curve: list[dict[str, Any]]

    diagnostics: dict[str, Any]


@dataclass
class _OpenPosition:
    """Internal mutable position used only by the simulator."""

    trade_id: str
    direction: AIDirection

    signal_time: Optional[str]
    entry_time: Optional[str]

    signal_price: float
    entry_price: float

    stop_loss: float
    take_profit: float
    position_size: float
    contract_size: float

    # Permanent original trade parameters.
    initial_stop_loss: float
    initial_take_profit: float
    initial_position_size: float
    initial_risk: float

    # Dynamic management state.
    break_even_active: bool = False
    partial_take_profit_taken: bool = False
    trailing_active: bool = False

    # PnL already realized by partial exits.
    realized_pnl: float = 0.0

    # Gross partial PnL before execution costs.
    partial_realized_gross_pnl: float = 0.0

    # Management audit trail.
    management_events: list[dict[str, Any]] = field(
        default_factory=list
    )

    bars_held: int = 0


class BacktestEngine:
    """
    Deterministic historical simulator.

    The engine deliberately does not execute through PaperExecutionGateway.
    """

    PARTIAL_TP_R = 1.0
    BREAK_EVEN_R = 1.0
    TP_EXTENSION_TRIGGER_R = 1.25
    TP_EXTENSION_R = 2.5
    TRAILING_TRIGGER_R = 1.5
    TRAILING_DISTANCE_R = 0.75

    def __init__(
        self,
        *,
        config: Optional[BacktestConfig] = None,
        pipeline_service: Optional[TradingPipelineService] = None,
    ) -> None:
        self.config = config or BacktestConfig()
        self.config.validate()

        self.pipeline_service = (
            pipeline_service
            or TradingPipelineService()
        )

        self.ai_engine = (
            self.pipeline_service.ai_engine
            if pipeline_service is not None
            else AITradingDecisionEngine()
        )

        self.risk_engine = (
            self.pipeline_service.risk_engine
            if pipeline_service is not None
            else RiskEngine()
        )

    def run(
        self,
        *,
        candles: Sequence[Mapping[str, Any]],
        specification: SymbolSpecification,
        lower_timeframe_candles: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> BacktestResult:

        self.config.validate()

        normalized = self._validate_and_normalize_candles(
            candles
        )

        normalized_lower: list[dict[str, Any]] = []
        if lower_timeframe_candles is not None:
            normalized_lower = self._validate_and_normalize_candles(
                lower_timeframe_candles,
                require_timestamps=True,
            )

        if self.config.require_lower_timeframe_confirmation:
            if not normalized_lower:
                raise BacktestEngineError(
                    "Lower-timeframe confirmation is enabled, but no lower-timeframe candles were supplied."
                )
            if len(normalized_lower) < self.config.warmup_candles:
                raise BacktestEngineError(
                    "Insufficient lower-timeframe candles for confirmation."
                )

        if len(normalized) <= self.config.warmup_candles:
            raise BacktestEngineError(
                "Insufficient historical candles. "
                f"At least {self.config.warmup_candles + 1} "
                "candles are required."
            )

        specification.validate()

        if (
            specification.symbol.upper()
            != self.config.symbol.upper()
        ):
            raise BacktestEngineError(
                "Symbol specification does not match backtest symbol."
            )

        balance = self.config.starting_balance
        peak_equity = balance

        max_drawdown = 0.0
        max_drawdown_percent = 0.0

        trades: list[BacktestTrade] = []
        equity_curve: list[BacktestEquityPoint] = []

        open_position: Optional[_OpenPosition] = None

        daily_loss = 0.0
        current_trading_day: Optional[date] = None

        diagnostics = BacktestDiagnostics()

        lower_cursor = 0
        lower_history: list[dict[str, Any]] = []

        for index in range(
            self.config.warmup_candles,
            len(normalized),
        ):
            candle = normalized[index]

            candle_day = self._trading_day(candle)

            if (
                candle_day is not None
                and candle_day != current_trading_day
            ):
                current_trading_day = candle_day
                daily_loss = 0.0

            if open_position is not None:
                open_position.bars_held += 1

                # IMPORTANT:
                # Existing SL/TP logic runs FIRST.
                # Management changes only become effective after this
                # check and therefore affect the next candle.
                closed_trade = self._check_exit(
                    position=open_position,
                    candle=candle,
                )

                if closed_trade is not None:
                    close_pnl = (
                        closed_trade.pnl
                        - closed_trade.partial_realized_pnl
                    )
                    balance += close_pnl

                    if close_pnl < 0:
                        daily_loss += abs(close_pnl)

                    trades.append(closed_trade)

                    open_position = None

                else:
                    management_pnl = (
                        self._manage_open_position(
                            position=open_position,
                            candle=candle,
                            diagnostics=diagnostics,
                        )
                    )

                    balance += management_pnl

                    if management_pnl < 0:
                        daily_loss += abs(
                            management_pnl
                        )

            unrealized = 0.0

            if open_position is not None:
                unrealized = self._unrealized_pnl(
                    position=open_position,
                    mark_price=float(candle["close"]),
                )

            equity = balance + unrealized

            if equity > peak_equity:
                peak_equity = equity

            drawdown = max(
                0.0,
                peak_equity - equity,
            )

            drawdown_percent = (
                (drawdown / peak_equity) * 100
                if peak_equity > 0
                else 0.0
            )

            max_drawdown = max(
                max_drawdown,
                drawdown,
            )

            max_drawdown_percent = max(
                max_drawdown_percent,
                drawdown_percent,
            )

            equity_curve.append(
                BacktestEquityPoint(
                    timestamp=self._timestamp(candle),
                    balance=round(balance, 8),
                    equity=round(equity, 8),
                    drawdown=round(drawdown, 8),
                    drawdown_percent=round(
                        drawdown_percent,
                        8,
                    ),
                )
            )

            if open_position is not None:
                continue

            diagnostics.candles_evaluated += 1

            history = normalized[: index + 1]

            if normalized_lower:
                primary_timestamp = self._timestamp_datetime(candle)
                if primary_timestamp is not None:
                    while lower_cursor < len(normalized_lower):
                        lower_timestamp = self._timestamp_datetime(
                            normalized_lower[lower_cursor]
                        )
                        if lower_timestamp is None or lower_timestamp > primary_timestamp:
                            break
                        lower_history.append(normalized_lower[lower_cursor])
                        lower_cursor += 1

            try:
                decision = (
                    self.pipeline_service.evaluate_decision(
                        symbol=self.config.symbol,
                        timeframe=self.config.timeframe,
                        candles=history,
                    )
                )

            except (
                TradingPipelineServiceError,
                TechnicalIndicatorError,
                ValueError,
            ) as exc:

                diagnostics.record_exception(
                    timestamp=self._timestamp(candle),
                    error=exc,
                )

                raise BacktestEngineError(
                    "Strategy evaluation failed at historical "
                    f"index {index}: {exc}"
                ) from exc

            diagnostics.record_direction(
                decision=decision,
                timestamp=self._timestamp(candle),
            )

            if decision.direction is AIDirection.WAIT:
                diagnostics.record_wait(
                    decision=decision,
                    timestamp=self._timestamp(candle),
                )
                continue

            if decision.symbol.upper() != self.config.symbol.upper():
                raise BacktestEngineError(
                    "AI decision symbol does not match backtest symbol."
                )

            proposal = decision.proposal

            if proposal is None:
                diagnostics.record_missing_proposal(
                    decision=decision,
                    timestamp=self._timestamp(candle),
                )

                raise BacktestEngineError(
                    "AI returned BUY/SELL without a proposal."
                )

            if self.config.lower_timeframe and self.config.require_lower_timeframe_confirmation:
                diagnostics.lower_timeframe_checks += 1

                if len(lower_history) < self.config.warmup_candles:
                    diagnostics.lower_timeframe_rejections += 1
                    diagnostics.wait_reason_counts["LOWER_TIMEFRAME_WARMUP"] = (
                        diagnostics.wait_reason_counts.get("LOWER_TIMEFRAME_WARMUP", 0) + 1
                    )
                    continue

                try:
                    lower_decision = self.pipeline_service.evaluate_decision(
                        symbol=self.config.symbol,
                        timeframe=self.config.lower_timeframe,
                        candles=lower_history,
                    )
                except (
                    TradingPipelineServiceError,
                    TechnicalIndicatorError,
                    ValueError,
                ) as exc:
                    diagnostics.record_exception(
                        timestamp=self._timestamp(candle),
                        error=exc,
                    )
                    raise BacktestEngineError(
                        "Lower-timeframe strategy evaluation failed at historical "
                        f"index {index}: {exc}"
                    ) from exc

                lower_confidence = float(getattr(lower_decision, "confidence", 0.0) or 0.0)
                lower_confluence = float(getattr(lower_decision, "confluence_score", 0.0) or 0.0)

                lower_direction = getattr(lower_decision, "direction", AIDirection.WAIT)

                lower_ok = (
                    lower_direction is decision.direction
                    and lower_confidence >= self.config.lower_timeframe_min_confidence
                    and lower_confluence >= self.config.lower_timeframe_min_confluence
                )

                if not lower_ok:
                    diagnostics.lower_timeframe_rejections += 1
                    diagnostics.wait_reason_counts["LOWER_TIMEFRAME_CONFIRMATION"] = (
                        diagnostics.wait_reason_counts.get("LOWER_TIMEFRAME_CONFIRMATION", 0) + 1
                    )
                    continue

            diagnostics.decisions_with_proposal += 1

            if proposal.stop_loss is None:
                diagnostics.missing_stop_loss += 1

                raise BacktestEngineError(
                    "Trade proposal has no stop loss."
                )

            if proposal.take_profit is None:
                diagnostics.missing_take_profit += 1

                raise BacktestEngineError(
                    "Trade proposal has no take profit."
                )

            next_index = index + 1

            if (
                self.config.execute_on_next_open
                and next_index >= len(normalized)
            ):
                break

            if self.config.execute_on_next_open:
                execution_candle = normalized[next_index]

                raw_entry_price = float(
                    execution_candle["open"]
                )

                entry_price = self._apply_entry_costs(
                    direction=decision.direction,
                    raw_price=raw_entry_price,
                )

                entry_time = self._timestamp(
                    execution_candle
                )

            else:
                execution_candle = candle

                raw_entry_price = float(
                    proposal.entry_price
                )

                entry_price = self._apply_entry_costs(
                    direction=decision.direction,
                    raw_price=raw_entry_price,
                )

                entry_time = self._timestamp(candle)

            stop_loss, take_profit = (
                self._rebase_protective_levels(
                    direction=decision.direction,
                    signal_entry=float(
                        proposal.entry_price
                    ),
                    actual_entry=entry_price,
                    stop_loss=float(
                        proposal.stop_loss
                    ),
                    take_profit=float(
                        proposal.take_profit
                    ),
                )
            )

            try:
                position_size = (
                    self.risk_engine
                    .calculate_position_size_from_symbol(
                        equity=equity,
                        entry_price=entry_price,
                        stop_loss_price=stop_loss,
                        specification=specification,
                    )
                )

                if position_size <= 0:
                    diagnostics.record_zero_position_size(
                        decision=decision,
                        timestamp=self._timestamp(candle),
                    )
                    continue

                proposed_notional = abs(
                    position_size
                    * entry_price
                    * specification.contract_size
                )

                proposed_exposure = (
                    proposed_notional
                    / self.config.exposure_leverage
                )

                if not isfinite(proposed_notional):
                    raise BacktestEngineError(
                        "Calculated proposed notional exposure is not finite."
                    )

                if not isfinite(proposed_exposure):
                    raise BacktestEngineError(
                        "Calculated proposed exposure is not finite."
                    )

                diagnostics.risk_checks += 1

                risk_decision = (
                    self.risk_engine.pre_trade_check(
                        equity=equity,
                        daily_loss=daily_loss,
                        open_positions=0,
                        current_exposure=0.0,
                        proposed_exposure=proposed_exposure,
                        entry_price=entry_price,
                        stop_loss_price=stop_loss,
                        take_profit_price=take_profit,
                        volume=position_size,
                        side=decision.direction.value,
                        specification=specification,
                    )
                )

            except RiskEngineError as exc:

                diagnostics.record_exception(
                    timestamp=self._timestamp(candle),
                    error=exc,
                )

                raise BacktestEngineError(
                    "Risk Engine failed at historical "
                    f"index {index}: {exc}"
                ) from exc

            if not risk_decision.allowed:
                diagnostics.record_risk_rejection(
                    decision=decision,
                    timestamp=self._timestamp(candle),
                    risk_decision=risk_decision,
                )
                continue

            diagnostics.accepted_entries += 1

            initial_risk = abs(
                entry_price - stop_loss
            )

            if (
                not isfinite(initial_risk)
                or initial_risk <= 0
            ):
                raise BacktestEngineError(
                    "Calculated initial trade risk is invalid."
                )

            open_position = _OpenPosition(
                trade_id=self._new_trade_id(),
                direction=decision.direction,
                signal_time=self._timestamp(candle),
                entry_time=entry_time,
                signal_price=float(
                    proposal.entry_price
                ),
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=position_size,
                contract_size=float(specification.contract_size),
                initial_stop_loss=stop_loss,
                initial_take_profit=take_profit,
                initial_position_size=position_size,
                initial_risk=initial_risk,
            )

        if (
            open_position is not None
            and self.config.close_open_position_at_end
        ):
            final_candle = normalized[-1]

            raw_exit_price = float(
                final_candle["close"]
            )

            exit_price = self._apply_exit_costs(
                direction=open_position.direction,
                raw_price=raw_exit_price,
            )

            final_trade = self._close_position(
                position=open_position,
                exit_price=exit_price,
                exit_time=self._timestamp(
                    final_candle
                ),
                exit_reason="end_of_data",
            )

            final_close_pnl = (
                final_trade.pnl
                - final_trade.partial_realized_pnl
            )
            balance += final_close_pnl
            trades.append(final_trade)

            open_position = None

            if equity_curve:
                final_equity = balance

                if final_equity > peak_equity:
                    peak_equity = final_equity

                final_drawdown = max(
                    0.0,
                    peak_equity - final_equity,
                )

                final_drawdown_percent = (
                    (final_drawdown / peak_equity) * 100
                    if peak_equity > 0
                    else 0.0
                )

                max_drawdown = max(
                    max_drawdown,
                    final_drawdown,
                )

                max_drawdown_percent = max(
                    max_drawdown_percent,
                    final_drawdown_percent,
                )

                equity_curve.append(
                    BacktestEquityPoint(
                        timestamp=self._timestamp(
                            final_candle
                        ),
                        balance=round(balance, 8),
                        equity=round(final_equity, 8),
                        drawdown=round(
                            final_drawdown,
                            8,
                        ),
                        drawdown_percent=round(
                            final_drawdown_percent,
                            8,
                        ),
                    )
                )

        result = self._build_result(
            normalized=normalized,
            balance=balance,
            trades=trades,
            equity_curve=equity_curve,
            max_drawdown=max_drawdown,
            max_drawdown_percent=max_drawdown_percent,
            diagnostics=diagnostics,
        )

        self._print_diagnostics(
            diagnostics=diagnostics,
            result=result,
        )

        return result

    @staticmethod
    def _validate_and_normalize_candles(
        candles: Sequence[Mapping[str, Any]],
        *,
        require_timestamps: bool = False,
    ) -> list[dict[str, Any]]:

        if not candles:
            raise BacktestEngineError(
                "At least one historical candle is required."
            )

        normalized: list[dict[str, Any]] = []

        previous_timestamp: Optional[str] = None

        for index, raw in enumerate(candles):

            if not isinstance(raw, Mapping):
                raise BacktestEngineError(
                    f"Candle {index} is not an object."
                )

            required = (
                "open",
                "high",
                "low",
                "close",
            )

            for field_name in required:
                if field_name not in raw:
                    raise BacktestEngineError(
                        f"Candle {index} is missing '{field_name}'."
                    )

            try:
                open_price = float(raw["open"])
                high = float(raw["high"])
                low = float(raw["low"])
                close = float(raw["close"])

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise BacktestEngineError(
                    f"Candle {index} contains a non-numeric OHLC value."
                ) from exc

            values = (
                open_price,
                high,
                low,
                close,
            )

            if not all(
                isfinite(value)
                for value in values
            ):
                raise BacktestEngineError(
                    f"Candle {index} contains a non-finite OHLC value."
                )

            if low > high:
                raise BacktestEngineError(
                    f"Candle {index} has low greater than high."
                )

            if not (
                low
                <= open_price
                <= high
            ):
                raise BacktestEngineError(
                    f"Candle {index} open is outside "
                    "the candle range."
                )

            if not (
                low
                <= close
                <= high
            ):
                raise BacktestEngineError(
                    f"Candle {index} close is outside "
                    "the candle range."
                )

            item = dict(raw)

            item["open"] = open_price
            item["high"] = high
            item["low"] = low
            item["close"] = close

            timestamp = (
                item.get("timestamp")
                if item.get("timestamp") is not None
                else item.get("time")
            )

            if timestamp is None:
                timestamp = item.get("datetime")

            if timestamp is None and require_timestamps:
                raise BacktestEngineError(
                    f"Candle {index} requires a timestamp for multi-timeframe alignment."
                )

            if timestamp is not None:

                timestamp_text = str(timestamp)

                if (
                    previous_timestamp is not None
                    and timestamp_text <= previous_timestamp
                ):
                    raise BacktestEngineError(
                        "Historical candles must be strictly "
                        "chronological."
                    )

                previous_timestamp = timestamp_text

            normalized.append(item)

        return normalized

    def _check_exit(
        self,
        *,
        position: _OpenPosition,
        candle: Mapping[str, Any],
    ) -> Optional[BacktestTrade]:

        open_price = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])

        if position.direction is AIDirection.BUY:

            hit_stop = low <= position.stop_loss
            hit_target = high >= position.take_profit

            if open_price <= position.stop_loss:

                exit_price = self._apply_exit_costs(
                    direction=position.direction,
                    raw_price=open_price,
                )

                return self._close_position(
                    position=position,
                    exit_price=exit_price,
                    exit_time=self._timestamp(candle),
                    exit_reason="stop_loss_gap",
                )

            if open_price >= position.take_profit:

                exit_price = self._apply_exit_costs(
                    direction=position.direction,
                    raw_price=open_price,
                )

                return self._close_position(
                    position=position,
                    exit_price=exit_price,
                    exit_time=self._timestamp(candle),
                    exit_reason="take_profit_gap",
                )

            # If both are touched, SL is assumed first.
            if hit_stop:

                exit_price = self._apply_exit_costs(
                    direction=position.direction,
                    raw_price=position.stop_loss,
                )

                return self._close_position(
                    position=position,
                    exit_price=exit_price,
                    exit_time=self._timestamp(candle),
                    exit_reason="stop_loss",
                )

            if hit_target:

                exit_price = self._apply_exit_costs(
                    direction=position.direction,
                    raw_price=position.take_profit,
                )

                return self._close_position(
                    position=position,
                    exit_price=exit_price,
                    exit_time=self._timestamp(candle),
                    exit_reason="take_profit",
                )

        elif position.direction is AIDirection.SELL:

            hit_stop = high >= position.stop_loss
            hit_target = low <= position.take_profit

            if open_price >= position.stop_loss:

                exit_price = self._apply_exit_costs(
                    direction=position.direction,
                    raw_price=open_price,
                )

                return self._close_position(
                    position=position,
                    exit_price=exit_price,
                    exit_time=self._timestamp(candle),
                    exit_reason="stop_loss_gap",
                )

            if open_price <= position.take_profit:

                exit_price = self._apply_exit_costs(
                    direction=position.direction,
                    raw_price=open_price,
                )

                return self._close_position(
                    position=position,
                    exit_price=exit_price,
                    exit_time=self._timestamp(candle),
                    exit_reason="take_profit_gap",
                )

            # If both are touched, SL is assumed first.
            if hit_stop:

                exit_price = self._apply_exit_costs(
                    direction=position.direction,
                    raw_price=position.stop_loss,
                )

                return self._close_position(
                    position=position,
                    exit_price=exit_price,
                    exit_time=self._timestamp(candle),
                    exit_reason="stop_loss",
                )

            if hit_target:

                exit_price = self._apply_exit_costs(
                    direction=position.direction,
                    raw_price=position.take_profit,
                )

                return self._close_position(
                    position=position,
                    exit_price=exit_price,
                    exit_time=self._timestamp(candle),
                    exit_reason="take_profit",
                )

        return None

    def _manage_open_position(
        self,
        *,
        position: _OpenPosition,
        candle: Mapping[str, Any],
        diagnostics: BacktestDiagnostics,
    ) -> float:
        """
        Apply dynamic management AFTER the current candle's normal SL/TP
        check.

        Returns realized PnL generated by a partial exit on this candle.
        """

        if position.position_size <= 0:
            raise BacktestEngineError(
                "Open position has invalid remaining position size."
            )

        risk = position.initial_risk

        if (
            not isfinite(risk)
            or risk <= 0
        ):
            raise BacktestEngineError(
                "Open position has invalid initial risk."
            )

        high = float(candle["high"])
        low = float(candle["low"])
        timestamp = self._timestamp(candle)

        management_pnl = 0.0

        if position.direction is AIDirection.BUY:

            one_r_price = (
                position.entry_price
                + risk * self.PARTIAL_TP_R
            )

            one_point_two_five_r_price = (
                position.entry_price
                + risk * self.TP_EXTENSION_TRIGGER_R
            )

            one_point_five_r_price = (
                position.entry_price
                + risk * self.TRAILING_TRIGGER_R
            )

            two_point_five_r_price = (
                position.entry_price
                + risk * self.TP_EXTENSION_R
            )

            # ---------------------------------------------------------
            # 1R PARTIAL TP
            # ---------------------------------------------------------
            if (
                high >= one_r_price
                and not position.partial_take_profit_taken
            ):
                partial_size = (
                    position.position_size * 0.50
                )

                if partial_size > 0:

                    raw_partial_exit = one_r_price

                    partial_exit_price = (
                        self._apply_exit_costs(
                            direction=position.direction,
                            raw_price=raw_partial_exit,
                        )
                    )

                    gross_partial_pnl = (
                        partial_exit_price
                        - position.entry_price
                    ) * partial_size * position.contract_size

                    commission = (
                        self.config.commission_per_unit
                        * partial_size
                    )

                    partial_pnl = (
                        gross_partial_pnl
                        - commission
                    )

                    position.position_size -= partial_size

                    if position.position_size < 0:
                        position.position_size = 0.0

                    position.realized_pnl += partial_pnl
                    position.partial_realized_gross_pnl += (
                        gross_partial_pnl
                    )
                    position.partial_take_profit_taken = True

                    management_pnl += partial_pnl

                    self._record_management_event(
                        position=position,
                        diagnostics=diagnostics,
                        event="PARTIAL_TAKE_PROFIT",
                        timestamp=timestamp,
                        details={
                            "r_multiple": 1.0,
                            "raw_price": round(
                                raw_partial_exit,
                                8,
                            ),
                            "execution_price": round(
                                partial_exit_price,
                                8,
                            ),
                            "closed_size": round(
                                partial_size,
                                8,
                            ),
                            "remaining_size": round(
                                position.position_size,
                                8,
                            ),
                            "pnl": round(
                                partial_pnl,
                                8,
                            ),
                        },
                    )

            # ---------------------------------------------------------
            # BREAK EVEN
            # ---------------------------------------------------------
            if (
                high >= one_r_price
                and not position.break_even_active
            ):
                old_stop = position.stop_loss

                if position.stop_loss < position.entry_price:
                    position.stop_loss = position.entry_price

                position.break_even_active = True

                self._record_management_event(
                    position=position,
                    diagnostics=diagnostics,
                    event="BREAK_EVEN",
                    timestamp=timestamp,
                    details={
                        "old_stop_loss": round(
                            old_stop,
                            8,
                        ),
                        "new_stop_loss": round(
                            position.stop_loss,
                            8,
                        ),
                        "r_multiple": 1.0,
                    },
                )

            # ---------------------------------------------------------
            # TP EXTENSION
            # ---------------------------------------------------------
            if (
                high >= one_point_two_five_r_price
                and position.take_profit
                < two_point_five_r_price
            ):
                old_take_profit = position.take_profit

                position.take_profit = (
                    two_point_five_r_price
                )

                self._record_management_event(
                    position=position,
                    diagnostics=diagnostics,
                    event="TAKE_PROFIT_EXTENSION",
                    timestamp=timestamp,
                    details={
                        "old_take_profit": round(
                            old_take_profit,
                            8,
                        ),
                        "new_take_profit": round(
                            position.take_profit,
                            8,
                        ),
                        "trigger_r": 1.25,
                        "target_r": 2.5,
                    },
                )

            # ---------------------------------------------------------
            # TRAILING STOP
            # ---------------------------------------------------------
            if high >= one_point_five_r_price:

                if not position.trailing_active:
                    position.trailing_active = True

                    self._record_management_event(
                        position=position,
                        diagnostics=diagnostics,
                        event="TRAILING_ACTIVATED",
                        timestamp=timestamp,
                        details={
                            "trigger_r": 1.5,
                            "distance_r": 0.75,
                        },
                    )

                proposed_stop = (
                    high
                    - risk * self.TRAILING_DISTANCE_R
                )

                # Never move a BUY stop backwards.
                proposed_stop = max(
                    proposed_stop,
                    position.stop_loss,
                )

                # Keep protective stop below target.
                if (
                    position.take_profit > 0
                    and proposed_stop
                    < position.take_profit
                ):
                    if proposed_stop > position.stop_loss:

                        old_stop = position.stop_loss
                        position.stop_loss = proposed_stop

                        self._record_management_event(
                            position=position,
                            diagnostics=diagnostics,
                            event="TRAILING_STOP_UPDATE",
                            timestamp=timestamp,
                            details={
                                "old_stop_loss": round(
                                    old_stop,
                                    8,
                                ),
                                "new_stop_loss": round(
                                    position.stop_loss,
                                    8,
                                ),
                                "candle_high": round(
                                    high,
                                    8,
                                ),
                                "distance_r": 0.75,
                            },
                        )

        elif position.direction is AIDirection.SELL:

            one_r_price = (
                position.entry_price
                - risk * self.PARTIAL_TP_R
            )

            one_point_two_five_r_price = (
                position.entry_price
                - risk * self.TP_EXTENSION_TRIGGER_R
            )

            one_point_five_r_price = (
                position.entry_price
                - risk * self.TRAILING_TRIGGER_R
            )

            two_point_five_r_price = (
                position.entry_price
                - risk * self.TP_EXTENSION_R
            )

            # ---------------------------------------------------------
            # 1R PARTIAL TP
            # ---------------------------------------------------------
            if (
                low <= one_r_price
                and not position.partial_take_profit_taken
            ):
                partial_size = (
                    position.position_size * 0.50
                )

                if partial_size > 0:

                    raw_partial_exit = one_r_price

                    partial_exit_price = (
                        self._apply_exit_costs(
                            direction=position.direction,
                            raw_price=raw_partial_exit,
                        )
                    )

                    gross_partial_pnl = (
                        position.entry_price
                        - partial_exit_price
                    ) * partial_size * position.contract_size

                    commission = (
                        self.config.commission_per_unit
                        * partial_size
                    )

                    partial_pnl = (
                        gross_partial_pnl
                        - commission
                    )

                    position.position_size -= partial_size

                    if position.position_size < 0:
                        position.position_size = 0.0

                    position.realized_pnl += partial_pnl
                    position.partial_realized_gross_pnl += (
                        gross_partial_pnl
                    )
                    position.partial_take_profit_taken = True

                    management_pnl += partial_pnl

                    self._record_management_event(
                        position=position,
                        diagnostics=diagnostics,
                        event="PARTIAL_TAKE_PROFIT",
                        timestamp=timestamp,
                        details={
                            "r_multiple": 1.0,
                            "raw_price": round(
                                raw_partial_exit,
                                8,
                            ),
                            "execution_price": round(
                                partial_exit_price,
                                8,
                            ),
                            "closed_size": round(
                                partial_size,
                                8,
                            ),
                            "remaining_size": round(
                                position.position_size,
                                8,
                            ),
                            "pnl": round(
                                partial_pnl,
                                8,
                            ),
                        },
                    )

            # ---------------------------------------------------------
            # BREAK EVEN
            # ---------------------------------------------------------
            if (
                low <= one_r_price
                and not position.break_even_active
            ):
                old_stop = position.stop_loss

                if position.stop_loss > position.entry_price:
                    position.stop_loss = position.entry_price

                position.break_even_active = True

                self._record_management_event(
                    position=position,
                    diagnostics=diagnostics,
                    event="BREAK_EVEN",
                    timestamp=timestamp,
                    details={
                        "old_stop_loss": round(
                            old_stop,
                            8,
                        ),
                        "new_stop_loss": round(
                            position.stop_loss,
                            8,
                        ),
                        "r_multiple": 1.0,
                    },
                )

            # ---------------------------------------------------------
            # TP EXTENSION
            # ---------------------------------------------------------
            if (
                low <= one_point_two_five_r_price
                and position.take_profit
                > two_point_five_r_price
            ):
                old_take_profit = position.take_profit

                position.take_profit = (
                    two_point_five_r_price
                )

                self._record_management_event(
                    position=position,
                    diagnostics=diagnostics,
                    event="TAKE_PROFIT_EXTENSION",
                    timestamp=timestamp,
                    details={
                        "old_take_profit": round(
                            old_take_profit,
                            8,
                        ),
                        "new_take_profit": round(
                            position.take_profit,
                            8,
                        ),
                        "trigger_r": 1.25,
                        "target_r": 2.5,
                    },
                )

            # ---------------------------------------------------------
            # TRAILING STOP
            # ---------------------------------------------------------
            if low <= one_point_five_r_price:

                if not position.trailing_active:
                    position.trailing_active = True

                    self._record_management_event(
                        position=position,
                        diagnostics=diagnostics,
                        event="TRAILING_ACTIVATED",
                        timestamp=timestamp,
                        details={
                            "trigger_r": 1.5,
                            "distance_r": 0.75,
                        },
                    )

                proposed_stop = (
                    low
                    + risk * self.TRAILING_DISTANCE_R
                )

                # Never move a SELL stop backwards.
                proposed_stop = min(
                    proposed_stop,
                    position.stop_loss,
                )

                # Keep protective stop above target.
                if (
                    position.take_profit > 0
                    and proposed_stop
                    > position.take_profit
                ):
                    if proposed_stop < position.stop_loss:

                        old_stop = position.stop_loss
                        position.stop_loss = proposed_stop

                        self._record_management_event(
                            position=position,
                            diagnostics=diagnostics,
                            event="TRAILING_STOP_UPDATE",
                            timestamp=timestamp,
                            details={
                                "old_stop_loss": round(
                                    old_stop,
                                    8,
                                ),
                                "new_stop_loss": round(
                                    position.stop_loss,
                                    8,
                                ),
                                "candle_low": round(
                                    low,
                                    8,
                                ),
                                "distance_r": 0.75,
                            },
                        )

        else:
            raise BacktestEngineError(
                "Cannot manage WAIT position."
            )

        # Apply the additional profit-protection layer after the existing
        # management rules. This means it can tighten a stop but can never
        # loosen a stop already improved by break-even or trailing logic.
        if self.config.profit_protection_enabled:
            self._apply_profit_protection(
                position=position,
                candle=candle,
                diagnostics=diagnostics,
            )

        return management_pnl

    def _apply_profit_protection(
        self,
        *,
        position: _OpenPosition,
        candle: Mapping[str, Any],
        diagnostics: BacktestDiagnostics,
    ) -> None:
        """Lock a small profit once the trade has proved itself."""

        risk = position.initial_risk
        trigger = self.config.profit_protection_trigger_r
        lock = self.config.profit_protection_lock_r

        if risk <= 0 or trigger <= 0:
            return

        if position.direction is AIDirection.BUY:
            trigger_price = position.entry_price + risk * trigger
            protected_stop = position.entry_price + risk * lock
            reached = float(candle["high"]) >= trigger_price

            if reached and protected_stop > position.stop_loss:
                old_stop = position.stop_loss
                position.stop_loss = min(
                    protected_stop,
                    position.take_profit - max(risk * 0.001, 1e-9),
                )
                if position.stop_loss > old_stop:
                    self._record_management_event(
                        position=position,
                        diagnostics=diagnostics,
                        event="PROFIT_PROTECTION",
                        timestamp=self._timestamp(candle),
                        details={
                            "trigger_r": trigger,
                            "lock_r": lock,
                            "old_stop_loss": round(old_stop, 8),
                            "new_stop_loss": round(position.stop_loss, 8),
                        },
                    )

        elif position.direction is AIDirection.SELL:
            trigger_price = position.entry_price - risk * trigger
            protected_stop = position.entry_price - risk * lock
            reached = float(candle["low"]) <= trigger_price

            if reached and protected_stop < position.stop_loss:
                old_stop = position.stop_loss
                position.stop_loss = max(
                    protected_stop,
                    position.take_profit + max(risk * 0.001, 1e-9),
                )
                if position.stop_loss < old_stop:
                    self._record_management_event(
                        position=position,
                        diagnostics=diagnostics,
                        event="PROFIT_PROTECTION",
                        timestamp=self._timestamp(candle),
                        details={
                            "trigger_r": trigger,
                            "lock_r": lock,
                            "old_stop_loss": round(old_stop, 8),
                            "new_stop_loss": round(position.stop_loss, 8),
                        },
                    )

    @staticmethod
    def _record_management_event(
        *,
        position: _OpenPosition,
        diagnostics: BacktestDiagnostics,
        event: str,
        timestamp: Optional[str],
        details: Optional[dict[str, Any]] = None,
    ) -> None:

        record: dict[str, Any] = {
            "event": event,
            "timestamp": timestamp,
        }

        if details:
            record.update(details)

        position.management_events.append(record)

        diagnostics.record_management(
            event=event,
            timestamp=timestamp,
            details=details,
        )

    def _close_position(
        self,
        *,
        position: _OpenPosition,
        exit_price: float,
        exit_time: Optional[str],
        exit_reason: str,
    ) -> BacktestTrade:

        if position.direction is AIDirection.BUY:

            gross_pnl = (
                exit_price
                - position.entry_price
            ) * position.position_size * position.contract_size

        elif position.direction is AIDirection.SELL:

            gross_pnl = (
                position.entry_price
                - exit_price
            ) * position.position_size * position.contract_size

        else:
            raise BacktestEngineError(
                "Cannot close WAIT position."
            )

        commission = (
            self.config.commission_per_unit
            * position.position_size
        )

        remaining_pnl = (
            gross_pnl
            - commission
        )

        # The position's realized partial PnL was already added to balance
        # when the partial exit occurred. Therefore this method returns ONLY
        # the PnL from the remaining position plus the remaining exit cost.
        total_pnl = (
            position.realized_pnl
            + remaining_pnl
        )

        total_execution_cost = (
            (
                abs(
                    position.partial_realized_gross_pnl
                    - position.realized_pnl
                )
            )
            + abs(
                gross_pnl
                - remaining_pnl
            )
        )

        notional = abs(
            position.entry_price
            * position.initial_position_size
            * position.contract_size
        )

        pnl_percent = (
            (total_pnl / notional) * 100
            if notional > 0
            else 0.0
        )

        management_events = [
            dict(event)
            for event in position.management_events
        ]

        return BacktestTrade(
            trade_id=position.trade_id,
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            direction=position.direction.value,
            signal_time=position.signal_time,
            entry_time=position.entry_time,
            exit_time=exit_time,
            signal_price=position.signal_price,
            entry_price=round(
                position.entry_price,
                8,
            ),
            exit_price=round(
                exit_price,
                8,
            ),
            stop_loss=round(
                position.stop_loss,
                8,
            ),
            take_profit=round(
                position.take_profit,
                8,
            ),
            position_size=round(
                position.initial_position_size,
                8,
            ),
            pnl=round(
                total_pnl,
                8,
            ),
            pnl_percent=round(
                pnl_percent,
                8,
            ),
            execution_cost=round(
                total_execution_cost,
                8,
            ),
            exit_reason=exit_reason,
            bars_held=position.bars_held,
            initial_stop_loss=round(
                position.initial_stop_loss,
                8,
            ),
            initial_take_profit=round(
                position.initial_take_profit,
                8,
            ),
            initial_position_size=round(
                position.initial_position_size,
                8,
            ),
            remaining_position_size=round(
                position.position_size,
                8,
            ),
            initial_risk=round(
                position.initial_risk,
                8,
            ),
            partial_realized_pnl=round(
                position.realized_pnl,
                8,
            ),
            break_even_active=(
                position.break_even_active
            ),
            partial_take_profit_taken=(
                position.partial_take_profit_taken
            ),
            trailing_active=(
                position.trailing_active
            ),
            management_event_count=len(
                management_events
            ),
            management_events=management_events,
        )

    @staticmethod
    def _unrealized_pnl(
        *,
        position: _OpenPosition,
        mark_price: float,
    ) -> float:

        if not isfinite(mark_price):
            raise BacktestEngineError(
                "Mark price must be finite."
            )

        if position.direction is AIDirection.BUY:
            return (
                mark_price
                - position.entry_price
            ) * position.position_size * position.contract_size

        if position.direction is AIDirection.SELL:
            return (
                position.entry_price
                - mark_price
            ) * position.position_size * position.contract_size

        raise BacktestEngineError(
            "Cannot calculate unrealized PnL for WAIT position."
        )

    def _apply_entry_costs(
        self,
        *,
        direction: AIDirection,
        raw_price: float,
    ) -> float:

        half_spread = self.config.spread / 2.0

        if direction is AIDirection.BUY:

            adjusted = (
                raw_price
                + half_spread
                + self.config.slippage
            )

        elif direction is AIDirection.SELL:

            adjusted = (
                raw_price
                - half_spread
                - self.config.slippage
            )

        else:
            raise BacktestEngineError(
                "WAIT cannot create an entry."
            )

        if not isfinite(adjusted) or adjusted <= 0:
            raise BacktestEngineError(
                "Execution-cost model produced an invalid entry price."
            )

        return adjusted

    def _apply_exit_costs(
        self,
        *,
        direction: AIDirection,
        raw_price: float,
    ) -> float:

        half_spread = self.config.spread / 2.0

        if direction is AIDirection.BUY:

            adjusted = (
                raw_price
                - half_spread
                - self.config.slippage
            )

        elif direction is AIDirection.SELL:

            adjusted = (
                raw_price
                + half_spread
                + self.config.slippage
            )

        else:
            raise BacktestEngineError(
                "WAIT cannot create an exit."
            )

        if not isfinite(adjusted) or adjusted <= 0:
            raise BacktestEngineError(
                "Execution-cost model produced an invalid exit price."
            )

        return adjusted

    @staticmethod
    def _rebase_protective_levels(
        *,
        direction: AIDirection,
        signal_entry: float,
        actual_entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> tuple[float, float]:

        if not all(
            isfinite(value)
            for value in (
                signal_entry,
                actual_entry,
                stop_loss,
                take_profit,
            )
        ):
            raise BacktestEngineError(
                "Protective levels must be finite."
            )

        delta = (
            actual_entry
            - signal_entry
        )

        rebased_stop = stop_loss + delta

        rebased_take_profit = (
            take_profit + delta
        )

        if direction is AIDirection.BUY:

            if not (
                rebased_stop
                < actual_entry
                < rebased_take_profit
            ):
                raise BacktestEngineError(
                    "Invalid BUY protective levels after "
                    "next-open rebasing."
                )

        elif direction is AIDirection.SELL:

            if not (
                rebased_take_profit
                < actual_entry
                < rebased_stop
            ):
                raise BacktestEngineError(
                    "Invalid SELL protective levels after "
                    "next-open rebasing."
                )

        else:
            raise BacktestEngineError(
                "WAIT cannot create protective levels."
            )

        return (
            rebased_stop,
            rebased_take_profit,
        )

    @staticmethod
    def _timestamp_datetime(
        candle: Mapping[str, Any],
    ) -> Optional[datetime]:
        value = candle.get("timestamp")
        if value is None:
            value = candle.get("time")
        if value is None:
            value = candle.get("datetime")
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _trading_day(
        candle: Mapping[str, Any],
    ) -> Optional[date]:

        value = candle.get("timestamp")

        if value is None:
            value = candle.get("time")

        if value is None:
            value = candle.get("datetime")

        if value is None:
            return None

        if isinstance(value, datetime):

            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc)

            return value.date()

        if isinstance(value, date):
            return value

        if isinstance(value, (int, float)):

            if not isfinite(float(value)):
                return None

            try:
                return datetime.fromtimestamp(
                    float(value),
                    tz=timezone.utc,
                ).date()

            except (
                OverflowError,
                OSError,
                ValueError,
            ):
                return None

        text = str(value).strip()

        if not text:
            return None

        try:

            parsed = datetime.fromisoformat(
                text.replace("Z", "+00:00")
            )

            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc)

            return parsed.date()

        except ValueError:
            pass

        try:
            return date.fromisoformat(
                text[:10]
            )

        except ValueError:
            return None

    def _build_result(
        self,
        *,
        normalized: Sequence[Mapping[str, Any]],
        balance: float,
        trades: Sequence[BacktestTrade],
        equity_curve: Sequence[BacktestEquityPoint],
        max_drawdown: float,
        max_drawdown_percent: float,
        diagnostics: BacktestDiagnostics,
    ) -> BacktestResult:

        wins = [
            trade
            for trade in trades
            if trade.pnl > 0
        ]

        losses = [
            trade
            for trade in trades
            if trade.pnl < 0
        ]

        breakeven = [
            trade
            for trade in trades
            if trade.pnl == 0
        ]

        gross_profit = sum(
            trade.pnl
            for trade in wins
        )

        gross_loss = abs(
            sum(
                trade.pnl
                for trade in losses
            )
        )

        total_execution_cost = sum(
            trade.execution_cost
            for trade in trades
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (
                None
                if gross_profit == 0
                else float("inf")
            )
        )

        net_profit = (
            balance
            - self.config.starting_balance
        )

        net_profit_percent = (
            net_profit
            / self.config.starting_balance
            * 100
        )

        win_rate = (
            len(wins)
            / len(trades)
            * 100
            if trades
            else 0.0
        )

        average_trade = (
            net_profit / len(trades)
            if trades
            else 0.0
        )

        average_win = (
            gross_profit / len(wins)
            if wins
            else 0.0
        )

        average_loss = (
            -gross_loss / len(losses)
            if losses
            else 0.0
        )

        serialized_trades: list[dict[str, Any]] = []

        for trade in trades:

            serialized = asdict(trade)

            serialized["symbol"] = (
                self.config.symbol
            )

            serialized["timeframe"] = (
                self.config.timeframe
            )

            serialized_trades.append(
                serialized
            )

        serialized_equity = [
            asdict(point)
            for point in equity_curve
        ]

        return BacktestResult(
            status="completed",
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            start_time=self._timestamp(
                normalized[0]
            ),
            end_time=self._timestamp(
                normalized[-1]
            ),
            starting_balance=round(
                self.config.starting_balance,
                8,
            ),
            ending_balance=round(
                balance,
                8,
            ),
            net_profit=round(
                net_profit,
                8,
            ),
            net_profit_percent=round(
                net_profit_percent,
                8,
            ),
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            breakeven_trades=len(breakeven),
            win_rate_percent=round(
                win_rate,
                8,
            ),
            gross_profit=round(
                gross_profit,
                8,
            ),
            gross_loss=round(
                gross_loss,
                8,
            ),
            profit_factor=(
                round(
                    profit_factor,
                    8,
                )
                if profit_factor is not None
                and profit_factor != float("inf")
                else profit_factor
            ),
            total_execution_cost=round(
                total_execution_cost,
                8,
            ),
            max_drawdown=round(
                max_drawdown,
                8,
            ),
            max_drawdown_percent=round(
                max_drawdown_percent,
                8,
            ),
            average_trade=round(
                average_trade,
                8,
            ),
            average_win=round(
                average_win,
                8,
            ),
            average_loss=round(
                average_loss,
                8,
            ),
            bars_processed=len(normalized),
            warmup_candles=self.config.warmup_candles,
            trades=serialized_trades,
            equity_curve=serialized_equity,
            diagnostics=diagnostics.to_dict(),
        )

    @staticmethod
    def _print_diagnostics(
        *,
        diagnostics: BacktestDiagnostics,
        result: BacktestResult,
    ) -> None:

        print(
            "",
            flush=True,
        )

        print(
            "========================================",
            flush=True,
        )

        print(
            "RAYMOND v2.8 BACKTEST DIAGNOSTICS",
            flush=True,
        )

        print(
            "========================================",
            flush=True,
        )

        print(
            f"Candles evaluated: "
            f"{diagnostics.candles_evaluated:,}",
            flush=True,
        )

        print(
            f"WAIT decisions: "
            f"{diagnostics.wait_decisions:,}",
            flush=True,
        )

        print(
            f"BUY decisions: "
            f"{diagnostics.buy_decisions:,}",
            flush=True,
        )

        print(
            f"SELL decisions: "
            f"{diagnostics.sell_decisions:,}",
            flush=True,
        )

        print(
            f"Decisions with proposal: "
            f"{diagnostics.decisions_with_proposal:,}",
            flush=True,
        )

        print(
            f"Decisions without proposal: "
            f"{diagnostics.decisions_without_proposal:,}",
            flush=True,
        )

        print(
            f"Missing stop loss: "
            f"{diagnostics.missing_stop_loss:,}",
            flush=True,
        )

        print(
            f"Missing take profit: "
            f"{diagnostics.missing_take_profit:,}",
            flush=True,
        )

        print(
            f"Zero position size: "
            f"{diagnostics.zero_position_size:,}",
            flush=True,
        )

        print(
            f"Risk checks: "
            f"{diagnostics.risk_checks:,}",
            flush=True,
        )

        print(
            f"Risk rejections: "
            f"{diagnostics.risk_rejections:,}",
            flush=True,
        )

        print(
            f"Accepted entries: "
            f"{diagnostics.accepted_entries:,}",
            flush=True,
        )

        print(
            f"Actual completed trades: "
            f"{result.total_trades:,}",
            flush=True,
        )

        print(
            "",
            flush=True,
        )

        print(
            "POSITION MANAGEMENT:",
            flush=True,
        )

        print(
            f"  Partial take profits: "
            f"{diagnostics.partial_take_profits:,}",
            flush=True,
        )

        print(
            f"  Break-even activations: "
            f"{diagnostics.break_even_activations:,}",
            flush=True,
        )

        print(
            f"  TP extensions: "
            f"{diagnostics.take_profit_extensions:,}",
            flush=True,
        )

        print(
            f"  Trailing activations: "
            f"{diagnostics.trailing_activations:,}",
            flush=True,
        )

        print(
            f"  Trailing stop updates: "
            f"{diagnostics.trailing_stop_updates:,}",
            flush=True,
        )

        print(
            f"  Profit protection activations: "
            f"{diagnostics.profit_protection_activations:,}",
            flush=True,
        )

        print(
            f"  Lower-timeframe checks: "
            f"{diagnostics.lower_timeframe_checks:,}",
            flush=True,
        )

        print(
            f"  Lower-timeframe rejections: "
            f"{diagnostics.lower_timeframe_rejections:,}",
            flush=True,
        )

        print(
            "",
            flush=True,
        )

        print(
            "WAIT REASONS:",
            flush=True,
        )

        if diagnostics.wait_reason_counts:

            for reason, count in sorted(
                diagnostics.wait_reason_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            ):
                print(
                    f"  {reason}: {count:,}",
                    flush=True,
                )

        else:

            print(
                "  None recorded",
                flush=True,
            )

        print(
            "",
            flush=True,
        )

        print(
            "RISK REJECTION REASONS:",
            flush=True,
        )

        if diagnostics.risk_rejection_reason_counts:

            for reason, count in sorted(
                diagnostics.risk_rejection_reason_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            ):
                print(
                    f"  {reason}: {count:,}",
                    flush=True,
                )

        else:

            print(
                "  None recorded",
                flush=True,
            )

        print(
            "",
            flush=True,
        )

        print(
            "CONFIDENCE:",
            flush=True,
        )

        print(
            f"  Observations: "
            f"{diagnostics.confidence_observations:,}",
            flush=True,
        )

        print(
            f"  Minimum: "
            f"{diagnostics.minimum_confidence_observed}",
            flush=True,
        )

        print(
            f"  Maximum: "
            f"{diagnostics.maximum_confidence_observed}",
            flush=True,
        )

        print(
            "",
            flush=True,
        )

        print(
            "CONFLUENCE:",
            flush=True,
        )

        print(
            f"  Observations: "
            f"{diagnostics.confluence_observations:,}",
            flush=True,
        )

        print(
            f"  Minimum: "
            f"{diagnostics.minimum_confluence_observed}",
            flush=True,
        )

        print(
            f"  Maximum: "
            f"{diagnostics.maximum_confluence_observed}",
            flush=True,
        )

        print(
            "",
            flush=True,
        )

        print(
            "EXAMPLES:",
            flush=True,
        )

        if diagnostics.examples:

            for example in diagnostics.examples:

                print(
                    "  "
                    + str(example),
                    flush=True,
                )

        else:

            print(
                "  None recorded",
                flush=True,
            )

        print(
            "",
            flush=True,
        )

        print(
            "FULL DIAGNOSTICS JSON:",
            flush=True,
        )

        print(
            __import__("json").dumps(
                diagnostics.to_dict(),
                indent=2,
                allow_nan=False,
            ),
            flush=True,
        )

        print(
            "========================================",
            flush=True,
        )

    @staticmethod
    def _timestamp(
        candle: Mapping[str, Any],
    ) -> Optional[str]:

        value = candle.get(
            "timestamp",
            candle.get(
                "time",
                candle.get("datetime"),
            ),
        )

        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            return value.isoformat()

        return str(value)

    @staticmethod
    def _new_trade_id() -> str:
        return (
            "BT-"
            + uuid4().hex[:12].upper()
        )


def backtest_result_to_dict(
    result: BacktestResult,
) -> dict[str, Any]:
    """
    Stable API serialization helper.
    """

    return asdict(result)
