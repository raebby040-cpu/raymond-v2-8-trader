"""Shared fixtures and configuration for pytest."""

from datetime import datetime, timedelta

import pytest

from app.brokers import (
    ExnessBrokerAdapter,
    ExecutionVerifier,
    MT5BrokerAdapter,
)
from app.market_data import (
    Candlestick,
    MockMarketDataProvider,
    Tick,
)
from app.risk_management import (
    PortfolioRiskMonitor,
    RiskParameters,
)
from app.strategy import (
    AIDecisionLayer,
    StrategyEngine,
)


@pytest.fixture
def sample_candlesticks():
    """Generate sample candlestick data."""
    candlesticks = []

    current_time = datetime.utcnow()
    current_price = 2048.00

    for i in range(50):
        timestamp = current_time - timedelta(hours=50 - i)

        change = (i % 5) * 1.0 - 2.0

        open_price = current_price
        close_price = open_price + change

        high_price = max(open_price, close_price) + 1.5
        low_price = min(open_price, close_price) - 1.5

        volume = 1_500_000 + (i * 5_000)

        candlesticks.append(
            Candlestick(
                timestamp,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
            )
        )

        current_price = close_price

    return candlesticks


@pytest.fixture
def sample_tick():
    """Generate a sample tick with bid/ask."""
    return Tick(
        timestamp=datetime.utcnow(),
        bid=2050.40,
        ask=2050.50,
        bid_volume=1_000_000.0,
        ask_volume=1_000_000.0,
    )


@pytest.fixture
def strategy_engine():
    """Create a strategy engine instance."""
    return StrategyEngine()


@pytest.fixture
def ai_decision_layer():
    """Create an AI decision layer instance."""
    return AIDecisionLayer()


@pytest.fixture
def risk_parameters():
    """Create risk-management parameters."""
    return RiskParameters()


@pytest.fixture
def portfolio_risk_monitor():
    """Create a portfolio risk monitor."""
    params = RiskParameters()
    return PortfolioRiskMonitor(params)


@pytest.fixture
async def mt5_adapter():
    """Create a safe MT5 broker adapter."""
    adapter = MT5BrokerAdapter()
    await adapter.connect()
    return adapter


@pytest.fixture
async def exness_adapter():
    """Create a safe Exness broker adapter."""
    adapter = ExnessBrokerAdapter()
    await adapter.connect()
    return adapter


@pytest.fixture
def execution_verifier():
    """Create an execution verifier."""
    return ExecutionVerifier()


@pytest.fixture
def market_data_provider():
    """Create a mock market-data provider."""
    return MockMarketDataProvider()


@pytest.fixture
def sample_position():
    """Generate sample paper-position data."""
    return {
        "position_id": "POS-001",
        "symbol": "XAUUSD",
        "direction": "buy",
        "entry_price": 2048.50,
        "quantity": 0.5,
        "stop_loss": 2045.00,
        "take_profit": 2055.00,
    }


@pytest.fixture
def sample_order():
    """Generate sample paper-order data."""
    return {
        "symbol": "XAUUSD",
        "order_type": "market",
        "direction": "buy",
        "quantity": 0.5,
        "price": 2050.45,
    }
