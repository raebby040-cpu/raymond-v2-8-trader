"""
RAYMOND v2.8 - Unified Execution API

One authenticated API surface for DEMO and LIVE execution.

DEMO:
    Uses the controlled MT5 DEMO executor.

LIVE:
    Uses the existing LiveExecutionGateway and its independent
    fail-closed safety architecture.

This module does not modify the Raymond strategy.
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
from app.execution_mode import ExecutionMode
from app.live_execution_gateway import (
    LiveExecutionError,
    LiveOrderRequest,
    live_execution_gateway,
)
from app.live_safety_gate import require_live_armed


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
    """
    Explicit LIVE order request.

    Price is deliberately NOT accepted here.

    The live gateway obtains and validates the current broker
    market price immediately before order submission.
    """

    mode: ExecutionMode

    symbol: str = Field(
        min_length=1,
        max_length=32,
    )

    side: str = Field(
        min_length=3,
        max_length=4,
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

    client_order_id: str | None = Field(
        default=None,
        max_length=128,
    )


def _result_to_dict(
    result: Any,
) -> dict[str, Any]:
    return {
        "status": result.status,
        "execution_mode": result.execution_mode,
        "signal_id": getattr(
            result,
            "signal_id",
            None,
        ),
        "symbol": result.symbol,
        "side": result.side,
        "volume": getattr(
            result,
            "volume",
            getattr(
                result,
                "requested_volume",
                None,
            ),
        ),
        "requested_price": getattr(
            result,
            "requested_price",
            None,
        ),
        "executed_price": getattr(
            result,
            "executed_price",
            None,
        ),
        "stop_loss": getattr(
            result,
            "stop_loss",
            getattr(
                result,
                "requested_stop_loss",
                None,
            ),
        ),
        "take_profit": getattr(
            result,
            "take_profit",
            getattr(
                result,
                "requested_take_profit",
                None,
            ),
        ),
        "order_ticket": getattr(
            result,
            "order_ticket",
            getattr(
                result,
                "order_id",
                None,
            ),
        ),
        "deal_ticket": getattr(
            result,
            "deal_ticket",
            getattr(
                result,
                "deal_id",
                None,
            ),
        ),
        "position_ticket": getattr(
            result,
            "position_ticket",
            None,
        ),
        "broker_retcode": getattr(
            result,
            "broker_retcode",
            None,
        ),
        "broker_comment": getattr(
            result,
            "broker_comment",
            None,
        ),
        "verified": result.verified,
        "reason": getattr(
            result,
            "reason",
            "",
        ),
        "client_order_id": getattr(
            result,
            "client_order_id",
            None,
        ),
        "timestamp": result.timestamp,
    }


@router.get("/status")
async def execution_status() -> dict[str, Any]:
    """
    Return unified execution state.

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
                "fail_closed": True,
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


@router.post("/evaluate")
async def evaluate_execution(
    request: ExecutionRequest,
) -> dict[str, Any]:
    """
    Evaluate the frozen strategy.

    DEMO:
        Evaluate and execute through the controlled DEMO executor.

    LIVE:
        Evaluation only. Actual LIVE execution requires the explicit
        /live-order endpoint plus all existing LIVE gates.
    """

    if request.mode is ExecutionMode.LIVE:
        return {
            "status": "live_requires_explicit_order",
            "execution_mode": "live",
            "message": (
                "LIVE evaluation does not automatically create an order. "
                "Use the explicit LIVE order path after authorization."
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
            **_result_to_dict(result),
            "strategy_frozen": True,
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


@router.post("/live-order")
async def execute_live_order(
    request: LiveExecutionPayload,
) -> dict[str, Any]:
    """
    Explicit LIVE execution endpoint.

    This endpoint never bypasses the independent LIVE safety gate.
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

        live_request = LiveOrderRequest(
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
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
            "requested_stop_loss": (
                result.requested_stop_loss
            ),
            "requested_take_profit": (
                result.requested_take_profit
            ),
            "executed_price": result.executed_price,
            "client_order_id": result.client_order_id,
            "broker_retcode": result.broker_retcode,
            "broker_comment": result.broker_comment,
            "verified": result.verified,
            "timestamp": result.timestamp,
        }

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "LIVE_EXECUTION_NOT_ARMED",
                "message": str(exc),
            },
        ) from exc

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
