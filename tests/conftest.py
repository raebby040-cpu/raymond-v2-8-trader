"""Shared fixtures and configuration for pytest."""

import pytest

from app.brokers import (
    ExnessBrokerAdapter,
    ExecutionVerifier,
    MT5BrokerAdapter,
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
