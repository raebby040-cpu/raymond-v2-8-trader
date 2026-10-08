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
    order_check
        ->
    order_send
        ->
    broker verification

Safety:
    - DEMO account required.
    - REAL accounts rejected.
    - SL required.
    - TP required.
    - Risk Engine remains authoritative.
    - Broker symbol specification is used.
    - Duplicate execution is blocked by signal identity.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from app.risk_engine import (
    SymbolSpecification,
)
from app.trading_pipeline_service import (
    PaperRiskState,
    TradingPipelineService,
    TradingPipelineServiceError,
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
    LIVE remains the responsibility of the existing live execution gateway.
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

        self._processed_signals: dict[
            str,
            float,
        ] = {}

        self.magic = int(
            os.getenv(
                "RAYMOND_MT5_DEMO_MAGIC",
                "28001703",
            )
        )

    # ------------------------------------------------------------------
    # BASIC VALIDATION
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # ACCOUNT
    # ------------------------------------------------------------------

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

    async def require_demo_account(self) -> dict[str, Any]:
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

    # ------------------------------------------------------------------
    # SYMBOL SPECIFICATION
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # SIGNAL IDENTITY
    # ------------------------------------------------------------------

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

    def _already_processed(
        self,
        signal_id: str,
    ) -> bool:
        return signal_id in self._processed_signals

    # ------------------------------------------------------------------
    # MARKET DATA
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------------

    async def evaluate_and_execute(
        self,
        *,
        symbol: str = "XAUUSD",
        timeframe: str = "M15",
        candle_limit: int = 100,
    ) -> DemoExecutionResult:
        self._require_mt5()

        timestamp = self._utc_now()

        account_state = (
            await self.require_demo_account()
        )

        account = account_state["account"]

        specification = (
            await self.symbol_specification(
                symbol
            )
        )

        candles = await self.candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=candle_limit,
        )

        if not candles:
            raise DemoExecutionError(
                "No market candles were returned."
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
                    mt5.positions_get()
                    or ()
                ),
                total_exposure=0.0,
            ),
        )

        decision = result.decision

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
                requested_price=decision.proposal.entry_price,
                executed_price=None,
                stop_loss=decision.proposal.stop_loss,
                take_profit=decision.proposal.take_profit,
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

        proposal = decision.proposal

        if result.position_size is None:
            raise DemoExecutionError(
                "Approved Raymond decision has no position size."
            )

        tick = mt5.symbol_info_tick(
            symbol
        )

        if tick is None:
            raise DemoExecutionError(
                f"Unable to obtain current {symbol} tick."
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

        signal_id = self.build_signal_id(
            symbol=symbol,
            timeframe=timeframe,
            direction=side,
            entry_price=proposal.entry_price,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit,
            candle_time=candles[-1]["time"],
        )

        if self._already_processed(
            signal_id
        ):
            return DemoExecutionResult(
                status="duplicate_blocked",
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
                broker_retcode=None,
                broker_comment=None,
                verified=False,
                reason="Signal was already processed.",
                timestamp=timestamp,
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
            "comment": "RAYMOND_DEMO",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        check = mt5.order_check(
            request
        )

        if check is None:
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
                broker_comment=str(
                    check_data.get(
                        "comment",
                        "",
                    )
                ),
                verified=False,
                reason="MT5 rejected order_check.",
                timestamp=timestamp,
            )

        result_mt5 = mt5.order_send(
            request
        )

        if result_mt5 is None:
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

        order_ticket = send_data.get(
            "order"
        )

        deal_ticket = send_data.get(
            "deal"
        )

        comment = str(
            send_data.get(
                "comment",
                "",
            )
        )

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
                order_ticket=(
                    int(order_ticket)
                    if order_ticket
                    else None
                ),
                deal_ticket=(
                    int(deal_ticket)
                    if deal_ticket
                    else None
                ),
                position_ticket=None,
                broker_retcode=retcode,
                broker_comment=comment,
                verified=False,
                reason="MT5 rejected the demo order.",
                timestamp=timestamp,
            )

        time.sleep(0.5)

        positions = (
            mt5.positions_get(
                symbol=symbol
            )
            or ()
        )

        matching = [
            p
            for p in positions
            if int(
                getattr(
                    p,
                    "magic",
                    -1,
                )
            )
            == self.magic
        ]

        if not matching:
            return DemoExecutionResult(
                status="sent_unverified",
                execution_mode="demo",
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                volume=result.position_size,
                requested_price=price,
                executed_price=float(
                    send_data.get(
                        "price",
                        price,
                    )
                ),
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
                order_ticket=(
                    int(order_ticket)
                    if order_ticket
                    else None
                ),
                deal_ticket=(
                    int(deal_ticket)
                    if deal_ticket
                    else None
                ),
                position_ticket=None,
                broker_retcode=retcode,
                broker_comment=comment,
                verified=False,
                reason=(
                    "Broker accepted the request but "
                    "Raymond could not yet verify the position."
                ),
                timestamp=timestamp,
            )

        position = matching[-1]

        self._processed_signals[
            signal_id
        ] = time.time()

        return DemoExecutionResult(
            status="verified",
            execution_mode="demo",
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            volume=result.position_size,
            requested_price=price,
            executed_price=float(
                getattr(
                    position,
                    "price_open",
                    price,
                )
            ),
            stop_loss=float(
                getattr(
                    position,
                    "sl",
                    proposal.stop_loss,
                )
            ),
            take_profit=float(
                getattr(
                    position,
                    "tp",
                    proposal.take_profit,
                )
            ),
            order_ticket=(
                int(order_ticket)
                if order_ticket
                else None
            ),
            deal_ticket=(
                int(deal_ticket)
                if deal_ticket
                else None
            ),
            position_ticket=int(
                getattr(
                    position,
                    "ticket",
                )
            ),
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
