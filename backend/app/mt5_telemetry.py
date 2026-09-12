from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(
    prefix="/api/mt5",
    tags=["MT5 Telemetry"],
)


class MT5Telemetry(BaseModel):
    bridge_version: str = Field(..., max_length=32)
    mode: str = Field(..., max_length=32)
    trading_enabled: bool

    symbol: str = Field(..., min_length=1, max_length=32)

    bid: float = Field(..., ge=0)
    ask: float = Field(..., ge=0)
    spread: float = Field(..., ge=0)

    balance: float = Field(..., ge=0)
    equity: float = Field(..., ge=0)
    margin: float = Field(..., ge=0)
    free_margin: float = Field(..., ge=0)

    open_positions: int = Field(..., ge=0)
    timestamp: int = Field(..., ge=0)


@router.post("/telemetry")
async def receive_mt5_telemetry(
    telemetry: MT5Telemetry,
):
    # ---------------------------------------------------------
    # HARD SAFETY VALIDATION
    # Step 11B-3 is READ ONLY.
    # ---------------------------------------------------------

    if telemetry.mode != "READ_ONLY":
        return {
            "accepted": False,
            "reason": "Only READ_ONLY telemetry is accepted.",
        }

    if telemetry.trading_enabled:
        return {
            "accepted": False,
            "reason": "Telemetry reporting cannot enable trading.",
        }

    if telemetry.ask < telemetry.bid:
        return {
            "accepted": False,
            "reason": "Invalid market data: ask is below bid.",
        }

    received_at = datetime.now(timezone.utc).isoformat()

    return {
        "accepted": True,
        "mode": "READ_ONLY",
        "trading_enabled": False,
        "symbol": telemetry.symbol,
        "received_at": received_at,
        "open_positions": telemetry.open_positions,
        "message": "MT5 telemetry received successfully.",
    }
