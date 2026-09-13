"""Tests for safe broker adapters and execution verification."""

import pytest

from app.brokers import (
    BrokerFactory,
    BrokerType,
    ExnessBrokerAdapter,
    ExecutionVerifier,
    MT5BrokerAdapter,
    OrderStatus,
    broker_execution_safety_status,
)


@pytest.mark.asyncio
class TestMT5BrokerAdapter:
    """Test safe MT5 broker adapter."""

    async def test_connect_requires_configuration(self):
        """MT5 adapter does not claim a broker connection without config."""
        adapter = MT5BrokerAdapter()

        result = await adapter.connect()

        assert result is False
        assert adapter.is_connected is False

    async def test_disconnect(self):
        """Test safe MT5 disconnection."""
        adapter = MT5BrokerAdapter()

        result = await adapter.disconnect()

        assert result is True
        assert adapter.is_connected is False

    async def test_place_order_is_rejected(self, mt5_adapter, sample_order):
        """Broker order placement must always be rejected."""
        result = await mt5_adapter.place_order(sample_order)

        assert result["status"] == OrderStatus.REJECTED.value
        assert result["execution_allowed"] is False
        assert result["execution_authorized"] is False
        assert result["live_trading_enabled"] is False
        assert result["real_orders_allowed"] is False
        assert result["read_only"] is True

    async def test_cancel_order_is_rejected(self, mt5_adapter):
        """Broker order cancellation must remain disabled."""
        result = await mt5_adapter.cancel_order("ORDER-001")

        assert result["status"] == OrderStatus.REJECTED.value
        assert result["execution_allowed"] is False
        assert result["real_orders_allowed"] is False

    async def test_close_position_is_rejected(self, mt5_adapter):
        """Broker position closing must remain disabled."""
        result = await mt5_adapter.close_position("POS-001")

        assert result["status"] == OrderStatus.REJECTED.value
        assert result["execution_allowed"] is False
        assert result["real_orders_allowed"] is False

    async def test_account_info_is_read_only(self, mt5_adapter):
        """Account information must not authorize trading."""
        info = await mt5_adapter.get_account_info()

        assert info["broker"] == "mt5"
        assert info["read_only"] is True
        assert info["live_trading_enabled"] is False
        assert info["real_orders_allowed"] is False

    async def test_open_positions_are_read_only(self, mt5_adapter):
        """Position reporting must not imply live broker execution."""
        positions = await mt5_adapter.get_open_positions()

        assert positions["broker"] == "mt5"
        assert positions["total"] == 0
        assert positions["positions"] == []
        assert positions["read_only"] is True
        assert positions["live_broker_query"] is False
        assert positions["real_orders_allowed"] is False

    async def test_status_is_fail_closed(self, mt5_adapter):
        """Adapter status must report execution as disabled."""
        status = mt5_adapter.status()

        assert status["broker"] == "mt5"
        assert status["read_only"] is True
        assert status["paper_only"] is True
        assert status["live_trading_enabled"] is False
        assert status["execution_authorized"] is False
        assert status["real_orders_allowed"] is False


