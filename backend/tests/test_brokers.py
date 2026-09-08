"""Tests for broker adapters"""
import pytest
from app.brokers import MT5BrokerAdapter, ExnessBrokerAdapter, BrokerFactory, BrokerType, ExecutionVerifier

class TestMT5Adapter:
    """Test MT5 broker adapter"""
    
    def setup_method(self):
        """Setup for each test"""
        self.adapter = MT5BrokerAdapter()
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test MT5 connection"""
        result = await self.adapter.connect()
        
        assert result is True
        assert self.adapter.is_connected is True
        assert self.adapter.account_info["balance"] == 10000.0
    
    @pytest.mark.asyncio
    async def test_place_order(self):
        """Test placing an order on MT5"""
        await self.adapter.connect()
        
        order_data = {
            "symbol": "XAUUSD",
            "order_type": "market",
            "direction": "buy",
            "quantity": 0.5,
            "price": 2050.00
        }
        
        result = await self.adapter.place_order(order_data)
        
        assert "order_id" in result
        assert result["symbol"] == "XAUUSD"
        assert result["quantity"] == 0.5
        assert result["broker"] == "mt5"
    
    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test cancelling an order on MT5"""
        await self.adapter.connect()
        
        # Place order first
        order_data = {
            "symbol": "XAUUSD",
            "order_type": "market",
            "direction": "buy",
            "quantity": 0.5,
            "price": 2050.00
        }
        placed = await self.adapter.place_order(order_data)
        order_id = placed["order_id"]
        
        # Cancel it
        result = await self.adapter.cancel_order(order_id)
        
        assert result["status"] == "cancelled"
        assert "cancelled_at" in result
    
    @pytest.mark.asyncio
    async def test_get_account_info(self):
        """Test getting account info"""
        await self.adapter.connect()
        
        result = await self.adapter.get_account_info()
        
        assert result["broker"] == "mt5"
        assert "account_info" in result
        assert result["account_info"]["balance"] == 10000.0

class TestExnessAdapter:
    """Test Exness broker adapter"""
    
    def setup_method(self):
        """Setup for each test"""
        self.adapter = ExnessBrokerAdapter()
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test Exness connection"""
        result = await self.adapter.connect()
        
        assert result is True
        assert self.adapter.is_connected is True
    
    @pytest.mark.asyncio
    async def test_place_order(self):
        """Test placing an order on Exness"""
        await self.adapter.connect()
        
        order_data = {
            "symbol": "XAUUSD",
            "order_type": "market",
            "direction": "sell",
            "quantity": 1.0,
            "price": 2050.00
        }
        
        result = await self.adapter.place_order(order_data)
        
        assert "order_id" in result
        assert result["direction"] == "sell"
        assert result["broker"] == "exness"

class TestBrokerFactory:
    """Test broker factory pattern"""
    
    def test_create_mt5_adapter(self):
        """Test creating MT5 adapter via factory"""
        adapter = BrokerFactory.create_adapter(BrokerType.MT5)
        
        assert isinstance(adapter, MT5BrokerAdapter)
        assert adapter.broker_type == BrokerType.MT5
    
    def test_create_exness_adapter(self):
        """Test creating Exness adapter via factory"""
        adapter = BrokerFactory.create_adapter(BrokerType.EXNESS)
        
        assert isinstance(adapter, ExnessBrokerAdapter)
        assert adapter.broker_type == BrokerType.EXNESS
    
    def test_invalid_broker_type(self):
        """Test invalid broker type"""
        with pytest.raises(ValueError):
            BrokerFactory.create_adapter("invalid_broker")

class TestExecutionVerifier:
    """Test execution verifier"""
    
    def setup_method(self):
        """Setup for each test"""
        self.verifier = ExecutionVerifier()
        self.adapter = MT5BrokerAdapter()
    
    @pytest.mark.asyncio
    async def test_verify_order(self):
        """Test order verification"""
        await self.adapter.connect()
        
        # Place order
        order_data = {
            "symbol": "XAUUSD",
            "order_type": "market",
            "direction": "buy",
            "quantity": 0.5,
            "price": 2050.00,
            "status": "filled"
        }
        
        placed = await self.adapter.place_order(order_data)
        placed["status"] = "filled"
        
        # Verify it
        result = await self.verifier.verify_order(placed, self.adapter)
        
        assert result["verified"] is True
        assert len(result["discrepancies"]) == 0
    
    @pytest.mark.asyncio
    async def test_verification_report(self):
        """Test verification report"""
        await self.adapter.connect()
        
        # Verify multiple orders
        for i in range(3):
            order_data = {
                "symbol": "XAUUSD",
                "order_type": "market",
                "direction": "buy",
                "quantity": 0.5,
                "price": 2050.00,
                "status": "filled"
            }
            
            placed = await self.adapter.place_order(order_data)
            placed["status"] = "filled"
            await self.verifier.verify_order(placed, self.adapter)
        
        report = self.verifier.get_verification_report()
        
        assert report["total_verifications"] == 3
        assert report["verified_count"] == 3
        assert report["verification_rate"] == 100.0
