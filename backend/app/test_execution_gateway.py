"""
Tests for the Step 5 trade execution gateway.
"""

import pytest

from app.execution_gateway import (
    ExecutionGatewayError,
    ExecutionStatus,
    OrderRequest,
    OrderSide,
    OrderType,
    PaperExecutionGateway,
)


@pytest.mark.asyncio
async def test_valid_paper_market_order_is_accepted():
    gateway = PaperExecutionGateway()

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.10,
        stop_loss=2300.0,
        take_profit=2350.0,
    )

    result = await gateway.execute(order)

    assert result.status == ExecutionStatus.ACCEPTED
    assert result.execution_type == "paper"
    assert result.broker == "paper"
    assert result.symbol == "XAUUSD"
    assert result.side == "buy"
    assert result.volume == 0.10
    assert result.stop_loss == 2300.0
    assert result.take_profit == 2350.0
    assert result.order_id.startswith("PAPER-")


@pytest.mark.asyncio
async def test_paper_orders_receive_unique_ids():
    gateway = PaperExecutionGateway()

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        volume=0.10,
    )

    first = await gateway.execute(order)
    second = await gateway.execute(order)

    assert first.order_id != second.order_id


@pytest.mark.asyncio
async def test_invalid_symbol_is_rejected():
    gateway = PaperExecutionGateway()

    order = OrderRequest(
        symbol="",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.10,
    )

    with pytest.raises(
        ExecutionGatewayError,
        match="Symbol is required",
    ):
        await gateway.execute(order)


@pytest.mark.asyncio
async def test_invalid_volume_is_rejected():
    gateway = PaperExecutionGateway()

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0,
    )

    with pytest.raises(
        ExecutionGatewayError,
        match="Volume must be greater than zero",
    ):
        await gateway.execute(order)


@pytest.mark.asyncio
async def test_limit_order_requires_price():
    gateway = PaperExecutionGateway()

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        volume=0.10,
    )

    with pytest.raises(
        ExecutionGatewayError,
        match="Price is required",
    ):
        await gateway.execute(order)


@pytest.mark.asyncio
async def test_limit_order_with_price_is_accepted():
    gateway = PaperExecutionGateway()

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        volume=0.10,
        price=2300.0,
    )

    result = await gateway.execute(order)

    assert result.status == ExecutionStatus.ACCEPTED
    assert result.order_type == "limit"
    assert result.price == 2300.0


@pytest.mark.asyncio
async def test_live_execution_is_rejected():
    gateway = PaperExecutionGateway(
        live_trading_enabled=True
    )

    order = OrderRequest(
        symbol="XAUUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.10,
    )

    with pytest.raises(
        ExecutionGatewayError,
        match="refuses live execution",
    ):
        await gateway.execute(order)


def test_gateway_is_paper_only_by_default():
    gateway = PaperExecutionGateway(
        live_trading_enabled=False
    )

    assert gateway.live_trading_enabled is False
