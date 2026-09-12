"""Shared fixtures and configuration for pytest"""
import pytest
from datetime import datetime, timedelta
from app.market_data import Candlestick, Tick, MockMarketDataProvider
from app.strategy import StrategyEngine, AIDecisionLayer
from app.risk_management import RiskParameters, PositionRiskCalculator, PortfolioRiskMonitor
from app.brokers import MT5BrokerAdapter, ExnessBrokerAdapter, ExecutionVerifier
from app.backtest import BacktestEngine, PriceBar, BacktestTrade


@pytest.fixture
def sample_price_bars():
    """Generate sample OHLCV price bars for testing"""
    bars = []
    current_time = datetime.utcnow()
    current_price = 2048.00
    
    for i in range(100):
        timestamp = current_time - timedelta(hours=100-i)
        change = (i % 10) * 0.5 - 2.5  # Oscillating pattern
        open_price = current_price
        close_price = open_price + change
        high_price = max(open_price, close_price) + 2.0
        low_price = min(open_price, close_price) - 2.0
        volume = 1000000 + (i * 10000)
        
        bar = PriceBar(timestamp, open_price, high_price, low_price, close_price, volume)
        bars.append(bar)
        current_price = close_price
    
    return bars


@pytest.fixture
def sample_candlesticks():
    """Generate sample candlestick data"""
    candlesticks = []
    current_time = datetime.utcnow()
    current_price = 2048.00
    
    for i in range(50):
        timestamp = current_time - timedelta(hours=50-i)
        change = (i % 5) * 1.0 - 2.0
        open_price = current_price
        close_price = open_price + change
        high_price = max(open_price, close_price) + 1.5
        low_price = min(open_price, close_price) - 1.5
        volume = 1500000 + (i * 5000)
        
        cs = Candlestick(timestamp, open_price, high_price, low_price, close_price, volume)
        candlesticks.append(cs)
        current_price = close_price
    
    return candlesticks


@pytest.fixture
def sample_tick():
    """Generate a sample tick with bid/ask"""
    return Tick(
        timestamp=datetime.utcnow(),
        bid=2050.40,
        ask=2050.50,
        bid_volume=1000000.0,
        ask_volume=1000000.0
    )


@pytest.fixture
def strategy_engine():
    """Create a strategy engine instance"""
    return StrategyEngine()


@pytest.fixture
def ai_decision_layer():
    """Create an AI decision layer instance"""
    return AIDecisionLayer()


@pytest.fixture
def risk_parameters():
    """Create risk management parameters"""
    return RiskParameters()


@pytest.fixture
def portfolio_risk_monitor():
    """Create a portfolio risk monitor"""
    params = RiskParameters()
    return PortfolioRiskMonitor(params)


@pytest.fixture
async def mt5_adapter():
    """Create an MT5 broker adapter"""
    adapter = MT5BrokerAdapter()
    await adapter.connect()
    return adapter


@pytest.fixture
async def exness_adapter():
    """Create an Exness broker adapter"""
    adapter = ExnessBrokerAdapter()
    await adapter.connect()
    return adapter


@pytest.fixture
def execution_verifier():
    """Create an execution verifier"""
    return ExecutionVerifier()


@pytest.fixture
def backtest_engine():
    """Create a backtest engine"""
    return BacktestEngine(symbol="XAUUSD", initial_balance=10000.0)


@pytest.fixture
def market_data_provider():
    """Create a mock market data provider"""
    return MockMarketDataProvider()


@pytest.fixture
def sample_position():
    """Generate sample position data"""
    return {
        "position_id": "POS-001",
        "symbol": "XAUUSD",
        "direction": "buy",
        "entry_price": 2048.50,
        "quantity": 0.5,
        "stop_loss": 2045.00,
        "take_profit": 2055.00
    }


@pytest.fixture
def sample_order():
    """Generate sample order data"""
    return {
        "symbol": "XAUUSD",
        "order_type": "market",
        "direction": "buy",
        "quantity": 0.5,
        "price": 2050.45
    }