@pytest.mark.asyncio
class TestExnessBrokerAdapter:
    """Test safe Exness broker adapter."""

    async def test_connect_requires_configuration(self):
        """Exness adapter does not claim a broker connection without config."""
        adapter = ExnessBrokerAdapter()

        result = await adapter.connect()

        assert result is False
        assert adapter.is_connected is False

    async def test_disconnect(self):
        """Test safe Exness disconnection."""
        adapter = ExnessBrokerAdapter()

        result = await adapter.disconnect()

        assert result is True
        assert adapter.is_connected is False

    async def test_place_order_is_rejected(self, exness_adapter, sample_order):
        """Exness order placement must always be rejected."""
        result = await exness_adapter.place_order(sample_order)

        assert result["status"] == OrderStatus.REJECTED.value
        assert result["execution_allowed"] is False
        assert result["execution_authorized"] is False
        assert result["live_trading_enabled"] is False
        assert result["real_orders_allowed"] is False
        assert result["read_only"] is True

    async def test_cancel_order_is_rejected(self, exness_adapter):
        """Exness order cancellation must remain disabled."""
        result = await exness_adapter.cancel_order("ORDER-001")

        assert result["status"] == OrderStatus.REJECTED.value
        assert result["execution_allowed"] is False
        assert result["real_orders_allowed"] is False

    async def test_close_position_is_rejected(self, exness_adapter):
        """Exness position closing must remain disabled."""
        result = await exness_adapter.close_position("POS-001")

        assert result["status"] == OrderStatus.REJECTED.value
        assert result["execution_allowed"] is False
        assert result["real_orders_allowed"] is False

    async def test_account_info_is_read_only(self, exness_adapter):
        """Account information must not authorize trading."""
        info = await exness_adapter.get_account_info()

        assert info["broker"] == "exness"
        assert info["read_only"] is True
        assert info["live_trading_enabled"] is False
        assert info["real_orders_allowed"] is False

    async def test_open_positions_are_read_only(self, exness_adapter):
        """Position reporting must not imply live broker execution."""
        positions = await exness_adapter.get_open_positions()

        assert positions["broker"] == "exness"
        assert positions["total"] == 0
        assert positions["positions"] == []
        assert positions["read_only"] is True
        assert positions["live_broker_query"] is False
        assert positions["real_orders_allowed"] is False

    async def test_status_is_fail_closed(self, exness_adapter):
        """Adapter status must report execution as disabled."""
        status = exness_adapter.status()

        assert status["broker"] == "exness"
        assert status["read_only"] is True
        assert status["paper_only"] is True
        assert status["live_trading_enabled"] is False
        assert status["execution_authorized"] is False
        assert status["real_orders_allowed"] is False


class TestBrokerFactory:
    """Test safe broker adapter factory."""

    def test_create_mt5_adapter(self):
        """Factory creates the safe MT5 adapter."""
        adapter = BrokerFactory.create_adapter(BrokerType.MT5)

        assert isinstance(adapter, MT5BrokerAdapter)
        assert adapter.broker_type == BrokerType.MT5

    def test_create_exness_adapter(self):
        """Factory creates the safe Exness adapter."""
        adapter = BrokerFactory.create_adapter(BrokerType.EXNESS)

        assert isinstance(adapter, ExnessBrokerAdapter)
        assert adapter.broker_type == BrokerType.EXNESS

    def test_create_adapter_from_string(self):
        """Factory accepts broker names as strings."""
        mt5 = BrokerFactory.create_adapter("mt5")
        exness = BrokerFactory.create_adapter("exness")

        assert isinstance(mt5, MT5BrokerAdapter)
        assert isinstance(exness, ExnessBrokerAdapter)

    def test_unknown_broker_is_rejected(self):
        """Unknown broker types must fail closed."""
        with pytest.raises(ValueError):
            BrokerFactory.create_adapter("unknown")


@pytest.mark.asyncio
class TestExecutionVerifier:
    """Test safe execution verification."""

    async def test_verify_order_does_not_confirm_real_execution(
        self,
        execution_verifier,
        mt5_adapter,
        sample_order,
    ):
        """Verifier must never claim real broker execution."""
        order_result = await mt5_adapter.place_order(sample_order)

        verification = await execution_verifier.verify_order(
            order_result,
            mt5_adapter,
        )

        assert verification["verified"] is False
        assert verification["execution_confirmed"] is False
        assert verification["real_broker_execution"] is False
        assert verification["live_trading_enabled"] is False
        assert verification["real_orders_allowed"] is False

    def test_get_verification_report_is_fail_closed(
        self,
        execution_verifier,
    ):
        """Verification report must never report real execution."""
        report = execution_verifier.get_verification_report()

        assert report["total_verifications"] == 0
        assert report["verified_count"] == 0
        assert report["verification_rate"] == 0.0
        assert report["real_broker_execution_confirmed"] is False
        assert report["live_trading_enabled"] is False
        assert report["real_orders_allowed"] is False


class TestBrokerExecutionSafetyStatus:
    """Test absolute broker execution safety status."""

    def test_execution_is_hard_locked_off(self):
        """Broker execution must remain disabled."""
        status = broker_execution_safety_status()

        assert status["live_trading_enabled"] is False
        assert status["execution_authorized"] is False
        assert status["real_broker_orders_allowed"] is False
        assert status["read_only"] is True
        assert status["paper_only"] is True
        assert status["broker_order_placement"] is False
        assert status["broker_position_closing"] is False
        assert status["broker_position_modification"] is False
