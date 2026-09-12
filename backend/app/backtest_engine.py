"""
RAYMOND v2.8 - Production Backtest Engine

Historical simulation for the canonical RAYMOND trading pipeline.

Architecture:

    Historical OHLC
        ->
    Technical Indicators
        ->
    Step 13 AI Decision
        ->
    Step 14-compatible Risk Engine sizing/checks
        ->
    Deterministic simulated execution
        ->
    Trade ledger + equity curve + performance metrics

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
  This is intentionally conservative because OHLC data cannot prove
  intrabar ordering.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Mapping, Optional, Sequence
from uuid import uuid4

from app.ai_trading_decision import (
    AIDirection,
    AITradingDecisionEngine,
)
from app.risk_engine import (
    RiskDecision,
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

    # Minimum number of candles before the strategy is evaluated.
    # EMA50 is the longest primary indicator, so 50 is the minimum.
    warmup_candles: int = 50

    # Only one simulated position is allowed in this first production
    # implementation. This keeps accounting deterministic and prevents
    # accidental portfolio-level assumptions.
    max_open_positions: int = 1

    # When a signal is generated at candle close, execution occurs at
    # the NEXT candle open. This avoids look-ahead bias.
    execute_on_next_open: bool = True

    # If a position remains open when historical data ends, close it at
    # the final available close.
    close_open_position_at_end: bool = True

    def validate(self) -> None:
        if not self.symbol.strip():
            raise BacktestEngineError("symbol is required.")

        if not self.timeframe.strip():
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

    exit_reason: str
    bars_held: int


@dataclass(frozen=True)
class BacktestEquityPoint:
    """One point on the simulated equity curve."""

    timestamp: Optional[str]
    balance: float
    equity: float
    drawdown: float
    drawdown_percent: float


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

    max_drawdown: float
    max_drawdown_percent: float

    average_trade: float
    average_win: float
    average_loss: float

    bars_processed: int
    warmup_candles: int

    trades: list[dict[str, Any]]
    equity_curve: list[dict[str, Any]]


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

    bars_held: int = 0


class BacktestEngine:
    """
    Deterministic historical simulator.

    The engine deliberately does not execute through PaperExecutionGateway.
    Backtesting has its own simulation layer so historical results cannot
    accidentally become paper/live execution requests.
    """

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

    # ============================================================
    # PUBLIC API
    # ============================================================

    def run(
        self,
        *,
        candles: Sequence[Mapping[str, Any]],
        specification: SymbolSpecification,
    ) -> BacktestResult:
        """
        Execute one deterministic backtest.

        Decisions are calculated using candles available only up to
        the current signal candle.

        Entry occurs on the next candle open.

        Existing open positions are checked against each candle's
        OHLC range before a new signal is considered.
        """

        self.config.validate()

        normalized = self._validate_and_normalize_candles(
            candles
        )

        if len(normalized) <= self.config.warmup_candles:
            raise BacktestEngineError(
                "Insufficient historical candles. "
                f"At least {self.config.warmup_candles + 1} "
                "candles are required."
            )

        specification.validate()

        if specification.symbol.upper() != self.config.symbol.upper():
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

        # The daily loss supplied to RiskEngine is intentionally based
        # on realized loss during this historical simulation.
        daily_loss = 0.0

        for index in range(
            self.config.warmup_candles,
            len(normalized),
        ):
            candle = normalized[index]

            # ----------------------------------------------------
            # 1. Manage an existing position first.
            # ----------------------------------------------------

            if open_position is not None:
                open_position.bars_held += 1

                closed_trade = self._check_exit(
                    position=open_position,
                    candle=candle,
                )

                if closed_trade is not None:
                    balance += closed_trade.pnl

                    if closed_trade.pnl < 0:
                        daily_loss += abs(
                            closed_trade.pnl
                        )

                    trades.append(
                        closed_trade
                    )

                    open_position = None

            # ----------------------------------------------------
            # 2. Mark current equity.
            # ----------------------------------------------------

            unrealized = 0.0

            if open_position is not None:
                unrealized = self._unrealized_pnl(
                    position=open_position,
                    mark_price=candle["close"],
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

            # ----------------------------------------------------
            # 3. Do not open another position while one exists.
            # ----------------------------------------------------

            if open_position is not None:
                continue

            # ----------------------------------------------------
            # 4. Generate the signal using ONLY candles up to
            #    and including the current completed candle.
            # ----------------------------------------------------

            history = normalized[: index + 1]

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
                raise BacktestEngineError(
                    "Strategy evaluation failed at historical "
                    f"index {index}: {exc}"
                ) from exc

            if decision.direction is AIDirection.WAIT:
                continue

            proposal = decision.proposal

            if proposal is None:
                raise BacktestEngineError(
                    "AI returned BUY/SELL without a proposal."
                )

            if proposal.stop_loss is None:
                raise BacktestEngineError(
                    "Trade proposal has no stop loss."
                )

            if proposal.take_profit is None:
                raise BacktestEngineError(
                    "Trade proposal has no take profit."
                )

            # ----------------------------------------------------
            # 5. We need a future candle to execute the signal.
            # ----------------------------------------------------

            next_index = index + 1

            if (
                self.config.execute_on_next_open
                and next_index >= len(normalized)
            ):
                break

            if self.config.execute_on_next_open:
                execution_candle = normalized[
                    next_index
                ]

                entry_price = float(
                    execution_candle["open"]
                )

                entry_time = self._timestamp(
                    execution_candle
                )

            else:
                execution_candle = candle
                entry_price = float(
                    proposal.entry_price
                )
                entry_time = self._timestamp(
                    candle
                )

            # ----------------------------------------------------
            # 6. Rebase SL/TP around the actual simulated entry.
            #
            # This preserves the same distance from the signal
            # price rather than silently moving the risk boundary.
            # ----------------------------------------------------

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

            # ----------------------------------------------------
            # 7. Run the existing Risk Engine.
            # ----------------------------------------------------

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
                    continue

                proposed_exposure = abs(
                    position_size
                    * entry_price
                    * specification.contract_size
                )

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
                raise BacktestEngineError(
                    "Risk Engine failed at historical "
                    f"index {index}: {exc}"
                ) from exc

            if not risk_decision.allowed:
                continue

            # ----------------------------------------------------
            # 8. Open simulated position.
            # ----------------------------------------------------

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
            )

            # ----------------------------------------------------
            # If entry happens on the next candle open, the next
            # iteration will manage its exit. We intentionally do
            # not use future intrabar data from the signal candle.
            # ----------------------------------------------------

        # ========================================================
        # FINALIZE ANY OPEN POSITION
        # ========================================================

        if (
            open_position is not None
            and self.config.close_open_position_at_end
        ):
            final_candle = normalized[-1]

            exit_price = float(
                final_candle["close"]
            )

            final_trade = self._close_position(
                position=open_position,
                exit_price=exit_price,
                exit_time=self._timestamp(
                    final_candle
                ),
                exit_reason="end_of_data",
            )

            balance += final_trade.pnl
            trades.append(final_trade)

            open_position = None

        # ========================================================
        # FINAL METRICS
        # ========================================================

        return self._build_result(
            normalized=normalized,
            balance=balance,
            trades=trades,
            equity_curve=equity_curve,
            max_drawdown=max_drawdown,
            max_drawdown_percent=max_drawdown_percent,
        )

    # ============================================================
    # CANDLE VALIDATION
    # ============================================================

    @staticmethod
    def _validate_and_normalize_candles(
        candles: Sequence[Mapping[str, Any]],
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

            for field in required:
                if field not in raw:
                    raise BacktestEngineError(
                        f"Candle {index} is missing '{field}'."
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

            # FIX:
            # dict.get() accepts only (key, default).
            # The previous implementation incorrectly passed three
            # arguments, causing:
            # TypeError: get expected at most 2 arguments, got 3
            timestamp = item.get("timestamp")

            if timestamp is None:
                timestamp = item.get("time")

            if timestamp is None:
                timestamp = item.get("datetime")

            if timestamp is not None:
                timestamp_text = (
                    str(timestamp)
                )

                if (
                    previous_timestamp is not None
                    and timestamp_text <= previous_timestamp
                ):
                    raise BacktestEngineError(
                        "Historical candles must be strictly "
                        "chronological."
                    )

                previous_timestamp = timestamp_text

                item["timestamp"] = timestamp_text

            normalized.append(item)

        return normalized

    # ============================================================
    # EXIT LOGIC
    # ============================================================

    def _check_exit(
        self,
        *,
        position: _OpenPosition,
        candle: Mapping[str, Any],
    ) -> Optional[BacktestTrade]:
        high = float(candle["high"])
        low = float(candle["low"])

        if position.direction is AIDirection.BUY:
            hit_stop = low <= position.stop_loss
            hit_target = high >= position.take_profit

            # Conservative intrabar policy:
            # if both are touched, assume SL first.
            if hit_stop:
                return self._close_position(
                    position=position,
                    exit_price=position.stop_loss,
                    exit_time=self._timestamp(candle),
                    exit_reason="stop_loss",
                )

            if hit_target:
                return self._close_position(
                    position=position,
                    exit_price=position.take_profit,
                    exit_time=self._timestamp(candle),
                    exit_reason="take_profit",
                )

        elif position.direction is AIDirection.SELL:
            hit_stop = high >= position.stop_loss
            hit_target = low <= position.take_profit

            if hit_stop:
                return self._close_position(
                    position=position,
                    exit_price=position.stop_loss,
                    exit_time=self._timestamp(candle),
                    exit_reason="stop_loss",
                )

            if hit_target:
                return self._close_position(
                    position=position,
                    exit_price=position.take_profit,
                    exit_time=self._timestamp(candle),
                    exit_reason="take_profit",
                )

        return None

    @staticmethod
    def _close_position(
        *,
        position: _OpenPosition,
        exit_price: float,
        exit_time: Optional[str],
        exit_reason: str,
    ) -> BacktestTrade:
        if position.direction is AIDirection.BUY:
            pnl = (
                exit_price
                - position.entry_price
            ) * position.position_size

        elif position.direction is AIDirection.SELL:
            pnl = (
                position.entry_price
                - exit_price
            ) * position.position_size

        else:
            raise BacktestEngineError(
                "Cannot close WAIT position."
            )

        notional = abs(
            position.entry_price
            * position.position_size
        )

        pnl_percent = (
            (pnl / notional) * 100
            if notional > 0
            else 0.0
        )

        return BacktestTrade(
            trade_id=position.trade_id,
            symbol="",
            timeframe="",
            direction=position.direction.value,
            signal_time=position.signal_time,
            entry_time=position.entry_time,
            exit_time=exit_time,
            signal_price=position.signal_price,
            entry_price=position.entry_price,
            exit_price=exit_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            position_size=position.position_size,
            pnl=round(pnl, 8),
            pnl_percent=round(
                pnl_percent,
                8,
            ),
            exit_reason=exit_reason,
            bars_held=position.bars_held,
        )

    @staticmethod
    def _unrealized_pnl(
        *,
        position: _OpenPosition,
        mark_price: float,
    ) -> float:
        if position.direction is AIDirection.BUY:
            return (
                mark_price
                - position.entry_price
            ) * position.position_size

        return (
            position.entry_price
            - mark_price
        ) * position.position_size

    # ============================================================
    # PRICE LEVEL HANDLING
    # ============================================================

    @staticmethod
    def _rebase_protective_levels(
        *,
        direction: AIDirection,
        signal_entry: float,
        actual_entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> tuple[float, float]:
        """
        Move SL/TP by the same entry-price delta.

        This avoids silently changing the intended risk/reward geometry
        when the next candle opens away from the signal close.
        """

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

    # ============================================================
    # RESULT HELPERS
    # ============================================================

    def _build_result(
        self,
        *,
        normalized: Sequence[Mapping[str, Any]],
        balance: float,
        trades: Sequence[BacktestTrade],
        equity_curve: Sequence[BacktestEquityPoint],
        max_drawdown: float,
        max_drawdown_percent: float,
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

        # Populate symbol/timeframe on immutable trade records.
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
            warmup_candles=(
                self.config.warmup_candles
            ),
            trades=serialized_trades,
            equity_curve=serialized_equity,
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
