"""
RAYMOND v2.8 - Unified Execution API

One API for both DEMO and LIVE.

DEMO:
    Uses the controlled MT5 DEMO executor.

LIVE:
    Uses the existing LiveExecutionGateway and therefore retains
    the existing independent live safety architecture.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field

from app.api_auth import require_api_auth
from app.demo_mt5_execution import (
    DemoExecutionError,
    demo_mt5_execution_engine,
)
from app.execution_mode import (
    ExecutionMode,
)
from app.live_execution_gateway import (
    LiveExecutionError,
    LiveOrderRequest,
    live_execution_gateway,
)
from app.live_safety_gate import (
    require_live_armed,
)


router = APIRouter(
    prefix="/api/execution",
    tags=["Unified Execution"],
    dependencies=[
        Depends(require_api_auth)
    ],
)


class ExecutionRequest(BaseModel):
    mode: ExecutionMode = Field(
        ...,
        description="demo or live",
    )

    symbol: str = Field(
        default="XAUUSD",
        min_length=1,
        max_length=32,
    )

    timeframe: str = Field(
        default="M15",
        min_length=2,
        max_length=8,
    )

    candle_limit: int = Field(
        default=100,
        ge=50,
        le=500,
    )


class LiveExecutionPayload(BaseModel):
    mode: ExecutionMode

    symbol: str

    side: str

    volume: float

    price: float

    stop_loss: float

    take_profit: float

    client_order_id: str | None = None


@router.get(
    "/status"
)
async def execution_status() -> dict[str, Any]:
    """
    Return the unified execution state.

    This endpoint never creates or modifies an order.
    """

    return {
        "status": "ok",
        "execution_modes": {
            "demo": {
                "available": True,
                "account_required": True,
                "real_account_allowed": False,
            },
            "live": {
                "available": True,
                "existing_live_gateway": True,
                "independent_safety_gate": True,
            },
        },
        "strategy": {
            "frozen": True,
            "strategy_modified": False,
        },
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.post(
    "/evaluate"
)
async def evaluate_execution(
    request: ExecutionRequest,
) -> dict[str, Any]:
    """
    Run the frozen strategy and, for DEMO mode, execute the result.

    LIVE is deliberately not automatically executed by this endpoint.
    """

    if request.mode is ExecutionMode.LIVE:
        return {
            "status": "live_requires_explicit_order",
            "execution_mode": "live",
            "message": (
                "LIVE mode uses the existing live execution gateway "
                "and explicit live authorization."
            ),
            "strategy_frozen": True,
        }

    try:
        result = (
            await demo_mt5_execution_engine
            .evaluate_and_execute(
                symbol=request.symbol,
                timeframe=request.timeframe,
                candle_limit=request.candle_limit,
            )
        )

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
            "strategy_frozen": True,
            "timestamp": result.timestamp,
        }

    except DemoExecutionError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "DEMO_EXECUTION_BLOCKED",
                "message": str(exc),
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
        ) from exc


@router.post(
    "/live-order"
)
async def execute_live_order(
    request: LiveExecutionPayload,
) -> dict[str, Any]:
    """
    Explicit LIVE execution endpoint.

    This does NOT bypass the existing live safety gate.
    """

    if request.mode is not ExecutionMode.LIVE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_EXECUTION_MODE",
                "message": (
                    "This endpoint only accepts LIVE mode."
                ),
            },
        )

    try:
        require_live_armed()

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "LIVE_EXECUTION_NOT_ARMED",
                "message": str(exc),
            },
        ) from exc

    try:
        live_request = LiveOrderRequest(
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            price=request.price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            client_order_id=request.client_order_id,
        )

        result = (
            await live_execution_gateway.execute(
                live_request
            )
        )

        return {
            "status": result.status,
            "execution_mode": "live",
            "order_id": result.order_id,
            "deal_id": result.deal_id,
            "position_ticket": result.position_ticket,
            "symbol": result.symbol,
            "side": result.side,
            "requested_volume": result.requested_volume,
            "executed_volume": result.executed_volume,
            "requested_stop_loss": result.requested_stop_loss,
            "requested_take_profit": result.requested_take_profit,
            "executed_price": result.executed_price,
            "client_order_id": result.client_order_id,
            "broker_retcode": result.broker_retcode,
            "broker_comment": result.broker_comment,
            "verified": result.verified,
            "timestamp": result.timestamp,
        }

    except LiveExecutionError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "LIVE_EXECUTION_BLOCKED",
                "message": str(exc),
            },
        ) from exc


__all__ = [
    "router",
      ]
