"""Tests for broker adapters and execution verification"""
import pytest
from app.brokers import MT5BrokerAdapter, ExnessBrokerAdapter, ExecutionVerifier, OrderStatus


@pytest.mark.asyncio
class TestMT5BrokerAdapter:
    """Test MT5 broker adapter"""
    
    async def test_connect(self, mt5_adapter):
        """Test MT5 connection"""
        assert mt5_adapter.is_connected is True
        assert mt5_adapter.account_info["server"] is not None
    
    async def test_disconnect(self, mt5_adapter):
        """Test MT5 disconnection"""
        result = await mt5_adapter.disconnect()
        assert result is True
        assert mt5_adapter.is_connected is False
    
    async def test_place_order(self, mt5_adapter, sample_order):
        """Test placing order on MT5"""
        result = await mt5_adapter.place_order(sample_order)
        
        assert "order_id" in result
        assert result["status"] == OrderStatus.FILLED
        assert result["symbol"] == "XAUUSD"
        assert result["broker"] == "mt5"
    
    async def test_place_order_not_connected(self):
        """Test placing order when not connected"""
        adapter = MT5BrokerAdapter()
        result = await adapter.place_order({"symbol": "XAUUSD"})
        
        assert "error" in result or result.get("status") != OrderStatus.FILLED
    
    async def test_get_account_info(self, mt5_adapter):
        """Test getting MT5 account info"""
        info = await mt5_adapter.get_account_info()
        
        assert info["broker"] == "mt5"
        assert "account_info" in info
        assert info["account_info"]["balance"] == 10000.0
    
    async def test_get_open_positions(self, mt5_adapter, sample_order):
        """Test getting open positions"""
        await mt5_adapter.place_order(sample_order)
        positions = await mt5_adapter.get_open_positions()
        
        assert positions["broker"] == "mt5"
        assert positions["total"] == 1
        assert len(positions["positions"]) == 1
    
    async def test_cancel_order(self, mt5_adapter, sample_order):
        """Test canceling an order"""
        order_result = await mt5_adapter.place_order(sample_order)
        order_id = order_result["order_id"]
        
        cancel_result = await mt5_adapter.cancel_order(order_id)
        
        assert cancel_result["status"] == OrderStatus.CANCELLED
        assert cancel_result["order_id"] == order_id


@pytest.mark.asyncio
class TestExnessBrokerAdapter:
    """Test Exness broker adapter"""
    
    async def test_connect(self, exness_adapter):
        """Test Exness connection"""
        assert exness_adapter.is_connected is True
        assert exness_adapter.account_info["account_id"] is not None
    
    async def test_disconnect(self, exness_adapter):
        """Test Exness disconnection"""
        result = await exness_adapter.disconnect()
        assert result is True
        assert exness_adapter.is_connected is False
    
    async def test_place_order(self, exness_adapter, sample_order):
        """Test placing order on Exness"""
        result = await exness_adapter.place_order(sample_order)
        
        assert "order_id" in result
        assert result["status"] == OrderStatus.FILLED
        assert result["broker"] == "exness"
    
    async def test_get_account_info(self, exness_adapter):
        """Test getting Exness account info"""
        info = await exness_adapter.get_account_info()
        
        assert info["broker"] == "exness"
        assert "account_info" in info
        assert info["account_info"]["account_type"] is not None
    
    async def test_close_position(self, exness_adapter):
        """Test closing Exness position"""
        result = await exness_adapter.close_position("POS-001")
        
        assert result["status"] == "closed"
        assert result["position_id"] == "POS-001"


class TestExecutionVerifier:
    """Test execution verification"""
    
    @pytest.mark.asyncio
    async def test_verify_order(self, execution_verifier, mt5_adapter, sample_order):
        """Test order verification"""
        order_result = await mt5_adapter.place_order(sample_order)
        
        verification = await execution_verifier.verify_order(order_result, mt5_adapter)
        
        assert verification["verified"] is True
        assert verification["broker"] == "mt5"
        assert verification["order_id"] is not None
    
    def test_get_verification_report(self, execution_verifier):
        """Test verification report generation"""
        report = execution_verifier.get_verification_report()
        
        assert "total_verifications" in report
        assert "verified_count" in report
        assert "verification_rate" in report
        assert report["verification_rate"] >= 0
