"""
RAYMOND v2.8 - Trade Execution Gateway

STEP 5:
- Validates execution requests.
- Provides a paper-only execution path.
- Does NOT send orders to MT5.
- Does NOT modify or close real positions.
- Live execution is explicitly rejected.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import os
import uuid
from typing import Optional


class ExecutionGatewayError(Exception):
    """Raised when an execution request is rejected."""


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class ExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class OrderRequest:
    """Validated order request."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    volume: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    client_order_id: Optional[str] = None

    def validate(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ExecutionGatewayError(
                "Symbol is required."
            )

        if self.volume <= 0:
            raise ExecutionGatewayError(
                "Volume must be greater than zero."
            )

        if self.order_type != OrderType.MARKET:
            if self.price is None or self.price <= 0:
                raise ExecutionGatewayError(
                    "Price is required for non-market orders."
                )

        if self.stop_loss is not None and self.stop_loss <= 0:
            raise ExecutionGatewayError(
                "Stop-loss must be greater than zero."
            )

        if self.take_profit is not None and self.take_profit <= 0:
            raise ExecutionGatewayError(
                "Take-profit must be greater than zero."
            )


@dataclass(frozen=True)
class ExecutionResult:
    """Result returned by the execution gateway."""

    order_id: str
    client_order_id: Optional[str]
    status: ExecutionStatus
    execution_type: str
    symbol: str
    side: str
    order_type: str
    volume: float
    price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    timestamp: str
    broker: str
    message: str


@dataclass
class ExecutionGateway:
    """
    Safety boundary between strategy/risk logic and execution.

    The base gateway intentionally has no broker execution
    implementation.
    """

    live_trading_enabled: bool = field(
        default=False
    )

    async def execute(
        self,
        order: OrderRequest,
    ) -> ExecutionResult:
        """
        Execute an order through the configured gateway.

        Live execution is deliberately unavailable in Step 5.
        """

        order.validate()

        if self.live_trading_enabled:
            raise ExecutionGatewayError(
                "Live execution is not implemented in Step 5."
            )

        raise ExecutionGatewayError(
            "No execution backend is configured."
        )


class PaperExecutionGateway(ExecutionGateway):
    """
    Paper-only execution gateway.

    This class never contacts MT5 or any live broker.
    """

    def __init__(
        self,
        live_trading_enabled: Optional[bool] = None,
    ):
        if live_trading_enabled is None:
            live_trading_enabled = (
                os.getenv(
                    "LIVE_TRADING",
                    "false",
                ).strip().lower()
                == "true"
            )

        super().__init__(
            live_trading_enabled=live_trading_enabled
        )

    async def execute(
        self,
        order: OrderRequest,
    ) -> ExecutionResult:
        """Accept a validated order as a paper trade."""

        order.validate()

        if self.live_trading_enabled:
            raise ExecutionGatewayError(
                "Live trading is enabled, but the "
                "Step 5 paper gateway refuses live execution."
            )

        order_id = (
            "PAPER-"
            + uuid.uuid4().hex.upper()
        )

        timestamp = (
            datetime.now(timezone.utc)
            .isoformat()
        )

        return ExecutionResult(
            order_id=order_id,
            client_order_id=order.client_order_id,
            status=ExecutionStatus.ACCEPTED,
            execution_type="paper",
            symbol=order.symbol.strip(),
            side=order.side.value,
            order_type=order.order_type.value,
            volume=order.volume,
            price=order.price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            timestamp=timestamp,
            broker="paper",
            message="Paper order accepted. No live trade was sent.",
        )


def create_execution_gateway() -> PaperExecutionGateway:
    """
    Create the Step 5 execution gateway.

    Always returns the paper gateway.
    """

    return PaperExecutionGateway()
