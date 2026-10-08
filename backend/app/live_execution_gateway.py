"""
RAYMOND v2.8 - Live MT5 Execution Gateway

STEP 17.5B

Real MT5 execution boundary with:

- Environment live-trading gate
- Explicit Raymond live ARM gate
- Selected broker account gate
- Account verification
- Account live authorization
- Emergency stop
- MT5 heartbeat
- MT5 account permissions
- MT5 terminal permissions
- Broker symbol specification
- Direction validation
- Volume validation
- Current market price validation
- Stop-loss / take-profit validation
- Risk/reward validation
- Broker minimum stop distance
- LIVE POSITION RECONCILIATION
- MT5 order_check()
- MT5 order_send()
- Broker execution verification
- Raymond live-position registration
- Post-execution reconciliation

IMPORTANT:

This module contains the real MT5 order path.

It remains fail-closed.

A live order requires ALL relevant safety gates to pass.

No broker password is returned.

No strategy optimization is performed here.

No order is sent unless the complete safety chain passes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import os
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


# ============================================================
# IMPORTS
# ============================================================

try:
    from .broker_accounts import BrokerAccount

    from .database import SessionLocal

    from .emergency_stop import (
        EmergencyStopError,
        EmergencyStopManager,
    )

    from .live_safety_gate import (
        require_live_armed,
        live_safety_status,
    )

    from .live_reconciliation import (
        reconcile_live_positions,
        require_reconciliation_safe,
        register_live_position,
        reconciliation_status,
    )

    from .mt5_service import (
        MT5ServiceError,
        mt5,
        mt5_service,
    )

    from .risk_engine import (
        RiskEngine,
        RiskEngineError,
        SymbolSpecification,
    )

except ImportError:
    from broker_accounts import BrokerAccount

    from database import SessionLocal

    from emergency_stop import (
        EmergencyStopError,
        EmergencyStopManager,
    )

    from live_safety_gate import (
        require_live_armed,
        live_safety_status,
    )

    from live_reconciliation import (
        reconcile_live_positions,
        require_reconciliation_safe,
        register_live_position,
        reconciliation_status,
    )

    from mt5_service import (
        MT5ServiceError,
        mt5,
        mt5_service,
    )

    from risk_engine import (
        RiskEngine,
        RiskEngineError,
        SymbolSpecification,
    )


# ============================================================
# ERRORS
# ============================================================

class LiveExecutionError(RuntimeError):
    """
    Raised when live execution cannot safely proceed.
    """


# ============================================================
# REQUEST MODEL
# ============================================================

class LiveOrderRequest(BaseModel):
    symbol: str = Field(
        min_length=1,
        max_length=100,
    )

    side: str = Field(
        min_length=1,
        max_length=10,
    )

    volume: float = Field(
        gt=0,
    )

    stop_loss: float = Field(
        gt=0,
    )

    take_profit: float = Field(
        gt=0,
    )

    deviation: int = Field(
        default=20,
        ge=0,
        le=1000,
    )

    magic: int = Field(
        default=28001703,
        ge=0,
    )

    comment: str = Field(
        default="RAYMOND-V2.8",
        min_length=1,
        max_length=31,
    )

    client_order_id: Optional[str] = Field(
        default=None,
        max_length=100,
    )


# ============================================================
# RESULT MODEL
# ============================================================

@dataclass(frozen=True)
class LiveExecutionResult:
    status: str

    execution_type: str

    order_id: Optional[int]

    deal_id: Optional[int]

    position_ticket: Optional[int]

    symbol: str

    side: str

    requested_volume: float

    executed_volume: Optional[float]

    requested_stop_loss: float

    requested_take_profit: float

    executed_price: Optional[float]

    client_order_id: str

    broker_retcode: Optional[int]

    broker_comment: Optional[str]

    verified: bool

    timestamp: str


# ============================================================
# GLOBAL SAFETY OBJECTS
# ============================================================

safety_manager = EmergencyStopManager()

risk_engine = RiskEngine()


# ============================================================
# ENVIRONMENT LIVE GATE
# ============================================================

def _environment_live_enabled() -> bool:
    """
    Explicit production live-trading switch.

    Default is FALSE.
    """

    return (
        os.getenv(
            "LIVE_TRADING_ENABLED",
            "false",
        )
        .strip()
        .lower()
        == "true"
    )


# ============================================================
# SELECTED BROKER ACCOUNT
# ============================================================

def _get_selected_account():
    """
    Return selected broker account metadata.

    Credentials are never returned.
    """

    db = SessionLocal()

    try:
        account = (
            db.query(BrokerAccount)
            .filter(
                BrokerAccount.selected == 1
            )
            .first()
        )

        if account is None:
            raise LiveExecutionError(
                "No broker account is selected."
            )

        if not account.account_verified:
            raise LiveExecutionError(
                "Selected broker account is not verified."
            )

        if not account.trading_allowed:
            raise LiveExecutionError(
                "Trading is not allowed on the selected "
                "broker account."
            )

        if not account.live_trading_authorized:
            raise LiveExecutionError(
                "Live trading has not been explicitly authorized "
                "for the selected broker account."
            )

        return {
            "account_id": account.account_id,
            "broker": account.broker,
            "platform": account.platform,
            "server": account.server,
            "account_number": account.account_number,
        }

    finally:
        db.close()


# ============================================================
# MT5 REQUIREMENT
# ============================================================

def _require_mt5() -> None:

    if mt5 is None:
        raise LiveExecutionError(
            "MetaTrader5 Python package is not installed."
        )


# ============================================================
# ORDER TYPE
# ============================================================

def _order_type_for_side(side: str):

    normalized = side.upper().strip()

    if normalized == "BUY":
        return mt5.ORDER_TYPE_BUY

    if normalized == "SELL":
        return mt5.ORDER_TYPE_SELL

    raise LiveExecutionError(
        "side must be BUY or SELL."
    )


def _position_type_for_side(side: str):

    normalized = side.upper().strip()

    if normalized == "BUY":
        return 0

    if normalized == "SELL":
        return 1

    raise LiveExecutionError(
        "side must be BUY or SELL."
    )


# ============================================================
# SYMBOL SPECIFICATION
# ============================================================

def _symbol_specification_from_dict(
    data: dict,
) -> SymbolSpecification:

    required_fields = [
        "symbol",
        "digits",
        "point",
        "tick_size",
        "tick_value",
        "tick_value_profit",
        "tick_value_loss",
        "contract_size",
        "volume_min",
        "volume_max",
        "volume_step",
        "volume_limit",
        "trade_mode",
        "trade_execution_mode",
        "trade_stops_level",
        "trade_freeze_level",
        "currency_base",
        "currency_profit",
        "currency_margin",
        "spread",
        "spread_float",
    ]

    missing = [
        field
        for field in required_fields
        if data.get(field) is None
    ]

    if missing:
        raise LiveExecutionError(
            "Broker symbol specification is incomplete: "
            + ", ".join(missing)
        )

    try:
        return SymbolSpecification(
            symbol=str(data["symbol"]),

            digits=int(data["digits"]),

            point=float(data["point"]),

            tick_size=float(data["tick_size"]),

            tick_value=float(data["tick_value"]),

            tick_value_profit=float(
                data["tick_value_profit"]
            ),

            tick_value_loss=float(
                data["tick_value_loss"]
            ),

            contract_size=float(
                data["contract_size"]
            ),

            volume_min=float(
                data["volume_min"]
            ),

            volume_max=float(
                data["volume_max"]
            ),

            volume_step=float(
                data["volume_step"]
            ),

            volume_limit=float(
                data["volume_limit"]
            ),

            trade_mode=int(
                data["trade_mode"]
            ),

            trade_execution_mode=int(
                data["trade_execution_mode"]
            ),

            trade_stops_level=int(
                data["trade_stops_level"]
            ),

            trade_freeze_level=int(
                data["trade_freeze_level"]
            ),

            currency_base=str(
                data["currency_base"] or ""
            ),

            currency_profit=str(
                data["currency_profit"] or ""
            ),

            currency_margin=str(
                data["currency_margin"] or ""
            ),

            spread=int(
                data["spread"] or 0
            ),

            spread_float=bool(
                data["spread_float"]
            ),
        )

    except (
        TypeError,
        ValueError,
        KeyError,
    ) as exc:

        raise LiveExecutionError(
            f"Invalid broker symbol specification: {exc}"
        ) from exc


# ============================================================
# NORMALIZATION
# ============================================================

def _normalize_price(
    price: float,
    digits: int,
) -> float:

    return round(
        float(price),
        int(digits),
    )


def _normalize_volume(
    volume: float,
    specification: SymbolSpecification,
) -> float:

    step = specification.volume_step

    if step <= 0:
        raise LiveExecutionError(
            "Broker volume step is invalid."
        )

    steps = int(
        volume / step
    )

    normalized = steps * step

    return round(
        normalized,
        8,
    )


# ============================================================
# PRE-TRADE SAFETY GATES
# ============================================================

async def _validate_live_gate(
    request: LiveOrderRequest,
):

    # --------------------------------------------------------
    # GATE 1 - ENVIRONMENT
    # --------------------------------------------------------

    if not _environment_live_enabled():

        raise LiveExecutionError(
            "LIVE_TRADING_ENABLED is false."
        )

    # --------------------------------------------------------
    # GATE 2 - EXPLICIT LIVE ARM
    # --------------------------------------------------------

    try:
        require_live_armed()

    except PermissionError as exc:

        raise LiveExecutionError(
            str(exc)
        ) from exc

    # --------------------------------------------------------
    # GATE 3 - SELECTED ACCOUNT
    # --------------------------------------------------------

    account = _get_selected_account()

    # --------------------------------------------------------
    # GATE 4 - PLATFORM
    # --------------------------------------------------------

    if (
        str(
            account["platform"]
        ).upper()
        != "MT5"
    ):

        raise LiveExecutionError(
            "The selected broker account is not an MT5 account."
        )

    # --------------------------------------------------------
    # GATE 5 - MT5 HEARTBEAT
    # --------------------------------------------------------

    try:

        heartbeat = (
            await mt5_service.heartbeat()
        )

    except Exception as exc:

        raise LiveExecutionError(
            f"Unable to verify MT5 heartbeat: {exc}"
        ) from exc

    if not heartbeat.get(
        "connected",
        False,
    ):

        raise LiveExecutionError(
            "MT5 connection is not healthy."
        )

    safety_manager.record_heartbeat()

    # --------------------------------------------------------
    # GATE 6 - EMERGENCY STOP
    # --------------------------------------------------------

    try:

        safety_manager.require_trade_permission()

    except EmergencyStopError as exc:

        raise LiveExecutionError(
            str(exc)
        ) from exc

    # --------------------------------------------------------
    # GATE 7 - ACCOUNT PERMISSION
    # --------------------------------------------------------

    try:

        account_info = (
            await mt5_service.get_account_info()
        )

    except MT5ServiceError as exc:

        raise LiveExecutionError(
            f"Unable to read broker account: {exc}"
        ) from exc

    if not account_info.get(
        "trade_allowed",
        False,
    ):

        raise LiveExecutionError(
            "Broker account does not permit trading."
        )

    if not account_info.get(
        "trade_expert",
        False,
    ):

        raise LiveExecutionError(
            "MT5 Expert Advisor/API trading permission "
            "is not enabled."
        )

    # --------------------------------------------------------
    # GATE 8 - TERMINAL
    # --------------------------------------------------------

    try:

        terminal = (
            await mt5_service.get_terminal_info()
        )

    except MT5ServiceError as exc:

        raise LiveExecutionError(
            f"Unable to read MT5 terminal: {exc}"
        ) from exc

    if not terminal.get(
        "connected",
        False,
    ):

        raise LiveExecutionError(
            "MT5 terminal is not connected."
        )

    if not terminal.get(
        "trade_allowed",
        False,
    ):

        raise LiveExecutionError(
            "MT5 terminal trading is disabled."
        )

    if terminal.get(
        "tradeapi_disabled",
        False,
    ):

        raise LiveExecutionError(
            "MT5 trading API is disabled."
        )

    # --------------------------------------------------------
    # GATE 9 - SYMBOL
    # --------------------------------------------------------

    symbol = request.symbol.strip()

    if not symbol:

        raise LiveExecutionError(
            "Trading symbol cannot be empty."
        )

    try:

        specification_raw = (
            await mt5_service.get_symbol_specification(
                symbol
            )
        )

    except MT5ServiceError as exc:

        raise LiveExecutionError(
            f"Unable to read broker specification for "
            f"{symbol}: {exc}"
        ) from exc

    specification = (
        _symbol_specification_from_dict(
            specification_raw
        )
    )

    # --------------------------------------------------------
    # GATE 10 - DIRECTION
    # --------------------------------------------------------

    normalized_side = (
        request.side.upper().strip()
    )

    try:

        risk_engine.validate_trade_direction(
            specification.trade_mode,
            normalized_side,
        )

    except RiskEngineError as exc:

        raise LiveExecutionError(
            str(exc)
        ) from exc

    # --------------------------------------------------------
    # GATE 11 - VOLUME
    # --------------------------------------------------------

    if (
        request.volume
        < specification.volume_min
    ):

        raise LiveExecutionError(
            "Requested volume is below broker minimum."
        )

    if (
        request.volume
        > specification.volume_max
    ):

        raise LiveExecutionError(
            "Requested volume exceeds broker maximum."
        )

    normalized_volume = (
        _normalize_volume(
            request.volume,
            specification,
        )
    )

    if normalized_volume <= 0:

        raise LiveExecutionError(
            "Requested volume cannot be aligned to "
            "the broker volume step."
        )

    if abs(
        normalized_volume
        - request.volume
    ) > 1e-8:

        raise LiveExecutionError(
            "Requested volume is not aligned to "
            "the broker volume step."
        )

    try:

        risk_engine.validate_volume(
            request.volume,
            specification,
        )

    except RiskEngineError as exc:

        raise LiveExecutionError(
            str(exc)
        ) from exc

    # --------------------------------------------------------
    # GATE 12 - CURRENT MARKET PRICE
    # --------------------------------------------------------

    try:

        tick = (
            await mt5_service.get_symbol_tick(
                symbol
            )
        )

    except MT5ServiceError as exc:

        raise LiveExecutionError(
            f"Unable to read current {symbol} price: {exc}"
        ) from exc

    bid = float(
        tick.get(
            "bid",
            0,
        )
    )

    ask = float(
        tick.get(
            "ask",
            0,
        )
    )

    if bid <= 0 or ask <= 0:

        raise LiveExecutionError(
            "Broker returned an invalid bid/ask price."
        )

    entry_price = (
        ask
        if normalized_side == "BUY"
        else bid
    )

    # --------------------------------------------------------
    # GATE 13 - SL / TP
    # --------------------------------------------------------

    stop_loss = float(
        request.stop_loss
    )

    take_profit = float(
        request.take_profit
    )

    if stop_loss <= 0:

        raise LiveExecutionError(
            "Stop-loss must be greater than zero."
        )

    if take_profit <= 0:

        raise LiveExecutionError(
            "Take-profit must be greater than zero."
        )

    # --------------------------------------------------------
    # GATE 14 - RISK ENGINE
    # --------------------------------------------------------

    try:

        risk_engine.validate_stop_loss(
            entry_price,
            stop_loss,
        )

        risk_engine.validate_risk_reward(
            entry_price,
            stop_loss,
            take_profit,
        )

    except RiskEngineError as exc:

        raise LiveExecutionError(
            str(exc)
        ) from exc

    # --------------------------------------------------------
    # GATE 15 - BROKER STOP DISTANCE
    # --------------------------------------------------------

    minimum_stop_distance = (
        specification.trade_stops_level
        * specification.point
    )

    if minimum_stop_distance > 0:

        if abs(
            entry_price
            - stop_loss
        ) < minimum_stop_distance:

            raise LiveExecutionError(
                "Stop-loss is too close to the current "
                "market price for the broker."
            )

        if abs(
            take_profit
            - entry_price
        ) < minimum_stop_distance:

            raise LiveExecutionError(
                "Take-profit is too close to the current "
                "market price for the broker."
            )

    # --------------------------------------------------------
    # GATE 16 - RECONCILIATION
    # --------------------------------------------------------
    #
    # Raymond must know the current broker position state
    # before opening another live position.
    #
    # If reconciliation has never successfully completed,
    # this gate remains CLOSED.
    #

    try:

        reconciliation = (
            await reconcile_live_positions(
                symbol=symbol,
                magic=int(request.magic),
            )
        )

    except Exception as exc:

        raise LiveExecutionError(
            "Live reconciliation failed. "
            "New live orders are blocked: "
            f"{exc}"
        ) from exc

    if not (
        reconciliation.safe_for_new_live_orders
    ):

        raise LiveExecutionError(
            "Live reconciliation detected a broker/Raymond "
            "position mismatch. New live orders are blocked."
        )

    # --------------------------------------------------------
    # ALL PRE-TRADE GATES PASSED
    # --------------------------------------------------------

    return {
        "account": account,

        "account_info": account_info,

        "terminal": terminal,

        "specification": specification,

        "tick": tick,

        "entry_price": entry_price,

        "volume": normalized_volume,

        "side": normalized_side,
    }


# ============================================================
# POSITION VERIFICATION
# ============================================================

async def _verify_position(
    *,
    symbol: str,
    side: str,
    volume: float,
    magic: int,
    order_id: Optional[int],
):

    try:

        positions = (
            await mt5_service.get_positions(
                symbol=symbol
            )
        )

    except MT5ServiceError as exc:

        raise LiveExecutionError(
            "Order may have been sent, but broker "
            "position verification failed: "
            f"{exc}"
        ) from exc

    expected_type = (
        _position_type_for_side(side)
    )

    matching = []

    for position in positions:

        try:

            position_magic = int(
                position.get(
                    "magic",
                    -1,
                )
            )

            position_type = int(
                position.get(
                    "type",
                    -1,
                )
            )

            position_volume = float(
                position.get(
                    "volume",
                    0,
                )
            )

            if (
                position_magic == magic
                and position_type == expected_type
                and position_volume > 0
            ):

                matching.append(
                    {
                        "ticket": position.get(
                            "ticket"
                        ),

                        "volume": position_volume,

                        "type": position_type,

                        "reason": position.get(
                            "reason"
                        ),

                        "symbol": position.get(
                            "symbol"
                        ),

                        "price_open": position.get(
                            "price_open"
                        ),

                        "sl": position.get(
                            "sl"
                        ),

                        "tp": position.get(
                            "tp"
                        ),

                        "profit": position.get(
                            "profit"
                        ),

                        "magic": position_magic,
                    }
                )

        except (
            TypeError,
            ValueError,
        ):

            continue

    if not matching:

        return {
            "verified": False,
            "position": None,
            "positions_found": len(
                positions
            ),
            "order_id": order_id,
        }

    matching.sort(
        key=lambda item: abs(
            float(
                item["volume"]
            )
            - float(volume)
        )
    )

    return {
        "verified": True,

        "position": matching[0],

        "positions_found": len(
            positions
        ),

        "order_id": order_id,
    }


# ============================================================
# EXECUTION GATEWAY
# ============================================================

class LiveExecutionGateway:

    execution_type = "mt5_live"

    async def execute(
        self,
        request: LiveOrderRequest,
    ) -> LiveExecutionResult:

        # ----------------------------------------------------
        # FIRST ARM CHECK
        # ----------------------------------------------------

        try:

            require_live_armed()

        except PermissionError as exc:

            raise LiveExecutionError(
                str(exc)
            ) from exc

        # ----------------------------------------------------
        # MT5
        # ----------------------------------------------------

        _require_mt5()

        # ----------------------------------------------------
        # COMPLETE PRE-TRADE VALIDATION
        # ----------------------------------------------------

        gate = await _validate_live_gate(
            request
        )

        specification = gate[
            "specification"
        ]

        symbol = request.symbol.strip()

        side = gate[
            "side"
        ]

        volume = gate[
            "volume"
        ]

        entry_price = gate[
            "entry_price"
        ]

        digits = specification.digits

        stop_loss = _normalize_price(
            request.stop_loss,
            digits,
        )

        take_profit = _normalize_price(
            request.take_profit,
            digits,
        )

        client_order_id = (
            request.client_order_id
            or (
                "RAYMOND-"
                + uuid.uuid4().hex.upper()
            )
        )

        order_type = (
            _order_type_for_side(
                side
            )
        )

        magic = int(
            request.magic
        )

        # ----------------------------------------------------
        # FINAL PRICE SAFETY CHECK
        # ----------------------------------------------------

        if side == "BUY":

            if not (
                stop_loss
                < entry_price
                < take_profit
            ):

                raise LiveExecutionError(
                    "BUY order requires SL below entry "
                    "and TP above entry."
                )

        elif side == "SELL":

            if not (
                take_profit
                < entry_price
                < stop_loss
            ):

                raise LiveExecutionError(
                    "SELL order requires TP below entry "
                    "and SL above entry."
                )

        else:

            raise LiveExecutionError(
                "Unsupported order side."
            )

        # ----------------------------------------------------
        # BUILD MT5 REQUEST
        # ----------------------------------------------------

        mt5_request = {
            "action": mt5.TRADE_ACTION_DEAL,

            "symbol": symbol,

            "volume": volume,

            "type": order_type,

            "price": _normalize_price(
                entry_price,
                digits,
            ),

            "sl": stop_loss,

            "tp": take_profit,

            "deviation": int(
                request.deviation
            ),

            "magic": magic,

            "comment": request.comment,

            "type_time": mt5.ORDER_TIME_GTC,

            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # ----------------------------------------------------
        # BROKER PRE-CHECK
        # ----------------------------------------------------

        try:

            check_result = await asyncio.to_thread(
                mt5.order_check,
                mt5_request,
            )

        except Exception as exc:

            raise LiveExecutionError(
                f"MT5 order_check failed: {exc}"
            ) from exc

        if check_result is None:

            raise LiveExecutionError(
                "MT5 order_check returned no result."
            )

        if hasattr(
            check_result,
            "_asdict",
        ):

            check_dict = (
                check_result._asdict()
            )

        else:

            check_dict = {}

        check_retcode = check_dict.get(
            "retcode"
        )

        if (
            check_retcode is not None
            and int(check_retcode)
            != int(
                mt5.TRADE_RETCODE_DONE
            )
        ):

            return LiveExecutionResult(
                status="rejected_precheck",

                execution_type=self.execution_type,

                order_id=None,

                deal_id=None,

                position_ticket=None,

                symbol=symbol,

                side=side,

                requested_volume=volume,

                executed_volume=None,

                requested_stop_loss=stop_loss,

                requested_take_profit=take_profit,

                executed_price=None,

                client_order_id=client_order_id,

                broker_retcode=int(
                    check_retcode
                ),

                broker_comment=check_dict.get(
                    "comment"
                ),

                verified=False,

                timestamp=(
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            )

        # ----------------------------------------------------
        # FINAL ARM CHECK
        # ----------------------------------------------------

        try:

            require_live_armed()

        except PermissionError as exc:

            raise LiveExecutionError(
                str(exc)
            ) from exc

        # ----------------------------------------------------
        # FINAL RECONCILIATION CHECK
        # ----------------------------------------------------

        try:

            require_reconciliation_safe()

        except PermissionError as exc:

            raise LiveExecutionError(
                str(exc)
            ) from exc

        # ----------------------------------------------------
        # REAL MT5 ORDER
        # ----------------------------------------------------

        try:

            send_result = await asyncio.to_thread(
                mt5.order_send,
                mt5_request,
            )

        except Exception as exc:

            raise LiveExecutionError(
                f"MT5 order_send failed: {exc}"
            ) from exc

        if send_result is None:

            raise LiveExecutionError(
                "MT5 order_send returned no result."
            )

        if hasattr(
            send_result,
            "_asdict",
        ):

            send_dict = (
                send_result._asdict()
            )

        else:

            send_dict = {}

        retcode = send_dict.get(
            "retcode"
        )

        order_id = send_dict.get(
            "order"
        )

        deal_id = send_dict.get(
            "deal"
        )

        broker_comment = send_dict.get(
            "comment"
        )

        executed_price = send_dict.get(
            "price"
        )

        executed_volume = send_dict.get(
            "volume"
        )

        # ----------------------------------------------------
        # SUCCESS CODES
        # ----------------------------------------------------

        successful_codes = {
            int(
                mt5.TRADE_RETCODE_DONE
            ),

            int(
                getattr(
                    mt5,
                    "TRADE_RETCODE_DONE_PARTIAL",
                    mt5.TRADE_RETCODE_DONE,
                )
            ),
        }

        if (
            retcode is None
            or int(retcode)
            not in successful_codes
        ):

            return LiveExecutionResult(
                status="rejected",

                execution_type=self.execution_type,

                order_id=(
                    int(order_id)
                    if order_id is not None
                    else None
                ),

                deal_id=(
                    int(deal_id)
                    if deal_id is not None
                    else None
                ),

                position_ticket=None,

                symbol=symbol,

                side=side,

                requested_volume=volume,

                executed_volume=(
                    float(executed_volume)
                    if executed_volume is not None
                    else None
                ),

                requested_stop_loss=stop_loss,

                requested_take_profit=take_profit,

                executed_price=(
                    float(executed_price)
                    if executed_price is not None
                    else None
                ),

                client_order_id=client_order_id,

                broker_retcode=(
                    int(retcode)
                    if retcode is not None
                    else None
                ),

                broker_comment=broker_comment,

                verified=False,

                timestamp=(
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            )

        # ----------------------------------------------------
        # VERIFY BROKER POSITION
        # ----------------------------------------------------

        verification = (
            await _verify_position(
                symbol=symbol,
                side=side,
                volume=volume,
                magic=magic,
                order_id=(
                    int(order_id)
                    if order_id is not None
                    else None
                ),
            )
        )

        position = verification.get(
            "position"
        )

        if not verification.get(
            "verified",
            False,
        ):

            # The order may have been executed even though
            # Raymond could not verify the resulting position.
            #
            # NEVER report this as a successful verified trade.

            return LiveExecutionResult(
                status="sent_unverified",

                execution_type=self.execution_type,

                order_id=(
                    int(order_id)
                    if order_id is not None
                    else None
                ),

                deal_id=(
                    int(deal_id)
                    if deal_id is not None
                    else None
                ),

                position_ticket=None,

                symbol=symbol,

                side=side,

                requested_volume=volume,

                executed_volume=(
                    float(executed_volume)
                    if executed_volume is not None
                    else None
                ),

                requested_stop_loss=stop_loss,

                requested_take_profit=take_profit,

                executed_price=(
                    float(executed_price)
                    if executed_price is not None
                    else None
                ),

                client_order_id=client_order_id,

                broker_retcode=(
                    int(retcode)
                    if retcode is not None
                    else None
                ),

                broker_comment=broker_comment,

                verified=False,

                timestamp=(
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            )

        # ----------------------------------------------------
        # REGISTER VERIFIED POSITION
        # ----------------------------------------------------

        position_ticket = None

        if position is not None:

            raw_ticket = position.get(
                "ticket"
            )

            if raw_ticket is not None:

                try:
                    position_ticket = int(
                        raw_ticket
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    position_ticket = None

        try:

            register_live_position(
                client_order_id=client_order_id,

                symbol=symbol,

                side=side,

                volume=(
                    float(
                        executed_volume
                    )
                    if executed_volume is not None
                    else float(volume)
                ),

                stop_loss=stop_loss,

                take_profit=take_profit,

                position_ticket=position_ticket,

                magic=magic,
            )

        except Exception as exc:

            # The broker position exists, but Raymond could
            # not register its local state.
            #
            # This is deliberately treated as unsafe.

            raise LiveExecutionError(
                "Broker position was verified, but Raymond "
                "could not register the live position. "
                "New live orders must remain blocked until "
                "reconciliation is restored: "
                f"{exc}"
            ) from exc

        # ----------------------------------------------------
        # POST-EXECUTION RECONCILIATION
        # ----------------------------------------------------
        #
        # The broker state is checked again after the order.
        #
        # This catches situations where the broker state does
        # not match what Raymond registered.
        #

        try:

            post_reconciliation = (
                await reconcile_live_positions(
                    symbol=symbol,
                    magic=magic,
                )
            )

        except Exception as exc:

            raise LiveExecutionError(
                "Live order was executed and verified, but "
                "post-execution reconciliation failed. "
                "Further live orders are blocked: "
                f"{exc}"
            ) from exc

        if not (
            post_reconciliation.safe_for_new_live_orders
        ):

            raise LiveExecutionError(
                "Live order was executed, but post-execution "
                "reconciliation detected a mismatch. "
                "Further live orders are blocked."
            )

        # ----------------------------------------------------
        # FINAL VERIFIED RESULT
        # ----------------------------------------------------

        return LiveExecutionResult(
            status="verified",

            execution_type=self.execution_type,

            order_id=(
                int(order_id)
                if order_id is not None
                else None
            ),

            deal_id=(
                int(deal_id)
                if deal_id is not None
                else None
            ),

            position_ticket=position_ticket,

            symbol=symbol,

            side=side,

            requested_volume=volume,

            executed_volume=(
                float(executed_volume)
                if executed_volume is not None
                else None
            ),

            requested_stop_loss=stop_loss,

            requested_take_profit=take_profit,

            executed_price=(
                float(executed_price)
                if executed_price is not None
                else None
            ),

            client_order_id=client_order_id,

            broker_retcode=(
                int(retcode)
                if retcode is not None
                else None
            ),

            broker_comment=broker_comment,

            verified=True,

            timestamp=(
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        )


# ============================================================
# SINGLETON
# ============================================================

live_execution_gateway = (
    LiveExecutionGateway()
)


# ============================================================
# API ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/live-execution",
    tags=["Live Execution"],
)


# ============================================================
# STATUS
# ============================================================

@router.get("/status")
async def live_execution_status():

    environment_enabled = (
        _environment_live_enabled()
    )

    selected_account = None

    db = SessionLocal()

    try:

        account = (
            db.query(BrokerAccount)
            .filter(
                BrokerAccount.selected == 1
            )
            .first()
        )

        if account is not None:

            account_number = str(
                account.account_number
                or ""
            )

            selected_account = {
                "account_id": (
                    account.account_id
                ),

                "broker": account.broker,

                "platform": account.platform,

                "server": account.server,

                "account_number": (
                    "****"
                    + account_number[-4:]
                    if len(account_number) > 4
                    else "****"
                ),

                "verified": bool(
                    account.account_verified
                ),

                "trading_allowed": bool(
                    account.trading_allowed
                ),

                "live_authorized": bool(
                    account.live_trading_authorized
                ),
            }

    finally:
        db.close()

    safety = safety_manager.status()

    live_arm = live_safety_status()

    reconciliation = (
        reconciliation_status()
    )

    all_account_gates = (
        selected_account is not None
        and selected_account["verified"]
        and selected_account["trading_allowed"]
        and selected_account["live_authorized"]
    )

    emergency_gate = (
        safety.trading_allowed
        and not safety.emergency_stop_active
        and not safety.connection_stale
    )

    reconciliation_gate = (
        reconciliation.get(
            "safe_for_new_live_orders",
            False,
        )
    )

    order_execution_available = (
        environment_enabled
        and live_arm.get(
            "armed",
            False,
        )
        and all_account_gates
        and emergency_gate
        and reconciliation_gate
    )

    return {
        "status": "ok",

        "execution_type": "mt5_live",

        "environment_enabled": (
            environment_enabled
        ),

        "live_arm": {
            "armed": live_arm.get(
                "armed",
                False,
            ),

            "arm_token_configured": (
                live_arm.get(
                    "arm_token_configured",
                    False,
                )
            ),

            "armed_at": live_arm.get(
                "armed_at"
            ),

            "armed_by": live_arm.get(
                "armed_by"
            ),

            "fail_closed": True,
        },

        "selected_account": (
            selected_account
        ),

        "safety": {
            "trading_allowed": (
                safety.trading_allowed
            ),

            "emergency_stop_active": (
                safety.emergency_stop_active
            ),

            "connection_healthy": (
                safety.connection_healthy
            ),

            "connection_stale": (
                safety.connection_stale
            ),

            "reason": safety.reason,
        },

        "reconciliation": {
            "safe_for_new_live_orders": (
                reconciliation_gate
            ),

            "last_run_at": (
                reconciliation.get(
                    "last_run_at"
                )
            ),

            "last_error": (
                reconciliation.get(
                    "last_error"
                )
            ),

            "result": (
                reconciliation.get(
                    "result"
                )
            ),

            "fail_closed": True,
        },

        "gates": {
            "environment_enabled": (
                environment_enabled
            ),

            "live_explicitly_armed": (
                live_arm.get(
                    "armed",
                    False,
                )
            ),

            "account_selected": (
                selected_account is not None
            ),

            "account_verified": (
                bool(
                    selected_account
                    and selected_account[
                        "verified"
                    ]
                )
            ),

            "account_trading_allowed": (
                bool(
                    selected_account
                    and selected_account[
                        "trading_allowed"
                    ]
                )
            ),

            "account_live_authorized": (
                bool(
                    selected_account
                    and selected_account[
                        "live_authorized"
                    ]
                )
            ),

            "emergency_stop_clear": (
                not safety.emergency_stop_active
            ),

            "connection_not_stale": (
                not safety.connection_stale
            ),

            "reconciliation_safe": (
                reconciliation_gate
            ),

            "order_execution_available": (
                order_execution_available
            ),
        },

        "order_execution_available": (
            order_execution_available
        ),

        "execution_mode": (
            "armed"
            if order_execution_available
            else "fail_closed"
        ),

        "timestamp": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }


# ============================================================
# LIVE ORDER ENDPOINT
# ============================================================

@router.post("/order")
async def execute_live_order(
    request: LiveOrderRequest,
):

    try:

        # ----------------------------------------------------
        # API-LEVEL ARM CHECK
        # ----------------------------------------------------

        try:

            require_live_armed()

        except PermissionError as exc:

            raise HTTPException(
                status_code=403,

                detail={
                    "error": (
                        "LIVE_EXECUTION_NOT_ARMED"
                    ),

                    "message": str(exc),

                    "timestamp": (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    ),
                },
            ) from exc

        # ----------------------------------------------------
        # EXECUTION
        # ----------------------------------------------------

        result = (
            await live_execution_gateway.execute(
                request
            )
        )

        return {
            "status": result.status,

            "execution_type": (
                result.execution_type
            ),

            "order_id": result.order_id,

            "deal_id": result.deal_id,

            "position_ticket": (
                result.position_ticket
            ),

            "symbol": result.symbol,

            "side": result.side,

            "requested_volume": (
                result.requested_volume
            ),

            "executed_volume": (
                result.executed_volume
            ),

            "requested_stop_loss": (
                result.requested_stop_loss
            ),

            "requested_take_profit": (
                result.requested_take_profit
            ),

            "executed_price": (
                result.executed_price
            ),

            "client_order_id": (
                result.client_order_id
            ),

            "broker_retcode": (
                result.broker_retcode
            ),

            "broker_comment": (
                result.broker_comment
            ),

            "verified": result.verified,

            "timestamp": result.timestamp,
        }

    except HTTPException:
        raise

    except LiveExecutionError as exc:

        raise HTTPException(
            status_code=403,

            detail={
                "error": (
                    "LIVE_EXECUTION_BLOCKED"
                ),

                "message": str(exc),

                "timestamp": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            },
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,

            detail={
                "error": (
                    "LIVE_EXECUTION_FAILED"
                ),

                "message": str(exc),

                "timestamp": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            },
        ) from exc
