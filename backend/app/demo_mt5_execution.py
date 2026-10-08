"""
RAYMOND v2.8 - MT5 DEMO Execution Engine

Purpose:
    Execute the existing frozen Raymond strategy against an MT5
    DEMO account.

Important:
    This module does NOT modify the Step 13 strategy.

Pipeline:

    MT5 candles
        ->
    Raymond Step 13
        ->
    Raymond Step 14 Risk Engine
        ->
    broker specification
        ->
    persistent idempotency record
        ->
    order_check
        ->
    order_send
        ->
    broker verification
        ->
    persistent execution record

Safety:
    - DEMO account required.
    - REAL accounts rejected.
    - SL required.
    - TP required.
    - Risk Engine remains authoritative.
    - Broker symbol specification is used.
    - Duplicate execution is blocked persistently.
    - Database failure blocks a new order BEFORE order_send.
    - LIVE trading is not handled here.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

try:
    from .database import SessionLocal, engine
    from .execution_state import ExecutionRecord
except ImportError:
    from database import SessionLocal, engine
    from execution_state import ExecutionRecord

from sqlalchemy import select

from app.risk_engine import (
    SymbolSpecification,
)

from app.trading_pipeline_service import (
    PaperRiskState,
    TradingPipelineService,
)


class DemoExecutionError(RuntimeError):
    """Raised when DEMO execution fails safely."""


@dataclass(frozen=True)
class DemoExecutionResult:
    status: str
    execution_mode: str
    signal_id: str | None
    symbol: str
    side: str | None
    volume: float | None
    requested_price: float | None
    executed_price: float | None
    stop_loss: float | None
    take_profit: float | None
    order_ticket: int | None
    deal_ticket: int | None
    position_ticket: int | None
    broker_retcode: int | None
    broker_comment: str | None
    verified: bool
    reason: str
    timestamp: str


class DemoMT5ExecutionEngine:
    """
    Controlled MT5 DEMO executor.

    This class deliberately does not know how to authorize LIVE trading.

    LIVE remains the responsibility of the existing live execution
    gateway and independent LIVE safety gate.
    """

    def __init__(
        self,
        *,
        trading_pipeline: TradingPipelineService | None = None,
    ) -> None:
        self.pipeline = (
            trading_pipeline
            or TradingPipelineService()
        )

        self.magic = int(
            os.getenv(
                "RAYMOND_MT5_DEMO_MAGIC",
                "28001703",
            )
        )

        self.verification_attempts = max(
            1,
            int(
                os.getenv(
                    "RAYMOND_DEMO_VERIFICATION_ATTEMPTS",
                    "5",
                )
            ),
        )

        self.verification_delay_seconds = max(
            0.05,
            float(
                os.getenv(
                    "RAYMOND_DEMO_VERIFICATION_DELAY_SECONDS",
                    "0.25",
                )
            ),
        )

    # ==================================================================
    # BASIC VALIDATION
    # ==================================================================

    @staticmethod
    def _require_mt5() -> None:
        if mt5 is None:
            raise DemoExecutionError(
                "MetaTrader5 Python package is not installed."
            )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _utc_datetime() -> datetime:
        return datetime.utcnow()

    # ==================================================================
    # PERSISTENT EXECUTION STATE
    # ==================================================================

    @staticmethod
    def _ensure_execution_table() -> None:
        """
        Ensure the execution_records table exists.

        Only the ExecutionRecord table is created here.

        This keeps DEMO execution persistence independent from whether
        another application startup path has already initialized the
        database metadata.
        """

        try:
            ExecutionRecord.__table__.create(
                bind=engine,
                checkfirst=True,
            )
        except Exception as exc:
            raise DemoExecutionError(
                "Unable to initialize persistent execution state: "
                f"{exc}"
            ) from exc

    @classmethod
    def _get_execution_record(
        cls,
        idempotency_key: str,
    ) -> ExecutionRecord | None:
        cls._ensure_execution_table()

        try:
            with SessionLocal() as db:
                statement = (
                    select(ExecutionRecord)
                    .where(
                        ExecutionRecord.idempotency_key
                        == idempotency_key
                    )
                    .limit(1)
                )

                return db.execute(
                    statement
                ).scalar_one_or_none()

        except Exception as exc:
            raise DemoExecutionError(
                "Unable to read persistent execution state: "
                f"{exc}"
            ) from exc

    @classmethod
    def _create_pending_execution(
        cls,
        *,
        signal_id: str,
        symbol: str,
        timeframe: str,
        side: str,
        volume: float,
        requested_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> ExecutionRecord:
        """
        Create the persistent execution record BEFORE order_send.

        If this fails, no broker order is attempted.
        """

        cls._ensure_execution_table()

        try:
            with SessionLocal() as db:
                existing = (
                    db.execute(
                        select(ExecutionRecord)
                        .where(
                            ExecutionRecord.idempotency_key
                            == signal_id
                        )
                        .limit(1)
                    )
                    .scalar_one_or_none()
                )

                if existing is not None:
                    return existing

                record = ExecutionRecord(
                    idempotency_key=signal_id,
                    execution_mode="demo",
                    symbol=symbol,
                    timeframe=timeframe,
                    status="pending",
                    side=side,
                    volume=float(volume),
                    requested_price=float(
                        requested_price
                    ),
                    executed_price=None,
                    stop_loss=float(stop_loss),
                    take_profit=float(take_profit),
                    order_ticket=None,
                    deal_ticket=None,
                    position_ticket=None,
                    broker_retcode=None,
                    broker_comment=None,
                    verified=False,
                    reason="Persistent DEMO execution reserved.",
                    created_at=cls._utc_datetime(),
                    updated_at=cls._utc_datetime(),
                )

                db.add(record)
                db.commit()
                db.refresh(record)

                return record

        except Exception as exc:
            raise DemoExecutionError(
                "Unable to reserve persistent execution state. "
                "DEMO order was NOT sent: "
                f"{exc}"
            ) from exc

    @classmethod
    def _update_execution_record(
        cls,
        *,
        signal_id: str,
        status: str,
        executed_price: float | None = None,
        order_ticket: int | None = None,
        deal_ticket: int | None = None,
        position_ticket: int | None = None,
        broker_retcode: int | None = None,
        broker_comment: str | None = None,
        verified: bool = False,
        reason: str = "",
    ) -> ExecutionRecord:
        cls._ensure_execution_table()

        try:
            with SessionLocal() as db:
                record = (
                    db.execute(
                        select(ExecutionRecord)
                        .where(
                            ExecutionRecord.idempotency_key
                            == signal_id
                        )
                        .limit(1)
                    )
                    .scalar_one_or_none()
                )

                if record is None:
                    raise DemoExecutionError(
                        "Persistent execution record disappeared "
                        f"for signal {signal_id}."
                    )

                record.status = status

                if executed_price is not None:
                    record.executed_price = float(
                        executed_price
                    )

                if order_ticket is not None:
                    record.order_ticket = int(
                        order_ticket
                    )

                if deal_ticket is not None:
                    record.deal_ticket = int(
                        deal_ticket
                    )

                if position_ticket is not None:
                    record.position_ticket = int(
                        position_ticket
                    )

                if broker_retcode is not None:
                    record.broker_retcode = int(
                        broker_retcode
                    )

                if broker_comment is not None:
                    record.broker_comment = str(
                        broker_comment
                    )

                record.verified = bool(
                    verified
                )

                record.reason = reason
                record.updated_at = cls._utc_datetime()

                db.commit()
                db.refresh(record)

                return record

        except DemoExecutionError:
            raise

        except Exception as exc:
            raise DemoExecutionError(
                "Unable to update persistent execution state "
                f"for signal {signal_id}: {exc}"
            ) from exc

    @staticmethod
    def _record_to_result(
        record: ExecutionRecord,
        *,
        status_override: str | None = None,
        reason_override: str | None = None,
        verified_override: bool | None = None,
    ) -> DemoExecutionResult:
        return DemoExecutionResult(
            status=(
                status_override
                if status_override is not None
                else str(record.status)
            ),
            execution_mode=str(
                record.execution_mode
            ),
            signal_id=str(
                record.idempotency_key
            ),
            symbol=str(
                record.symbol
            ),
            side=str(
                record.side
            ),
            volume=float(
                record.volume
            ),
            requested_price=(
                float(record.requested_price)
                if record.requested_price is not None
                else None
            ),
            executed_price=(
                float(record.executed_price)
                if record.executed_price is not None
                else None
            ),
            stop_loss=(
                float(record.stop_loss)
                if record.stop_loss is not None
                else None
            ),
            take_profit=(
                float(record.take_profit)
                if record.take_profit is not None
                else None
            ),
            order_ticket=(
                int(record.order_ticket)
                if record.order_ticket is not None
                else None
            ),
            deal_ticket=(
                int(record.deal_ticket)
                if record.deal_ticket is not None
                else None
            ),
            position_ticket=(
                int(record.position_ticket)
                if record.position_ticket is not None
                else None
            ),
            broker_retcode=(
                int(record.broker_retcode)
                if record.broker_retcode is not None
                else None
            ),
            broker_comment=(
                str(record.broker_comment)
                if record.broker_comment is not None
                else None
            ),
            verified=(
                verified_override
                if verified_override is not None
                else bool(record.verified)
            ),
            reason=(
                reason_override
                if reason_override is not None
                else str(record.reason or "")
            ),
            timestamp=(
                record.updated_at.isoformat()
                if record.updated_at is not None
                else datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        )

    # ==================================================================
    # ACCOUNT
    # ==================================================================

    async def account_info(self) -> dict[str, Any]:
        self._require_mt5()

        info = mt5.account_info()

        if info is None:
            raise DemoExecutionError(
                "Unable to read MT5 account information: "
                f"{mt5.last_error()}"
            )

        return info._asdict()

    async def terminal_info(self) -> dict[str, Any]:
        self._require_mt5()

        info = mt5.terminal_info()

        if info is None:
            raise DemoExecutionError(
                "Unable to read MT5 terminal information: "
                f"{mt5.last_error()}"
            )

        return info._asdict()

    async def require_demo_account(
        self,
    ) -> dict[str, Any]:
        account = await self.account_info()
        terminal = await self.terminal_info()

        trade_mode = account.get(
            "trade_mode"
        )

        demo_mode = getattr(
            mt5,
            "ACCOUNT_TRADE_MODE_DEMO",
            0,
        )

        if trade_mode != demo_mode:
            raise DemoExecutionError(
                "DEMO execution blocked: connected account "
                "is not an MT5 DEMO account."
            )

        if not bool(
            account.get(
                "trade_allowed",
                False,
            )
        ):
            raise DemoExecutionError(
                "DEMO execution blocked: account trading is disabled."
            )

        if not bool(
            account.get(
                "trade_expert",
                False,
            )
        ):
            raise DemoExecutionError(
                "DEMO execution blocked: expert/API trading is disabled "
                "for the account."
            )

        if bool(
            terminal.get(
                "tradeapi_disabled",
                False,
            )
        ):
            raise DemoExecutionError(
                "DEMO execution blocked: MT5 external Python API "
                "trading is disabled."
            )

        if not bool(
            terminal.get(
                "trade_allowed",
                False,
            )
        ):
            raise DemoExecutionError(
                "DEMO execution blocked: MT5 terminal trading is disabled."
            )

        return {
            "account": account,
            "terminal": terminal,
            "demo": True,
        }

    # ==================================================================
    # SYMBOL SPECIFICATION
    # ==================================================================

    async def symbol_specification(
        self,
        symbol: str,
    ) -> SymbolSpecification:
        self._require_mt5()

        if not mt5.symbol_select(
            symbol,
            True,
        ):
            raise DemoExecutionError(
                f"Unable to select MT5 symbol {symbol}: "
                f"{mt5.last_error()}"
            )

        info = mt5.symbol_info(
            symbol
        )

        if info is None:
            raise DemoExecutionError(
                f"Unable to read specification for {symbol}: "
                f"{mt5.last_error()}"
            )

        data = info._asdict()

        specification = SymbolSpecification(
            symbol=data.get(
                "name",
                symbol,
            ),
            digits=int(
                data.get(
                    "digits",
                    0,
                )
            ),
            point=float(
                data.get(
                    "point",
                    0,
                )
            ),
            tick_size=float(
                data.get(
                    "trade_tick_size",
                    0,
                )
            ),
            tick_value=float(
                data.get(
                    "trade_tick_value",
                    0,
                )
            ),
            tick_value_profit=float(
                data.get(
                    "trade_tick_value_profit",
                    0,
                )
            ),
            tick_value_loss=float(
                data.get(
                    "trade_tick_value_loss",
                    0,
                )
            ),
            contract_size=float(
                data.get(
                    "trade_contract_size",
                    0,
                )
            ),
            volume_min=float(
                data.get(
                    "volume_min",
                    0,
                )
            ),
            volume_max=float(
                data.get(
                    "volume_max",
                    0,
                )
            ),
            volume_step=float(
                data.get(
                    "volume_step",
                    0,
                )
            ),
            volume_limit=float(
                data.get(
                    "volume_limit",
                    0,
                )
            ),
            trade_mode=int(
                data.get(
                    "trade_mode",
                    0,
                )
            ),
            trade_execution_mode=int(
                data.get(
                    "trade_exemode",
                    0,
                )
            ),
            trade_stops_level=int(
                data.get(
                    "trade_stops_level",
                    0,
                )
            ),
            trade_freeze_level=int(
                data.get(
                    "trade_freeze_level",
                    0,
                )
            ),
            currency_base=str(
                data.get(
                    "currency_base",
                    "",
                )
            ),
            currency_profit=str(
                data.get(
                    "currency_profit",
                    "",
                )
            ),
            currency_margin=str(
                data.get(
                    "currency_margin",
                    "",
                )
            ),
            spread=int(
                data.get(
                    "spread",
                    0,
                )
            ),
            spread_float=bool(
                data.get(
                    "spread_float",
                    False,
                )
            ),
        )

        specification.validate()

        return specification

    # ==================================================================
    # SIGNAL IDENTITY
    # ==================================================================

    @staticmethod
    def build_signal_id(
        *,
        symbol: str,
        timeframe: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        candle_time: Any,
    ) -> str:
        raw = "|".join(
            [
                symbol,
                timeframe,
                direction,
                str(entry_price),
                str(stop_loss),
                str(take_profit),
                str(candle_time),
            ]
        )

        return hashlib.sha256(
            raw.encode(
                "utf-8"
            )
        ).hexdigest()

    @staticmethod
    def _broker_comment(
        signal_id: str,
    ) -> str:
        """
        Keep a short deterministic signal fingerprint in the broker
        comment.

        This gives broker-side observability in addition to the
        persistent database idempotency record.
        """

        return (
            "RAYMOND_D_"
            + signal_id[:16]
        )

    # ==================================================================
    # MARKET DATA
    # ==================================================================

    async def candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_mt5()

        timeframe_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }

        mt5_timeframe = timeframe_map.get(
            timeframe.upper()
        )

        if mt5_timeframe is None:
            raise DemoExecutionError(
                f"Unsupported MT5 timeframe: {timeframe}"
            )

        rates = mt5.copy_rates_from_pos(
            symbol,
            mt5_timeframe,
            0,
            limit,
        )

        if rates is None:
            raise DemoExecutionError(
                f"Unable to read {symbol} candles: "
                f"{mt5.last_error()}"
            )

        return [
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
            for row in rates
        ]

    # ==================================================================
    # BROKER POSITION VERIFICATION
    # ==================================================================

    def _find_matching_position(
        self,
        *,
        symbol: str,
        side: str,
        signal_id: str,
        order_ticket: int | None,
        position_ticket: int | None,
    ) -> Any | None:
        """
        Locate the broker position belonging to this DEMO execution.

        Matching priority:
            1. Explicit position ticket returned by broker.
            2. Broker comment fingerprint.
            3. Raymond magic + symbol + direction.
        """

        positions = (
            mt5.positions_get(
                symbol=symbol
            )
            or ()
        )

        if not positions:
            return None

        if position_ticket is not None:
            for position in positions:
                if int(
                    getattr(
                        position,
                        "ticket",
                        -1,
                    )
                ) == int(position_ticket):
                    return position

        expected_comment = self._broker_comment(
            signal_id
        )

        for position in positions:
            if str(
                getattr(
                    position,
                    "comment",
                    "",
                )
            ).startswith(
                expected_comment
            ):
                return position

        expected_type = (
            getattr(
                mt5,
                "POSITION_TYPE_BUY",
                0,
            )
            if side == "BUY"
            else getattr(
                mt5,
                "POSITION_TYPE_SELL",
                1,
            )
        )

        candidates = []

        for position in positions:
            magic = int(
                getattr(
                    position,
                    "magic",
                    -1,
                )
            )

            position_type = int(
                getattr(
                    position,
                    "type",
                    -1,
                )
            )

            if (
                magic == self.magic
                and position_type == expected_type
            ):
                candidates.append(
                    position
                )

        if not candidates:
            return None

        return candidates[-1]

    async def _verify_position(
        self,
        *,
        symbol: str,
        side: str,
        signal_id: str,
        order_ticket: int | None,
        position_ticket: int | None,
    ) -> Any | None:
        """
        Poll without blocking the event loop.

        MT5 can require a short interval between order acceptance and
        the position becoming visible through positions_get().
        """

        for attempt in range(
            self.verification_attempts
        ):
            position = self._find_matching_position(
                symbol=symbol,
                side=side,
                signal_id=signal_id,
                order_ticket=order_ticket,
                position_ticket=position_ticket,
            )

            if position is not None:
                return position

            if (
                attempt
                < self.verification_attempts - 1
            ):
                await asyncio.sleep(
                    self.verification_delay_seconds
                )

        return None

    # ==================================================================
    # EXECUTION
    # ==================================================================

    async def evaluate_and_execute(
        self,
        *,
        symbol: str = "XAUUSD",
        timeframe: str = "M15",
        candle_limit: int = 100,
    ) -> DemoExecutionResult:
        self._require_mt5()

        timestamp = self._utc_now()

        # --------------------------------------------------------------
        # 1. HARD DEMO ACCOUNT CHECK
        # --------------------------------------------------------------

        account_state = (
            await self.require_demo_account()
        )

        account = account_state["account"]

        # --------------------------------------------------------------
        # 2. BROKER SYMBOL SPECIFICATION
        # --------------------------------------------------------------

        specification = (
            await self.symbol_specification(
                symbol
            )
        )

        # --------------------------------------------------------------
        # 3. MARKET DATA
        # --------------------------------------------------------------

        candles = await self.candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=candle_limit,
        )

        if not candles:
            raise DemoExecutionError(
                "No market candles were returned."
            )

        # --------------------------------------------------------------
        # 4. FROZEN RAYMOND STRATEGY + STEP 14 RISK
        # --------------------------------------------------------------

        broker_positions = (
            mt5.positions_get()
            or ()
        )

        result = self.pipeline.evaluate_risk(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            specification=specification,
            account_equity=float(
                account.get(
                    "equity",
                    account.get(
                        "balance",
                        0.0,
                    ),
                )
            ),
            risk_state=PaperRiskState(
                daily_loss=0.0,
                open_positions=len(
                    broker_positions
                ),
                total_exposure=0.0,
            ),
        )

        decision = result.decision

        # --------------------------------------------------------------
        # 5. RAYMOND WAIT
        # --------------------------------------------------------------

        if decision.proposal is None:
            return DemoExecutionResult(
                status="no_trade",
                execution_mode="demo",
                signal_id=None,
                symbol=symbol,
                side=None,
                volume=None,
                requested_price=None,
                executed_price=None,
                stop_loss=None,
                take_profit=None,
                order_ticket=None,
                deal_ticket=None,
                position_ticket=None,
                broker_retcode=None,
                broker_comment=None,
                verified=False,
                reason="Raymond returned WAIT.",
                timestamp=timestamp,
            )

        proposal = decision.proposal

        # --------------------------------------------------------------
        # 6. RISK REJECTION
        # --------------------------------------------------------------

        if (
            result.risk_decision is None
            or not result.risk_decision.allowed
        ):
            return DemoExecutionResult(
                status="risk_rejected",
                execution_mode="demo",
                signal_id=None,
                symbol=symbol,
                side=decision.direction.value,
                volume=result.position_size,
                requested_price=proposal.entry_price,
                executed_price=None,
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
                order_ticket=None,
                deal_ticket=None,
                position_ticket=None,
                broker_retcode=None,
                broker_comment=None,
                verified=False,
                reason=(
                    result.risk_decision.reason
                    if result.risk_decision is not None
                    else "Risk decision unavailable."
                ),
                timestamp=timestamp,
            )

        if result.position_size is None:
            raise DemoExecutionError(
                "Approved Raymond decision has no position size."
            )

        # --------------------------------------------------------------
        # 7. CURRENT MARKET PRICE
        # --------------------------------------------------------------

        tick = mt5.symbol_info_tick(
            symbol
        )

        if tick is None:
            raise DemoExecutionError(
                f"Unable to obtain current {symbol} tick: "
                f"{mt5.last_error()}"
            )

        side = decision.direction.value.upper()

        if side == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = float(tick.ask)

        elif side == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
            price = float(tick.bid)

        else:
            raise DemoExecutionError(
                f"Unsupported Raymond direction: {side}"
            )

        # --------------------------------------------------------------
        # 8. DETERMINISTIC SIGNAL ID
        # --------------------------------------------------------------

        signal_id = self.build_signal_id(
            symbol=symbol,
            timeframe=timeframe,
            direction=side,
            entry_price=proposal.entry_price,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit,
            candle_time=candles[-1]["time"],
        )

        # --------------------------------------------------------------
        # 9. PERSISTENT IDEMPOTENCY CHECK
        # --------------------------------------------------------------

        existing = self._get_execution_record(
            signal_id
        )

        if existing is not None:
            return self._record_to_result(
                existing,
                status_override="duplicate_blocked",
                reason_override=(
                    "Signal already has a persistent DEMO execution "
                    f"record with status '{existing.status}'. "
                    "No second broker order was submitted."
                ),
                verified_override=bool(
                    existing.verified
                ),
            )

        # --------------------------------------------------------------
        # 10. RESERVE EXECUTION BEFORE BROKER ORDER
        # --------------------------------------------------------------

        record = self._create_pending_execution(
            signal_id=signal_id,
            symbol=symbol,
            timeframe=timeframe,
            side=side,
            volume=float(
                result.position_size
            ),
            requested_price=price,
            stop_loss=float(
                proposal.stop_loss
            ),
            take_profit=float(
                proposal.take_profit
            ),
        )

        # A concurrent execution path may have found the same signal
        # between the first lookup and the persistent insert.
        if (
            record.idempotency_key
            != signal_id
        ):
            return self._record_to_result(
                record,
                status_override="duplicate_blocked",
                reason_override=(
                    "Persistent idempotency prevented a duplicate "
                    "DEMO execution."
                ),
            )

        # --------------------------------------------------------------
        # 11. BROKER REQUEST
        # --------------------------------------------------------------

        broker_comment = self._broker_comment(
            signal_id
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(
                result.position_size
            ),
            "type": order_type,
            "price": price,
            "sl": float(
                proposal.stop_loss
            ),
            "tp": float(
                proposal.take_profit
            ),
            "deviation": 20,
            "magic": self.magic,
            "comment": broker_comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # --------------------------------------------------------------
        # 12. BROKER ORDER CHECK
        # --------------------------------------------------------------

        check = mt5.order_check(
            request
        )

        if check is None:
            self._update_execution_record(
                signal_id=signal_id,
                status="order_check_failed",
                broker_comment=str(
                    mt5.last_error()
                ),
                verified=False,
                reason=(
                    "MT5 order_check returned no result."
                ),
            )

            raise DemoExecutionError(
                "MT5 order_check returned no result."
            )

        check_data = check._asdict()

        check_retcode = int(
            check_data.get(
                "retcode",
                -1,
            )
        )

        if check_retcode != 0:
            comment = str(
                check_data.get(
                    "comment",
                    "",
                )
            )

            self._update_execution_record(
                signal_id=signal_id,
                status="order_check_rejected",
                broker_retcode=check_retcode,
                broker_comment=comment,
                verified=False,
                reason="MT5 rejected order_check.",
            )

            return DemoExecutionResult(
                status="order_check_rejected",
                execution_mode="demo",
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                volume=result.position_size,
                requested_price=price,
                executed_price=None,
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
                order_ticket=None,
                deal_ticket=None,
                position_ticket=None,
                broker_retcode=check_retcode,
                broker_comment=comment,
                verified=False,
                reason="MT5 rejected order_check.",
                timestamp=timestamp,
            )

        # --------------------------------------------------------------
        # 13. BROKER ORDER SEND
        # --------------------------------------------------------------

        result_mt5 = mt5.order_send(
            request
        )

        if result_mt5 is None:
            self._update_execution_record(
                signal_id=signal_id,
                status="order_send_failed",
                broker_comment=str(
                    mt5.last_error()
                ),
                verified=False,
                reason=(
                    "MT5 order_send returned no result."
                ),
            )

            raise DemoExecutionError(
                "MT5 order_send returned no result."
            )

        send_data = result_mt5._asdict()

        retcode = int(
            send_data.get(
                "retcode",
                -1,
            )
        )

        order_ticket_raw = send_data.get(
            "order"
        )

        deal_ticket_raw = send_data.get(
            "deal"
        )

        position_ticket_raw = send_data.get(
            "position"
        )

        order_ticket = (
            int(order_ticket_raw)
            if order_ticket_raw
            else None
        )

        deal_ticket = (
            int(deal_ticket_raw)
            if deal_ticket_raw
            else None
        )

        position_ticket = (
            int(position_ticket_raw)
            if position_ticket_raw
            else None
        )

        comment = str(
            send_data.get(
                "comment",
                "",
            )
        )

        executed_price = float(
            send_data.get(
                "price",
                price,
            )
        )

        # --------------------------------------------------------------
        # 14. BROKER REJECTION
        # --------------------------------------------------------------

        success_codes = {
            getattr(
                mt5,
                "TRADE_RETCODE_DONE",
                10009,
            ),
            getattr(
                mt5,
                "TRADE_RETCODE_DONE_PARTIAL",
                10010,
            ),
        }

        if retcode not in success_codes:
            self._update_execution_record(
                signal_id=signal_id,
                status="broker_rejected",
                executed_price=executed_price,
                order_ticket=order_ticket,
                deal_ticket=deal_ticket,
                position_ticket=position_ticket,
                broker_retcode=retcode,
                broker_comment=comment,
                verified=False,
                reason="MT5 rejected the demo order.",
            )

            return DemoExecutionResult(
                status="broker_rejected",
                execution_mode="demo",
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                volume=result.position_size,
                requested_price=price,
                executed_price=None,
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
                order_ticket=order_ticket,
                deal_ticket=deal_ticket,
                position_ticket=position_ticket,
                broker_retcode=retcode,
                broker_comment=comment,
                verified=False,
                reason="MT5 rejected the demo order.",
                timestamp=timestamp,
            )

        # --------------------------------------------------------------
        # 15. PERSIST BROKER ACCEPTANCE IMMEDIATELY
        # --------------------------------------------------------------

        self._update_execution_record(
            signal_id=signal_id,
            status="sent",
            executed_price=executed_price,
            order_ticket=order_ticket,
            deal_ticket=deal_ticket,
            position_ticket=position_ticket,
            broker_retcode=retcode,
            broker_comment=comment,
            verified=False,
            reason=(
                "Broker accepted DEMO order; position verification "
                "is in progress."
            ),
        )

        # --------------------------------------------------------------
        # 16. NON-BLOCKING BROKER VERIFICATION
        # --------------------------------------------------------------

        position = await self._verify_position(
            symbol=symbol,
            side=side,
            signal_id=signal_id,
            order_ticket=order_ticket,
            position_ticket=position_ticket,
        )

        if position is None:
            self._update_execution_record(
                signal_id=signal_id,
                status="sent_unverified",
                executed_price=executed_price,
                order_ticket=order_ticket,
                deal_ticket=deal_ticket,
                position_ticket=position_ticket,
                broker_retcode=retcode,
                broker_comment=comment,
                verified=False,
                reason=(
                    "Broker accepted the DEMO order but Raymond "
                    "could not verify the open position."
                ),
            )

            return DemoExecutionResult(
                status="sent_unverified",
                execution_mode="demo",
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                volume=result.position_size,
                requested_price=price,
                executed_price=executed_price,
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
                order_ticket=order_ticket,
                deal_ticket=deal_ticket,
                position_ticket=position_ticket,
                broker_retcode=retcode,
                broker_comment=comment,
                verified=False,
                reason=(
                    "Broker accepted the request but Raymond "
                    "could not yet verify the position."
                ),
                timestamp=timestamp,
            )

        # --------------------------------------------------------------
        # 17. VERIFIED POSITION DETAILS
        # --------------------------------------------------------------

        actual_position_ticket = int(
            getattr(
                position,
                "ticket",
                position_ticket
                if position_ticket is not None
                else 0,
            )
        )

        actual_volume = float(
            getattr(
                position,
                "volume",
                result.position_size,
            )
        )

        actual_open_price = float(
            getattr(
                position,
                "price_open",
                executed_price,
            )
        )

        actual_stop_loss = float(
            getattr(
                position,
                "sl",
                proposal.stop_loss,
            )
        )

        actual_take_profit = float(
            getattr(
                position,
                "tp",
                proposal.take_profit,
            )
        )

        # --------------------------------------------------------------
        # 18. FINAL PERSISTENCE
        # --------------------------------------------------------------

        self._update_execution_record(
            signal_id=signal_id,
            status="verified",
            executed_price=actual_open_price,
            order_ticket=order_ticket,
            deal_ticket=deal_ticket,
            position_ticket=actual_position_ticket,
            broker_retcode=retcode,
            broker_comment=comment,
            verified=True,
            reason="DEMO position verified at broker.",
        )

        return DemoExecutionResult(
            status="verified",
            execution_mode="demo",
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            volume=actual_volume,
            requested_price=price,
            executed_price=actual_open_price,
            stop_loss=actual_stop_loss,
            take_profit=actual_take_profit,
            order_ticket=order_ticket,
            deal_ticket=deal_ticket,
            position_ticket=actual_position_ticket,
            broker_retcode=retcode,
            broker_comment=comment,
            verified=True,
            reason="DEMO position verified at broker.",
            timestamp=timestamp,
        )


demo_mt5_execution_engine = (
    DemoMT5ExecutionEngine()
)


__all__ = [
    "DemoExecutionError",
    "DemoExecutionResult",
    "DemoMT5ExecutionEngine",
    "demo_mt5_execution_engine",
            ]
